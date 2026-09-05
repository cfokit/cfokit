"""The shape every reader produces, and no reader's own shape.

One neutral description of a foreign system's books, so that adding a second source is a
reader rather than a second pipeline. The import path below it never learns what QuickBooks is.

**Signed the way a posting is signed: positive is a debit.** A reader is responsible for that
translation and for nothing else — a source that prints separate debit and credit columns has
them subtracted here, and one that signs its own amounts is passed through.

**Amounts are `Decimal`.** Never `float`, at any point between the file and the books
(ADR-0005). A reader that parses a spreadsheet cell reads it as text first.

**`system` names where the books came from**, and is what `IMP-04` requires an imported record
to carry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

__all__ = ["SourceAccount", "SourceBooks", "SourceEntry", "SourceLine", "StatedBalance"]


@dataclass(frozen=True, slots=True)
class SourceAccount:
    """One account in the source's chart.

    `account_type` is `unknown` where the source states none. Recorded as a question rather
    than guessed: a wrong type is a silent misclassification, and a missing one is something
    an operator can answer.
    """

    code: str
    name: str
    account_type: str
    parent: str = ""


@dataclass(frozen=True, slots=True)
class SourceLine:
    """One posting line."""

    account_code: str
    amount: Decimal
    commodity: str


@dataclass(frozen=True, slots=True)
class SourceEntry:
    """One transaction, as the source grouped it.

    `reference` is the source's own identifier for it where there is one, and a positional one
    where there is not. Either way it survives into `derived_from`, so a posting in CFOKit can
    be traced back to the row it came from (`IMP-04`, `SOC1-14`).
    """

    reference: str
    transaction_date: date
    description: str
    lines: tuple[SourceLine, ...]


@dataclass(frozen=True, slots=True)
class StatedBalance:
    """A balance the source states for one account — its arithmetic, not ours.

    This is what makes an import checkable. Summing the journal ourselves and comparing that
    against our own books would be comparing our arithmetic against itself (`IMP-08`,
    `NFR-01`).
    """

    account_code: str
    balance: Decimal


@dataclass(frozen=True, slots=True)
class SourceBooks:
    """One foreign system's books, in the shape an import reads.

    **`basis` and `balances_basis` are different questions and must not be one field.** The
    entries are the source's raw double-entry record; the stated balances are a *view* it
    computed, and a system can perfectly well print cash-basis reports over an accrual journal.
    Conflating them makes `IMP-06` refuse a file whose data is fine because a report beside it
    was run differently, and makes `IMP-08` unable to say why the obligation accounts diverged.

    `basis` is `unknown` where the source states none for its journal. That does not block an
    import: a system that prints no method on its raw record has not disagreed with anything.
    """

    system: str
    # The accounting method of the entries — what `IMP-06` refuses a conflict with.
    basis: str
    # The accounting method the stated balances were computed on. Not a gate; an explanation.
    # An accrual ledger reconciled against cash-basis balances differs by exactly what is
    # unsettled, and that is ADR-0037 working rather than a defect.
    balances_basis: str
    commodity: str
    accounts: tuple[SourceAccount, ...] = ()
    entries: tuple[SourceEntry, ...] = ()
    # What the source says the answer is, per account.
    balances: tuple[StatedBalance, ...] = ()
    # Subtotals the source prints over a parent and everything beneath it. Held apart from
    # `balances` because nothing posts to a subtotal: comparing one against a chart account
    # would report a divergence that is really a difference in what the two figures are.
    rollups: tuple[StatedBalance, ...] = field(default_factory=tuple)
