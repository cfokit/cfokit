"""Recording that a statement was issued, and detecting when it stops being true.

Hand-written SQL (ADR-0028). Supersession is a query over `posted_at`, exactly as a stale
year-end close is (ADR-0027): nothing sets a flag, so nothing can fail to.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import psycopg

__all__ = ["IssuedStatement", "insert_issued", "issued_statements", "postings_after"]


@dataclass(frozen=True, slots=True)
class IssuedStatement:
    """A statement that was given to somebody, and what it was produced from."""

    issuance_id: str
    report: str
    since: date | None
    as_of: date
    watermark: datetime
    issued_by: str
    issued_at: datetime
    issued_to: str
    figures: dict[str, Any]


def insert_issued(
    conn: psycopg.Connection[Any],
    *,
    entity_id: str,
    report: str,
    since: date | None,
    as_of: date,
    watermark: datetime,
    issued_by: str,
    issued_to: str,
    figures: str,
) -> str:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO issued_statement"
            " (entity_id, report, since, as_of, watermark, issued_by, issued_to, figures)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (entity_id, report, since, as_of, watermark, issued_by, issued_to, figures),
        )
        row = cur.fetchone()
    if row is None:  # pragma: no cover
        raise RuntimeError("insert returned no id")
    return str(row[0])


def issued_statements(
    conn: psycopg.Connection[Any], *, entity_id: str, issuance_id: str | None = None
) -> list[IssuedStatement]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, report, since, as_of, watermark, issued_by, issued_at, issued_to,"
            "       figures"
            "  FROM issued_statement"
            " WHERE entity_id = %s AND (%s::uuid IS NULL OR id = %s)"
            " ORDER BY issued_at DESC, id",
            (entity_id, issuance_id, issuance_id),
        )
        return [
            IssuedStatement(
                issuance_id=str(row[0]),
                report=str(row[1]),
                since=row[2],
                as_of=row[3],
                watermark=row[4],
                issued_by=str(row[5]),
                issued_at=row[6],
                issued_to=str(row[7]),
                figures=row[8],
            )
            for row in cur.fetchall()
        ]


def postings_after(
    conn: psycopg.Connection[Any],
    *,
    entity_id: str,
    watermark: datetime,
    since: date | None,
    as_of: date,
) -> int:
    """How many postings entered this statement's window after it was produced.

    Non-zero means `SOC1-20`'s condition is met: a correction posted after the statement was
    issued changes its figures. A posting dated outside the window changes nothing the
    statement said, which is why the window bounds the query rather than the watermark alone.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*)
              FROM ledger_transaction t
             WHERE t.entity_id = %(entity_id)s
               AND t.status = 'posted'
               AND t.posted_at > %(watermark)s
               AND t.transaction_date <= %(as_of)s
               AND (%(since)s::date IS NULL OR t.transaction_date >= %(since)s)
            """,
            {"entity_id": entity_id, "watermark": watermark, "since": since, "as_of": as_of},
        )
        row = cur.fetchone()
    return int(row[0]) if row is not None else 0
