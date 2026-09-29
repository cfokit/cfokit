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

__all__ = [
    "SourceAccount",
    "SourceBooks",
    "SourceEntry",
    "SourceLine",
    "StatedBalance",
    "StatedStatement",
    "StatedTotal",
]


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
class StatedTotal:
    """The source's own total over its raw journal — its arithmetic, over the rows we import.

    **The only figure in a QuickBooks export that carries no accounting basis**, because the
    journal is the record rather than a view of one. Every report beside it is run on whichever
    basis the company keeps, so a per-account comparison against one diverges on the obligation
    accounts by exactly what is unsettled; this does not (ADR-0050).

    It is `IMP-08`'s "totals" half, and it catches what an import actually gets wrong — a row
    dropped, an amount misread, a batch posted twice. It says nothing about which account a row
    landed in: two accounts transposed total the same.
    """

    debits: Decimal
    credits: Decimal


@dataclass(frozen=True, slots=True)
class StatedStatement:
    """A statement the source printed, by account.

    Leaf accounts only. A statement's subtotals are computed cells rather than stated figures,
    so reading one would mean evaluating a spreadsheet — and a total derived from the leaves is
    the same number without the pretense that the source stated it independently.

    `unmatched` names rows whose account could not be resolved to one the journal posts to.
    Reported rather than dropped: a line silently missing from a comparison is a difference
    that reads as agreement.
    """

    report: str
    basis: str
    lines: tuple[StatedBalance, ...] = ()
    unmatched: tuple[str, ...] = ()


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
    # A digest of the bytes this was read from — the source file's identity, not its content's.
    #
    # What makes an import replayable rather than duplicable (ADR-0029). An import is thousands
    # of writes in a loop, and a client that times out halfway through and retries would
    # otherwise post the whole company's books a second time — which under append-only is
    # undone only by a reversing entry per transaction (ADR-0007). Keying each entry's
    # idempotency key on this plus the source's own row reference makes the retry a replay.
    #
    # A property of the file rather than of the parse, so a reader change that alters the
    # parsed shape does not silently make an already-imported file importable again. Set by the
    # reader, which is the only thing holding the bytes.
    fingerprint: str
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
    # What the raw journal says it sums to, where the source prints it. `None` where it does
    # not, and never computed here: summing the rows ourselves and calling it an oracle would
    # compare our arithmetic against itself (ADR-0050).
    journal_total: StatedTotal | None = None
    # Subtotals the source prints over a parent and everything beneath it. Held apart from
    # `balances` because nothing posts to a subtotal: comparing one against a chart account
    # would report a divergence that is really a difference in what the two figures are.
    rollups: tuple[StatedBalance, ...] = field(default_factory=tuple)
    # The statements the source printed, for comparing against the ones CFOKit produces
    # (`IMP-08`, `NFR-01`). Signed as the source prints them, which is not how a posting is
    # signed — see `statements` in the reader.
    statements: tuple[StatedStatement, ...] = field(default_factory=tuple)
