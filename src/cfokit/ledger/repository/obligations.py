"""Obligations and the settlements applied to them. Hand-written SQL (ADR-0028).

Outstanding is derived — the obligation's amount less what has been applied — for the same
reason balances are (ADR-0003, ADR-0006). A stored outstanding figure would be a second place
the truth lives, and the two would disagree the first time a settlement was recorded and the
update missed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

import psycopg

__all__ = [
    "Obligation",
    "Settlement",
    "insert_obligation",
    "insert_settlement",
    "outstanding",
    "settlements_for",
]


@dataclass(frozen=True, slots=True)
class Obligation:
    """A commitment to receive or pay, recorded when it arises (`LED-17`)."""

    obligation_id: str
    transaction_id: str
    transaction_date: date
    amount: Decimal
    commodity: str
    settled: Decimal

    @property
    def outstanding(self) -> Decimal:
        return self.amount - self.settled


@dataclass(frozen=True, slots=True)
class Settlement:
    """One application of a payment to an obligation (`AR-12`)."""

    settlement_id: str
    obligation_id: str
    transaction_id: str
    transaction_date: date
    amount: Decimal
    commodity: str


def insert_obligation(
    conn: psycopg.Connection[Any],
    *,
    entity_id: str,
    transaction_id: str,
    amount: Decimal,
    commodity: str,
) -> str:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO obligation (entity_id, transaction_id, amount, commodity)"
            " VALUES (%s, %s, %s, %s) RETURNING id",
            (entity_id, transaction_id, amount, commodity),
        )
        row = cur.fetchone()
    if row is None:  # pragma: no cover
        raise RuntimeError("insert returned no id")
    return str(row[0])


def insert_settlement(
    conn: psycopg.Connection[Any],
    *,
    entity_id: str,
    obligation_id: str,
    transaction_id: str,
    amount: Decimal,
    commodity: str,
) -> str:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO settlement"
            " (entity_id, obligation_id, transaction_id, amount, commodity)"
            " VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (entity_id, obligation_id, transaction_id, amount, commodity),
        )
        row = cur.fetchone()
    if row is None:  # pragma: no cover
        raise RuntimeError("insert returned no id")
    return str(row[0])


OUTSTANDING = """
    SELECT o.id, o.transaction_id, t.transaction_date, o.amount, o.commodity,
           COALESCE(SUM(s.amount), 0)
      FROM obligation o
      JOIN ledger_transaction t ON t.id = o.transaction_id
      LEFT JOIN settlement s ON s.obligation_id = o.id
     WHERE o.entity_id = %(entity_id)s
       AND (%(obligation_id)s::uuid IS NULL OR o.id = %(obligation_id)s)
       AND (%(as_of)s::date IS NULL OR t.transaction_date <= %(as_of)s)
     GROUP BY o.id, o.transaction_id, t.transaction_date, o.amount, o.commodity
     ORDER BY t.transaction_date, o.id
"""


def outstanding(
    conn: psycopg.Connection[Any],
    *,
    entity_id: str,
    obligation_id: str | None = None,
    as_of: date | None = None,
    unsettled_only: bool = False,
) -> list[Obligation]:
    """Obligations and how much has been applied to each.

    Includes obligations raised by an unposted transaction only if there are none: a draft
    invoice is not in the books (`LED-07`), and the write path refuses to raise an obligation
    against one, so the join cannot see one.
    """
    with conn.cursor() as cur:
        cur.execute(
            OUTSTANDING,
            {"entity_id": entity_id, "obligation_id": obligation_id, "as_of": as_of},
        )
        found = [
            Obligation(
                obligation_id=str(row[0]),
                transaction_id=str(row[1]),
                transaction_date=row[2],
                amount=Decimal(row[3]),
                commodity=str(row[4]),
                settled=Decimal(row[5]),
            )
            for row in cur.fetchall()
        ]
    if unsettled_only:
        return [o for o in found if o.outstanding != 0]
    return found


def settlements_for(
    conn: psycopg.Connection[Any], *, entity_id: str, obligation_id: str
) -> list[Settlement]:
    """Every payment applied to one obligation, oldest first (`AR-12`)."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT s.id, s.obligation_id, s.transaction_id, t.transaction_date,"
            "       s.amount, s.commodity"
            "  FROM settlement s"
            "  JOIN ledger_transaction t ON t.id = s.transaction_id"
            " WHERE s.entity_id = %s AND s.obligation_id = %s"
            " ORDER BY t.transaction_date, s.id",
            (entity_id, obligation_id),
        )
        return [
            Settlement(
                settlement_id=str(row[0]),
                obligation_id=str(row[1]),
                transaction_id=str(row[2]),
                transaction_date=row[3],
                amount=Decimal(row[4]),
                commodity=str(row[5]),
            )
            for row in cur.fetchall()
        ]
