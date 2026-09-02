"""Accounts and their balances. Hand-written SQL (ADR-0028).

Balances are `SUM()` over postings and never stored. ADR-0003 chose Postgres partly for this,
and ADR-0027 depends on it: reopening a period recomputes rather than invalidating, because
there is nothing materialised to invalidate.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import psycopg

__all__ = ["income_statement_balances", "insert_account", "set_retained_earnings_account"]


def insert_account(
    conn: psycopg.Connection[Any],
    *,
    entity_id: str,
    code: str,
    name: str,
    account_type: str,
    parent_id: str | None,
) -> str:
    """Create an account. `LED-02` fixes the type at creation and never changes it."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO account (entity_id, code, name, type, parent_id)"
            " VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (entity_id, code, name, account_type, parent_id),
        )
        row = cur.fetchone()
    if row is None:  # pragma: no cover
        raise RuntimeError("insert returned no id")
    return str(row[0])


def set_retained_earnings_account(
    conn: psycopg.Connection[Any], *, entity_id: str, account_id: str
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE entity SET retained_earnings_account_id = %s WHERE id = %s",
            (account_id, entity_id),
        )


def income_statement_balances(
    conn: psycopg.Connection[Any], *, entity_id: str, start: date, end: date
) -> list[tuple[str, Decimal, str]]:
    """Income and expense balances for the fiscal year, as (account_id, balance, commodity).

    Posted transactions only — a draft is not in the books (`LED-07`) — and everything dated in
    the year, closing entries included. Including them is what makes a re-run self-correcting:
    a stale close and its reversal net to zero, leaving the original balances to close again.

    Accounts whose balance is exactly zero are omitted. There is nothing to move, and a posting
    of zero would be noise in a trail that `RPT-08` has to resolve.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT p.account_id, SUM(p.amount) AS balance, p.commodity
              FROM posting p
              JOIN account a ON a.id = p.account_id
              JOIN ledger_transaction t ON t.id = p.transaction_id
             WHERE p.entity_id = %s
               AND t.status = 'posted'
               AND t.transaction_date BETWEEN %s AND %s
               AND a.type IN ('income', 'expense')
             GROUP BY p.account_id, p.commodity
            HAVING SUM(p.amount) <> 0
             ORDER BY p.account_id
            """,
            (entity_id, start, end),
        )
        return [(str(row[0]), Decimal(row[1]), str(row[2])) for row in cur.fetchall()]
