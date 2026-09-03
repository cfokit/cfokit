"""Rounding, and where it happens (`RPT-12`, ADR-0025).

> "Rounding happens once, at presentation. Never to an intermediate, never stored back."

Pure: no database, no entity, no configuration. What is asserted is the arithmetic a reader
depends on when they check a column by hand.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from cfokit.ledger.presentation import present, present_total, present_trial_balance
from cfokit.ledger.repository.reports import AccountBalance
from cfokit.ledger.service.reports import TrialBalance

AMOUNTS = st.decimals(
    min_value=Decimal("-1e6"),
    max_value=Decimal("1e6"),
    allow_nan=False,
    allow_infinity=False,
    places=10,
)


def test_a_figure_is_rounded_half_up() -> None:
    """`RPT-12` says half-up, not banker's rounding: it is what a reader checking by hand
    expects, and the difference shows on exactly the figures they are most likely to check."""
    assert present(Decimal("2.345"), "USD") == Decimal("2.35")
    assert present(Decimal("2.355"), "USD") == Decimal("2.36")
    # Banker's rounding would give 2.34 and 2.36.


def test_rounding_a_negative_figure_goes_away_from_zero() -> None:
    """Half-up on the magnitude, so a credit rounds the way the matching debit would."""
    assert present(Decimal("-2.345"), "USD") == Decimal("-2.35")


def test_a_figure_already_at_scale_is_unchanged() -> None:
    assert present(Decimal("100.00"), "USD") == Decimal("100.00")


def test_a_total_is_computed_unrounded_then_rounded() -> None:
    """`RPT-12`'s whole point, and the reason it is stated as a requirement at all.

    Three figures of 0.004 display as 0.00 each. Summing what is displayed gives 0.00; summing
    exactly and rounding once gives 0.01, which is the correct total.
    """
    parts = [Decimal("0.004")] * 3

    assert sum(present(p, "USD") for p in parts) == Decimal("0.00")
    assert present_total(parts, "USD") == Decimal("0.01")


def test_an_empty_total_is_zero_at_scale() -> None:
    assert present_total([], "USD") == Decimal("0.00")


@given(st.lists(AMOUNTS, max_size=40))
def test_a_total_never_drifts_further_than_half_a_unit(amounts: list[Decimal]) -> None:
    """`RPT-12`'s acceptance, as a property: "A column of displayed figures summed by hand may
    differ from the printed total by less than one unit of display scale.\""""
    printed = present_total(amounts, "USD")
    by_hand = sum((present(a, "USD") for a in amounts), Decimal(0))

    assert abs(printed - by_hand) <= Decimal("0.005") * max(len(amounts), 1)
    # And the printed total is the one that matches the exact arithmetic.
    assert abs(printed - sum(amounts, Decimal(0))) <= Decimal("0.005")


# --- The trial balance's two columns ------------------------------------------------------


def balance(code: str, amount: str, account_type: str = "asset") -> AccountBalance:
    return AccountBalance(
        account_id=f"id-{code}",
        code=code,
        name=f"Account {code}",
        account_type=account_type,
        commodity="USD",
        balance=Decimal(amount),
    )


def report(*rows: AccountBalance) -> TrialBalance:
    return TrialBalance(
        as_of=date(2026, 9, 1),
        watermark=None,
        accounting_basis="accrual",
        functional_currency="USD",
        rows=rows,
    )


def test_sign_decides_the_column() -> None:
    """A positive balance is a debit and a negative one a credit, whatever the account's type.

    That is what a trial balance shows, and it is why the columns agree for any set of
    balanced transactions rather than because anything checks them.
    """
    presented = present_trial_balance(
        report(balance("1000", "100.00"), balance("4000", "-100.00", "income"))
    )

    assert [(line.code, line.debit, line.credit) for line in presented.lines] == [
        ("1000", Decimal("100.00"), None),
        ("4000", None, Decimal("100.00")),
    ]


def test_balanced_postings_produce_agreeing_columns() -> None:
    presented = present_trial_balance(
        report(balance("1000", "100.00"), balance("4000", "-100.00", "income"))
    )

    assert presented.total_debit == presented.total_credit == Decimal("100.00")
    assert presented.balances is True


def test_the_totals_survive_figures_that_do_not_divide_evenly() -> None:
    """Three thirds of a penny on each side: the columns still agree, because both are summed
    exactly before either is rounded."""
    third = "0.0033333333"
    presented = present_trial_balance(
        report(
            balance("1000", third),
            balance("1001", third),
            balance("1002", third),
            balance("4000", f"-{third}", "income"),
            balance("4001", f"-{third}", "income"),
            balance("4002", f"-{third}", "income"),
        )
    )

    assert presented.total_debit == presented.total_credit == Decimal("0.01")
    assert presented.balances is True
    # Every line displays as zero, and the totals do not.
    assert all(
        line.debit == Decimal("0.00") or line.credit == Decimal("0.00")
        for line in presented.lines
    )


def test_the_basis_is_carried_onto_the_report() -> None:
    """`RPT-10`: every report states the basis it was produced on, on its face."""
    assert present_trial_balance(report(balance("1000", "1.00"))).accounting_basis == "accrual"


def test_an_empty_trial_balance_still_balances() -> None:
    """An entity that has posted nothing has a report, not an error."""
    presented = present_trial_balance(report())

    assert presented.lines == ()
    assert presented.balances is True
