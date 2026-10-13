"""Which agents have connected for a person. Hand-written SQL (ADR-0028, migration 0022).

Every statement here runs in a transaction that declared the person in `cfokit.person_id`
(`Database.person_records`), so row-level security admits that person's rows and no one
else's. The functions filter on the person as well, because RLS misconfiguration is silent.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import psycopg

__all__ = [
    "Connection",
    "connections_of",
    "declare_person",
    "member_connections",
    "record_connection",
]


@dataclass(frozen=True, slots=True)
class Connection:
    """One agent's connections for one person, as the last of them left it."""

    agent_id: str
    acting_for: str
    client_name: str | None
    client_version: str | None
    person_email: str | None
    person_name: str | None
    first_connected_at: datetime
    last_connected_at: datetime


def declare_person(conn: psycopg.Connection[Any], person_id: str) -> None:
    """Scope the rest of this transaction to one person's connections.

    Transaction-local (`set_config(..., true)`), so a connection never carries it into the next.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT set_config('cfokit.person_id', %s, true)", (person_id,))


def record_connection(
    conn: psycopg.Connection[Any],
    *,
    agent_id: str,
    acting_for: str,
    client_name: str | None,
    client_version: str | None,
    person_email: str | None,
    person_name: str | None,
) -> Connection:
    """Record that the agent connected now: the first time inserts, every later one updates.

    What the client and the token say replaces what they said before, because the page shows
    the agent as it is now. The history is the audit trail's.
    """
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO agent_connection"
            " (agent_id, acting_for, client_name, client_version, person_email, person_name)"
            " VALUES (%s, %s, %s, %s, %s, %s)"
            " ON CONFLICT (agent_id, acting_for) DO UPDATE SET"
            "   client_name = EXCLUDED.client_name,"
            "   client_version = EXCLUDED.client_version,"
            "   person_email = EXCLUDED.person_email,"
            "   person_name = EXCLUDED.person_name,"
            "   last_connected_at = now()"
            " RETURNING agent_id, acting_for, client_name, client_version, person_email,"
            "   person_name, first_connected_at, last_connected_at",
            (agent_id, acting_for, client_name, client_version, person_email, person_name),
        )
        row = cur.fetchone()
    if row is None:  # pragma: no cover - an upsert with RETURNING always returns its row
        raise RuntimeError("agent connection upsert returned no row")
    return _connection(row)


def connections_of(
    conn: psycopg.Connection[Any], *, acting_for: str, agent_id: str | None
) -> list[Connection]:
    """The person's agents, most recently connected first; one agent's where it is named."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT agent_id, acting_for, client_name, client_version, person_email,"
            "       person_name, first_connected_at, last_connected_at"
            "  FROM agent_connection"
            " WHERE acting_for = %s AND (%s::text IS NULL OR agent_id = %s)"
            " ORDER BY last_connected_at DESC, agent_id",
            (acting_for, agent_id, agent_id),
        )
        return [_connection(row) for row in cur.fetchall()]


def member_connections(
    conn: psycopg.Connection[Any], *, entity_id: str, agent_id: str | None
) -> list[Connection]:
    """Connections made for this entity's members, under its scope (migration 0023); one agent's
    where it is named.

    Filtered on membership here as well as by the policy: RLS misconfiguration is silent.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT c.agent_id, c.acting_for, c.client_name, c.client_version, c.person_email,"
            "       c.person_name, c.first_connected_at, c.last_connected_at"
            "  FROM agent_connection c"
            " WHERE (%s::text IS NULL OR c.agent_id = %s)"
            "   AND EXISTS ("
            "       SELECT 1 FROM entity_grant g"
            "        WHERE g.entity_id = %s"
            "          AND g.principal_id = c.acting_for"
            "          AND g.granted_at <= now()"
            "          AND (g.lapses_at IS NULL OR g.lapses_at > now())"
            "          AND (g.revoked_at IS NULL OR g.revoked_at > now()))"
            " ORDER BY c.last_connected_at DESC, c.agent_id, c.acting_for",
            (agent_id, agent_id, entity_id),
        )
        return [_connection(row) for row in cur.fetchall()]


def _connection(row: tuple[Any, ...]) -> Connection:
    return Connection(
        agent_id=str(row[0]),
        acting_for=str(row[1]),
        client_name=row[2],
        client_version=row[3],
        person_email=row[4],
        person_name=row[5],
        first_connected_at=row[6],
        last_connected_at=row[7],
    )
