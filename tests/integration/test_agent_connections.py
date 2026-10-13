"""Which agents have connected, for whom, and as what (ADR-0066 § 3).

Expected values come from the record: a session an agent opens is recorded with the client's
reported name and version and the account its token names, with one `audit_log` row; a later
session updates the same record; a person reads only their own agents' records, and an agent
reads none (`not_a_person`). A person's own token opens no agent connection.
"""

from __future__ import annotations

import uuid
from typing import Any

import psycopg
import pytest

from cfokit.ledger.errors import NotAPerson
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.authentication import WEB_CLIENT_ID, principal_from_claims
from cfokit.ledger.service.connections import agent_connections, record_connection

pytestmark = pytest.mark.integration


def principals(azp: str = "claude-connector") -> tuple[Any, Any, str]:
    """A person new to this test, and an agent acting for them. Returns (person, agent, sub)."""
    sub = f"user:{uuid.uuid4().hex[:12]}"
    person = principal_from_claims({"sub": sub, "azp": WEB_CLIENT_ID})
    agent = principal_from_claims({"sub": sub, "azp": f"{azp}-{uuid.uuid4().hex[:8]}"})
    return person, agent, sub


def connect(database: Database, agent: Any, *, version: str = "0.1.0", request: str) -> None:
    record_connection(
        database,
        principal=agent,
        request_id=request,
        client_name="claude-ai",
        client_version=version,
        person_email="dana@example.test",
        person_name="Dana Whitfield",
    )


def test_a_session_is_recorded_with_what_the_client_and_token_said(database: Database) -> None:
    person, agent, _ = principals()

    connect(database, agent, request=f"req-{uuid.uuid4().hex}")

    [found] = agent_connections(database, principal=person)
    assert found.agent_id == agent.id
    assert (found.client_name, found.client_version) == ("claude-ai", "0.1.0")
    assert (found.person_email, found.person_name) == ("dana@example.test", "Dana Whitfield")
    assert found.first_connected_at == found.last_connected_at


def test_connecting_again_updates_the_record_and_keeps_the_first_time(
    database: Database,
) -> None:
    person, agent, _ = principals()
    connect(database, agent, request=f"req-{uuid.uuid4().hex}")

    connect(database, agent, version="0.2.0", request=f"req-{uuid.uuid4().hex}")

    [found] = agent_connections(database, principal=person)
    assert found.client_version == "0.2.0"
    assert found.last_connected_at > found.first_connected_at


def test_each_session_writes_one_audit_row_naming_no_entity_and_no_account(
    database: Database, owner_conn: psycopg.Connection[Any]
) -> None:
    _, agent, sub = principals()
    request = f"req-{uuid.uuid4().hex}"

    connect(database, agent, request=request)

    with owner_conn.cursor() as cur:
        cur.execute(
            "SELECT entity_id, actor, action, detail FROM audit_log WHERE request_id = %s",
            (request,),
        )
        rows = cur.fetchall()
    assert len(rows) == 1
    entity_id, actor, action, detail = rows[0]
    assert entity_id is None
    assert actor == f"{agent.id} for {sub}"
    assert action == "connect_agent"
    assert detail == {
        "agent_id": agent.id,
        "client_name": "claude-ai",
        "client_version": "0.1.0",
    }


def test_a_person_reads_their_own_agents_and_no_one_elses(database: Database) -> None:
    person, agent, _ = principals()
    stranger, strangers_agent, _ = principals()
    connect(database, agent, request=f"req-{uuid.uuid4().hex}")
    connect(database, strangers_agent, request=f"req-{uuid.uuid4().hex}")

    assert [found.agent_id for found in agent_connections(database, principal=person)] == [
        agent.id
    ]
    assert [found.agent_id for found in agent_connections(database, principal=stranger)] == [
        strangers_agent.id
    ]


def test_row_level_security_hides_connections_from_an_undeclared_transaction(
    database: Database, app_conn: psycopg.Connection[Any]
) -> None:
    """The second layer: without the person declared, the application role sees no row."""
    _, agent, _ = principals()
    connect(database, agent, request=f"req-{uuid.uuid4().hex}")

    with app_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM agent_connection WHERE agent_id = %s", (agent.id,))
        row = cur.fetchone()
    assert row is not None
    assert row[0] == 0


def test_an_agent_may_not_read_which_agents_its_person_connected(database: Database) -> None:
    _, agent, _ = principals()

    with pytest.raises(NotAPerson):
        agent_connections(database, principal=agent)


def test_a_persons_own_token_opens_no_agent_connection(database: Database) -> None:
    person, _, _ = principals()

    assert (
        record_connection(
            database,
            principal=person,
            request_id=f"req-{uuid.uuid4().hex}",
            client_name="cfokit-web",
            client_version=None,
            person_email=None,
            person_name=None,
        )
        is None
    )
    assert agent_connections(database, principal=person) == []
