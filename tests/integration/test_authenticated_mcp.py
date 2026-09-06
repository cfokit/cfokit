"""The MCP half of the join: a real token, over the real transport, to the real books.

`test_authenticated_access.py` proves the REST adapter accepts a token the configured issuer
minted. That says nothing about this surface. MCP authenticates through the SDK's own bearer
middleware and `LedgerTokenVerifier` — a different path that happens to call the same
authenticator — and ADR-0009 makes the two adapters siblings rather than one wrapping the other.

**This is the path a client actually takes.** A real SDK client, over streamable HTTP, carrying
a token from a client that registered itself through RFC 7591. Every layer that could reject a
caller is present: the transport handshake, the bearer middleware, a signature checked against
the issuer's JWKS, audience and issuer validation, the principal, and the entity grant.

`tests/test_mcp_transport.py` drives the same transport with a stub authenticator and no
database, which is what keeps it in the unit suite. This is the same shape with nothing stubbed.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx2 as httpx
import psycopg
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from cfokit.ledger.config import Settings
from cfokit.ledger.mcp import create_server

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

ISSUER = os.environ.get("AUTH_ISSUER_URL", "").rstrip("/")
AUDIENCE = os.environ.get("AUTH_AUDIENCE", "")
TIMEOUT = 10


@pytest.fixture(autouse=True)
def _requires_issuer() -> None:
    if not (ISSUER and AUDIENCE):
        pytest.skip("needs the issuer: docker compose --profile test run --rm test")
    try:
        httpx.get(f"{ISSUER}/.well-known/openid-configuration", timeout=TIMEOUT)
    except httpx.HTTPError:  # pragma: no cover - environment dependent
        pytest.skip(f"issuer at {ISSUER} is not reachable")


@pytest.fixture
def settings(app_dsn: str) -> Settings:
    """Pointed at the real issuer, with no authenticator override anywhere below."""
    return Settings(
        database_url=app_dsn,
        public_base_url="http://localhost:8081",
        auth_issuer_url=ISSUER,
        auth_audience=AUDIENCE,
    )


@pytest.fixture
def caller() -> tuple[str, str]:
    """A self-registered client and its token. Returns (subject, token).

    Registered through RFC 7591 and configured by nobody, which is how an MCP client arrives.
    """
    metadata = httpx.get(f"{ISSUER}/.well-known/openid-configuration", timeout=TIMEOUT).json()
    endpoint = metadata.get("registration_endpoint")
    if not endpoint:
        pytest.skip("issuer advertises no registration endpoint")

    registered = httpx.post(
        endpoint,
        json={
            "client_name": f"cfokit-mcp-e2e-{uuid.uuid4().hex[:8]}",
            "grant_types": ["client_credentials"],
            "response_types": ["token"],
            "token_endpoint_auth_method": "client_secret_post",
        },
        timeout=TIMEOUT,
    )
    assert registered.status_code in (200, 201), registered.text
    client = registered.json()

    issued = httpx.post(
        metadata["token_endpoint"],
        data={
            "grant_type": "client_credentials",
            "client_id": client["client_id"],
            "client_secret": client["client_secret"],
        },
        timeout=TIMEOUT,
    )
    assert issued.status_code == 200, issued.text
    token = str(issued.json()["access_token"])
    return _subject(token), token


def _subject(token: str) -> str:
    import base64
    import json

    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    subject = json.loads(base64.urlsafe_b64decode(payload))["sub"]
    assert isinstance(subject, str)
    return subject


def grant(conn: psycopg.Connection[Any], entity_id: str, principal_id: str) -> None:
    """Arranged through the owner connection: the grant path is `test_grants.py`'s subject."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO entity_grant (entity_id, principal_id, role, granted_by)"
            " VALUES (%s, %s, 'owner', 'test')",
            (entity_id, principal_id),
        )


@asynccontextmanager
async def session(settings: Settings, *, token: str | None) -> AsyncIterator[ClientSession]:
    """A real SDK client over streamable HTTP, against the app in process.

    Built with `host="0.0.0.0"` because that is how the entrypoint binds it, and the SDK
    auto-enables DNS rebinding protection only for a localhost bind. Building it another way
    would test a configuration that never ships.
    """
    app = create_server(settings).streamable_http_app(
        stateless_http=True,
        json_response=True,
        host="0.0.0.0",  # noqa: S104
    )
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://ledger", headers=headers
        ) as http,
        streamable_http_client("http://ledger/mcp", http_client=http) as (read, write),
        ClientSession(read, write) as client,
    ):
        yield client


def payload(result: Any) -> dict[str, Any]:
    """A tool result's structured content, which is what a client reads."""
    content = result.structured_content
    assert isinstance(content, dict)
    return content


# --- the join, on the surface a client actually speaks --------------------------------------


async def test_a_self_registered_client_reads_the_books(
    settings: Settings,
    owner_conn: psycopg.Connection[Any],
    books: tuple[str, str, str],
    caller: tuple[str, str],
) -> None:
    """**The Claude Desktop path, minus the network.**

    Everything between a client and a figure is present and none of it is stubbed: the
    handshake, the bearer middleware, a signature checked against the issuer's published keys,
    the audience, the issuer, the principal, and the grant.
    """
    entity_id, _, _ = books
    subject, token = caller
    grant(owner_conn, entity_id, subject)

    async with session(settings, token=token) as client:
        await client.initialize()
        result = await client.call_tool(
            "trial_balance", {"entity_id": entity_id, "as_of": "2026-12-31"}
        )

    assert payload(result)["ok"] is True


async def test_a_token_without_a_grant_is_authenticated_and_then_refused(
    settings: Settings, books: tuple[str, str, str], caller: tuple[str, str]
) -> None:
    """ADR-0009: the same stable code as REST for the same condition.

    Reaching a refusal at all is the assertion — the caller got past the middleware, so the
    token was read and a principal derived from it. A transport that had rejected the token
    would never have produced a tool result to carry a code.
    """
    entity_id, _, _ = books
    _, token = caller

    async with session(settings, token=token) as client:
        await client.initialize()
        result = await client.call_tool(
            "trial_balance", {"entity_id": entity_id, "as_of": "2026-12-31"}
        )

    body = payload(result)
    assert body["ok"] is False
    assert body["code"] == "not_authorised"


async def post_to_mcp(settings: Settings, *, token: str | None) -> int:
    """One JSON-RPC request over HTTP, returning the status.

    Below the SDK client deliberately. A refusal happens in the bearer middleware, before a
    session exists, and the client surfaces that as an `ExceptionGroup` whose own message says
    only "unhandled errors in a TaskGroup" — so asserting through it would match on the shape of
    the SDK's error handling rather than on the status the middleware returned.
    """
    app = create_server(settings).streamable_http_app(
        stateless_http=True,
        json_response=True,
        host="0.0.0.0",  # noqa: S104
    )
    headers = {
        "content-type": "application/json",
        "accept": "application/json, text/event-stream",
    }
    if token:
        headers["authorization"] = f"Bearer {token}"
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://ledger"
        ) as http,
    ):
        response = await http.post(
            "/mcp",
            headers=headers,
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        )
    return response.status_code


async def test_a_request_without_a_token_is_refused(settings: Settings) -> None:
    """The bearer middleware answers before any tool runs. `LED-20` requires every write to
    record what made it, and there would be nothing true to record."""
    assert await post_to_mcp(settings, token=None) == 401


async def test_a_token_for_another_audience_is_refused(
    settings: Settings, caller: tuple[str, str]
) -> None:
    """`NFR-06`, on this surface too. A valid, correctly signed token offered to a deployment
    expecting a different audience — which is what stops a token being replayed between two
    CFOKit deployments sharing an issuer."""
    _, token = caller
    elsewhere = Settings(
        database_url=settings.database_url,
        public_base_url=settings.public_base_url,
        auth_issuer_url=settings.auth_issuer_url,
        auth_audience="somebody-elses-ledger",
    )

    assert await post_to_mcp(elsewhere, token=token) == 401


async def test_a_valid_token_reaches_past_the_middleware(
    settings: Settings, caller: tuple[str, str]
) -> None:
    """The other side of the two above, so they are not both passing because the request was
    malformed. Same request, a token this deployment accepts, and it is served."""
    _, token = caller

    assert await post_to_mcp(settings, token=token) == 200
