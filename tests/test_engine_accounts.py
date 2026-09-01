"""Account type determines the statement and the sign convention (`LED-02`)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from cfokit.ledger.engine import (
    AccountType,
    NormalBalance,
    Statement,
    increases,
    normal_balance,
    statement,
)


@pytest.mark.parametrize(
    ("account_type", "expected"),
    [
        (AccountType.ASSET, NormalBalance.DEBIT),
        (AccountType.EXPENSE, NormalBalance.DEBIT),
        (AccountType.LIABILITY, NormalBalance.CREDIT),
        (AccountType.EQUITY, NormalBalance.CREDIT),
        (AccountType.INCOME, NormalBalance.CREDIT),
    ],
)
def test_normal_balance(account_type: AccountType, expected: NormalBalance) -> None:
    """Assets and expenses are debit-normal; the rest are credit-normal.

    This is the accounting equation rather than a convention CFOKit picked, which is why it
    is a constant and not configuration.
    """
    assert normal_balance(account_type) is expected


@pytest.mark.parametrize(
    ("account_type", "expected"),
    [
        (AccountType.ASSET, Statement.BALANCE_SHEET),
        (AccountType.LIABILITY, Statement.BALANCE_SHEET),
        (AccountType.EQUITY, Statement.BALANCE_SHEET),
        (AccountType.INCOME, Statement.INCOME_STATEMENT),
        (AccountType.EXPENSE, Statement.INCOME_STATEMENT),
    ],
)
def test_statement(account_type: AccountType, expected: Statement) -> None:
    assert statement(account_type) is expected


def test_the_accounts_that_close_at_year_end_are_the_income_statement_ones() -> None:
    """`LED-12` closes income and expense to retained earnings, which is the same division
    as the one between the two statements. Stated as a test so the two cannot drift."""
    closing = {t for t in AccountType if statement(t) is Statement.INCOME_STATEMENT}

    assert closing == {AccountType.INCOME, AccountType.EXPENSE}


def test_the_five_types_match_the_schema() -> None:
    """The CHECK constraint in 0001 enumerates exactly these (`LED-02`)."""
    assert {t.value for t in AccountType} == {
        "asset",
        "liability",
        "equity",
        "income",
        "expense",
    }


@pytest.mark.parametrize(
    ("account_type", "amount", "expected"),
    [
        (AccountType.ASSET, "100.00", True),
        (AccountType.ASSET, "-100.00", False),
        (AccountType.EXPENSE, "100.00", True),
        (AccountType.INCOME, "-100.00", True),
        (AccountType.INCOME, "100.00", False),
        (AccountType.LIABILITY, "-100.00", True),
        (AccountType.EQUITY, "-100.00", True),
    ],
)
def test_increases(account_type: AccountType, amount: str, expected: bool) -> None:
    """Positive is a debit, so a debit-normal account grows on a positive amount."""
    assert increases(account_type, Decimal(amount)) is expected


@pytest.mark.parametrize("account_type", list(AccountType))
def test_zero_increases_nothing(account_type: AccountType) -> None:
    assert increases(account_type, Decimal("0")) is False
