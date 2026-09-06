"""Every row this entity holds, for the complete export (`EXP-02`).

> "Everything the entity holds — the interchange content, plus supporting documents,
> attachments, raw ingested payloads, rule definitions and the attribution linking them to
> postings, approvals, the record of what an agent did and on what basis, and the audit trail."

**Rows as they are stored, not as a report renders them.** `EXP-04` requires a complete export
to reproduce the books in another deployment, and a figure that has been through a presentation
step cannot do that. Nothing here rounds, groups, or derives (ADR-0025).

**One literal SELECT per table.** No query builder and no table loop composing identifiers:
what this reads out of a customer's books is the kind of thing that has to be readable as
text, which is the same reason there is no ORM (ADR-0028). The cost is repetition, and it is
the right cost.

**Only what the entity holds.** `role` and `role_privilege` describe the deployment rather than
the entity, and `schema_migration` describes the database. `idempotency_key` is a replay cache
with a lifetime of its own; it is not part of the books, and carrying it would let a restored
entity refuse a write because an unrelated deployment once saw the key.
"""

from __future__ import annotations

from typing import Any

import psycopg

__all__ = ["TABLES", "read", "schema_version"]

# Ordered so a reader can create rows in the order it reads them: a row naming another arrives
# after the one it names. `account` is self-referencing, so it is additionally ordered
# parents-first within itself.
TABLES: tuple[tuple[str, str], ...] = (
    (
        "entity",
        "SELECT id, slug, name, accounting_basis, fiscal_year_end_month,"
        " fiscal_year_end_day, functional_currency, time_zone, created_at,"
        " retained_earnings_account_id, opening_balance_account_id"
        " FROM entity WHERE id = %(entity_id)s",
    ),
    (
        "account",
        "SELECT id, code, name, type, parent_id, created_at FROM account"
        " WHERE entity_id = %(entity_id)s ORDER BY parent_id NULLS FIRST, code",
    ),
    (
        "ledger_transaction",
        "SELECT id, status, transaction_date, recorded_at, posted_at, description,"
        " reverses_id, actor_principal_id, actor_class, acting_for_principal_id,"
        " decision_record_id, derived_from, entry_kind FROM ledger_transaction"
        " WHERE entity_id = %(entity_id)s ORDER BY transaction_date, recorded_at, id",
    ),
    (
        "posting",
        "SELECT p.id, p.transaction_id, p.account_id, p.amount, p.commodity, p.cost_amount,"
        " p.cost_commodity, p.lot_id, p.created_at FROM posting p"
        " JOIN ledger_transaction t ON t.id = p.transaction_id"
        " WHERE p.entity_id = %(entity_id)s"
        " ORDER BY t.transaction_date, t.recorded_at, p.transaction_id, p.id",
    ),
    (
        "obligation",
        "SELECT id, transaction_id, amount, commodity, created_at FROM obligation"
        " WHERE entity_id = %(entity_id)s ORDER BY created_at, id",
    ),
    (
        "settlement",
        "SELECT id, obligation_id, transaction_id, amount, commodity, created_at"
        " FROM settlement WHERE entity_id = %(entity_id)s ORDER BY created_at, id",
    ),
    (
        "period_close",
        "SELECT id, period_year, period_month, closed_at, closed_by, reopened_at,"
        " reopened_by, reopen_reason FROM period_close"
        " WHERE entity_id = %(entity_id)s ORDER BY period_year, period_month, closed_at",
    ),
    (
        "issued_statement",
        "SELECT id, report, since, as_of, watermark, issued_by, issued_at, issued_to, figures"
        " FROM issued_statement WHERE entity_id = %(entity_id)s ORDER BY issued_at, id",
    ),
    (
        "entity_grant",
        "SELECT id, principal_id, role, granted_by, granted_at, lapses_at, revoked_at,"
        " revoked_by FROM entity_grant WHERE entity_id = %(entity_id)s ORDER BY granted_at, id",
    ),
    (
        "customer",
        "SELECT id, name, email, created_at, archived_at FROM customer"
        " WHERE entity_id = %(entity_id)s ORDER BY created_at, id",
    ),
    (
        "invoice",
        "SELECT id, customer_id, status, number, issue_date, due_date, terms, commodity,"
        " note, created_at, issued_at, transaction_id, cancelled_at, cancel_reason"
        " FROM invoice WHERE entity_id = %(entity_id)s ORDER BY created_at, id",
    ),
    (
        "invoice_line",
        "SELECT l.id, l.invoice_id, l.position, l.description, l.account_id, l.quantity,"
        " l.unit_amount, l.created_at FROM invoice_line l"
        " JOIN invoice i ON i.id = l.invoice_id"
        " WHERE l.entity_id = %(entity_id)s ORDER BY i.created_at, l.invoice_id, l.position",
    ),
    (
        # Where the gapless series stands. A restore without it would begin numbering at 1
        # again and collide with every invoice already issued (`AR-05`).
        "invoice_series",
        "SELECT entity_id, next FROM invoice_series WHERE entity_id = %(entity_id)s",
    ),
    (
        "audit_log",
        "SELECT id, request_id, actor, action, subject_type, subject_id, occurred_at, detail"
        " FROM audit_log WHERE entity_id = %(entity_id)s ORDER BY occurred_at, id",
    ),
)


def read(
    conn: psycopg.Connection[Any], *, entity_id: str, table: str
) -> tuple[list[str], list[tuple[Any, ...]]]:
    """One table's rows for this entity, with the column names they came back under.

    Every statement carries its own `entity_id` predicate rather than relying on row-level
    security to apply one. RLS is the backstop and it does apply here; a query that would read
    another entity's rows if the policy were ever dropped is not one to write (ADR-0003).
    """
    statement = dict(TABLES)[table]
    with conn.cursor() as cur:
        cur.execute(statement, {"entity_id": entity_id})
        columns = [column.name for column in cur.description or ()]
        return columns, cur.fetchall()


def schema_version(conn: psycopg.Connection[Any]) -> str:
    """The highest migration version applied to this database.

    Not entity-scoped, and deliberately part of a complete export: `EXP-04` has a receiving
    deployment reproduce the books, and rows written under a schema it has not caught up to are
    rows it cannot place. The archive states the version so that is a refusal rather than a
    silent partial restore.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT max(version) FROM schema_migration")
        row = cur.fetchone()
    return str(row[0]) if row is not None and row[0] is not None else ""
