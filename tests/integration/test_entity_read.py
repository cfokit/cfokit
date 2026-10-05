"""Reading what an entity declared, over REST and MCP (`LED-14`, `LED-15`, `PLT-08`, `IAM-01`).

ADR-0036 layer 3. Each expected value is either a declaration this test made when it created the
entity, or `IAM-01`'s stated acceptance: an identity holding no role for an entity can do
nothing with it, reading included.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from fastapi.testclient import TestClient
from mcp.server.auth.middleware.auth_context import auth_context_var
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.auth.provider import AccessToken

from cfokit.ledger.config import Settings
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.administration import create_entity
from cfokit.ledger.service.principal import ActorClass, Principal
from cfokit.server import mcp_server, rest_app

pytestmark = pytest.mark.integration

ISSUER = "http://localhost:8180/realms/cfokit"

OWNER = Principal(id="user:entity-reader", actor_class=ActorClass.PERSON)
STRANGER = Principal(id="user:entity-stranger", actor_class=ActorClass.PERSON)
NEIGHBOR = Principal(id="user:entity-neighbor", actor_class=ActorClass.PERSON)


def declare(database: Database, owner: Principal, name: str) -> tuple[str, dict[str, Any]]:
    """Create an entity with declarations unlike any fixture's, and return what was declared."""
    declared: dict[str, Any] = {
        "slug": f"read-{uuid.uuid4().hex[:12]}",
        "name": name,
        "accounting_basis": "cash",
        "fiscal_year_end_month": 6,
        "fiscal_year_end_day": 30,
        "functional_currency": "GBP",
        "time_zone": "Europe/London",
    }
    created = create_entity(
        database, principal=owner, request_id="entity-read-test", **declared
    )
    return created.entity_id, declared


@pytest.fixture
def books(database: Database) -> tuple[str, dict[str, Any]]:
    return declare(database, OWNER, "Harbor Lane Bakery Ltd")


def claims(who: Principal) -> dict[str, Any]:
    return {"sub": who.id, "iss": ISSUER, "aud": "cfokit-ledger"}


class StubAuthenticator:
    """Stands in for the issuer; the claims still go through `principal_from_claims`."""

    def __init__(self, who: Principal) -> None:
        self._who = who

    def claims_for(self, credential: str | None) -> dict[str, Any]:
        return claims(self._who)


def settings(app_dsn: str) -> Settings:
    return Settings(
        database_url=app_dsn,
        public_base_url="http://localhost:8080",
        auth_issuer_url=ISSUER,
        auth_audience="cfokit-ledger",
    )


def rest(app_dsn: str, who: Principal) -> TestClient:
    return TestClient(rest_app(settings(app_dsn), authenticator=StubAuthenticator(who)))


@contextmanager
def authenticated(who: Principal) -> Iterator[None]:
    """Present a verified token to the MCP tools, as the SDK's bearer middleware does."""
    token = AccessToken(
        token="stub",  # noqa: S106 — a stand-in, never validated
        client_id=who.id,
        scopes=[],
        subject=who.id,
        claims=claims(who),
    )
    reset = auth_context_var.set(AuthenticatedUser(token))
    try:
        yield
    finally:
        auth_context_var.reset(reset)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def test_the_owner_reads_what_the_entity_declared(
    app_dsn: str, books: tuple[str, dict[str, Any]]
) -> None:
    entity_id, declared = books

    read = rest(app_dsn, OWNER).get(f"/entities/{entity_id}")

    assert read.status_code == 200
    assert read.json() == {"id": entity_id, **declared}


def test_a_caller_holding_no_role_is_refused(
    app_dsn: str, books: tuple[str, dict[str, Any]]
) -> None:
    refused = rest(app_dsn, STRANGER).get(f"/entities/{books[0]}")

    assert refused.status_code == 403
    assert refused.json()["code"] == "not_authorized"


def test_another_entitys_owner_is_refused(
    app_dsn: str, database: Database, books: tuple[str, dict[str, Any]]
) -> None:
    """Owning some books confers nothing over anybody else's (`IAM-01`, `NFR-04`)."""
    declare(database, NEIGHBOR, "Next Door Ltd")

    refused = rest(app_dsn, NEIGHBOR).get(f"/entities/{books[0]}")

    assert refused.status_code == 403
    assert refused.json()["code"] == "not_authorized"
    assert "Harbor Lane" not in refused.text


def test_an_entity_that_does_not_exist_is_not_found(app_dsn: str) -> None:
    missing = rest(app_dsn, OWNER).get(f"/entities/{uuid.uuid4()}")

    assert missing.status_code == 404
    assert missing.json()["code"] == "entity_not_found"


@pytest.mark.anyio
async def test_the_agent_names_the_company_over_mcp(
    app_dsn: str, books: tuple[str, dict[str, Any]]
) -> None:
    entity_id, declared = books

    async def call(who: Principal) -> dict[str, Any]:
        server: Any = mcp_server(settings(app_dsn), authenticator=StubAuthenticator(who))
        with authenticated(who):
            result = await server.call_tool("read_entity", {"entity_id": entity_id})
        payload: dict[str, Any] = json.loads(result.content[0].text)
        return payload

    assert await call(OWNER) == {"ok": True, "id": entity_id, **declared}

    refused = await call(STRANGER)
    assert refused["ok"] is False
    assert refused["code"] == "not_authorized"
