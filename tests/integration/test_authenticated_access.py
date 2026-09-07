"""A real token, from the real issuer, presented to the real ledger (ADR-0019, ADR-0036 § 3).

Every other authentication test supplies a stub: `test_authentication.py` checks the derivation
without an issuer, `test_protocol.py` drives both adapters with a fabricated principal, and the
conformance suite measures the issuer without ever showing it to the application. Each half is
covered and the join between them was not — which is how the shipped stack came to hold an
issuer that signed nothing, advertised a hostname the application would reject, and issued
opaque tokens the application cannot read, with every test green.

So this is the one test where nothing is stubbed. The token is minted by the configured issuer,
signed by a key the application fetches from that issuer's JWKS, and presented over HTTP to a
route that reads the books.

**A refusal for the right reason is the point.** A caller holding no grant is authenticated and
then refused: 403 rather than 401 is the whole distinction, and a test that only asserted "not
200" would pass just as well against an issuer that never worked.
"""

from __future__ import annotations

import contextlib
import os
import uuid
from collections.abc import Iterator
from typing import Any

import httpx2 as httpx
import psycopg
import pytest
from fastapi.testclient import TestClient

from cfokit.ledger.api import create_app
from cfokit.ledger.config import Settings

pytestmark = pytest.mark.integration

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
    """Configured exactly as a deployment is, and pointed at the real issuer.

    No `authenticator=` override anywhere in this file. `create_app` builds a
    `TokenAuthenticator` against `AUTH_ISSUER_URL` and `AUTH_AUDIENCE`, which is what makes
    this a test of the join rather than of either side.
    """
    return Settings(
        database_url=app_dsn,
        public_base_url="http://localhost:8080",
        auth_issuer_url=ISSUER,
        auth_audience=AUDIENCE,
    )


@pytest.fixture
def client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings))


def registration_endpoint() -> str:
    metadata = httpx.get(f"{ISSUER}/.well-known/openid-configuration", timeout=TIMEOUT).json()
    endpoint = metadata.get("registration_endpoint")
    if not endpoint:
        pytest.skip("issuer advertises no registration endpoint")
    return str(endpoint)


@pytest.fixture
def caller() -> Iterator[tuple[str, str]]:
    """A client that registered itself, and the token it was issued. Returns (subject, token).

    Registered through RFC 7591 and configured by nobody, which is the case that matters: an
    MCP client arrives this way, and if a self-registered client's token is unusable then the
    whole path is unusable however well the pieces test in isolation.
    """
    registered = httpx.post(
        registration_endpoint(),
        json={
            "client_name": f"cfokit-e2e-{uuid.uuid4().hex[:8]}",
            "grant_types": ["client_credentials"],
            "response_types": ["token"],
            "token_endpoint_auth_method": "client_secret_post",
        },
        timeout=TIMEOUT,
    )
    assert registered.status_code in (200, 201), registered.text
    client = registered.json()

    metadata = httpx.get(f"{ISSUER}/.well-known/openid-configuration", timeout=TIMEOUT).json()
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
    # The subject is the service account's, not the client id, and the application takes it
    # from the token rather than from anything the caller says (ADR-0033).
    token = str(issued.json()["access_token"])

    yield _subject(token), token

    deregister(client)


def deregister(client: dict[str, Any]) -> None:
    """Delete a client this test registered, through RFC 7591's own management endpoint.

    A registration is durable, and a suite that leaves one behind on every run fills the realm
    — `max-clients` is a policy with a number on it, and the run that crosses it fails for a
    reason unrelated to the change that triggered it.

    The registration response carries the credentials for exactly this, scoped to the one
    client, so nothing here needs an administrator.
    """
    uri, token = client.get("registration_client_uri"), client.get("registration_access_token")
    if not (uri and token):  # pragma: no cover - an issuer that does not offer management
        return
    with contextlib.suppress(httpx.HTTPError):
        httpx.delete(uri, headers={"authorization": f"Bearer {token}"}, timeout=TIMEOUT)


def _subject(token: str) -> str:
    import base64
    import json

    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    subject = json.loads(base64.urlsafe_b64decode(payload))["sub"]
    assert isinstance(subject, str)
    return subject


def grant(conn: psycopg.Connection[Any], entity_id: str, principal_id: str) -> None:
    """Make the caller an owner of this entity, arranged rather than exercised.

    Through the owner connection, because what is under test is authentication reaching
    authorisation — not the grant path, which `test_grants.py` covers.
    """
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO entity_grant (entity_id, principal_id, role, granted_by)"
            " VALUES (%s, %s, 'owner', 'test')",
            (entity_id, principal_id),
        )


# --- the join ------------------------------------------------------------------------------


def test_a_real_token_authenticates_and_is_then_authorised(
    client: TestClient,
    owner_conn: psycopg.Connection[Any],
    books: tuple[str, str, str],
    caller: tuple[str, str],
) -> None:
    """**The whole point of this file.** A token nobody fabricated, read by an application
    nobody stubbed, against books that exist.

    The signature is verified against a key fetched from the issuer's JWKS, the audience
    against `AUTH_AUDIENCE`, and the issuer against `AUTH_ISSUER_URL`. All three had to be
    right at once, and none of them was in the stack as it shipped before this.
    """
    entity_id, _, _ = books
    subject, token = caller
    grant(owner_conn, entity_id, subject)

    response = client.get(
        f"/entities/{entity_id}/trial-balance",
        headers={"authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200, response.text


def test_a_real_token_without_a_grant_is_authenticated_and_then_refused(
    client: TestClient, books: tuple[str, str, str], caller: tuple[str, str]
) -> None:
    """403, not 401 — and the distinction is the assertion.

    401 would mean the token was never read. 403 means it was read, the principal was derived
    from it, and the entity grant said no (`IAM-01`). A test asserting only "not 200" would
    pass against an issuer that had never worked.
    """
    entity_id, _, _ = books
    _, token = caller

    response = client.get(
        f"/entities/{entity_id}/trial-balance",
        headers={"authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "not_authorised"


def test_the_grant_is_matched_against_the_tokens_own_subject(
    client: TestClient,
    owner_conn: psycopg.Connection[Any],
    books: tuple[str, str, str],
    caller: tuple[str, str],
) -> None:
    """Someone else holds the grant, and this caller does not inherit it.

    Which is worth asserting because a token carries several identifiers — `sub`, `azp`,
    `client_id` — and matching a grant against the wrong one would still let the right caller
    in most of the time. Here the entity is owned by a principal this token does not name, and
    the answer must be no.
    """
    entity_id, _, _ = books
    _, token = caller
    grant(owner_conn, entity_id, f"user:someone-else-{uuid.uuid4().hex[:8]}")

    response = client.get(
        f"/entities/{entity_id}/trial-balance",
        headers={"authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "not_authorised"


# --- what must be refused -------------------------------------------------------------------


def test_no_token_is_refused(client: TestClient, books: tuple[str, str, str]) -> None:
    """`LED-20` requires every transaction to record what wrote it, so a request that names
    nobody cannot be served."""
    entity_id, _, _ = books

    response = client.get(f"/entities/{entity_id}/trial-balance")

    assert response.status_code == 401


def test_a_token_from_somewhere_else_is_refused(
    client: TestClient, books: tuple[str, str, str], caller: tuple[str, str]
) -> None:
    """A token signed by a key this issuer never published. The signature check is what makes
    every other claim in the token worth reading."""
    entity_id, _, _ = books
    _, token = caller
    header, payload, _ = token.split(".")
    forged = f"{header}.{payload}.{'A' * 86}"

    response = client.get(
        f"/entities/{entity_id}/trial-balance",
        headers={"authorization": f"Bearer {forged}"},
    )

    assert response.status_code == 401


def test_a_token_for_another_audience_is_refused(
    settings: Settings, books: tuple[str, str, str], caller: tuple[str, str]
) -> None:
    """`NFR-06`: "A request meant for somewhere else is refused rather than interpreted."

    The same valid, correctly signed token, offered to a deployment expecting a different
    audience. This is the control the whole realm configuration exists to make possible, and
    the one that silently did nothing while the issuer returned no audience at all.
    """
    entity_id, _, _ = books
    _, token = caller
    elsewhere = TestClient(
        create_app(
            Settings(
                database_url=settings.database_url,
                public_base_url=settings.public_base_url,
                auth_issuer_url=settings.auth_issuer_url,
                auth_audience="somebody-elses-ledger",
            )
        )
    )

    response = elsewhere.get(
        f"/entities/{entity_id}/trial-balance",
        headers={"authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401
