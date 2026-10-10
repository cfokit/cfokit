"""Every MCP answer about one company names it (`IAM-08`).

ADR-0036 layer 3. A person may hold several sets of books, and the agent carries which one it
is working in only as an argument it repeats. Each answer naming its company is what lets the
agent, and the person reading it, see which books a figure came from. Expected values are the
declarations this test made: the company's id and the name it was created with.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from mcp.server.auth.middleware.auth_context import auth_context_var
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.auth.provider import AccessToken

from cfokit.ledger.config import Settings
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.administration import create_entity
from cfokit.ledger.service.principal import ActorClass, Principal
from cfokit.server import mcp_server

pytestmark = pytest.mark.integration

ISSUER = "http://localhost:8180/realms/cfokit"

# These take an entity and return it whole, or list what the person can reach.
ABOUT_THE_ENTITY_ITSELF = {"read_entity", "list_entities", "create_entity"}


def person(label: str) -> Principal:
    return Principal(id=f"user:{label}-{uuid.uuid4().hex[:8]}", actor_class=ActorClass.PERSON)


def company(database: Database, owner: Principal, name: str) -> str:
    return create_entity(
        database,
        principal=owner,
        request_id="names-the-company-test",
        slug=f"named-{uuid.uuid4().hex[:12]}",
        name=name,
        accounting_basis="accrual",
        fiscal_year_end_month=12,
        fiscal_year_end_day=31,
        functional_currency="USD",
        time_zone="America/New_York",
    ).entity_id


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


async def answer(server: Any, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    result = await server.call_tool(name, arguments)
    payload: dict[str, Any] = json.loads(result.content[0].text)
    return payload


@pytest.mark.anyio
async def test_every_tool_needing_only_the_entity_names_it(
    app_dsn: str, database: Database
) -> None:
    """Each tool on the surface whose only required argument is the entity, so the test reaches
    every one without knowing its shape, including the ones each module registers."""
    owner = person("owner")
    entity_id = company(database, owner, "Harbor Lights LLC")
    company(database, owner, "Second Company Inc")
    server: Any = mcp_server(settings(app_dsn), authenticator=StubAuthenticator(owner))

    tools = [
        tool.name
        for tool in await server.list_tools()
        if tool.name not in ABOUT_THE_ENTITY_ITSELF
        and tool.input_schema.get("required", []) == ["entity_id"]
    ]
    assert len(tools) >= 4

    with authenticated(owner):
        for name in tools:
            payload = await answer(server, name, {"entity_id": entity_id})
            assert payload["ok"] is True, (name, payload)
            assert payload["company"] == {"id": entity_id, "name": "Harbor Lights LLC"}, name


@pytest.mark.anyio
async def test_a_write_names_the_company_it_wrote_to(app_dsn: str, database: Database) -> None:
    owner = person("owner")
    first = company(database, owner, "Harbor Lights LLC")
    second = company(database, owner, "Second Company Inc")
    server: Any = mcp_server(settings(app_dsn), authenticator=StubAuthenticator(owner))

    with authenticated(owner):
        for entity_id, name in ((first, "Harbor Lights LLC"), (second, "Second Company Inc")):
            payload = await answer(server, "replay_assignments", {"entity_id": entity_id})
            assert payload["company"] == {"id": entity_id, "name": name}


@pytest.mark.anyio
async def test_a_refusal_names_no_company(app_dsn: str, database: Database) -> None:
    """A refusal keeps the shape and code ADR-0015 publishes; it vouches for no books."""
    owner = person("owner")
    company(database, owner, "Harbor Lights LLC")
    theirs = company(database, person("someone-else"), "Not Theirs Inc")
    server: Any = mcp_server(settings(app_dsn), authenticator=StubAuthenticator(owner))

    with authenticated(owner):
        payload = await answer(server, "open_notifications", {"entity_id": theirs})

    assert payload["ok"] is False
    assert "company" not in payload
    assert "Not Theirs Inc" not in json.dumps(payload)


@pytest.mark.anyio
async def test_creating_books_names_the_new_company(app_dsn: str, database: Database) -> None:
    owner = person("owner")
    server: Any = mcp_server(settings(app_dsn), authenticator=StubAuthenticator(owner))

    with authenticated(owner):
        payload = await answer(
            server,
            "create_entity",
            {
                "slug": f"named-{uuid.uuid4().hex[:12]}",
                "name": "Fresh Start LLC",
                "accounting_basis": "cash",
                "fiscal_year_end_month": 12,
                "fiscal_year_end_day": 31,
                "functional_currency": "USD",
                "time_zone": "America/New_York",
            },
        )

    assert payload["company"] == {"id": payload["entity_id"], "name": "Fresh Start LLC"}
