"""Obligations and the settlements applied to them. Hand-written SQL (ADR-0028).

Outstanding is derived — the obligation's amount less what has been applied — for the same
reason balances are (ADR-0003, ADR-0006). A stored outstanding figure would be a second place
the truth lives, and the two would disagree the first time a settlement was recorded and the
update missed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import psycopg

__all__ = [
    "Obligation",
    "Settlement",
    "insert_obligation",
    "insert_settlement",
    "obligations_as_of",
    "outstanding",
    "settlements_for",
]


@dataclass(frozen=True, slots=True)
class Obligation:
    """A commitment to receive or pay, recorded when it arises (`LED-17`).

    `account_id` is the account that carries it, and `amount` is signed as its posting there: a
    receivable is a debit, so positive; a payable a credit, so negative (ADR-0059 § 3). A
    settlement is signed as the obligation it settles.
    """

    obligation_id: str
    transaction_id: str
    transaction_date: date
    account_id: str
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
    account_id: str,
    amount: Decimal,
    commodity: str,
) -> str:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO obligation (entity_id, transaction_id, account_id, amount, commodity)"
            " VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (entity_id, transaction_id, account_id, amount, commodity),
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


# Ordering is total: date, then when the row was written, then its id. Two obligations dated
# the same day resolve by the second, and a uuid tiebreak alone is not an order at all — it is
# whatever the database happened to return. `RPT-09` needs the same answer every time.
OUTSTANDING = """
    SELECT o.id, o.transaction_id, t.transaction_date, o.account_id, o.amount, o.commodity,
           COALESCE(SUM(s.amount), 0)
      FROM obligation o
      JOIN ledger_transaction t ON t.id = o.transaction_id
      LEFT JOIN settlement s ON s.obligation_id = o.id
     WHERE o.entity_id = %(entity_id)s
       AND (%(obligation_id)s::uuid IS NULL OR o.id = %(obligation_id)s)
       AND (%(as_of)s::date IS NULL OR t.transaction_date <= %(as_of)s)
     GROUP BY o.id, o.transaction_id, t.transaction_date, o.account_id, o.amount, o.commodity
     ORDER BY t.transaction_date, o.created_at, o.id
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
                account_id=str(row[3]),
                amount=Decimal(row[4]),
                commodity=str(row[5]),
                settled=Decimal(row[6]),
            )
            for row in cur.fetchall()
        ]
    if unsettled_only:
        return [o for o in found if o.outstanding != 0]
    return found


# The books as they stood at a moment (ADR-0013): an obligation recorded before it, less what
# settlements recorded before it applied. `excluding` leaves out what one transaction settled,
# so a reader rebuilding the moment just before that transaction wrote can do so even though
# its rows carry its database transaction's start time.
OBLIGATIONS_AS_OF = """
    SELECT o.id, o.transaction_id, t.transaction_date, o.account_id, o.amount, o.commodity,
           COALESCE((SELECT SUM(s.amount) FROM settlement s
                      WHERE s.obligation_id = o.id AND s.created_at < %(at)s
                        AND s.transaction_id IS DISTINCT FROM %(excluding)s::uuid), 0)
      FROM obligation o
      JOIN ledger_transaction t ON t.id = o.transaction_id
     WHERE o.entity_id = %(entity_id)s
       AND o.created_at < %(at)s
       AND (%(obligation_id)s::uuid IS NULL OR o.id = %(obligation_id)s::uuid)
     ORDER BY t.transaction_date, o.created_at, o.id
"""


def obligations_as_of(
    conn: psycopg.Connection[Any],
    *,
    entity_id: str,
    at: datetime,
    excluding_transaction: str | None = None,
    obligation_id: str | None = None,
) -> list[Obligation]:
    """Every obligation recorded before `at`, with what had been applied to it by then.

    A reconstruction rather than a lookup, because both tables are append-only and timestamped
    (ADR-0007, ADR-0013). Settled ones are included: whether one still counts is the caller's
    question to ask of the figure.
    """
    with conn.cursor() as cur:
        cur.execute(
            OBLIGATIONS_AS_OF,
            {
                "entity_id": entity_id,
                "at": at,
                "excluding": excluding_transaction,
                "obligation_id": obligation_id,
            },
        )
        return [
            Obligation(
                obligation_id=str(row[0]),
                transaction_id=str(row[1]),
                transaction_date=row[2],
                account_id=str(row[3]),
                amount=Decimal(row[4]),
                commodity=str(row[5]),
                settled=Decimal(row[6]),
            )
            for row in cur.fetchall()
        ]


def settlements_for(
    conn: psycopg.Connection[Any], *, entity_id: str, obligation_id: str
) -> list[Settlement]:
    """Every payment applied to one obligation, oldest first (`AR-12`).

    Ordered by date, then by when the row was written: two payments applied on the same day
    resolve by the order they were recorded rather than by a random uuid.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT s.id, s.obligation_id, s.transaction_id, t.transaction_date,"
            "       s.amount, s.commodity"
            "  FROM settlement s"
            "  JOIN ledger_transaction t ON t.id = s.transaction_id"
            " WHERE s.entity_id = %s AND s.obligation_id = %s"
            " ORDER BY t.transaction_date, s.created_at, s.id",
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
