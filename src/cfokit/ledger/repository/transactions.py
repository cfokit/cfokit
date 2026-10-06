"""Reading and writing transactions and their postings. Hand-written SQL (ADR-0028).

Every statement here is parameterised through the driver. String interpolation into SQL is
never acceptable, and ruff's bandit rules catch it.

Nothing in this module updates a financial field on a posted row or deletes anything: the
schema refuses both (ADR-0007), and offering a function for it would be offering a way to
find out.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from cfokit.ledger.engine import Posting

__all__ = [
    "Movement",
    "StoredTransaction",
    "add_postings",
    "insert_draft",
    "load",
    "mark_posted",
    "movements_as_of",
]


@dataclass(frozen=True, slots=True)
class Movement:
    """What one transaction moved on one account: its postings there, summed."""

    transaction_id: str
    transaction_date: date
    amount: Decimal


@dataclass(frozen=True, slots=True)
class StoredTransaction:
    """A transaction as the books hold it, with the attribution that cannot be added later."""

    id: str
    status: str
    transaction_date: date
    description: str | None
    reverses_id: str | None
    entry_kind: str
    actor_principal_id: str
    actor_class: str
    acting_for_principal_id: str | None
    postings: tuple[Posting, ...]


def insert_draft(
    conn: psycopg.Connection[Any],
    *,
    entity_id: str,
    transaction_date: date,
    description: str | None,
    reverses_id: str | None,
    entry_kind: str,
    actor_principal_id: str,
    actor_class: str,
    acting_for_principal_id: str | None,
    derived_from: dict[str, Any] | None = None,
) -> str:
    """Insert a transaction as a draft and return its id.

    **Always a draft, whatever the caller intends.** Posting is a separate statement, so the
    zero-sum trigger sees a complete set of postings rather than the first one (ADR-0006), and
    so the draft-to-posted transition is the one-way move ADR-0007 requires rather than an
    initial value.

    `actor_principal_id` and `actor_class` arrive from the authenticated principal. No write
    path accepts them from a request body — the same device ADR-0013 used for `recorded_at`
    (ADR-0033 § 2). `recorded_at` itself is not settable here at all; the column defaults.

    `derived_from` is what this entry came from *outside* the books — the column migration 0001
    added for `BKP-19` and left unpopulated because "the sources are not enumerable yet". An
    import is the first source, and it names itself (`IMP-04`, `SOC1-14`). Written at insert
    and never afterwards: the entry is append-only, so lineage that arrived later could not be
    attached, and lineage that can be attached later is lineage that can be changed.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO ledger_transaction
                (entity_id, status, transaction_date, description, reverses_id, entry_kind,
                 actor_principal_id, actor_class, acting_for_principal_id, derived_from)
            VALUES (%s, 'draft', %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                entity_id,
                transaction_date,
                description,
                reverses_id,
                entry_kind,
                actor_principal_id,
                actor_class,
                acting_for_principal_id,
                Jsonb(derived_from) if derived_from is not None else None,
            ),
        )
        row = cur.fetchone()

    if row is None:  # pragma: no cover — RETURNING on a successful insert always yields
        raise RuntimeError("insert returned no id")
    return str(row[0])


def add_postings(
    conn: psycopg.Connection[Any],
    *,
    entity_id: str,
    transaction_id: str,
    postings: Sequence[Posting],
    assigned_by: Mapping[int, str] | None = None,
) -> None:
    """Insert postings for a transaction.

    `entity_id` is written onto every posting rather than joined from the transaction, because
    row-level security is keyed on it: a posting without it would be invisible to the policies
    that isolate entities (ADR-0003).

    `assigned_by` names, per posting, what decided its account (`BKP-10`). Written here at
    insert for the reason `derived_from` is, one function above: lineage that can be attached
    later is lineage that can be changed. Keyed by position rather than carried on `Posting`,
    because `Posting` belongs to the pure engine and a rule is a module's concept the engine
    must not learn (ADR-0022). Opaque, and deliberately not a foreign key — see migration
    0012.
    """
    attribution = assigned_by or {}
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO posting"
            " (transaction_id, entity_id, account_id, amount, commodity,"
            "  assigned_by_rule_version_id)"
            " VALUES (%s, %s, %s, %s, %s, %s)",
            [
                (
                    transaction_id,
                    entity_id,
                    p.account_id,
                    p.amount,
                    p.commodity,
                    attribution.get(index),
                )
                for index, p in enumerate(postings)
            ],
        )


def mark_posted(conn: psycopg.Connection[Any], transaction_id: str) -> None:
    """Move a draft to posted. The point of no return (`LED-07`).

    Sets `posted_at` in the same statement because the schema's CHECK requires it to be set
    exactly when status is `posted`, and the two drifting apart is not a state to allow.

    The deferred zero-sum trigger fires on this update even though no posting row changes,
    which is why 0001 carries a constraint trigger on `ledger_transaction` as well as on
    `posting` (ADR-0006).
    """
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE ledger_transaction SET status = 'posted', posted_at = now()"
            " WHERE id = %s AND status = 'draft'",
            (transaction_id,),
        )


def load(conn: psycopg.Connection[Any], transaction_id: str) -> StoredTransaction | None:
    """Read a transaction and its postings, or `None` if this entity cannot see it.

    "Cannot see" rather than "does not exist": row-level security scopes the query to the
    entity set on the connection, so another entity's transaction is indistinguishable from
    an absent one. That is the intended answer (`NFR-04`).
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, status, transaction_date, description, reverses_id, entry_kind,
                   actor_principal_id, actor_class, acting_for_principal_id
              FROM ledger_transaction
             WHERE id = %s
            """,
            (transaction_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None

        cur.execute(
            "SELECT account_id, amount, commodity FROM posting"
            " WHERE transaction_id = %s ORDER BY created_at, id",
            (transaction_id,),
        )
        postings = tuple(
            Posting(account_id=str(a), amount=Decimal(amount), commodity=str(commodity))
            for a, amount, commodity in cur.fetchall()
        )

    return StoredTransaction(
        id=str(row[0]),
        status=str(row[1]),
        transaction_date=row[2],
        description=row[3],
        reverses_id=str(row[4]) if row[4] is not None else None,
        entry_kind=str(row[5]),
        actor_principal_id=str(row[6]),
        actor_class=str(row[7]),
        acting_for_principal_id=str(row[8]) if row[8] is not None else None,
        postings=postings,
    )


# The books as they stood at a moment (ADR-0013): a transaction recorded before it, and not
# reversed by one recorded before it. Ordinary entries only — an opening or closing entry states
# a balance rather than a movement (`LED-10`, `LED-12`). A reversal is not a movement either: it
# undoes one. `excluding` leaves out one transaction, so a reader rebuilding the moment just
# before that transaction wrote can do so although its row carries its database transaction's
# start time.
MOVEMENTS_AS_OF = """
    SELECT t.id, t.transaction_date, SUM(p.amount)
      FROM ledger_transaction t
      JOIN posting p ON p.transaction_id = t.id
     WHERE t.entity_id = %(entity_id)s
       AND t.recorded_at < %(at)s
       AND t.id IS DISTINCT FROM %(excluding)s::uuid
       AND t.entry_kind = 'ordinary'
       AND t.reverses_id IS NULL
       AND NOT EXISTS (SELECT 1 FROM ledger_transaction r
                        WHERE r.reverses_id = t.id AND r.recorded_at < %(at)s)
       AND p.account_id = %(account_id)s
       AND p.commodity = %(commodity)s
       AND (%(transaction_id)s::uuid IS NULL OR t.id = %(transaction_id)s::uuid)
     GROUP BY t.id, t.transaction_date
    HAVING (%(amount)s::numeric IS NULL OR SUM(p.amount) = %(amount)s::numeric)
     ORDER BY t.transaction_date, t.id
"""


def movements_as_of(
    conn: psycopg.Connection[Any],
    *,
    entity_id: str,
    account_id: str,
    commodity: str,
    at: datetime,
    amount: Decimal | None = None,
    excluding_transaction: str | None = None,
    transaction_id: str | None = None,
) -> list[Movement]:
    """What each transaction moved on one account, as the books stood at `at`.

    Drafts as well as posted entries: a draft is not in the books (`LED-07`), but it is a record
    somebody made, and whether to count it is the caller's question. `amount`, when given, keeps
    only the transactions whose postings on the account sum to exactly it.
    """
    with conn.cursor() as cur:
        cur.execute(
            MOVEMENTS_AS_OF,
            {
                "entity_id": entity_id,
                "account_id": account_id,
                "commodity": commodity,
                "at": at,
                "amount": amount,
                "excluding": excluding_transaction,
                "transaction_id": transaction_id,
            },
        )
        return [
            Movement(
                transaction_id=str(row[0]), transaction_date=row[1], amount=Decimal(row[2])
            )
            for row in cur.fetchall()
        ]
