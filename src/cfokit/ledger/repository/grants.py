"""Reading grants. Hand-written SQL (ADR-0028).

A grant is in force at a moment when it was granted before it, has not lapsed (`IAM-09`), and
has not been revoked (`IAM-15`). All three are columns rather than a computed status, so the
same query answers "what is in force now" and `IAM-14`'s "what was in force then" by changing
one parameter.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import psycopg

__all__ = ["roles_in_force"]

IN_FORCE = """
    SELECT role
      FROM entity_grant
     WHERE entity_id = %s
       AND principal_id = %s
       AND granted_at <= %s
       AND (lapses_at IS NULL OR lapses_at > %s)
       AND (revoked_at IS NULL OR revoked_at > %s)
"""


def roles_in_force(
    conn: psycopg.Connection[Any], entity_id: str, principal_id: str, at: datetime
) -> frozenset[str]:
    """Every role this principal holds in this entity at `at`.

    An empty set is the ordinary answer for a principal with no access, and `IAM-01` makes it
    mean "can do nothing with it" rather than "can do the default".
    """
    with conn.cursor() as cur:
        cur.execute(IN_FORCE, (entity_id, principal_id, at, at, at))
        return frozenset(str(row[0]) for row in cur.fetchall())
