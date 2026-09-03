"""Reading balances for a report. Hand-written SQL (ADR-0028).

Balances are `SUM()` over postings and never stored (ADR-0003, ADR-0006). Every figure here is
exact: `NUMERIC(28,10)` in, `Decimal` out, and no rounding anywhere in this layer (ADR-0025).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import psycopg

__all__ = ["AccountBalance", "trial_balance"]


@dataclass(frozen=True, slots=True)
class AccountBalance:
    """One account's balance, signed. Positive is a debit."""

    account_id: str
    code: str
    name: str
    account_type: str
    commodity: str
    balance: Decimal


TRIAL_BALANCE = """
    SELECT a.id, a.code, a.name, a.type, p.commodity, SUM(p.amount)
      FROM posting p
      JOIN account a ON a.id = p.account_id
      JOIN ledger_transaction t ON t.id = p.transaction_id
     WHERE p.entity_id = %(entity_id)s
       AND t.status = 'posted'
       AND t.transaction_date <= %(as_of)s
       AND (%(watermark)s::timestamptz IS NULL OR t.posted_at <= %(watermark)s)
     GROUP BY a.id, a.code, a.name, a.type, p.commodity
    HAVING SUM(p.amount) <> 0
     ORDER BY a.code, p.commodity
"""


def trial_balance(
    conn: psycopg.Connection[Any],
    *,
    entity_id: str,
    as_of: date,
    watermark: datetime | None,
) -> list[AccountBalance]:
    """Every account with a non-zero balance as of `as_of`.

    `watermark` is `RPT-11`: the books as they stood at an earlier moment. It filters on
    `posted_at` rather than `recorded_at`, because what a lender saw in March is what was
    *posted* by March — a draft recorded in February and posted in April was not in that
    statement, though its record predates it.

    Posted only, because a draft is not in the books (`LED-07`). Accounts at exactly zero are
    omitted: a trial balance lists what has a balance, and a zero line is noise a reader has to
    scan past.
    """
    with conn.cursor() as cur:
        cur.execute(
            TRIAL_BALANCE, {"entity_id": entity_id, "as_of": as_of, "watermark": watermark}
        )
        return [
            AccountBalance(
                account_id=str(row[0]),
                code=str(row[1]),
                name=str(row[2]),
                account_type=str(row[3]),
                commodity=str(row[4]),
                balance=Decimal(row[5]),
            )
            for row in cur.fetchall()
        ]
