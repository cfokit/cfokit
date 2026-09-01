"""Reading and writing transactions and their postings. Hand-written SQL (ADR-0028).

Every statement here is parameterised through the driver. String interpolation into SQL is
never acceptable, and ruff's bandit rules catch it.

Nothing in this module updates a financial field on a posted row or deletes anything: the
schema refuses both (ADR-0007), and offering a function for it would be offering a way to
find out.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

import psycopg

from cfokit.ledger.engine import Posting

__all__ = ["StoredTransaction", "add_postings", "insert_draft", "load", "mark_posted"]


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
) -> str:
    """Insert a transaction as a draft and return its id.

    **Always a draft, whatever the caller intends.** Posting is a separate statement, so the
    zero-sum trigger sees a complete set of postings rather than the first one (ADR-0006), and
    so the draft-to-posted transition is the one-way move ADR-0007 requires rather than an
    initial value.

    `actor_principal_id` and `actor_class` arrive from the authenticated principal. No write
    path accepts them from a request body — the same device ADR-0013 used for `recorded_at`
    (ADR-0033 § 2). `recorded_at` itself is not settable here at all; the column defaults.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO ledger_transaction
                (entity_id, status, transaction_date, description, reverses_id, entry_kind,
                 actor_principal_id, actor_class, acting_for_principal_id)
            VALUES (%s, 'draft', %s, %s, %s, %s, %s, %s, %s)
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
) -> None:
    """Insert postings for a transaction.

    `entity_id` is written onto every posting rather than joined from the transaction, because
    row-level security is keyed on it: a posting without it would be invisible to the policies
    that isolate entities (ADR-0003).
    """
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO posting (transaction_id, entity_id, account_id, amount, commodity)"
            " VALUES (%s, %s, %s, %s, %s)",
            [
                (transaction_id, entity_id, p.account_id, p.amount, p.commodity)
                for p in postings
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
