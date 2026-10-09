"""Listing the entities a caller may read, over REST and MCP (`IAM-08`, `IAM-11`, `IAM-15`).

ADR-0036 layer 3. Each expected value is either a declaration this test made, or a requirement's
stated rule: one identity holds independent roles in each entity it can reach and none in the
rest (`IAM-08`); an agent's authority is the intersection of its own and the person's
(`IAM-11`); a revocation takes effect at once (`IAM-15`).

Every principal is new to each test, because the database is the whole suite's and a list is
the one read that sees across entities.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient
from mcp.server.auth.middleware.auth_context import auth_context_var
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.auth.provider import AccessToken

from cfokit.ledger.config import Settings
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.administration import create_entity, grant_role, revoke_grant
from cfokit.ledger.service.principal import ActorClass, Principal
from cfokit.ledger.service.read import list_entities
from cfokit.server import mcp_server, rest_app

pytestmark = pytest.mark.integration

ISSUER = "http://localhost:8180/realms/cfokit"


def person(label: str) -> Principal:
    return Principal(id=f"user:{label}-{uuid.uuid4().hex[:8]}", actor_class=ActorClass.PERSON)


def company(database: Database, owner: Principal, name: str) -> str:
    return create_entity(
        database,
        principal=owner,
        request_id="entity-list-test",
        slug=f"list-{uuid.uuid4().hex[:12]}",
        name=name,
        accounting_basis="accrual",
        fiscal_year_end_month=12,
        fiscal_year_end_day=31,
        functional_currency="USD",
        time_zone="America/Chicago",
    ).entity_id


def names(database: Database, who: Principal) -> list[str]:
    return [entity.name for entity in list_entities(database, principal=who)]


def test_a_person_sees_every_company_they_hold_a_role_in_by_name(database: Database) -> None:
    owner = person("owner")
    company(database, owner, "Zephyr Holdings")
    company(database, owner, "acme widgets")
    company(database, person("someone-else"), "Not Theirs Inc")

    assert names(database, owner) == ["acme widgets", "Zephyr Holdings"]


def test_a_person_holding_nothing_sees_nothing(database: Database) -> None:
    company(database, person("owner"), "Somebody's Books")

    assert names(database, person("stranger")) == []


def test_a_role_granted_in_another_company_lists_it(database: Database) -> None:
    """`IAM-08`: an advisor across many entities is the ordinary case."""
    owner = person("owner")
    advisor = person("advisor")
    entity_id = company(database, owner, "Client Co")
    grant_role(
        database,
        entity_id=entity_id,
        principal=owner,
        request_id="grant",
        to_principal=advisor.id,
        role="reader",
        lapses_at=None,
    )

    assert names(database, advisor) == ["Client Co"]


def test_a_revoked_role_stops_listing_the_company_at_once(database: Database) -> None:
    owner = person("owner")
    advisor = person("advisor")
    entity_id = company(database, owner, "Former Client")
    grant_id = grant_role(
        database,
        entity_id=entity_id,
        principal=owner,
        request_id="grant",
        to_principal=advisor.id,
        role="reader",
        lapses_at=None,
    )
    revoke_grant(
        database, entity_id=entity_id, principal=owner, request_id="revoke", grant_id=grant_id
    )

    assert names(database, advisor) == []


def test_an_agent_sees_only_where_it_and_the_person_both_hold_a_role(
    database: Database,
) -> None:
    """`IAM-11` and `IAM-12`: a company the person holds and the agent was never authorized in
    is not one the agent can reach."""
    owner = person("owner")
    skill_id = f"skill:bookkeeper-{uuid.uuid4().hex[:8]}"
    authorized = company(database, owner, "Authorized Co")
    company(database, owner, "Unauthorized Co")
    grant_role(
        database,
        entity_id=authorized,
        principal=owner,
        request_id="grant",
        to_principal=skill_id,
        role="reader",
        lapses_at=None,
    )
    agent = Principal(id=skill_id, actor_class=ActorClass.AGENT, acting_for=owner.id)

    assert names(database, agent) == ["Authorized Co"]


def test_declaring_a_principal_reveals_only_its_own_grants(
    database: Database, app_conn: psycopg.Connection[Any]
) -> None:
    """Migration 0019's whole allowance, measured as the application role: a transaction that
    declares a principal sees that principal's grant rows and nothing else — no other
    principal's grant, and no entity's books."""
    owner = person("owner")
    other = person("other")
    mine = company(database, owner, "Mine")
    company(database, other, "Theirs")

    with app_conn.transaction(), app_conn.cursor() as cur:
        cur.execute("SELECT set_config('cfokit.principal_id', %s, true)", (owner.id,))
        cur.execute("SELECT DISTINCT principal_id, entity_id::text FROM entity_grant")
        grants = cur.fetchall()
        cur.execute("SELECT count(*) FROM account")
        accounts = cur.fetchone()
        cur.execute("SELECT count(*) FROM audit_log")
        audit = cur.fetchone()

    assert grants == [(owner.id, mine)]
    assert accounts == (0,)
    assert audit == (0,)


def test_the_declaration_does_not_widen_a_write(
    database: Database, app_conn: psycopg.Connection[Any]
) -> None:
    """The policy is for reading. Revoking a grant still needs the entity's scope."""
    owner = person("owner")
    company(database, owner, "Mine")

    with app_conn.transaction(), app_conn.cursor() as cur:
        cur.execute("SELECT set_config('cfokit.principal_id', %s, true)", (owner.id,))
        cur.execute(
            "UPDATE entity_grant SET revoked_at = now(), revoked_by = 'x'"
            " WHERE principal_id = %s",
            (owner.id,),
        )
        assert cur.rowcount == 0


# --- the two surfaces --------------------------------------------------------------------


def settings(app_dsn: str) -> Settings:
    return Settings(
        database_url=app_dsn,
        public_base_url="http://localhost:8080",
        auth_issuer_url=ISSUER,
        auth_audience="cfokit-ledger",
    )


def claims(who: Principal) -> dict[str, Any]:
    return {"sub": who.id, "iss": ISSUER, "aud": "cfokit-ledger"}


class StubAuthenticator:
    def __init__(self, who: Principal) -> None:
        self._who = who

    def claims_for(self, credential: str | None) -> dict[str, Any]:
        return claims(self._who)


@contextmanager
def authenticated(who: Principal) -> Iterator[None]:
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


def test_rest_lists_the_callers_companies(app_dsn: str, database: Database) -> None:
    owner = person("owner")
    entity_id = company(database, owner, "Growth Lane LLC")

    listed = TestClient(
        rest_app(settings(app_dsn), authenticator=StubAuthenticator(owner))
    ).get("/entities")

    assert listed.status_code == 200
    assert [(e["id"], e["name"], e["time_zone"]) for e in listed.json()["entities"]] == [
        (entity_id, "Growth Lane LLC", "America/Chicago")
    ]


@pytest.mark.anyio
async def test_the_agent_finds_the_company_by_name_over_mcp(
    app_dsn: str, database: Database
) -> None:
    owner = person("owner")
    entity_id = company(database, owner, "Growth Lane LLC")
    server: Any = mcp_server(settings(app_dsn), authenticator=StubAuthenticator(owner))

    with authenticated(owner):
        result = await server.call_tool("list_entities", {})
    payload = json.loads(result.content[0].text)

    assert payload["ok"] is True
    assert [(e["id"], e["name"]) for e in payload["entities"]] == [
        (entity_id, "Growth Lane LLC")
    ]
