"""Which account carries an obligation (`LED-17`, ADR-0059 § 3), with no infrastructure.

Each expected account is read off the entry by hand: the one account whose postings sum to the
obligation's amount, signed as a posting — a receivable a debit, a payable a credit.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from cfokit.ledger.engine import Entry, Posting, carrying_account

RECEIVABLE = "1200"
PAYABLE = "2000"
REVENUE = "4000"
TAX = "2200"
EXPENSE = "6000"
DEPOSITS = "1300"


def entry(*legs: tuple[str, str]) -> Entry:
    return Entry(
        transaction_date=date(2026, 3, 14),
        postings=tuple(Posting(account, Decimal(amount), "USD") for account, amount in legs),
    )


def test_an_invoice_is_carried_by_its_receivable() -> None:
    """AR-03's entry: income credited, receivables debited. The debit is the obligation."""
    invoice = entry((RECEIVABLE, "100.00"), (REVENUE, "-100.00"))

    assert carrying_account(invoice, Decimal("100.00"), "USD") == RECEIVABLE


def test_an_invoice_with_tax_is_carried_by_the_whole_receivable() -> None:
    invoice = entry((RECEIVABLE, "110.00"), (REVENUE, "-100.00"), (TAX, "-10.00"))

    assert carrying_account(invoice, Decimal("110.00"), "USD") == RECEIVABLE


def test_a_bill_is_carried_by_its_payable_as_a_credit() -> None:
    bill = entry((EXPENSE, "45.50"), (PAYABLE, "-45.50"))

    assert carrying_account(bill, Decimal("-45.50"), "USD") == PAYABLE
    # Unsigned, the figure is the expense's debit, which is not what is owed.
    assert carrying_account(bill, Decimal("45.50"), "USD") == EXPENSE


def test_postings_on_one_account_are_summed() -> None:
    split = entry((RECEIVABLE, "60.00"), (RECEIVABLE, "40.00"), (REVENUE, "-100.00"))

    assert carrying_account(split, Decimal("100"), "USD") == RECEIVABLE


def test_two_accounts_carrying_the_figure_name_neither() -> None:
    """Which one is owed is unstated, and choosing would be a guess."""
    both = entry((RECEIVABLE, "100.00"), (DEPOSITS, "100.00"), (REVENUE, "-200.00"))

    assert carrying_account(both, Decimal("100.00"), "USD") is None


def test_no_account_carrying_the_figure_names_none() -> None:
    invoice = entry((RECEIVABLE, "100.00"), (REVENUE, "-100.00"))

    assert carrying_account(invoice, Decimal("90.00"), "USD") is None
    assert carrying_account(invoice, Decimal("100.00"), "EUR") is None
