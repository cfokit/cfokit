"""Finding a fiscal year's closing entries, and whether they are stale (ADR-0027).

**Staleness is detected, not remembered.** A closing entry moved the income and expense
balances as they stood when it ran; a posting recorded into that year afterwards means it moved
the wrong amount. `recorded_at` already carries when a transaction entered the books
(ADR-0013), so the closing entry's own `recorded_at` is the watermark and staleness is a
comparison. Nothing has to maintain a flag, and nothing can forget to.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import psycopg

__all__ = ["closing_entries", "posted_after"]


def closing_entries(
    conn: psycopg.Connection[Any], *, entity_id: str, start: date, end: date
) -> list[str]:
    """Every closing transaction dated in this fiscal year, oldest first.

    A re-run reverses the previous entries and posts new ones, both marked `closing`
    (`LED-12`), so this returns the whole chain rather than one row.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM ledger_transaction"
            " WHERE entity_id = %s AND entry_kind = 'closing' AND status = 'posted'"
            "   AND transaction_date BETWEEN %s AND %s"
            " ORDER BY recorded_at, id",
            (entity_id, start, end),
        )
        return [str(row[0]) for row in cur.fetchall()]


def posted_after(
    conn: psycopg.Connection[Any], *, entity_id: str, start: date, end: date, close_id: str
) -> int:
    """How many ordinary postings entered this year after its close was computed.

    Non-zero means the close is stale: it moved the wrong amount to retained earnings, and
    `LED-12`'s acceptance — income and expense at zero on the first day of the new year — no
    longer holds until it is re-run.

    Closing entries are excluded because they are the machinery, not activity: counting them
    would make every close instantly stale by its own reversal.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*)
              FROM ledger_transaction t
             WHERE t.entity_id = %s
               AND t.status = 'posted'
               AND t.entry_kind <> 'closing'
               AND t.transaction_date BETWEEN %s AND %s
               AND t.recorded_at > (
                     SELECT recorded_at FROM ledger_transaction WHERE id = %s
                   )
            """,
            (entity_id, start, end, close_id),
        )
        row = cur.fetchone()
    return int(row[0]) if row is not None else 0
