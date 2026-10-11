"""An agent is the client it signs in through, and acts in a company once the person allows it
(ADR-0066, `IAM-11`, `IAM-12`, `IAM-15`).

Expected values come from the record and the requirements: an agent with no grant is refused
where its person holds a role, allowing it is a grant like any other and revoking it ends it at
once, one company's grant says nothing about another's, and an agent that creates a company
makes its person the owner and itself the bookkeeper.
"""

from __future__ import annotations

import uuid
from typing import Any

import psycopg
import pytest

from cfokit.ledger.errors import AgentNotAllowed, NotAuthorized
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.administration import (
    create_entity,
    grant_role,
    list_grants,
    revoke_grant,
)
from cfokit.ledger.service.authentication import WEB_CLIENT_ID, principal_from_claims
from cfokit.ledger.service.principal import Principal
from cfokit.ledger.service.read import list_entities, read_entity

pytestmark = pytest.mark.integration

PERSON = principal_from_claims({"sub": "user:geoff", "azp": WEB_CLIENT_ID})
CLAUDE = principal_from_claims({"sub": "user:geoff", "azp": "claude-connector"})
OTHER_CLIENT = principal_from_claims({"sub": "user:geoff", "azp": "mcp-remote"})
STRANGERS_AGENT = principal_from_claims({"sub": "user:stranger", "azp": "claude-connector"})


def new_company(database: Database, principal: Principal) -> str:
    return create_entity(
        database,
        principal=principal,
        request_id=f"req-{uuid.uuid4().hex[:8]}",
        slug=f"agents-{uuid.uuid4().hex[:12]}",
        name="Acme",
        accounting_basis="accrual",
        fiscal_year_end_month=12,
        fiscal_year_end_day=31,
        functional_currency="USD",
        time_zone="UTC",
    ).entity_id


def allow(database: Database, entity_id: str, agent: Principal, role: str) -> str:
    return grant_role(
        database,
        entity_id=entity_id,
        principal=PERSON,
        request_id=f"req-{uuid.uuid4().hex[:8]}",
        to_principal=agent.id,
        role=role,
    )


def test_an_agent_the_person_has_not_allowed_is_refused_with_its_own_code(
    database: Database,
) -> None:
    company = new_company(database, PERSON)

    with pytest.raises(AgentNotAllowed) as caught:
        read_entity(database, entity_id=company, principal=CLAUDE)

    assert caught.value.code == "agent_not_allowed"
    assert caught.value.agent == "client:claude-connector"


def test_where_the_person_holds_nothing_the_refusal_is_the_ordinary_one(
    database: Database,
) -> None:
    """Saying "allow this agent" about a company the person cannot reach would tell them it
    exists; the ordinary refusal says no more than it would to anyone."""
    company = new_company(database, PERSON)

    with pytest.raises(NotAuthorized) as caught:
        read_entity(database, entity_id=company, principal=STRANGERS_AGENT)

    assert caught.value.code == "not_authorized"


def test_allowing_an_agent_lets_it_act_and_revoking_ends_it_at_once(database: Database) -> None:
    company = new_company(database, PERSON)

    grant_id = allow(database, company, CLAUDE, "reader")
    assert read_entity(database, entity_id=company, principal=CLAUDE).id == company

    revoke_grant(
        database,
        entity_id=company,
        principal=PERSON,
        request_id="req-revoke",
        grant_id=grant_id,
    )
    with pytest.raises(AgentNotAllowed):
        read_entity(database, entity_id=company, principal=CLAUDE)


def test_allowing_an_agent_in_one_company_says_nothing_about_another(
    database: Database,
) -> None:
    allowed = new_company(database, PERSON)
    other = new_company(database, PERSON)
    allow(database, allowed, CLAUDE, "bookkeeper")

    listed = {found.id for found in list_entities(database, principal=CLAUDE)}

    assert allowed in listed
    assert other not in listed
    with pytest.raises(AgentNotAllowed):
        read_entity(database, entity_id=other, principal=CLAUDE)


def test_each_client_is_allowed_on_its_own(database: Database) -> None:
    company = new_company(database, PERSON)
    allow(database, company, CLAUDE, "reader")

    with pytest.raises(AgentNotAllowed):
        read_entity(database, entity_id=company, principal=OTHER_CLIENT)


def test_an_agent_cannot_allow_itself_or_any_other(database: Database) -> None:
    """Neither agent role carries `grant`, so the intersection never does (`IAM-11`)."""
    company = new_company(database, PERSON)
    allow(database, company, CLAUDE, "bookkeeper")

    with pytest.raises(NotAuthorized):
        grant_role(
            database,
            entity_id=company,
            principal=CLAUDE,
            request_id="req-self",
            to_principal=OTHER_CLIENT.id,
            role="bookkeeper",
        )


def test_an_agent_that_creates_a_company_makes_its_person_the_owner_and_itself_the_bookkeeper(
    database: Database, owner_conn: psycopg.Connection[Any]
) -> None:
    company = new_company(database, CLAUDE)

    held = {
        (g.principal_id, g.role)
        for g in list_grants(database, entity_id=company, principal=PERSON)
    }
    assert held == {("user:geoff", "owner"), ("client:claude-connector", "bookkeeper")}
    assert read_entity(database, entity_id=company, principal=CLAUDE).id == company
    with pytest.raises(AgentNotAllowed):
        read_entity(database, entity_id=company, principal=OTHER_CLIENT)

    with owner_conn.cursor() as cur:
        cur.execute(
            "SELECT action, detail FROM audit_log WHERE entity_id = %s"
            " ORDER BY occurred_at, id",
            (company,),
        )
        rows = cur.fetchall()
    assert [row[0] for row in rows].count("create_entity") == 1
    assert {"to": "client:claude-connector", "role": "bookkeeper"} in [row[1] for row in rows]


def test_a_person_creating_a_company_grants_no_agent(database: Database) -> None:
    company = new_company(database, PERSON)

    held = [g.principal_id for g in list_grants(database, entity_id=company, principal=PERSON)]

    assert held == ["user:geoff"]


def test_only_someone_who_can_grant_reads_the_grants(database: Database) -> None:
    company = new_company(database, PERSON)
    allow(database, company, CLAUDE, "bookkeeper")

    with pytest.raises(NotAuthorized):
        list_grants(database, entity_id=company, principal=CLAUDE)
