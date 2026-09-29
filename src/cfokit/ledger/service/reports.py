"""Reports over the books (`RPT-01`, `RPT-10`, `RPT-11`).

**Every figure here is exact.** Rounding is a presentation act and happens once, in
`cfokit.ledger.presentation`, which the adapters call — a rounding call in this layer would
mean the boundary has been misplaced (ADR-0025).

**A report states the basis it was produced on** (`RPT-10`). It is read from the entity rather
than taken from the caller, for the same reason the functional currency is: a caller who could
state the basis could label a report as something it is not.

**A report is reproducible as the books stood at an earlier moment** (`RPT-11`). That is a
parameter here rather than a separate code path, because a report that reproduces the past by
different machinery than it reports the present is two reports that can disagree.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from cfokit.ledger.engine.periods import preceding_window, year_earlier_window
from cfokit.ledger.errors import AccountNotFound
from cfokit.ledger.repository import reports as store
from cfokit.ledger.repository.reports import Account, AccountBalance, AccountEntry
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.authorization import Capability, authorize
from cfokit.ledger.service.principal import Principal

__all__ = [
    "AccountDetail",
    "BalanceSheet",
    "Comparative",
    "ComparativeProfitAndLoss",
    "JournalTotals",
    "ProfitAndLoss",
    "TrialBalance",
    "account_detail",
    "balance_sheet",
    "comparative_profit_and_loss",
    "journal_totals",
    "profit_and_loss",
    "trial_balance",
]

INCOME_STATEMENT_TYPES = ("income", "expense")
BALANCE_SHEET_TYPES = ("asset", "liability", "equity")


@dataclass(frozen=True, slots=True)
class TrialBalance:
    """A trial balance, with what it was produced on stated on its face."""

    as_of: date
    watermark: datetime | None
    accounting_basis: str
    functional_currency: str
    rows: tuple[AccountBalance, ...]


@dataclass(frozen=True, slots=True)
class JournalTotals:
    """What moved through the books, gross rather than netted by account."""

    since: date | None
    as_of: date
    debits: Decimal
    credits: Decimal


def journal_totals(
    database: Database,
    *,
    entity_id: str,
    principal: Principal,
    as_of: date,
    since: date | None = None,
) -> JournalTotals:
    """Gross posting volume, which is what a source system's journal states about itself.

    **Not a trial balance.** A trial balance nets within each account, so an account paid into
    and out of a hundred times contributes only what it is left holding; this is the volume
    that passed through. On a real QuickBooks export the two are 2,616,030.82 and
    8,480,703.91 — the same books, two different questions.

    a journal total is the only one an export states (`IMP-08`, ADR-0050).
    Requires `READ`, like every other report.
    a journal total is the only one an export states (`IMP-08`, ADR-0050). Requires `READ`, like
    every other report.
    """
    with database.entity_write(entity_id) as write:
        authorize(write, Capability.READ, principal)
        gross_debits, gross_credits = store.journal_totals(
            write.connection, entity_id=entity_id, as_of=as_of, since=since
        )
    return JournalTotals(since=since, as_of=as_of, debits=gross_debits, credits=gross_credits)


def trial_balance(
    database: Database,
    *,
    entity_id: str,
    principal: Principal,
    as_of: date,
    watermark: datetime | None = None,
) -> TrialBalance:
    """Every account with a non-zero balance as of `as_of` (`RPT-01`).

    `watermark` reproduces the books as they stood then (`RPT-11`). Two runs over the same
    watermark return the same figures; two runs over different ones differ by exactly the
    transactions posted between them, because nothing is stored and every figure is derived
    from the postings that were in the books at that moment.
    """
    with database.entity_write(entity_id) as write:
        authorize(write, Capability.READ, principal)
        settings = write.settings
        rows = write.account_balances(as_of=as_of, watermark=watermark)

    return TrialBalance(
        as_of=as_of,
        watermark=watermark,
        accounting_basis=settings.accounting_basis,
        functional_currency=settings.functional_currency,
        rows=tuple(rows),
    )


@dataclass(frozen=True, slots=True)
class ProfitAndLoss:
    """Income and expense over a period (`RPT-02`)."""

    since: date
    as_of: date
    watermark: datetime | None
    accounting_basis: str
    functional_currency: str
    rows: tuple[AccountBalance, ...]


@dataclass(frozen=True, slots=True)
class BalanceSheet:
    """Assets, liabilities and equity as of a date (`RPT-03`).

    `unclosed` is the net of every income and expense balance still standing. Those amounts
    belong to equity and have not been moved there yet, because `LED-12` moves them only at a
    fiscal year end. Without them the statement would not balance, and the gap would be exactly
    the earnings nobody had closed.
    """

    as_of: date
    watermark: datetime | None
    accounting_basis: str
    functional_currency: str
    rows: tuple[AccountBalance, ...]
    unclosed: tuple[AccountBalance, ...]


def profit_and_loss(
    database: Database,
    *,
    entity_id: str,
    principal: Principal,
    since: date,
    as_of: date,
    watermark: datetime | None = None,
) -> ProfitAndLoss:
    """Income and expense for the period `since`..`as_of` inclusive (`RPT-02`).

    A period rather than a point, which is the whole difference from a balance sheet: income
    and expense measure what happened between two dates, and assets and liabilities are what
    stands at one.
    """
    with database.entity_write(entity_id) as write:
        authorize(write, Capability.READ, principal)
        settings = write.settings
        rows = write.account_balances(
            as_of=as_of, since=since, types=INCOME_STATEMENT_TYPES, watermark=watermark
        )

    return ProfitAndLoss(
        since=since,
        as_of=as_of,
        watermark=watermark,
        accounting_basis=settings.accounting_basis,
        functional_currency=settings.functional_currency,
        rows=tuple(rows),
    )


def balance_sheet(
    database: Database,
    *,
    entity_id: str,
    principal: Principal,
    as_of: date,
    watermark: datetime | None = None,
) -> BalanceSheet:
    """Assets, liabilities and equity as of `as_of` (`RPT-03`).

    Cumulative from the beginning of the books, because that is what a balance sheet is.
    """
    with database.entity_write(entity_id) as write:
        authorize(write, Capability.READ, principal)
        settings = write.settings
        rows = write.account_balances(
            as_of=as_of, types=BALANCE_SHEET_TYPES, watermark=watermark
        )
        # Every income and expense balance still standing, whichever year it belongs to. A
        # prior year left unclosed shows up here too, which is correct: those earnings are
        # equity and nothing has moved them yet.
        unclosed = write.account_balances(
            as_of=as_of, types=INCOME_STATEMENT_TYPES, watermark=watermark
        )

    return BalanceSheet(
        as_of=as_of,
        watermark=watermark,
        accounting_basis=settings.accounting_basis,
        functional_currency=settings.functional_currency,
        rows=tuple(rows),
        unclosed=tuple(unclosed),
    )


@dataclass(frozen=True, slots=True)
class AccountDetail:
    """One account's movements over a period (`RPT-05`)."""

    account: Account
    since: date
    as_of: date
    watermark: datetime | None
    accounting_basis: str
    functional_currency: str
    opening_balance: Decimal
    entries: tuple[AccountEntry, ...]

    @property
    def closing_balance(self) -> Decimal:
        """What the account stood at when the period ended."""
        if self.entries:
            return self.entries[-1].running_balance
        return self.opening_balance


def account_detail(
    database: Database,
    *,
    entity_id: str,
    principal: Principal,
    account_id: str,
    since: date,
    as_of: date,
    watermark: datetime | None = None,
) -> AccountDetail:
    """Every posting against `account_id` between two dates, in order (`RPT-05`).

    This is what `RPT-08` resolves down to: from a figure on a statement to the postings that
    produced it, and from a posting to the transaction and the principal that wrote it
    (`LED-20`). Resolving a posting to the rule that assigned it is the other half of `RPT-08`'s
    chain, and belongs with rules rather than here.
    """
    with database.entity_write(entity_id) as write:
        authorize(write, Capability.READ, principal)
        settings = write.settings
        found = write.account(account_id)
        if found is None:
            raise AccountNotFound(f"no account {account_id} in this entity")
        opening, entries = write.account_detail(
            account_id=account_id, since=since, as_of=as_of, watermark=watermark
        )

    return AccountDetail(
        account=found,
        since=since,
        as_of=as_of,
        watermark=watermark,
        accounting_basis=settings.accounting_basis,
        functional_currency=settings.functional_currency,
        opening_balance=opening,
        entries=tuple(entries),
    )


class Comparative(StrEnum):
    """Which period `RPT-07` offers to compare against."""

    PRECEDING = "preceding"
    YEAR_EARLIER = "year_earlier"


@dataclass(frozen=True, slots=True)
class ComparativeProfitAndLoss:
    """One period beside another, and what changed (`RPT-07`)."""

    comparative: Comparative
    current: ProfitAndLoss
    comparison: ProfitAndLoss


def comparative_profit_and_loss(
    database: Database,
    *,
    entity_id: str,
    principal: Principal,
    since: date,
    as_of: date,
    comparative: Comparative,
    watermark: datetime | None = None,
) -> ComparativeProfitAndLoss:
    """A profit and loss beside the preceding period or the same period a year earlier.

    Both halves are the same report over different dates rather than a second query shaped for
    comparison — `RPT-09` wants one answer per question, and a comparative built by different
    machinery than the report it compares could disagree with it.

    The same `watermark` applies to both, so a comparative reproduced later reproduces whole
    (`RPT-11`). Reading the comparison at a different moment from the current period would
    produce a variance that never existed.
    """
    if comparative is Comparative.PRECEDING:
        earlier_since, earlier_as_of = preceding_window(since, as_of)
    else:
        earlier_since, earlier_as_of = year_earlier_window(since, as_of)

    current = profit_and_loss(
        database,
        entity_id=entity_id,
        principal=principal,
        since=since,
        as_of=as_of,
        watermark=watermark,
    )
    comparison = profit_and_loss(
        database,
        entity_id=entity_id,
        principal=principal,
        since=earlier_since,
        as_of=earlier_as_of,
        watermark=watermark,
    )
    return ComparativeProfitAndLoss(
        comparative=comparative, current=current, comparison=comparison
    )
