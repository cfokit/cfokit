"""CFOKit's agent exchanges a person's token for its own, against the shipped realm
(ADR-0077).

ADR-0036 layer 3. What is measured is the realm CFOKit ships
(`infra/keycloak/cfokit-realm.json`) and the agent's own exchange code together: a person
signs in through the web client exactly as a browser does, with authorization code and PKCE, and
the agent presents that token.

Expected values come from outside the implementation: RFC 8693 § 2.2.1 (the token is issued to
the client that asked, for the subject of the token presented), ADR-0077 (the server sees the
agent `client:cfokit-agent` acting for that person) read through the ledger's own principal
derivation as a second enforcement point, and `AUTH_AUDIENCE`, which the API validates.

This file knows the issuer is Keycloak, which the issuer conformance suite deliberately does
not: creating a person needs an administrator, and the sign-in page is the issuer's. It skips
unless the stack's local administrator is given to it, so a deployment with another issuer skips
it."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import re
import secrets
from collections.abc import Iterator
from typing import Any

import httpx2 as httpx
import pytest

from cfokit.agent.tokens import Exchange, TokenRefused
from cfokit.ledger.service.authentication import principal_from_claims
from cfokit.ledger.service.principal import ActorClass

pytestmark = pytest.mark.integration

ISSUER = os.environ.get("AUTH_ISSUER_URL", "").rstrip("/")
AUDIENCE = os.environ.get("AUTH_AUDIENCE", "")
WEB = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
ADMIN = os.environ.get("KEYCLOAK_ADMIN", "")
ADMIN_PASSWORD = os.environ.get("KEYCLOAK_ADMIN_PASSWORD", "")
AGENT_SECRET = os.environ.get("CFOKIT_AGENT_CLIENT_SECRET", "")
TIMEOUT = 10


@pytest.fixture(autouse=True)
def _requires_the_shipped_issuer() -> None:
    if not (ISSUER and WEB and ADMIN and ADMIN_PASSWORD and AGENT_SECRET):
        pytest.skip("needs the compose issuer: docker compose --profile test run --rm test")


def claims(token: str) -> dict[str, Any]:
    """A JWT's claims, unverified: what the issuer put in it is what is under test."""
    payload = token.split(".")[1]
    decoded = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    assert isinstance(decoded, dict)
    return decoded


@pytest.fixture
def person() -> Iterator[str]:
    """An access token from the web client for a person made for this test, then removed."""
    origin = ISSUER.split("/realms/")[0]
    realm = ISSUER.rsplit("/", 1)[1]
    with httpx.Client(timeout=TIMEOUT) as http:
        admin = http.post(
            f"{origin}/realms/master/protocol/openid-connect/token",
            data={
                "grant_type": "password",
                "client_id": "admin-cli",
                "username": ADMIN,
                "password": ADMIN_PASSWORD,
            },
        )
        admin.raise_for_status()
        signed_in = {"authorization": f"Bearer {admin.json()['access_token']}"}
        email = f"agent-{secrets.token_hex(4)}@example.com"
        password = secrets.token_urlsafe(24)
        created = http.post(
            f"{origin}/admin/realms/{realm}/users",
            headers=signed_in,
            json={
                "username": email,
                "email": email,
                "emailVerified": True,
                "enabled": True,
                "firstName": "Services",
                "lastName": "Exchange",
                "credentials": [{"type": "password", "value": password, "temporary": False}],
            },
        )
        created.raise_for_status()
        try:
            yield _sign_in(http, email, password)
        finally:
            http.delete(created.headers["location"], headers=signed_in)


def _sign_in(http: httpx.Client, email: str, password: str) -> str:
    """Authorization code with PKCE through the sign-in page, as the web client's browser
    does."""
    verifier = secrets.token_urlsafe(48)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    redirect = f"{WEB}/app/"
    page = http.get(
        f"{ISSUER}/protocol/openid-connect/auth",
        params={
            "client_id": "cfokit-web",
            "response_type": "code",
            "redirect_uri": redirect,
            "scope": "openid",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "agent-exchange",
        },
    )
    action = re.search(r'"loginAction":\s*"([^"]+)"', page.text)
    assert action, "the sign-in page names no form action"
    answered = http.post(action.group(1), data={"username": email, "password": password})
    code = re.search(r"[?&]code=([^&]+)", answered.headers.get("location", ""))
    assert code, f"signing in did not return to the web client ({answered.status_code})"
    token = http.post(
        f"{ISSUER}/protocol/openid-connect/token",
        data={
            "grant_type": "authorization_code",
            "client_id": "cfokit-web",
            "code": code.group(1),
            "redirect_uri": redirect,
            "code_verifier": verifier,
        },
    )
    token.raise_for_status()
    return str(token.json()["access_token"])


def exchange(person_token: str, *, secret: str = AGENT_SECRET) -> str:
    async def run() -> str:
        async with httpx.AsyncClient(timeout=TIMEOUT) as http:
            return await Exchange(
                issuer_url=ISSUER,
                client_id="cfokit-agent",
                client_secret=secret,
                http=http,
            ).for_person(person_token)

    return asyncio.run(run())


def test_the_agent_receives_a_token_of_its_own_for_the_person(person: str) -> None:
    """RFC 8693 § 2.2.1: issued to the client that asked, for the subject it presented."""
    theirs, ours = claims(person), claims(exchange(person))
    assert ours["sub"] == theirs["sub"]
    assert ours["azp"] == "cfokit-agent"
    assert AUDIENCE in ours["aud"]


def test_the_api_sees_the_agent_acting_for_the_person(person: str) -> None:
    """ADR-0077: an agent, allowed per company like any other, never the person themselves."""
    theirs, ours = claims(person), claims(exchange(person))
    principal = principal_from_claims(ours)
    assert principal.actor_class is ActorClass.AGENT
    assert principal.id == "client:cfokit-agent"
    assert principal.acting_for == theirs["sub"]


def test_a_token_not_meant_for_the_agent_is_not_exchanged() -> None:
    """A token another client holds, such as a person's own agent's, does not name the agent
    in its audience, so the agent cannot turn it into one of its own (ADR-0077)."""
    with httpx.Client(timeout=TIMEOUT) as http:
        metadata = http.get(f"{ISSUER}/.well-known/openid-configuration").json()
        registered = http.post(
            metadata["registration_endpoint"],
            json={
                "client_name": "agent exchange test",
                "grant_types": ["client_credentials"],
                "token_endpoint_auth_method": "client_secret_basic",
            },
        )
        registered.raise_for_status()
        client = registered.json()
        try:
            other = http.post(
                metadata["token_endpoint"],
                data={"grant_type": "client_credentials"},
                auth=(client["client_id"], client["client_secret"]),
            )
            other.raise_for_status()
            assert "cfokit-agent" not in claims(other.json()["access_token"])["aud"]
            with pytest.raises(TokenRefused):
                exchange(other.json()["access_token"])
        finally:
            http.delete(
                client["registration_client_uri"],
                headers={"authorization": f"Bearer {client['registration_access_token']}"},
            )


def test_a_wrong_secret_exchanges_nothing(person: str) -> None:
    with pytest.raises(TokenRefused):
        exchange(person, secret="not-the-secret")  # noqa: S106 - deliberately wrong
