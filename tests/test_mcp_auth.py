"""The MCP surface's bearer verification (ADR-0019, `IAM-10`).

Pure: no issuer, no network, no database. What is asserted is the adapter between the
ledger's `Authenticator` and the SDK's `TokenVerifier` protocol — that a rejected token
becomes `None` so the SDK can answer 401 with the metadata a client needs, and that the
claims travel intact so the principal is derived by the same rule REST uses.
"""

from __future__ import annotations

from typing import Any

import pytest
from starlette.testclient import TestClient

from cfokit.ledger.config import Settings
from cfokit.ledger.errors import NotAuthenticated
from cfokit.ledger.mcp import create_server
from cfokit.ledger.mcp.auth import LedgerTokenVerifier
from cfokit.ledger.service.authentication import DenyAll, principal_from_claims
from cfokit.ledger.service.principal import ActorClass

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def settings() -> Settings:
    return Settings(
        database_url="postgresql://unused/unused",
        public_base_url="http://localhost:8081",
        auth_issuer_url="http://localhost:8180/realms/cfokit",
        auth_audience="cfokit-ledger",
    )


class Accepts:
    def __init__(self, claims: dict[str, Any]) -> None:
        self._claims = claims

    def claims_for(self, credential: str | None) -> dict[str, Any]:
        return self._claims


async def test_a_valid_token_carries_its_claims_through() -> None:
    verifier = LedgerTokenVerifier(Accepts({"sub": "user:ana", "exp": 4102444800}))

    token = await verifier.verify_token("anything")

    assert token is not None
    assert token.subject == "user:ana"
    assert token.claims == {"sub": "user:ana", "exp": 4102444800}
    assert token.expires_at == 4102444800


async def test_a_rejected_token_is_none_rather_than_an_exception() -> None:
    """The SDK turns `None` into a 401 carrying the resource metadata URL.

    Raising would produce a 500 and tell an MCP client nothing about where to get a token.
    """
    assert await LedgerTokenVerifier(DenyAll()).verify_token("anything") is None


async def test_a_token_with_no_subject_is_rejected() -> None:
    """There would be nothing to attribute a write to (`LED-20`)."""
    assert await LedgerTokenVerifier(Accepts({"iss": "x"})).verify_token("anything") is None


async def test_the_principal_is_derived_from_the_claims_the_verifier_carried() -> None:
    """`IAM-11` and ADR-0033: delegation comes from the token's shape, not from a claim
    that says "I am an agent"."""
    verifier = LedgerTokenVerifier(
        Accepts({"sub": "skill:bookkeeper", "act": {"sub": "user:ana"}})
    )

    token = await verifier.verify_token("anything")
    assert token is not None and token.claims is not None
    principal = principal_from_claims(token.claims)

    assert principal.id == "skill:bookkeeper"
    assert principal.actor_class is ActorClass.AGENT
    assert principal.acting_for == "user:ana"


async def test_verification_failure_is_not_swallowed_as_success() -> None:
    """A `NotAuthenticated` from the authenticator must never become a token."""

    class Refuses:
        def claims_for(self, credential: str | None) -> dict[str, Any]:
            raise NotAuthenticated("token rejected")

    assert await LedgerTokenVerifier(Refuses()).verify_token("anything") is None


# --- The wire, not the dispatch -----------------------------------------------------------
#
# ADR-0036 asks for the protocol surfaces exercised as a client drives them, and notes the
# MCP half is covered by `call_tool` dispatch rather than the transport. These close the part
# of that gap that needs no database: what an unauthenticated caller actually receives, and
# what it can discover from it.


def _app(settings: Settings) -> Any:
    return create_server(settings, authenticator=DenyAll()).streamable_http_app(
        stateless_http=True, json_response=True
    )


def test_the_wire_refuses_a_request_with_no_token(settings: Settings) -> None:
    """401 before dispatch, so no tool runs and nothing reaches the database."""
    with TestClient(_app(settings)) as client:
        response = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            headers={
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
            },
        )

    assert response.status_code == 401
    challenge = response.headers["www-authenticate"]
    assert 'error="invalid_token"' in challenge
    # The client needs this to find the issuer and come back with a token.
    assert "resource_metadata=" in challenge


def test_a_client_can_discover_the_issuer_from_the_challenge(settings: Settings) -> None:
    """The resource metadata names the issuer, so the issuer stays swappable by
    configuration and no client is built against a particular one (ADR-0019)."""
    with TestClient(_app(settings)) as client:
        metadata = client.get("/.well-known/oauth-protected-resource").json()

    # Compared without a trailing slash on either side. The SDK normalises a bare origin to
    # end in one and leaves a path alone, so pinning the exact string would assert a quirk of
    # whichever issuer URL the test happened to use rather than the property a client needs.
    advertised = [server.rstrip("/") for server in metadata["authorization_servers"]]

    assert advertised == [settings.auth_issuer_url.rstrip("/")]
    assert metadata["bearer_methods_supported"] == ["header"]


def test_the_advertised_resource_comes_from_public_base_url(settings: Settings) -> None:
    """Never from a request header. Behind a proxy or a tunnel the headers lie, and this URL
    is what a client fetches metadata from (ADR-0004)."""
    with TestClient(_app(settings)) as client:
        metadata = client.get(
            "/.well-known/oauth-protected-resource", headers={"Host": "evil.example"}
        ).json()

    assert metadata["resource"].startswith(settings.public_base_url)


# --- Operations ---------------------------------------------------------------------------


def test_liveness_needs_no_token(settings: Settings) -> None:
    """A platform probe holds no credential, and liveness must not depend on one."""
    with TestClient(_app(settings)) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_liveness_touches_nothing(settings: Settings) -> None:
    """The DSN is unroutable. If liveness reached the database this would not answer.

    A database blip must not restart every healthy container, which is what turns a
    recoverable outage into a rolling one.
    """
    with TestClient(_app(settings)) as client:
        assert client.get("/healthz").status_code == 200


def test_readiness_reports_not_ready_when_the_database_is_unreachable(
    settings: Settings,
) -> None:
    """503 so a rollout stops, rather than serving against a schema older than the code."""
    with TestClient(_app(settings)) as client:
        response = client.get("/readyz")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["database_reachable"] is False


# --- the deployed surface, not the generated one --------------------------------------------


def test_readiness_reports_the_tool_surface_this_instance_serves(settings: Settings) -> None:
    """**What a stale deployment looks like from outside.**

    Gate 5 diffs the contract this *code* generates against the one committed. Nothing compared
    either against what a *running* container serves — so a tool merged and never rolled out
    was invisible: the repository agreed with itself while the deployment served an older
    surface, and the only symptom was a client reporting that the tool did not exist.

    Reported unauthenticated because it is not a secret. The tool surface is published
    (ADR-0015) and `docs/contracts/mcp-tools.json` is the same list.
    """
    with TestClient(_app(settings)) as client:
        body = client.get("/readyz").json()

    surface = body["tools"]
    assert surface["count"] == len(surface["names"])
    assert surface["digest"]
    assert "trial_balance" in surface["names"]
