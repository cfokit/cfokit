"""The audit trail. Exactly one row per state-changing service call (ADR-0011).

`audit_log` is insert-only: the trigger refuses `UPDATE` and `DELETE`, and the application
role does not hold either privilege. There is deliberately no update or delete function here.

**Identifiers and counts only.** Never posting amounts, account numbers or payee names
(CLAUDE.md, Observability). `detail` is `jsonb` and it is easy to put the whole request in
it; that is the mistake this docstring exists to prevent.
"""

from __future__ import annotations

from typing import Any

import psycopg
from psycopg.types.json import Jsonb

__all__ = ["record"]


def record(
    conn: psycopg.Connection[Any],
    *,
    entity_id: str | None,
    request_id: str,
    actor: str,
    action: str,
    subject_type: str,
    subject_id: str | None,
    detail: dict[str, Any] | None = None,
) -> None:
    """Write the one audit row for a state change.

    `request_id` is the inbound request's id, propagated so a row in the trail can be joined
    to the call that produced it (CLAUDE.md, Observability).

    `entity_id` is nullable because a deployment-scoped act — the bootstrap, or creating an
    entity — happens before there is an entity to attribute it to. The column has always
    allowed it; this annotation lagged the schema.
    """
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO audit_log"
            " (entity_id, request_id, actor, action, subject_type, subject_id, detail)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (
                entity_id,
                request_id,
                actor,
                action,
                subject_type,
                subject_id,
                Jsonb(detail) if detail is not None else None,
            ),
        )
