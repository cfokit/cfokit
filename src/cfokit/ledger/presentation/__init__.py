"""Turning exact recorded values into figures a reader sees (`RPT-12`, ADR-0025).

**Rounding happens here and nowhere else.** ADR-0025: "Rounding happens once, at presentation.
Never to an intermediate, never stored back. A rounding call in `engine`, `repository`, or
`service` means the boundary has been misplaced." So this is its own module rather than a
helper inside one of those — the boundary is visible in the layout, and a rounding call
appearing in the booking path is a diff rather than a judgement.

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

from cfokit.ledger.service.reports import TrialBalance

__all__ = [
    "DEFAULT_DISPLAY_SCALE",
    "PresentedTrialBalance",
    "TrialBalanceLine",
    "display_scale",
    "present",
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
