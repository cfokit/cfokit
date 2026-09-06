"""Customers and draft invoices: everything up to the point of no return (`AR-01` to `AR-06`).

**Nothing here posts.** A customer is not a financial record and a draft invoice is not in the
books (`AR-04`), so every call in this module writes rows the ledger never sees. Issuing — which
assigns a number, posts the entry and raises the obligation in one transaction — is a separate
act and is not built here.

**Authorisation is the ledger's** (ADR-0039). Privileges are a code enum and roles are rows; a
module inventing a privilege of its own would put a second authority beside that one. `RECORD`
is what a caller needs to draft an invoice, because drafting an invoice is drafting the entry
it will become; `GRANT` is what changing the customer list needs, on the same reasoning that
makes the chart of accounts administrative rather than a posting act.

**One transaction, the ledger's.** A module is a sibling in the same deployable sharing one
database and one transaction (ADR-0022 § 3), so these run inside `Database.entity_write`: the
entity is scoped and locked exactly as it is for a ledger write, and row-level security applies
to this module's tables through the same session setting.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from cfokit.ledger.errors import LedgerError
from cfokit.ledger.repository.unit_of_work import Database, EntityWrite
from cfokit.ledger.service.authorisation import Capability, require
from cfokit.ledger.service.principal import Principal
from cfokit.receivables import Invoice, LineInput
from cfokit.receivables import repository as store

__all__ = [
    "CustomerNotFound",
    "InvoiceNotDraft",
    "InvoiceNotFound",
    "create_customer",
    "draft_invoice",
    "invoice",
    "invoices",
    "list_customers",
    "replace_lines",
    "update_customer",
]


class CustomerNotFound(LedgerError):
    """No such customer in this entity."""

    code = "customer_not_found"
    status = 404


class InvoiceNotFound(LedgerError):
    """No such invoice in this entity."""

    code = "invoice_not_found"
    status = 404


class InvoiceNotDraft(LedgerError):
    """An issued invoice is never edited (`AR-14`).

    Refused here as well as by the trigger, so a caller gets a stable `code` rather than a
    constraint violation (ADR-0015). The trigger is what makes it true; this is what makes it
    legible.
    """

    code = "invoice_not_draft"
    status = 409


class LineWithoutIncome(LedgerError):
    """A line naming an account that is not income (`AR-03`).

    An invoice line credits income. Naming an expense account would produce an entry that
    balances and means nothing, which is worse than one that is refused.
    """

    code = "line_without_income"
    status = 422


def create_customer(
    database: Database,
    *,
    entity_id: str,
    principal: Principal,
    request_id: str,
    name: str,
    email: str | None = None,
) -> str:
    """Add a customer to the entity (`AR-01`)."""
    with database.entity_write(entity_id) as write:
        _require(write, principal, Capability.GRANT)
        customer_id = store.create_customer(
            write.connection, entity_id=entity_id, name=name, email=email
        )
        write.record_audit(
            request_id=request_id,
            actor=principal.audit_actor,
            action="create_customer",
            subject_type="customer",
            subject_id=customer_id,
            # An identifier, never the name: a customer list is exactly the sort of thing the
            # observability rules keep out of a log (CLAUDE.md, Observability).
            detail={},
        )
    return customer_id


def update_customer(
    database: Database,
    *,
    entity_id: str,
    principal: Principal,
    request_id: str,
    customer_id: str,
    name: str | None = None,
    email: str | None = None,
    archived: bool | None = None,
) -> None:
    """Correct or archive a customer.

    Editable, unlike anything the ledger holds, because a customer is not a financial record. A
    name corrected after an invoice was issued does not change the invoice: that names its
    customer by id and carries its own frozen figures (`AR-14`).
    """
    with database.entity_write(entity_id) as write:
        _require(write, principal, Capability.GRANT)
        found = store.update_customer(
            write.connection,
            entity_id=entity_id,
            customer_id=customer_id,
            name=name,
            email=email,
            archived=archived,
        )
        if not found:
            raise CustomerNotFound(customer_id)
        write.record_audit(
            request_id=request_id,
            actor=principal.audit_actor,
            action="update_customer",
            subject_type="customer",
            subject_id=customer_id,
            detail={"archived": archived} if archived is not None else {},
        )


def list_customers(
    database: Database,
    *,
    entity_id: str,
    principal: Principal,
    include_archived: bool = False,
) -> list[store.Customer]:
    with database.entity_write(entity_id) as write:
        _require(write, principal, Capability.READ)
        return store.customers(
            write.connection, entity_id=entity_id, include_archived=include_archived
        )


def draft_invoice(
    database: Database,
    *,
    entity_id: str,
    principal: Principal,
    request_id: str,
    customer_id: str,
    lines: list[LineInput],
    terms: str | None = None,
    note: str | None = None,
) -> str:
    """Raise a draft invoice against a customer (`AR-02`, `AR-03`).

    A draft, always. It is freely editable and it is not in the books; issuing is the point of
    no return and a separate act (`AR-04`).

    The commodity is the entity's functional currency, read here rather than taken from the
    caller — a caller who could state it could state their way past `LED-15`'s refusal of a
    foreign amount, which is why the ledger reads it the same way.
    """
    with database.entity_write(entity_id) as write:
        _require(write, principal, Capability.RECORD)
        _require_customer(write, entity_id, customer_id)
        _require_income(write, lines)

        invoice_id = store.insert_draft(
            write.connection,
            entity_id=entity_id,
            customer_id=customer_id,
            commodity=write.settings.functional_currency,
            terms=terms,
            note=note,
        )
        store.add_lines(
            write.connection, entity_id=entity_id, invoice_id=invoice_id, lines=lines
        )
        write.record_audit(
            request_id=request_id,
            actor=principal.audit_actor,
            action="draft_invoice",
            subject_type="invoice",
            subject_id=invoice_id,
            # Counts, not amounts. `AR-15` reports receivables; a log does not.
            detail={"customer_id": customer_id, "lines": len(lines)},
        )
    return invoice_id


def replace_lines(
    database: Database,
    *,
    entity_id: str,
    principal: Principal,
    request_id: str,
    invoice_id: str,
    lines: list[LineInput],
) -> None:
    """Rewrite a draft's lines. Refused once the invoice is issued (`AR-04`, `AR-14`)."""
    with database.entity_write(entity_id) as write:
        _require(write, principal, Capability.RECORD)
        found = store.invoice(write.connection, entity_id=entity_id, invoice_id=invoice_id)
        if found is None:
            raise InvoiceNotFound(invoice_id)
        if not found.is_draft:
            raise InvoiceNotDraft(f"invoice {invoice_id} is {found.status}")
        _require_income(write, lines)

        store.replace_lines(
            write.connection, entity_id=entity_id, invoice_id=invoice_id, lines=lines
        )
        write.record_audit(
            request_id=request_id,
            actor=principal.audit_actor,
            action="replace_invoice_lines",
            subject_type="invoice",
            subject_id=invoice_id,
            detail={"lines": len(lines)},
        )


def invoice(
    database: Database, *, entity_id: str, principal: Principal, invoice_id: str
) -> Invoice:
    with database.entity_write(entity_id) as write:
        _require(write, principal, Capability.READ)
        found = store.invoice(write.connection, entity_id=entity_id, invoice_id=invoice_id)
    if found is None:
        raise InvoiceNotFound(invoice_id)
    return found


def invoices(
    database: Database, *, entity_id: str, principal: Principal, status: str | None = None
) -> list[Invoice]:
    with database.entity_write(entity_id) as write:
        _require(write, principal, Capability.READ)
        return store.invoices(write.connection, entity_id=entity_id, status=status)


def total(lines: list[LineInput]) -> Decimal:
    """What a set of lines comes to, exactly. Never rounded (ADR-0025)."""
    from cfokit.receivables import total_of

    return total_of(lines)


def _require(write: EntityWrite, principal: Principal, capability: Capability) -> None:
    now = datetime.now(UTC)
    actor = write.privileges_in_force(principal.id, now)
    acted_for = (
        write.privileges_in_force(principal.acting_for, now)
        if principal.acting_for is not None
        else frozenset()
    )
    require(capability, principal, actor, acted_for)


def _require_customer(write: EntityWrite, entity_id: str, customer_id: str) -> None:
    known = {
        customer.id
        for customer in store.customers(
            write.connection, entity_id=entity_id, include_archived=True
        )
    }
    if customer_id not in known:
        raise CustomerNotFound(customer_id)


def _require_income(write: EntityWrite, lines: list[LineInput]) -> None:
    """Every line credits an income account (`AR-03`).

    Checked against the chart rather than trusted, because the account is what makes an issued
    invoice a posting rather than a document — and an invoice whose lines name the wrong kind
    of account produces an entry that balances and says something false.
    """
    if not lines:
        return
    types = {account.account_id: account.account_type for account in write.chart()}
    for line in lines:
        stated = types.get(line.account_id)
        if stated is None:
            raise LineWithoutIncome(f"no account {line.account_id} in this entity")
        if stated != "income":
            raise LineWithoutIncome(
                f"an invoice line credits income; account {line.account_id} is {stated}"
            )
