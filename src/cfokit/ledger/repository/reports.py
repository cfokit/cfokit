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

__all__ = [
    "Account",
    "AccountBalance",
    "AccountEntry",
    "ExportedPosting",
    "account",
    "account_balances",
    "account_detail",
    "chart",
    "exportable_postings",
]


@dataclass(frozen=True, slots=True)
class AccountBalance:
    """One account's balance, signed. Positive is a debit."""

    account_id: str
    code: str
    name: str
    account_type: str
    commodity: str
    balance: Decimal


BALANCES = """
    SELECT a.id, a.code, a.name, a.type, p.commodity, SUM(p.amount)
      FROM posting p
      JOIN account a ON a.id = p.account_id
      JOIN ledger_transaction t ON t.id = p.transaction_id
     WHERE p.entity_id = %(entity_id)s
       AND t.status = 'posted'
       AND t.transaction_date <= %(as_of)s
       AND (%(since)s::date IS NULL OR t.transaction_date >= %(since)s)
       AND (%(types)s::text[] IS NULL OR a.type = ANY(%(types)s))
       AND (%(watermark)s::timestamptz IS NULL OR t.posted_at <= %(watermark)s)
     GROUP BY a.id, a.code, a.name, a.type, p.commodity
    HAVING SUM(p.amount) <> 0
     ORDER BY a.code, p.commodity
"""


def account_balances(
    conn: psycopg.Connection[Any],
    *,
    entity_id: str,
    as_of: date,
    since: date | None = None,
    types: tuple[str, ...] | None = None,
    watermark: datetime | None = None,
) -> list[AccountBalance]:
    """Every account with a non-zero balance, filtered to a window and a set of types.

    One query for every statement, because they differ only in those two filters. A balance
    sheet is cumulative and takes no `since`; a profit and loss is a period and takes one; a
    trial balance takes neither filter. Three reports over one query cannot disagree about what
    a balance is, which is what `RPT-09` asks for.

    `watermark` is `RPT-11`: the books as they stood at an earlier moment. It filters on
    `posted_at` rather than `recorded_at`, because what a lender saw in March is what was
    *posted* by March — a draft recorded in February and posted in April was not in that
    statement, though its record predates it.

    Posted only, because a draft is not in the books (`LED-07`). Accounts at exactly zero are
    omitted: a statement lists what has a balance, and a zero line is noise a reader scans past.
    """
    with conn.cursor() as cur:
        cur.execute(
            BALANCES,
            {
                "entity_id": entity_id,
                "as_of": as_of,
                "since": since,
                "types": list(types) if types is not None else None,
                "watermark": watermark,
            },
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


@dataclass(frozen=True, slots=True)
class Account:
    """An account's identity, for a report that is about one of them."""

    account_id: str
    code: str
    name: str
    account_type: str
    # Codes are what two systems agree on; ids are ours alone (`IMP-08`). Only the chart
    # populates this, because only an export needs the hierarchy.
    parent_code: str | None = None


def account(
    conn: psycopg.Connection[Any], *, entity_id: str, account_id: str
) -> Account | None:
    """One account in this entity, or None. Row-level security scopes it (ADR-0003)."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, code, name, type FROM account WHERE entity_id = %s AND id = %s",
            (entity_id, account_id),
        )
        row = cur.fetchone()
    if row is None:
        return None
    return Account(
        account_id=str(row[0]), code=str(row[1]), name=str(row[2]), account_type=str(row[3])
    )


@dataclass(frozen=True, slots=True)
class AccountEntry:
    """One posting against an account, with the balance after it."""

    transaction_id: str
    transaction_date: date
    description: str | None
    entry_kind: str
    reverses_id: str | None
    actor_principal_id: str
    actor_class: str
    acting_for_principal_id: str | None
    amount: Decimal
    commodity: str
    running_balance: Decimal


OPENING_BALANCE = """
    SELECT COALESCE(SUM(p.amount), 0)
      FROM posting p
      JOIN ledger_transaction t ON t.id = p.transaction_id
     WHERE p.entity_id = %(entity_id)s
       AND p.account_id = %(account_id)s
       AND t.status = 'posted'
       AND t.transaction_date < %(since)s
       AND (%(watermark)s::timestamptz IS NULL OR t.posted_at <= %(watermark)s)
"""

# The running balance starts from what stood before the period and accumulates in the same
# order the rows are read. Ordering by (date, posted_at, posting id) is total: two postings on
# one day resolve by when they entered the books, and two in one transaction by a unique id.
# `RPT-09` needs the report to be the same every time it is asked for, and an order that can
# tie is an order the database may return differently on a different day.
ACCOUNT_DETAIL = """
    SELECT t.id, t.transaction_date, t.description, t.entry_kind, t.reverses_id,
           t.actor_principal_id, t.actor_class, t.acting_for_principal_id,
           p.amount, p.commodity,
           %(opening)s + SUM(p.amount) OVER (
               ORDER BY t.transaction_date, t.posted_at, p.id
               ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
           )
      FROM posting p
      JOIN ledger_transaction t ON t.id = p.transaction_id
     WHERE p.entity_id = %(entity_id)s
       AND p.account_id = %(account_id)s
       AND t.status = 'posted'
       AND t.transaction_date >= %(since)s
       AND t.transaction_date <= %(as_of)s
       AND (%(watermark)s::timestamptz IS NULL OR t.posted_at <= %(watermark)s)
     ORDER BY t.transaction_date, t.posted_at, p.id
"""


def account_detail(
    conn: psycopg.Connection[Any],
    *,
    entity_id: str,
    account_id: str,
    since: date,
    as_of: date,
    watermark: datetime | None = None,
) -> tuple[Decimal, list[AccountEntry]]:
    """Every posting against one account in a period, and the balance it opened with.

    `RPT-05`: "every transaction against it, in order, with a running balance". The opening
    balance is what makes the running one true — a March statement that started from zero would
    show the right movements against the wrong figures.
    """
    parameters: dict[str, Any] = {
        "entity_id": entity_id,
        "account_id": account_id,
        "since": since,
        "as_of": as_of,
        "watermark": watermark,
    }
    with conn.cursor() as cur:
        cur.execute(OPENING_BALANCE, parameters)
        row = cur.fetchone()
        opening = Decimal(row[0]) if row is not None else Decimal(0)

        cur.execute(ACCOUNT_DETAIL, {**parameters, "opening": opening})
        entries = [
            AccountEntry(
                transaction_id=str(entry[0]),
                transaction_date=entry[1],
                description=entry[2],
                entry_kind=str(entry[3]),
                reverses_id=str(entry[4]) if entry[4] is not None else None,
                actor_principal_id=str(entry[5]),
                actor_class=str(entry[6]),
                acting_for_principal_id=str(entry[7]) if entry[7] is not None else None,
                amount=Decimal(entry[8]),
                commodity=str(entry[9]),
                running_balance=Decimal(entry[10]),
            )
            for entry in cur.fetchall()
        ]
    return opening, entries


@dataclass(frozen=True, slots=True)
class ExportedPosting:
    """One posting as an interchange archive carries it (`EXP-01`)."""

    transaction_id: str
    transaction_date: date
    description: str | None
    account_code: str
    amount: Decimal
    commodity: str


def chart(conn: psycopg.Connection[Any], *, entity_id: str) -> list[Account]:
    """Every account in this entity, parents before children, in code order.

    Ordered so a receiving system can create them in the order read: a child naming a parent
    that does not exist yet is a needless failure to hand somebody.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, code, name, type, parent_id FROM account"
            " WHERE entity_id = %s ORDER BY parent_id NULLS FIRST, code",
            (entity_id,),
        )
        rows = cur.fetchall()
    codes = {str(row[0]): str(row[1]) for row in rows}
    return [
        Account(
            account_id=str(row[0]),
            code=str(row[1]),
            name=str(row[2]),
            account_type=str(row[3]),
            parent_code=codes.get(str(row[4])) if row[4] is not None else None,
        )
        for row in rows
    ]


EXPORTABLE = """
    SELECT t.id, t.transaction_date, t.description, a.code, p.amount, p.commodity
      FROM posting p
      JOIN account a ON a.id = p.account_id
      JOIN ledger_transaction t ON t.id = p.transaction_id
     WHERE p.entity_id = %(entity_id)s
       AND t.status = 'posted'
       AND t.transaction_date <= %(as_of)s
       AND (%(watermark)s::timestamptz IS NULL OR t.posted_at <= %(watermark)s)
     ORDER BY t.transaction_date, t.posted_at, p.id
"""


def exportable_postings(
    conn: psycopg.Connection[Any],
    *,
    entity_id: str,
    as_of: date,
    watermark: datetime | None = None,
) -> list[ExportedPosting]:
    """Every posted posting up to `as_of`, in a total order.

    Ordered by date, then when the transaction entered the books, then the posting id — the
    same order account detail uses, so two exports of unchanged books are byte-identical and a
    diff between two exports shows only what actually changed.
    """
    with conn.cursor() as cur:
        cur.execute(
            EXPORTABLE, {"entity_id": entity_id, "as_of": as_of, "watermark": watermark}
        )
        return [
            ExportedPosting(
                transaction_id=str(row[0]),
                transaction_date=row[1],
                description=row[2],
                account_code=str(row[3]),
                amount=Decimal(row[4]),
                commodity=str(row[5]),
            )
            for row in cur.fetchall()
        ]
