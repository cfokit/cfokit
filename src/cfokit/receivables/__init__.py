"""Receivables: customers, invoices, and the postings an issue produces (`AR-01` to `AR-06`).

**A sibling of the ledger, not part of it** (ADR-0022, ADR-0040). The ledger owns the
double-entry primitive and knows nothing about customers or invoices; this module knows both,
and reaches the books through the ledger's published service layer like any other caller.

**In-process, because an issue must commit atomically with its postings.** ADR-0022 § 3 names
this case in as many words — "An invoice and its GL entries must reach one `COMMIT`" — and it
is the reason receivables is a module rather than a separate component.

**Draft until issued, permanent after** (`AR-04`). A draft is freely editable and is not in the
books; issuing assigns a number, posts the entry, and raises the obligation, in one
transaction. That boundary is the same one `LED-07` draws between a draft transaction and a
posted one, and it is enforced by triggers rather than by this code, because a rule only the
application honors is a rule the next bulk-import script will not (ADR-0007).

**Amounts are `Decimal` and are never rounded here.** A line's total is quantity times unit
amount at full precision; rounding happens once, at presentation (ADR-0025).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol

__all__ = ["Invoice", "InvoiceLine", "LineInput", "total_of"]


class Priced(Protocol):
    """Anything with an amount: a line being drafted, or one already stored."""

    @property
    def amount(self) -> Decimal: ...


@dataclass(frozen=True, slots=True)
class LineInput:
    """One line as a caller states it."""

    description: str
    account_id: str
    unit_amount: Decimal
    quantity: Decimal = Decimal(1)

    @property
    def amount(self) -> Decimal:
        """What this line is worth, exactly.

        Not rounded, and not rounded when the invoice is totalled either. A line priced at
        1/3 of a unit is worth what it is worth; what a document shows is a presentation
        decision made once, at the edge (ADR-0025).
        """
        return self.quantity * self.unit_amount


@dataclass(frozen=True, slots=True)
class InvoiceLine:
    """One line as stored."""

    id: str
    position: int
    description: str
    account_id: str
    quantity: Decimal
    unit_amount: Decimal

    @property
    def amount(self) -> Decimal:
        return self.quantity * self.unit_amount


@dataclass(frozen=True, slots=True)
class Invoice:
    """One invoice, and everything on it."""

    id: str
    customer_id: str
    status: str
    commodity: str
    lines: tuple[InvoiceLine, ...]
    number: int | None = None
    issue_date: date | None = None
    due_date: date | None = None
    terms: str | None = None
    note: str | None = None
    transaction_id: str | None = None
    cancel_reason: str | None = None

    @property
    def total(self) -> Decimal:
        return total_of(self.lines)

    @property
    def is_draft(self) -> bool:
        return self.status == "draft"


def total_of(lines: Iterable[Priced]) -> Decimal:
    """The sum of a set of lines, at full precision.

    A free function so the same arithmetic serves a stored invoice and one being drafted, and
    so nothing has to construct an `Invoice` to find out what it would come to.
    """
    return sum((line.amount for line in lines), Decimal(0))
