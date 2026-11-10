"""What a cash-basis report reads beside the postings (ADR-0080 § 4). Hand-written SQL.

The links an obligation and its settlements store, and the reversals of the transactions they
name, shaped for the engine's derivation. Nothing here derives anything: which figures change,
and by how much, is `cfokit.ledger.engine.cash`.

**Every read honors the watermark** (`RPT-11`), on the transaction and on the link alike, so a
cash-basis report reproduced as the books stood at a moment is derived from the links that
existed then.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import psycopg

from cfokit.ledger.engine import Line, Raised, Reversal, Settled

__all__ = ["Header", "Links", "Unlinked", "headers", "links", "unlinked"]


@dataclass(frozen=True, slots=True)
class Links:
    """Every obligation, settlement and reversal the derivation needs, in recognition order."""

    raised: tuple[Raised, ...]
    settled: tuple[Settled, ...]
    reversals: tuple[Reversal, ...]


# A raising transaction's postings in its obligation's commodity, in the order the ledger reads
# a transaction's postings everywhere else (`repository.transactions`): when written, then id.
RAISED = """
    SELECT o.id, o.transaction_id, t.transaction_date, o.account_id, o.amount, o.commodity,
           o.on_account, p.account_id, p.amount
      FROM obligation o
      JOIN ledger_transaction t ON t.id = o.transaction_id
      JOIN posting p ON p.transaction_id = o.transaction_id AND p.commodity = o.commodity
     WHERE o.entity_id = %(entity_id)s
       AND t.status = 'posted'
       AND (%(watermark)s::timestamptz IS NULL
            OR (t.posted_at <= %(watermark)s AND o.created_at <= %(watermark)s))
     ORDER BY t.transaction_date, t.posted_at, o.id, p.created_at, p.id
"""

# The order cumulative shares accrue in: when the money moved, then when it entered the books.
SETTLED = """
    SELECT s.obligation_id, s.transaction_id, t.transaction_date, s.amount
      FROM settlement s
      JOIN ledger_transaction t ON t.id = s.transaction_id
     WHERE s.entity_id = %(entity_id)s
       AND t.status = 'posted'
       AND (%(watermark)s::timestamptz IS NULL
            OR (t.posted_at <= %(watermark)s AND s.created_at <= %(watermark)s))
     ORDER BY t.transaction_date, t.posted_at, s.created_at, s.id
"""

# Every posted reversal, oldest first, so a reversal of a reversal finds what it negates. The
# engine ignores those that reverse nothing a link reaches.
REVERSALS = """
    SELECT t.id, t.transaction_date, t.reverses_id
      FROM ledger_transaction t
     WHERE t.entity_id = %(entity_id)s
       AND t.status = 'posted'
       AND t.reverses_id IS NOT NULL
       AND (%(watermark)s::timestamptz IS NULL OR t.posted_at <= %(watermark)s)
     ORDER BY t.transaction_date, t.posted_at, t.id
"""


def links(
    conn: psycopg.Connection[Any], *, entity_id: str, watermark: datetime | None
) -> Links:
    """Every link in the books, whatever its date: a report filters what it presents by date,
    but a settlement's share depends on every settlement of its obligation before it."""
    parameters = {"entity_id": entity_id, "watermark": watermark}
    with conn.cursor() as cur:
        cur.execute(RAISED, parameters)
        grouped: dict[str, tuple[tuple[Any, ...], list[Line]]] = {}
        for row in cur.fetchall():
            _, lines = grouped.setdefault(str(row[0]), (row, []))
            lines.append(Line(account_id=str(row[7]), amount=Decimal(row[8])))

        cur.execute(SETTLED, parameters)
        settled = tuple(
            Settled(
                obligation_id=str(row[0]),
                transaction_id=str(row[1]),
                transaction_date=row[2],
                amount=Decimal(row[3]),
            )
            for row in cur.fetchall()
        )

        cur.execute(REVERSALS, parameters)
        reversals = tuple(
            Reversal(
                transaction_id=str(row[0]), transaction_date=row[1], reverses_id=str(row[2])
            )
            for row in cur.fetchall()
        )

    raised = tuple(
        Raised(
            obligation_id=obligation_id,
            transaction_id=str(row[1]),
            transaction_date=row[2],
            account_id=str(row[3]),
            amount=Decimal(row[4]),
            commodity=str(row[5]),
            lines=tuple(lines),
            on_account=bool(row[6]),
        )
        for obligation_id, (row, lines) in grouped.items()
    )
    return Links(raised=raised, settled=settled, reversals=reversals)


@dataclass(frozen=True, slots=True)
class Unlinked:
    """What a cash-basis report presents as posted because no link reaches it (ADR-0080 § 3).

    Stated on the report's face (`NFR-16`): a cash figure resting on an accrual posting is
    disclosed rather than hidden.
    """

    # Postings on an account that carries an obligation, by a transaction that neither raises
    # nor settles one, nor reverses one that does: a journal entry to receivables, say.
    postings: int
    # Transactions an import landed. No import records payment links yet, so their history
    # reads as posted.
    imported_transactions: int


# An account carries obligations once one is recorded against it; a transaction is linked when
# it raises or settles one, or reverses a transaction that does.
UNLINKED = """
    WITH carrying AS (
        SELECT DISTINCT o.account_id
          FROM obligation o
         WHERE o.entity_id = %(entity_id)s
           AND (%(watermark)s::timestamptz IS NULL OR o.created_at <= %(watermark)s)
    ),
    linked AS (
        SELECT transaction_id FROM obligation WHERE entity_id = %(entity_id)s
        UNION
        SELECT transaction_id FROM settlement WHERE entity_id = %(entity_id)s
    )
    SELECT COUNT(*)
      FROM posting p
      JOIN ledger_transaction t ON t.id = p.transaction_id
     WHERE p.entity_id = %(entity_id)s
       AND p.account_id IN (SELECT account_id FROM carrying)
       AND t.status = 'posted'
       AND t.transaction_date <= %(as_of)s
       AND (%(since)s::date IS NULL OR t.transaction_date >= %(since)s)
       AND (%(watermark)s::timestamptz IS NULL OR t.posted_at <= %(watermark)s)
       AND t.id NOT IN (SELECT transaction_id FROM linked)
       AND (t.reverses_id IS NULL OR t.reverses_id NOT IN (SELECT transaction_id FROM linked))
"""

# `derived_from.import_id` is how an imported transaction names its import (`IMP-04`).
IMPORTED = """
    SELECT COUNT(*)
      FROM ledger_transaction t
     WHERE t.entity_id = %(entity_id)s
       AND t.status = 'posted'
       AND t.derived_from ? 'import_id'
       AND t.transaction_date <= %(as_of)s
       AND (%(since)s::date IS NULL OR t.transaction_date >= %(since)s)
       AND (%(watermark)s::timestamptz IS NULL OR t.posted_at <= %(watermark)s)
"""


def unlinked(
    conn: psycopg.Connection[Any],
    *,
    entity_id: str,
    as_of: date,
    since: date | None,
    watermark: datetime | None,
) -> Unlinked:
    """The counts for a report spanning `since`..`as_of`, or everything to `as_of`."""
    parameters = {
        "entity_id": entity_id,
        "as_of": as_of,
        "since": since,
        "watermark": watermark,
    }
    with conn.cursor() as cur:
        cur.execute(UNLINKED, parameters)
        postings = cur.fetchone()
        cur.execute(IMPORTED, parameters)
        imported = cur.fetchone()
    return Unlinked(
        postings=int(postings[0]) if postings is not None else 0,
        imported_transactions=int(imported[0]) if imported is not None else 0,
    )


@dataclass(frozen=True, slots=True)
class Header:
    """A transaction's own fields, for a movement account detail shows (`RPT-05`)."""

    transaction_id: str
    transaction_date: date
    posted_at: datetime
    description: str | None
    entry_kind: str
    reverses_id: str | None
    actor_principal_id: str
    actor_class: str
    acting_for_principal_id: str | None


HEADERS = """
    SELECT t.id, t.transaction_date, t.posted_at, t.description, t.entry_kind, t.reverses_id,
           t.actor_principal_id, t.actor_class, t.acting_for_principal_id
      FROM ledger_transaction t
     WHERE t.entity_id = %(entity_id)s
       AND t.id = ANY(%(ids)s::uuid[])
       AND t.status = 'posted'
"""


def headers(
    conn: psycopg.Connection[Any], *, entity_id: str, transaction_ids: list[str]
) -> dict[str, Header]:
    """The posted transactions among `transaction_ids`, by id."""
    if not transaction_ids:
        return {}
    with conn.cursor() as cur:
        cur.execute(HEADERS, {"entity_id": entity_id, "ids": transaction_ids})
        rows = cur.fetchall()
    return {
        str(row[0]): Header(
            transaction_id=str(row[0]),
            transaction_date=row[1],
            posted_at=row[2],
            description=row[3],
            entry_kind=str(row[4]),
            reverses_id=str(row[5]) if row[5] is not None else None,
            actor_principal_id=str(row[6]),
            actor_class=str(row[7]),
            acting_for_principal_id=str(row[8]) if row[8] is not None else None,
        )
        for row in rows
    }
