"""Account types, and the two things `LED-02` says a type determines.

> "Every account has a type — asset, liability, equity, income, or expense — fixed when the
> account is created. The type determines which statement the account appears on and the sign
> convention applied to it."

Both of those are total functions of the type and nothing else, so they live here as
lookups rather than as branches scattered through reporting code.
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

__all__ = [
    "AccountType",
    "NormalBalance",
    "Statement",
    "increases",
    "normal_balance",
    "statement",
]


class AccountType(StrEnum):
    """The five types, matching the schema's CHECK constraint exactly."""

    ASSET = "asset"
    LIABILITY = "liability"
    EQUITY = "equity"
    INCOME = "income"
    EXPENSE = "expense"


class NormalBalance(StrEnum):
    """The side on which an account of a given type carries a positive balance."""

    DEBIT = "debit"
    CREDIT = "credit"


class Statement(StrEnum):
    """Which statement an account appears on (`LED-02`)."""

    BALANCE_SHEET = "balance_sheet"
    INCOME_STATEMENT = "income_statement"


# Assets and expenses are debit-normal; everything else is credit-normal. This is the
# accounting equation, not a convention we chose, so it is a constant rather than a setting.
_DEBIT_NORMAL = frozenset({AccountType.ASSET, AccountType.EXPENSE})

# Income and expense close to retained earnings at year end (`LED-12`), which is the same
# division as the one between the two statements.
_INCOME_STATEMENT = frozenset({AccountType.INCOME, AccountType.EXPENSE})


def normal_balance(account_type: AccountType) -> NormalBalance:
    """The side on which this type carries a positive balance."""
    if account_type in _DEBIT_NORMAL:
        return NormalBalance.DEBIT
    return NormalBalance.CREDIT


def statement(account_type: AccountType) -> Statement:
    """Which statement an account of this type appears on (`LED-02`)."""
    if account_type in _INCOME_STATEMENT:
        return Statement.INCOME_STATEMENT
    return Statement.BALANCE_SHEET


def increases(account_type: AccountType, amount: Decimal) -> bool:
    """Whether a signed posting amount increases the account in its natural direction.

    Postings are signed with positive meaning debit (see `entry.Posting`), so a debit-normal
    account grows on a positive amount and a credit-normal account grows on a negative one.
    An amount of zero increases nothing.

    This is what a report needs to present a credit-normal balance as a positive figure
    without every caller re-deriving the sign rule.
    """
    if amount == 0:
        return False
    if normal_balance(account_type) is NormalBalance.DEBIT:
        return amount > 0
    return amount < 0
