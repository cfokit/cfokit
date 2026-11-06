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

**A cash-basis entity's reports are its cash view** (`AR-16`, ADR-0080). The postings are the
same on either basis (ADR-0037); where the entity declares cash, every balance-presenting
report here adds the adjustments `engine.cash` derives from the stored obligation-to-settlement
links, and states on its face what no link reached (`NFR-16`). This is the one place the
declared basis changes a figure, and no posting path reads it. The journal total is the record
rather than a view of it, and stays posted figures on every basis (ADR-0080 § 4).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from cfokit.ledger.engine import Adjustment, cash_adjustments
from cfokit.ledger.engine.periods import preceding_window, year_earlier_window
from cfokit.ledger.errors import AccountNotFound
from cfokit.ledger.repository import reports as store
from cfokit.ledger.repository.cash import Unlinked
from cfokit.ledger.repository.reports import Account, AccountBalance, AccountEntry
from cfokit.ledger.repository.unit_of_work import Database, EntityWrite
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
    "Unlinked",
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
    # What a cash-basis report presents as posted (ADR-0080 § 3). None on an accrual basis.
    unlinked: Unlinked | None = None


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
        unlinked = None
        if settings.accounting_basis == "cash":
            cash = _Cash.read(write, watermark)
            rows = cash.balances(rows, as_of=as_of)
            unlinked = write.unlinked(as_of=as_of, watermark=watermark)

    return TrialBalance(
        as_of=as_of,
        watermark=watermark,
        accounting_basis=settings.accounting_basis,
        functional_currency=settings.functional_currency,
        rows=tuple(rows),
        unlinked=unlinked,
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
    unlinked: Unlinked | None = None


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
    unlinked: Unlinked | None = None


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
        unlinked = None
        if settings.accounting_basis == "cash":
            cash = _Cash.read(write, watermark)
            rows = cash.balances(rows, as_of=as_of, since=since, types=INCOME_STATEMENT_TYPES)
            unlinked = write.unlinked(as_of=as_of, since=since, watermark=watermark)

    return ProfitAndLoss(
        since=since,
        as_of=as_of,
        watermark=watermark,
        accounting_basis=settings.accounting_basis,
        functional_currency=settings.functional_currency,
        rows=tuple(rows),
        unlinked=unlinked,
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
        unlinked = None
        if settings.accounting_basis == "cash":
            cash = _Cash.read(write, watermark)
            rows = cash.balances(rows, as_of=as_of, types=BALANCE_SHEET_TYPES)
            unclosed = cash.balances(unclosed, as_of=as_of, types=INCOME_STATEMENT_TYPES)
            unlinked = write.unlinked(as_of=as_of, watermark=watermark)

    return BalanceSheet(
        as_of=as_of,
        watermark=watermark,
        accounting_basis=settings.accounting_basis,
        functional_currency=settings.functional_currency,
        rows=tuple(rows),
        unclosed=tuple(unclosed),
        unlinked=unlinked,
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
    unlinked: Unlinked | None = None

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
        unlinked = None
        if settings.accounting_basis == "cash":
            cash = _Cash.read(write, watermark)
            opening, entries = cash.detail(
                write,
                account_id=account_id,
                opening=opening,
                entries=entries,
                since=since,
                as_of=as_of,
            )
            unlinked = write.unlinked(as_of=as_of, since=since, watermark=watermark)

    return AccountDetail(
        account=found,
        since=since,
        as_of=as_of,
        watermark=watermark,
        accounting_basis=settings.accounting_basis,
        functional_currency=settings.functional_currency,
        opening_balance=opening,
        entries=tuple(entries),
        unlinked=unlinked,
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


class _Cash:
    """The cash view of one entity's books, as a report needs it (ADR-0080 § 4).

    Read once per report, because every figure in it depends on every link: a settlement's
    share turns on the settlements of its obligation before it, whatever their dates. A report
    then takes the adjustments its own window and types include.
    """

    def __init__(self, adjustments: Sequence[Adjustment], chart: dict[str, Account]) -> None:
        self._adjustments = adjustments
        self._chart = chart

    @classmethod
    def read(cls, write: EntityWrite, watermark: datetime | None) -> _Cash:
        found = write.cash_links(watermark=watermark)
        adjustments = cash_adjustments(found.raised, found.settled, found.reversals)
        return cls(adjustments, {account.account_id: account for account in write.chart()})

    def _within(self, since: date | None, as_of: date) -> Iterable[Adjustment]:
        return (
            adjustment
            for adjustment in self._adjustments
            if adjustment.transaction_date <= as_of
            and (since is None or adjustment.transaction_date >= since)
        )

    def balances(
        self,
        rows: Iterable[AccountBalance],
        *,
        as_of: date,
        since: date | None = None,
        types: tuple[str, ...] | None = None,
    ) -> list[AccountBalance]:
        """The posted balances with the cash view's adjustments added, in the same order.

        An account the adjustments bring to zero is omitted, and one they give a balance is
        listed, exactly as a posted balance would be (`RPT-01`).
        """
        totals: dict[tuple[str, str], Decimal] = {
            (row.account_id, row.commodity): row.balance for row in rows
        }
        for adjustment in self._within(since, as_of):
            account = self._chart[adjustment.account_id]
            if types is not None and account.account_type not in types:
                continue
            key = (adjustment.account_id, adjustment.commodity)
            totals[key] = totals.get(key, Decimal(0)) + adjustment.amount

        balances = [
            AccountBalance(
                account_id=account_id,
                code=self._chart[account_id].code,
                name=self._chart[account_id].name,
                account_type=self._chart[account_id].account_type,
                commodity=commodity,
                balance=balance,
            )
            for (account_id, commodity), balance in totals.items()
            if balance != 0
        ]
        return sorted(balances, key=lambda row: (row.code, row.commodity))

    def detail(
        self,
        write: EntityWrite,
        *,
        account_id: str,
        opening: Decimal,
        entries: Sequence[AccountEntry],
        since: date,
        as_of: date,
    ) -> tuple[Decimal, list[AccountEntry]]:
        """One account's movements on the cash basis, with the running balance recomputed.

        A transaction the cash view changes on this account reads as one movement: what it
        posted here plus what the view adds. An invoice's receivable and a payment's credit to
        it come to nothing, and are not shown; a payment's share of an income line is shown as
        the payment, on its date (`RPT-08`: the figure resolves to what moved the cash).
        """
        mine = [a for a in self._adjustments if a.account_id == account_id]
        opening += sum((a.amount for a in mine if a.transaction_date < since), start=Decimal(0))
        changed: defaultdict[str, Decimal] = defaultdict(Decimal)
        commodity: dict[str, str] = {}
        for adjustment in self._within(since, as_of):
            if adjustment.account_id == account_id:
                changed[adjustment.transaction_id] += adjustment.amount
                commodity[adjustment.transaction_id] = adjustment.commodity
        for entry in entries:
            if entry.transaction_id in changed:
                changed[entry.transaction_id] += entry.amount

        headers = write.transaction_headers(
            sorted(set(changed) | {entry.transaction_id for entry in entries})
        )
        ordered: list[tuple[tuple[date, datetime, str, int], AccountEntry]] = []
        for position, entry in enumerate(entries):
            if entry.transaction_id in changed:
                continue
            header = headers[entry.transaction_id]
            key = (header.transaction_date, header.posted_at, header.transaction_id, position)
            ordered.append((key, entry))
        for transaction_id, amount in changed.items():
            if amount == 0:
                continue
            header = headers[transaction_id]
            movement = AccountEntry(
                transaction_id=transaction_id,
                transaction_date=header.transaction_date,
                description=header.description,
                entry_kind=header.entry_kind,
                reverses_id=header.reverses_id,
                actor_principal_id=header.actor_principal_id,
                actor_class=header.actor_class,
                acting_for_principal_id=header.acting_for_principal_id,
                amount=amount,
                commodity=commodity[transaction_id],
                running_balance=Decimal(0),
            )
            key = (header.transaction_date, header.posted_at, transaction_id, 0)
            ordered.append((key, movement))

        running = opening
        result: list[AccountEntry] = []
        for _, entry in sorted(ordered, key=lambda pair: pair[0]):
            running += entry.amount
            result.append(replace(entry, running_balance=running))
        return opening, result
