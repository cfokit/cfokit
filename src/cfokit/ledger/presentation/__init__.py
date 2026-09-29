"""Turning exact recorded values into figures a reader sees (`RPT-12`, ADR-0025).

**Rounding happens here and nowhere else.** ADR-0025: "Rounding happens once, at presentation.
Never to an intermediate, never stored back. A rounding call in `engine`, `repository`, or
`service` means the boundary has been misplaced." So this is its own module rather than a
helper inside one of those — the boundary is visible in the layout, and a rounding call
appearing in the booking path is a diff rather than a judgment.

**A total is computed from the unrounded values and then rounded**, never by summing figures
already rounded. `RPT-12`'s acceptance follows from that and is deliberate: "A column of
displayed figures summed by hand may differ from the printed total by less than one unit of
display scale. The printed total is the correct one."

Pure: no configuration, no I/O. Both adapters call it, which is why it is not inside either.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

from cfokit.ledger.engine.accounts import AccountType, natural_amount
from cfokit.ledger.repository.reports import AccountBalance
from cfokit.ledger.service.reports import (
    AccountDetail,
    BalanceSheet,
    Comparative,
    ComparativeProfitAndLoss,
    ProfitAndLoss,
    TrialBalance,
)

__all__ = [
    "DEFAULT_DISPLAY_SCALE",
    "AccountComparison",
    "ComparativeLine",
    "PresentedAccountDetail",
    "PresentedBalanceSheet",
    "PresentedComparative",
    "PresentedEntry",
    "PresentedProfitAndLoss",
    "PresentedReconciliation",
    "PresentedTrialBalance",
    "SourceBalance",
    "StatementLine",
    "TrialBalanceLine",
    "display_scale",
    "present",
    "present_account_detail",
    "present_balance_sheet",
    "present_comparative_profit_and_loss",
    "present_profit_and_loss",
    "present_reconciliation",
    "present_total",
    "present_trial_balance",
]

DEFAULT_DISPLAY_SCALE = 2
"""Where a commodity's own scale is not known.

ADR-0025 names the registry this stands in for — "USD 2, JPY 0, some currencies 3" — and
defaults to 2 until one exists. Two is right for the currencies CFOKit holds today and wrong
for JPY, which is the cost that record accepted. One function, so a registry replaces it in
one place.
"""


def display_scale(commodity: str) -> int:
    """The number of decimal places `commodity`'s amounts are shown at (`LED-06`)."""
    return DEFAULT_DISPLAY_SCALE


def present(amount: Decimal, commodity: str) -> Decimal:
    """Round one recorded amount to its display scale, half-up (`RPT-12`).

    Half-up rather than banker's rounding: `RPT-12` says so, and it is what a reader checking
    a figure by hand expects. The result is never written back — the recorded amount keeps its
    full precision (`LED-06`).
    """
    places = Decimal(1).scaleb(-display_scale(commodity))
    return amount.quantize(places, rounding=ROUND_HALF_UP)


def present_total(amounts: Iterable[Decimal], commodity: str) -> Decimal:
    """Sum exactly, then round once (`RPT-12`).

    Summing the rounded figures instead would drift by up to half a unit per line, and the
    drift grows with the number of lines — which is exactly the error a trial balance exists
    to make impossible.
    """
    return present(sum(amounts, Decimal(0)), commodity)


@dataclass(frozen=True, slots=True)
class TrialBalanceLine:
    """One line as a reader sees it: an account, and an amount in one of two columns."""

    account_id: str
    code: str
    name: str
    account_type: str
    debit: Decimal | None
    credit: Decimal | None


@dataclass(frozen=True, slots=True)
class PresentedTrialBalance:
    """A trial balance ready to render, with the two columns that must agree."""

    as_of: date
    watermark: datetime | None
    accounting_basis: str
    commodity: str
    lines: tuple[TrialBalanceLine, ...]
    total_debit: Decimal
    total_credit: Decimal

    @property
    def balances(self) -> bool:
        """Whether the two columns agree, which is the whole point of the report."""
        return self.total_debit == self.total_credit


def present_trial_balance(report: TrialBalance) -> PresentedTrialBalance:
    """Split signed balances into debit and credit columns, and round once (`RPT-12`).

    **Sign is the whole of the split.** A positive balance is a debit and a negative one a
    credit, whatever the account's type — that is what a trial balance shows, and it is why the
    two columns agree for any set of balanced transactions rather than because anything checks.

    Both totals are computed from the **unrounded** values and rounded once. Summing the
    displayed figures instead would drift by up to half a unit per line.
    """
    lines: list[TrialBalanceLine] = []
    debits: list[Decimal] = []
    credited: list[Decimal] = []

    for row in report.rows:
        if row.balance > 0:
            debits.append(row.balance)
        else:
            credited.append(-row.balance)
        lines.append(
            TrialBalanceLine(
                account_id=row.account_id,
                code=row.code,
                name=row.name,
                account_type=row.account_type,
                debit=present(row.balance, row.commodity) if row.balance > 0 else None,
                credit=present(-row.balance, row.commodity) if row.balance < 0 else None,
            )
        )

    return PresentedTrialBalance(
        as_of=report.as_of,
        watermark=report.watermark,
        accounting_basis=report.accounting_basis,
        commodity=report.functional_currency,
        lines=tuple(lines),
        total_debit=present_total(debits, report.functional_currency),
        total_credit=present_total(credited, report.functional_currency),
    )


@dataclass(frozen=True, slots=True)
class StatementLine:
    """One line of a statement, signed so positive means more of what the account is."""

    account_id: str
    code: str
    name: str
    account_type: str
    amount: Decimal


@dataclass(frozen=True, slots=True)
class PresentedProfitAndLoss:
    """A profit and loss ready to render (`RPT-02`)."""

    since: date
    as_of: date
    watermark: datetime | None
    accounting_basis: str
    commodity: str
    income: tuple[StatementLine, ...]
    expenses: tuple[StatementLine, ...]
    total_income: Decimal
    total_expenses: Decimal
    net_income: Decimal


@dataclass(frozen=True, slots=True)
class PresentedBalanceSheet:
    """A balance sheet ready to render (`RPT-03`)."""

    as_of: date
    watermark: datetime | None
    accounting_basis: str
    commodity: str
    assets: tuple[StatementLine, ...]
    liabilities: tuple[StatementLine, ...]
    equity: tuple[StatementLine, ...]
    unclosed_earnings: Decimal
    total_assets: Decimal
    total_liabilities: Decimal
    total_equity: Decimal

    @property
    def balances(self) -> bool:
        """Whether the accounting equation holds, which is what the statement asserts."""
        return self.total_assets == self.total_liabilities + self.total_equity


def _line(row: AccountBalance) -> StatementLine:
    return StatementLine(
        account_id=row.account_id,
        code=row.code,
        name=row.name,
        account_type=row.account_type,
        amount=present(
            natural_amount(AccountType(row.account_type), row.balance), row.commodity
        ),
    )


def _natural(rows: Iterable[AccountBalance]) -> list[Decimal]:
    """Exact naturally-signed amounts, for a total that is rounded once (`RPT-12`)."""
    return [natural_amount(AccountType(row.account_type), row.balance) for row in rows]


def present_profit_and_loss(report: ProfitAndLoss) -> PresentedProfitAndLoss:
    """Split income from expenses and total each, rounding once (`RPT-12`).

    Net income is computed from the **unrounded** totals rather than from the two rounded
    figures, so it cannot drift by a unit from the difference a reader takes by hand.
    """
    commodity = report.functional_currency
    income = [row for row in report.rows if row.account_type == "income"]
    expenses = [row for row in report.rows if row.account_type == "expense"]

    return PresentedProfitAndLoss(
        since=report.since,
        as_of=report.as_of,
        watermark=report.watermark,
        accounting_basis=report.accounting_basis,
        commodity=commodity,
        income=tuple(_line(row) for row in income),
        expenses=tuple(_line(row) for row in expenses),
        total_income=present_total(_natural(income), commodity),
        total_expenses=present_total(_natural(expenses), commodity),
        net_income=present_total(
            _natural(income) + [-e for e in _natural(expenses)], commodity
        ),
    )


def present_balance_sheet(report: BalanceSheet) -> PresentedBalanceSheet:
    """Group by type, and carry unclosed earnings into equity (`RPT-03`).

    **Equity includes earnings not yet closed.** `LED-12` moves income and expense to retained
    earnings only at a fiscal year end, so mid-year those balances are equity that has not been
    moved. Leaving them out would make the statement fail to balance by exactly that amount,
    which is a bug that looks like an accounting error.
    """
    commodity = report.functional_currency
    assets = [row for row in report.rows if row.account_type == "asset"]
    liabilities = [row for row in report.rows if row.account_type == "liability"]
    equity = [row for row in report.rows if row.account_type == "equity"]

    # Income is credit-normal and expense debit-normal, so naturally-signed income less
    # expenses is the earnings figure equity is short by.
    unclosed_exact = [
        natural_amount(AccountType(row.account_type), row.balance)
        if row.account_type == "income"
        else -natural_amount(AccountType(row.account_type), row.balance)
        for row in report.unclosed
    ]

    return PresentedBalanceSheet(
        as_of=report.as_of,
        watermark=report.watermark,
        accounting_basis=report.accounting_basis,
        commodity=commodity,
        assets=tuple(_line(row) for row in assets),
        liabilities=tuple(_line(row) for row in liabilities),
        equity=tuple(_line(row) for row in equity),
        unclosed_earnings=present_total(unclosed_exact, commodity),
        total_assets=present_total(_natural(assets), commodity),
        total_liabilities=present_total(_natural(liabilities), commodity),
        total_equity=present_total(_natural(equity) + unclosed_exact, commodity),
    )


@dataclass(frozen=True, slots=True)
class PresentedEntry:
    """One movement against an account, with what it left the balance at."""

    transaction_id: str
    transaction_date: date
    description: str | None
    entry_kind: str
    reverses_id: str | None
    actor_principal_id: str
    actor_class: str
    acting_for_principal_id: str | None
    amount: Decimal
    running_balance: Decimal


@dataclass(frozen=True, slots=True)
class PresentedAccountDetail:
    """An account's movements over a period, ready to render (`RPT-05`)."""

    account_id: str
    code: str
    name: str
    account_type: str
    since: date
    as_of: date
    watermark: datetime | None
    accounting_basis: str
    commodity: str
    opening_balance: Decimal
    closing_balance: Decimal
    entries: tuple[PresentedEntry, ...]


def present_account_detail(report: AccountDetail) -> PresentedAccountDetail:
    """Sign the movements the way the account's type reads, and round each once (`RPT-12`).

    Every figure — each movement, each running balance, both ends — is rounded from its own
    exact value rather than accumulated from rounded ones, so a reader adding the column gets
    the last running balance to within less than one unit of display scale.
    """
    commodity = report.functional_currency
    account_type = AccountType(report.account.account_type)
    return PresentedAccountDetail(
        account_id=report.account.account_id,
        code=report.account.code,
        name=report.account.name,
        account_type=account_type.value,
        since=report.since,
        as_of=report.as_of,
        watermark=report.watermark,
        accounting_basis=report.accounting_basis,
        commodity=commodity,
        opening_balance=present(
            natural_amount(account_type, report.opening_balance), commodity
        ),
        closing_balance=present(
            natural_amount(account_type, report.closing_balance), commodity
        ),
        entries=tuple(
            PresentedEntry(
                transaction_id=entry.transaction_id,
                transaction_date=entry.transaction_date,
                description=entry.description,
                entry_kind=entry.entry_kind,
                reverses_id=entry.reverses_id,
                actor_principal_id=entry.actor_principal_id,
                actor_class=entry.actor_class,
                acting_for_principal_id=entry.acting_for_principal_id,
                amount=present(natural_amount(account_type, entry.amount), commodity),
                running_balance=present(
                    natural_amount(account_type, entry.running_balance), commodity
                ),
            )
            for entry in report.entries
        ),
    )


@dataclass(frozen=True, slots=True)
class ComparativeLine:
    """One account across two periods, and what changed between them."""

    account_id: str
    code: str
    name: str
    account_type: str
    current: Decimal
    comparison: Decimal
    variance: Decimal


@dataclass(frozen=True, slots=True)
class PresentedComparative:
    """A profit and loss beside another period (`RPT-07`)."""

    comparative: Comparative
    since: date
    as_of: date
    comparison_since: date
    comparison_as_of: date
    watermark: datetime | None
    accounting_basis: str
    commodity: str
    income: tuple[ComparativeLine, ...]
    expenses: tuple[ComparativeLine, ...]
    total_income: ComparativeLine
    total_expenses: ComparativeLine
    net_income: ComparativeLine


def _totals_line(
    code: str,
    name: str,
    account_type: str,
    current: list[Decimal],
    comparison: list[Decimal],
    commodity: str,
) -> ComparativeLine:
    """A totals row, each figure summed exactly and rounded once (`RPT-12`)."""
    return ComparativeLine(
        account_id="",
        code=code,
        name=name,
        account_type=account_type,
        current=present_total(current, commodity),
        comparison=present_total(comparison, commodity),
        variance=present_total(current + [-c for c in comparison], commodity),
    )


def present_comparative_profit_and_loss(
    report: ComparativeProfitAndLoss,
) -> PresentedComparative:
    """Pair the two periods by account and show what changed (`RPT-07`).

    **An account absent from one period counts as zero there**, not as a missing row. A cost
    that started this quarter and a revenue stream that stopped are exactly what a reader is
    looking for, and dropping either would hide the largest variances on the page.

    **The variance is computed from the unrounded figures**, not by subtracting the two printed
    ones, for the same reason every other total is (`RPT-12`).

    Absolute only. A percentage divides by the comparison figure, which is zero for every line
    that is new — the lines a reader most wants — so it belongs where a renderer can decide
    what to show instead of a number.
    """
    commodity = report.current.functional_currency

    def by_account(rows: Iterable[AccountBalance]) -> dict[str, AccountBalance]:
        return {row.account_id: row for row in rows}

    def lines(account_type: str) -> tuple[ComparativeLine, ...]:
        current = by_account(r for r in report.current.rows if r.account_type == account_type)
        comparison = by_account(
            r for r in report.comparison.rows if r.account_type == account_type
        )
        paired: list[ComparativeLine] = []
        for account_id in sorted(
            current | comparison, key=lambda key: (current | comparison)[key].code
        ):
            row = current.get(account_id) or comparison[account_id]
            now = _exact(current.get(account_id))
            then = _exact(comparison.get(account_id))
            paired.append(
                ComparativeLine(
                    account_id=account_id,
                    code=row.code,
                    name=row.name,
                    account_type=row.account_type,
                    current=present(now, commodity),
                    comparison=present(then, commodity),
                    variance=present(now - then, commodity),
                )
            )
        return tuple(paired)

    income, expenses = lines("income"), lines("expense")
    current_income = [_exact(r) for r in report.current.rows if r.account_type == "income"]
    prior_income = [_exact(r) for r in report.comparison.rows if r.account_type == "income"]
    current_expense = [_exact(r) for r in report.current.rows if r.account_type == "expense"]
    prior_expense = [_exact(r) for r in report.comparison.rows if r.account_type == "expense"]

    return PresentedComparative(
        comparative=report.comparative,
        since=report.current.since,
        as_of=report.current.as_of,
        comparison_since=report.comparison.since,
        comparison_as_of=report.comparison.as_of,
        watermark=report.current.watermark,
        accounting_basis=report.current.accounting_basis,
        commodity=commodity,
        income=income,
        expenses=expenses,
        total_income=_totals_line(
            "", "Total income", "income", current_income, prior_income, commodity
        ),
        total_expenses=_totals_line(
            "", "Total expenses", "expense", current_expense, prior_expense, commodity
        ),
        net_income=_totals_line(
            "",
            "Net income",
            "income",
            current_income + [-e for e in current_expense],
            prior_income + [-e for e in prior_expense],
            commodity,
        ),
    )


def _exact(row: AccountBalance | None) -> Decimal:
    """A row's naturally-signed amount, or zero where the account has no row this period."""
    if row is None:
        return Decimal(0)
    return natural_amount(AccountType(row.account_type), row.balance)


# --- Reconciliation against a source system (`IMP-08`, `NFR-01`) --------------------------
#
# > `IMP-08`: "An import produces a reconciliation the operator can check against the source
# > system — balances by account, and totals by period — so that agreement is demonstrated
# > rather than assumed."
#
# Its acceptance is deliberately small: "The operator compares two figures per account and
# either agrees the import or rejects it." So this reports two figures and a difference, and
# says nothing about what a difference *means*. A comparison detects difference; it cannot say
# which side is wrong (ADR-0010), and deciding that in the tool would take a judgment that
# belongs to a person.
#
# **It lives here, not in `service`, because it compares figures a reader sees.** Where a
# source's own figures are already rounded — most exports are — both sides round once before
# comparing, and rounding happens only at presentation (ADR-0025). Putting it in the service
# layer put a rounding call below that boundary; `import-linter` refused it, correctly.
#
# **No tolerance.** `NFR-01`'s ledger target: "Exactness, not accuracy within a tolerance. A
# tolerance is a defect, not a target." A reconciliation that passes within a penny will one
# day hide a penny that mattered.


@dataclass(frozen=True, slots=True)
class SourceBalance:
    """One account's balance as a source system states it.

    Signed the way a posting is signed: positive is a debit. A converter from a foreign export
    is responsible for that translation and for nothing else.
    """

    account_code: str
    balance: Decimal


@dataclass(frozen=True, slots=True)
class AccountComparison:
    """Two figures for one account, and what separates them."""

    account_code: str
    ours: Decimal | None
    theirs: Decimal | None
    difference: Decimal

    @property
    def agrees(self) -> bool:
        return self.difference == 0 and self.ours is not None and self.theirs is not None

    @property
    def only_ours(self) -> bool:
        return self.theirs is None

    @property
    def only_theirs(self) -> bool:
        return self.ours is None


@dataclass(frozen=True, slots=True)
class PresentedReconciliation:
    """The comparison in full, and whether it agreed."""

    as_of: date
    watermark: datetime | None
    accounting_basis: str
    commodity: str
    source_is_rounded: bool
    comparisons: tuple[AccountComparison, ...]

    @property
    def disagreements(self) -> tuple[AccountComparison, ...]:
        return tuple(comparison for comparison in self.comparisons if not comparison.agrees)

    @property
    def agrees(self) -> bool:
        return not self.disagreements


def present_reconciliation(
    report: TrialBalance,
    source: Iterable[SourceBalance],
    *,
    source_is_rounded: bool = False,
) -> PresentedReconciliation:
    """Compare our trial balance against a source system's own figures, account by account.

    **Matched by account code, never by name.** Names get edited; codes are what two systems
    agree on.

    **An account on one side only is reported, not dropped.** `NFR-01` resolves disagreements
    rather than tolerating them, and an account silently missing from one side is the most
    tolerable-looking disagreement there is — so it differs by the whole of the side it is on,
    and never reads as zero.
    """
    commodity = report.functional_currency

    def at_scale(amount: Decimal | None) -> Decimal | None:
        if amount is None:
            return None
        return present(amount, commodity) if source_is_rounded else amount

    mine = {row.code: row.balance for row in report.rows}
    theirs = {balance.account_code: balance.balance for balance in source}

    comparisons: list[AccountComparison] = []
    for code in sorted(mine.keys() | theirs.keys()):
        ours, other = at_scale(mine.get(code)), at_scale(theirs.get(code))
        comparisons.append(
            AccountComparison(
                account_code=code,
                ours=ours,
                theirs=other,
                difference=(ours or Decimal(0)) - (other or Decimal(0)),
            )
        )

    return PresentedReconciliation(
        as_of=report.as_of,
        watermark=report.watermark,
        accounting_basis=report.accounting_basis,
        commodity=commodity,
        source_is_rounded=source_is_rounded,
        comparisons=tuple(comparisons),
    )
