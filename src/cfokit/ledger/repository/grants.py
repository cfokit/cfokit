"""Reading grants. Hand-written SQL (ADR-0028).

A grant is in force at a moment when it was granted before it, has not lapsed (`IAM-09`), and
has not been revoked (`IAM-15`). All three are columns rather than a computed status, so the
same query answers "what is in force now" and `IAM-14`'s "what was in force then" by changing
one parameter.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import psycopg

__all__ = [
    "RoleDefinition",
    "entities_held",
    "holders_of",
    "privileges_in_force",
    "role_definition",
]

# One query rather than roles-then-privileges: `IAM-01` makes authority the union over every
# role held, and the union is what the join produces. Resolving the catalog here also means
# a privilege map changed by migration takes effect without a cache to invalidate.
IN_FORCE = """
    SELECT DISTINCT rp.privilege
      FROM entity_grant g
      JOIN role_privilege rp ON rp.role_name = g.role
     WHERE g.entity_id = %s
       AND g.principal_id = %s
       AND g.granted_at <= %s
       AND (g.lapses_at IS NULL OR g.lapses_at > %s)
       AND (g.revoked_at IS NULL OR g.revoked_at > %s)
"""


def privileges_in_force(
    conn: psycopg.Connection[Any], entity_id: str, principal_id: str, at: datetime
) -> frozenset[str]:
    """Every privilege this principal holds in this entity at `at`, across all its roles.

    An empty set is the ordinary answer for a principal with no access, and `IAM-01` makes it
    mean "can do nothing with it" rather than "can do the default".
    """
    with conn.cursor() as cur:
        cur.execute(IN_FORCE, (entity_id, principal_id, at, at, at))
        return frozenset(str(row[0]) for row in cur.fetchall())


def entities_held(
    conn: psycopg.Connection[Any], principal_id: str, at: datetime
) -> frozenset[str]:
    """Every entity in which this principal holds a grant in force at `at`.

    Read under the principal's own scope (migration 0019): the transaction declares the
    principal, which row-level security lets see its own grants and no one else's, then clears
    the declaration so nothing later in the transaction reads with it. Never scoped to an
    entity, and never needs to be — what it returns is where the principal may then ask, one
    entity at a time, under that entity's scope.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT set_config('cfokit.principal_id', %s, true)", (principal_id,))
        cur.execute(
            "SELECT DISTINCT g.entity_id"
            "  FROM entity_grant g"
            " WHERE g.principal_id = %s"
            "   AND g.granted_at <= %s"
            "   AND (g.lapses_at IS NULL OR g.lapses_at > %s)"
            "   AND (g.revoked_at IS NULL OR g.revoked_at > %s)",
            (principal_id, at, at, at),
        )
        held = frozenset(str(row[0]) for row in cur.fetchall())
        cur.execute("SELECT set_config('cfokit.principal_id', '', true)")
    return held


def holders_of(
    conn: psycopg.Connection[Any], entity_id: str, privilege: str, at: datetime
) -> tuple[str, ...]:
    """Every principal holding `privilege` in this entity at `at`, in a stable order.

    Who a question goes to is who could answer it. The same three conditions as
    `privileges_in_force`, so a lapsed or revoked grant reaches nobody (`IAM-09`, `IAM-15`).
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT g.principal_id"
            "  FROM entity_grant g"
            "  JOIN role_privilege rp ON rp.role_name = g.role"
            " WHERE g.entity_id = %s"
            "   AND rp.privilege = %s"
            "   AND g.granted_at <= %s"
            "   AND (g.lapses_at IS NULL OR g.lapses_at > %s)"
            "   AND (g.revoked_at IS NULL OR g.revoked_at > %s)"
            " ORDER BY g.principal_id",
            (entity_id, privilege, at, at, at),
        )
        return tuple(str(row[0]) for row in cur.fetchall())


@dataclass(frozen=True, slots=True)
class RoleDefinition:
    """A row of the catalog: what a role carries, and whether it may be time-bounded."""

    name: str
    privileges: frozenset[str]
    never_lapses: bool


def role_definition(conn: psycopg.Connection[Any], name: str) -> RoleDefinition | None:
    """The catalog entry for a role, or None if this deployment defines no such role.

    A role with no privileges is a legitimate answer and is not None: it confers nothing, which
    is different from not existing.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT r.never_lapses, rp.privilege"
            "  FROM role r LEFT JOIN role_privilege rp ON rp.role_name = r.name"
            " WHERE r.name = %s",
            (name,),
        )
        rows = cur.fetchall()
    if not rows:
        return None
    return RoleDefinition(
        name=name,
        privileges=frozenset(str(row[1]) for row in rows if row[1] is not None),
        never_lapses=bool(rows[0][0]),
    )
