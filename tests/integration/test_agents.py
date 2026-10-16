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

from cfokit.ledger.errors import (
    AgentActsForNoMember,
    AgentNotAllowed,
    NotAnAgentRole,
    NotAuthorized,
)
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.administration import (
    agents_allowed_here,
    create_entity,
    grant_role,
    list_grants,
    revoke_grant,
)
from cfokit.ledger.service.authentication import WEB_CLIENT_ID, principal_from_claims
from cfokit.ledger.service.authorization import Capability, authorize
from cfokit.ledger.service.connections import record_connection
from cfokit.ledger.service.notifications import open_notifications
from cfokit.ledger.service.principal import Principal
from cfokit.ledger.service.read import list_entities, read_entity

pytestmark = pytest.mark.integration

PERSON = principal_from_claims({"sub": "user:geoff", "azp": WEB_CLIENT_ID})
CLAUDE = principal_from_claims({"sub": "user:geoff", "azp": "claude-connector"})
OTHER_CLIENT = principal_from_claims({"sub": "user:geoff", "azp": "mcp-remote"})
STRANGERS_AGENT = principal_from_claims({"sub": "user:stranger", "azp": "claude-connector"})
AGENT_ROLE_NAMES = ("reader", "bookkeeper")


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


def connected(database: Database, agent: Principal) -> None:
    """The agent opened a session for its person, which is how it comes to be allowed (§ 3)."""
    record_connection(
        database,
        principal=agent,
        request_id=f"req-{uuid.uuid4().hex[:8]}",
        client_name="claude-ai",
        client_version="0.1.0",
        person_email=None,
        person_name=None,
    )


def allow(
    database: Database, entity_id: str, agent: Principal, role: str, *, by: Principal = PERSON
) -> str:
    connected(database, agent)
    return grant_role(
        database,
        entity_id=entity_id,
        principal=by,
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


@pytest.mark.parametrize("role", ["owner", "poster"])
def test_an_agent_holds_only_the_roles_an_agent_may(database: Database, role: str) -> None:
    """Through the API as through the page: an agent never owns or grants (ADR-0066 § 2)."""
    company = new_company(database, PERSON)

    with pytest.raises(NotAnAgentRole):
        allow(database, company, CLAUDE, role)


# --- § 2: allowed only where it acts for a member --------------------------------------------


def test_an_agent_that_never_connected_is_not_allowed(database: Database) -> None:
    company = new_company(database, PERSON)
    never = principal_from_claims({"sub": "user:geoff", "azp": f"never-{uuid.uuid4().hex[:8]}"})

    with pytest.raises(AgentActsForNoMember) as caught:
        grant_role(
            database,
            entity_id=company,
            principal=PERSON,
            request_id="req-never",
            to_principal=never.id,
            role="reader",
        )
    assert caught.value.code == "agent_acts_for_no_member"


def test_an_agent_acting_for_someone_who_holds_nothing_here_is_not_allowed(
    database: Database,
) -> None:
    """A stranger's agent, handed to an owner: allowing it could confer nothing (`IAM-11`)."""
    company = new_company(database, PERSON)
    strangers = principal_from_claims(
        {"sub": f"user:stranger-{uuid.uuid4().hex[:8]}", "azp": f"x-{uuid.uuid4().hex[:8]}"}
    )
    connected(database, strangers)

    with pytest.raises(AgentActsForNoMember):
        grant_role(
            database,
            entity_id=company,
            principal=PERSON,
            request_id="req-stranger",
            to_principal=strangers.id,
            role="bookkeeper",
        )


# --- § 6: the other administrators are told ------------------------------------------------


def colleague(database: Database, company: str) -> Principal:
    """A second person who administers the company, with an agent of their own."""
    person = principal_from_claims(
        {"sub": f"user:colleague-{uuid.uuid4().hex[:8]}", "azp": WEB_CLIENT_ID}
    )
    grant_role(
        database,
        entity_id=company,
        principal=PERSON,
        request_id=f"req-{uuid.uuid4().hex[:8]}",
        to_principal=person.id,
        role="owner",
    )
    return person


def allowed_to_record(database: Database, company: str, who: Principal) -> None:
    """Raises unless `who` may record here now, read as every write reads it."""
    with database.entity_write(company) as write:
        authorize(write, Capability.RECORD, who)


def notices(database: Database, who: Principal, company: str) -> list[str]:
    return [
        n.subject_ref
        for n in open_notifications(database, principal=who, entity_id=company)
        if n.notification_class == "agent_allowed"
    ]


def test_allowing_an_agent_tells_each_other_administrator_and_not_who_allowed_it(
    database: Database,
) -> None:
    company = new_company(database, PERSON)
    other = new_company(database, PERSON)
    them = colleague(database, company)
    their_agent = principal_from_claims({"sub": them.id, "azp": f"c-{uuid.uuid4().hex[:8]}"})

    allow(database, company, their_agent, "bookkeeper", by=them)

    assert notices(database, PERSON, company) == [their_agent.id]
    assert notices(database, them, company) == []
    assert notices(database, PERSON, other) == []


def test_allowing_your_own_agent_where_you_alone_administer_tells_no_one(
    database: Database,
) -> None:
    company = new_company(database, PERSON)

    allow(database, company, CLAUDE, "bookkeeper")

    assert notices(database, PERSON, company) == []


def test_revoking_the_agent_answers_the_notice(database: Database) -> None:
    company = new_company(database, PERSON)
    them = colleague(database, company)
    their_agent = principal_from_claims({"sub": them.id, "azp": f"c-{uuid.uuid4().hex[:8]}"})
    grant_id = allow(database, company, their_agent, "reader", by=them)

    revoke_grant(
        database, entity_id=company, principal=PERSON, request_id="req-r", grant_id=grant_id
    )

    assert notices(database, PERSON, company) == []


def test_a_second_role_for_an_allowed_agent_tells_no_one_again(database: Database) -> None:
    """ADR-0073: the notice follows the agent's standing, not its grants."""
    company = new_company(database, PERSON)
    them = colleague(database, company)
    their_agent = principal_from_claims({"sub": them.id, "azp": f"c-{uuid.uuid4().hex[:8]}"})
    reading = allow(database, company, their_agent, "reader", by=them)
    allow(database, company, their_agent, "bookkeeper", by=them)

    assert notices(database, PERSON, company) == [their_agent.id]

    revoke_grant(
        database, entity_id=company, principal=PERSON, request_id="req-r", grant_id=reading
    )

    assert notices(database, PERSON, company) == [their_agent.id]


def test_removing_an_agents_last_role_answers_the_notice(database: Database) -> None:
    company = new_company(database, PERSON)
    them = colleague(database, company)
    their_agent = principal_from_claims({"sub": them.id, "azp": f"c-{uuid.uuid4().hex[:8]}"})
    roles = [allow(database, company, their_agent, role, by=them) for role in AGENT_ROLE_NAMES]

    for grant_id in roles:
        revoke_grant(
            database, entity_id=company, principal=PERSON, request_id="req-r", grant_id=grant_id
        )

    assert notices(database, PERSON, company) == []


def test_a_role_change_reaches_an_agent_on_its_next_call(database: Database) -> None:
    """`IAM-15` and ADR-0073: roles are read on every call, so the same token, unchanged,
    meets the new roles."""
    company = new_company(database, PERSON)
    reading = allow(database, company, CLAUDE, "reader")

    with pytest.raises(NotAuthorized):
        allowed_to_record(database, company, CLAUDE)

    allow(database, company, CLAUDE, "bookkeeper")
    revoke_grant(
        database, entity_id=company, principal=PERSON, request_id="req-r", grant_id=reading
    )

    allowed_to_record(database, company, CLAUDE)


def test_administrators_see_the_account_an_allowed_agent_signed_in_as(
    database: Database,
) -> None:
    company = new_company(database, PERSON)
    them = colleague(database, company)
    their_agent = principal_from_claims({"sub": them.id, "azp": f"c-{uuid.uuid4().hex[:8]}"})
    unallowed = principal_from_claims({"sub": them.id, "azp": f"u-{uuid.uuid4().hex[:8]}"})
    connected(database, unallowed)
    allow(database, company, their_agent, "reader", by=them)

    seen = agents_allowed_here(database, entity_id=company, principal=PERSON)

    assert [(found.agent_id, found.acting_for) for found in seen] == [(their_agent.id, them.id)]
    with pytest.raises(NotAuthorized):
        agents_allowed_here(database, entity_id=company, principal=their_agent)


def test_someone_holding_no_role_is_refused_the_agents_allowed_in_a_company(
    database: Database,
) -> None:
    company = new_company(database, PERSON)
    allow(database, company, CLAUDE, "reader")
    stranger = principal_from_claims(
        {"sub": f"user:stranger-{uuid.uuid4().hex[:8]}", "azp": WEB_CLIENT_ID}
    )

    with pytest.raises(NotAuthorized):
        agents_allowed_here(database, entity_id=company, principal=stranger)


def test_row_level_security_shows_a_company_only_the_agents_allowed_in_it(
    database: Database, app_conn: psycopg.Connection[Any]
) -> None:
    """The second layer: under a company's scope the application role reads the connection of
    an agent allowed there, and not one a member connected without allowing it here."""
    company = new_company(database, PERSON)
    them = colleague(database, company)
    allowed = principal_from_claims({"sub": them.id, "azp": f"a-{uuid.uuid4().hex[:8]}"})
    unallowed = principal_from_claims({"sub": them.id, "azp": f"u-{uuid.uuid4().hex[:8]}"})
    connected(database, unallowed)
    allow(database, company, allowed, "reader", by=them)

    with app_conn.transaction(), app_conn.cursor() as cur:
        cur.execute("SELECT set_config('cfokit.entity_id', %s, true)", (company,))
        cur.execute(
            "SELECT agent_id FROM agent_connection WHERE acting_for = %s ORDER BY agent_id",
            (them.id,),
        )
        seen = [row[0] for row in cur.fetchall()]

    assert seen == [allowed.id]
