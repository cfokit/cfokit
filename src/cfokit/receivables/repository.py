"""SQL for customers and invoices. Hand-written, like the ledger's (ADR-0028).

**This module's own repository, not the ledger's.** ADR-0022 forbids the ledger from depending
on a module, and a module reaching into the ledger's `EntityWrite` for its own tables would
have put invoice SQL inside the ledger by another route. The connection comes from the ledger's
unit of work — the transaction and the entity scoping are shared, which is the whole point of
being in-process — and the statements are here.

No ORM and no query builder: what reads and writes a customer's billing history has to be
readable as text.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

import psycopg

from cfokit.receivables import Invoice, InvoiceLine, LineInput

__all__ = [
    "Customer",
    "add_lines",
    "claim_number",
    "create_customer",
    "customers",
    "insert_draft",
    "invoice",
    "invoices",
    "mark_canceled",
    "mark_issued",
    "replace_lines",
    "update_customer",
]


@dataclass(frozen=True, slots=True)
class Customer:
    """One customer, as stored."""

    id: str
    name: str
    email: str | None
    archived: bool


def create_customer(
    conn: psycopg.Connection[Any], *, entity_id: str, name: str, email: str | None
) -> str:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO customer (entity_id, name, email) VALUES (%s, %s, %s) RETURNING id",
            (entity_id, name, email),
        )
        row = cur.fetchone()
    assert row is not None  # noqa: S101 - RETURNING on a successful insert always yields
    return str(row[0])


def update_customer(
    conn: psycopg.Connection[Any],
    *,
    entity_id: str,
    customer_id: str,
    name: str | None,
    email: str | None,
    archived: bool | None,
) -> bool:
    """Change what is changeable about a customer. Returns whether one was found.

    A customer is not a financial record — a name corrected after an invoice was issued does
    not change the invoice, which names the customer by id and carries its own frozen figures.
    Archiving is the closest thing to deletion (`AR-14` keeps the invoice, so the customer it
    names has to stay reachable).
    """
    with conn.cursor() as cur:
        cur.execute(
            # Every parameter is cast. Postgres infers a type from context, and `CASE WHEN $2
            # IS NULL` gives it none — "could not determine data type of parameter" rather
            # than a wrong answer, but a cast is what makes the statement say what it means.
            "UPDATE customer SET"
            " name = COALESCE(%(name)s::text, name),"
            " email = CASE WHEN %(email)s::text IS NULL THEN email ELSE %(email)s::text END,"
            " archived_at = CASE"
            "   WHEN %(archived)s::boolean IS NULL THEN archived_at"
            "   WHEN %(archived)s::boolean THEN COALESCE(archived_at, now())"
            "   ELSE NULL END"
            " WHERE id = %(customer_id)s AND entity_id = %(entity_id)s",
            {
                "name": name,
                "email": email,
                "archived": archived,
                "customer_id": customer_id,
                "entity_id": entity_id,
            },
        )
        return cur.rowcount > 0


def customers(
    conn: psycopg.Connection[Any], *, entity_id: str, include_archived: bool
) -> list[Customer]:
    """Every customer, name order, archived ones only when asked for."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, name, email, archived_at FROM customer"
            " WHERE entity_id = %s AND (%s OR archived_at IS NULL)"
            " ORDER BY lower(name), id",
            (entity_id, include_archived),
        )
        return [
            Customer(
                id=str(row[0]),
                name=str(row[1]),
                email=str(row[2]) if row[2] is not None else None,
                archived=row[3] is not None,
            )
            for row in cur.fetchall()
        ]


def insert_draft(
    conn: psycopg.Connection[Any],
    *,
    entity_id: str,
    customer_id: str,
    commodity: str,
    terms: str | None,
    note: str | None,
) -> str:
    """Always a draft, whatever the caller intends.

    Issuing is a separate statement for the same reason posting is in the ledger: the
    draft-to-issued move is one-way (`AR-04`), and a row that could be inserted already issued
    would make it an initial value instead.
    """
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO invoice (entity_id, customer_id, commodity, terms, note)"
            " VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (entity_id, customer_id, commodity, terms, note),
        )
        row = cur.fetchone()
    assert row is not None  # noqa: S101
    return str(row[0])


def add_lines(
    conn: psycopg.Connection[Any],
    *,
    entity_id: str,
    invoice_id: str,
    lines: list[LineInput],
    starting_at: int = 1,
) -> None:
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO invoice_line"
            " (entity_id, invoice_id, position, description, account_id, quantity, unit_amount)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s)",
            [
                (
                    entity_id,
                    invoice_id,
                    starting_at + offset,
                    line.description,
                    line.account_id,
                    line.quantity,
                    line.unit_amount,
                )
                for offset, line in enumerate(lines)
            ],
        )


def replace_lines(
    conn: psycopg.Connection[Any], *, entity_id: str, invoice_id: str, lines: list[LineInput]
) -> None:
    """Rewrite a draft's lines. The trigger refuses this once the invoice is issued."""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM invoice_line WHERE invoice_id = %s", (invoice_id,))
    add_lines(conn, entity_id=entity_id, invoice_id=invoice_id, lines=lines)


def claim_number(conn: psycopg.Connection[Any], *, entity_id: str) -> int:
    """The next number in the entity's series, consumed (`AR-05`).

    Inside the caller's transaction, so a rollback returns it. That is what "gapless" costs and
    what a Postgres sequence will not do: a sequence advances outside the transaction, which is
    what makes it fast and what would leave a hole here.

    The row is created on first use rather than when the entity is, so an entity that never
    invoices carries no series — and `ON CONFLICT` makes the creation itself safe to race.
    """
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO invoice_series (entity_id) VALUES (%s) ON CONFLICT DO NOTHING",
            (entity_id,),
        )
        cur.execute(
            "UPDATE invoice_series SET next = next + 1 WHERE entity_id = %s RETURNING next - 1",
            (entity_id,),
        )
        row = cur.fetchone()
    assert row is not None  # noqa: S101
    return int(row[0])


def mark_issued(
    conn: psycopg.Connection[Any],
    *,
    entity_id: str,
    invoice_id: str,
    number: int,
    issue_date: date,
    due_date: date | None,
    transaction_id: str,
) -> None:
    """Draft to issued, in one statement, only from draft.

    The `status = 'draft'` predicate is what makes a second issue a no-op rather than a second
    number: two callers racing would otherwise each claim one, and the loser's would be the gap
    `AR-05` forbids.
    """
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE invoice SET status = 'issued', number = %s, issue_date = %s,"
            " due_date = %s, transaction_id = %s, issued_at = now()"
            " WHERE id = %s AND entity_id = %s AND status = 'draft'",
            (number, issue_date, due_date, transaction_id, invoice_id, entity_id),
        )
        if cur.rowcount != 1:
            raise LookupError(invoice_id)


def mark_canceled(
    conn: psycopg.Connection[Any], *, entity_id: str, invoice_id: str, reason: str
) -> bool:
    """Cancel an issued invoice. It keeps its number and stays visible (`AR-05`)."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE invoice SET status = 'canceled', canceled_at = now(), cancel_reason = %s"
            " WHERE id = %s AND entity_id = %s AND status = 'issued'",
            (reason, invoice_id, entity_id),
        )
        return cur.rowcount == 1


# Both statements below spell their columns out rather than sharing a constant. Interpolating
# even a literal one puts a format string where SQL goes, and the rule that keeps this module
# auditable is that a statement reads as a statement (ADR-0028).


def invoice(
    conn: psycopg.Connection[Any], *, entity_id: str, invoice_id: str
) -> Invoice | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, customer_id, status, commodity, number, issue_date, due_date,"
            " terms, note, transaction_id, cancel_reason"
            " FROM invoice WHERE id = %s AND entity_id = %s",
            (invoice_id, entity_id),
        )
        row = cur.fetchone()
        if row is None:
            return None
        cur.execute(
            "SELECT id, position, description, account_id, quantity, unit_amount"
            " FROM invoice_line WHERE invoice_id = %s ORDER BY position",
            (invoice_id,),
        )
        lines = tuple(
            InvoiceLine(
                id=str(line[0]),
                position=int(line[1]),
                description=str(line[2]),
                account_id=str(line[3]),
                quantity=Decimal(line[4]),
                unit_amount=Decimal(line[5]),
            )
            for line in cur.fetchall()
        )
    return _invoice(row, lines)


def invoices(
    conn: psycopg.Connection[Any], *, entity_id: str, status: str | None
) -> list[Invoice]:
    """Every invoice, newest first, without its lines.

    Ordered by issue date then number then id — a total order, so two reads of unchanged books
    agree. A draft has neither date nor number and sorts last, which is where an unfinished
    thing belongs.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, customer_id, status, commodity, number, issue_date, due_date,"
            " terms, note, transaction_id, cancel_reason"
            " FROM invoice WHERE entity_id = %s AND (%s::text IS NULL OR status = %s)"
            " ORDER BY issue_date DESC NULLS FIRST, number DESC NULLS FIRST, id",
            (entity_id, status, status),
        )
        return [_invoice(row, ()) for row in cur.fetchall()]


def _invoice(row: tuple[Any, ...], lines: tuple[InvoiceLine, ...]) -> Invoice:
    return Invoice(
        id=str(row[0]),
        customer_id=str(row[1]),
        status=str(row[2]),
        commodity=str(row[3]),
        number=int(row[4]) if row[4] is not None else None,
        issue_date=row[5],
        due_date=row[6],
        terms=str(row[7]) if row[7] is not None else None,
        note=str(row[8]) if row[8] is not None else None,
        transaction_id=str(row[9]) if row[9] is not None else None,
        cancel_reason=str(row[10]) if row[10] is not None else None,
        lines=lines,
    )
