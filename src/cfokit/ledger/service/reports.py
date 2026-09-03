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
from datetime import UTC, date, datetime
from decimal import Decimal

from cfokit.ledger.errors import AccountNotFound
from cfokit.ledger.repository.reports import Account, AccountBalance, AccountEntry
from cfokit.ledger.repository.unit_of_work import Database, EntityWrite
from cfokit.ledger.service.authorisation import Capability, require
from cfokit.ledger.service.principal import Principal

__all__ = [
    "AccountDetail",
    "BalanceSheet",
    "ProfitAndLoss",
    "TrialBalance",
    "account_detail",
    "balance_sheet",
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
        _require_read(write, principal)
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
        _require_read(write, principal)
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
        _require_read(write, principal)
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


def _require_read(write: EntityWrite, principal: Principal) -> None:
    now = datetime.now(UTC)
    actor = write.privileges_in_force(principal.id, now)
    acted_for = (
        write.privileges_in_force(principal.acting_for, now)
        if principal.acting_for is not None
        else frozenset()
    )
    require(Capability.READ, principal, actor, acted_for)


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
        _require_read(write, principal)
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
