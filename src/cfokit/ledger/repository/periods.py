"""Reading and writing period closes. Hand-written SQL (ADR-0028).

A close is a row and a reopen is an update to it, so "is this period closed" is one lookup for
a row in force, and `SOC1-17`'s history is every row ever written for that period.
"""

from __future__ import annotations

from typing import Any

import psycopg

from cfokit.ledger.engine.periods import Period

__all__ = ["close_in_force", "insert_close", "reopen"]


def close_in_force(
    conn: psycopg.Connection[Any], *, entity_id: str, period: Period
) -> str | None:
    """The id of the close in force for this period, or None if it is open.

    Read inside the transaction that will do the work, so a close committed a moment ago is
    already in force and two concurrent writes cannot disagree about it (ADR-0011).
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM period_close"
            " WHERE entity_id = %s AND period_year = %s AND period_month = %s"
            "   AND reopened_at IS NULL",
            (entity_id, period.year, period.month),
        )
        row = cur.fetchone()
    return str(row[0]) if row is not None else None


def insert_close(
    conn: psycopg.Connection[Any], *, entity_id: str, period: Period, closed_by: str
) -> str:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO period_close (entity_id, period_year, period_month, closed_by)"
            " VALUES (%s, %s, %s, %s) RETURNING id",
            (entity_id, period.year, period.month, closed_by),
        )
        row = cur.fetchone()
    if row is None:  # pragma: no cover
        raise RuntimeError("insert returned no id")
    return str(row[0])


def reopen(
    conn: psycopg.Connection[Any], *, close_id: str, reopened_by: str, reason: str
) -> bool:
    """Reopen a close. False if it was already reopened.

    An `UPDATE` rather than a delete, and the only one the append-only trigger permits on this
    table: the row stays so the history can still say the period was closed and by whom.
    """
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE period_close"
            "   SET reopened_at = now(), reopened_by = %s, reopen_reason = %s"
            " WHERE id = %s AND reopened_at IS NULL",
            (reopened_by, reason, close_id),
        )
        return cur.rowcount == 1
