"""Corrections are reversing entries, and their dating follows the period state.

`LED-08`, ADR-0007 (reversal is a first-class operation), ADR-0030 § 4 (dating).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from cfokit.ledger.engine import (
    Entry,
    Posting,
    build_reversal,
    is_balanced,
    totals_by_commodity,
)

MARCH = date(2026, 3, 15)
SEPTEMBER = date(2026, 9, 1)


def original() -> Entry:
    return Entry(
        transaction_date=MARCH,
        postings=(
            Posting(account_id="cash", amount=Decimal("100.00"), commodity="USD"),
            Posting(account_id="revenue", amount=Decimal("-100.00"), commodity="USD"),
        ),
        description="Invoice 1001",
    )


def test_every_posting_is_negated() -> None:
    reversal = build_reversal(
        original(),
        reverses_id="txn-1",
        original_period_closed=False,
        current_period_date=SEPTEMBER,
    )

    assert [p.amount for p in reversal.postings] == [Decimal("-100.00"), Decimal("100.00")]
    assert [p.account_id for p in reversal.postings] == ["cash", "revenue"]


def test_a_reversal_is_itself_balanced() -> None:
    reversal = build_reversal(
        original(),
        reverses_id="txn-1",
        original_period_closed=False,
        current_period_date=SEPTEMBER,
    )

    assert is_balanced(reversal.postings)


def test_the_pair_nets_to_exactly_zero() -> None:
    """ADR-0036 names this invariant: a reversal restores the prior balance exactly."""
    entry = original()
    reversal = build_reversal(
        entry,
        reverses_id="txn-1",
        original_period_closed=False,
        current_period_date=SEPTEMBER,
    )

    combined = totals_by_commodity([*entry.postings, *reversal.postings])

    assert combined == {"USD": Decimal("0")}


def test_the_reversal_says_what_it_reverses() -> None:
    """ADR-0007: both entries stay visible, and the link is what makes the pair legible."""
    reversal = build_reversal(
        original(),
        reverses_id="txn-1",
        original_period_closed=False,
        current_period_date=SEPTEMBER,
    )

    assert reversal.reverses_id == "txn-1"


def test_the_original_is_not_mutated() -> None:
    """`LED-08`: "no field of the original has changed"."""
    entry = original()
    build_reversal(
        entry,
        reverses_id="txn-1",
        original_period_closed=False,
        current_period_date=SEPTEMBER,
    )

    assert entry.transaction_date == MARCH
    assert entry.postings[0].amount == Decimal("100.00")
    assert entry.reverses_id is None


def test_open_period_reversal_takes_the_original_date() -> None:
    """ADR-0030 § 4: the correction lands where the error was, so March comes out right."""
    reversal = build_reversal(
        original(),
        reverses_id="txn-1",
        original_period_closed=False,
        current_period_date=SEPTEMBER,
    )

    assert reversal.transaction_date == MARCH


def test_closed_period_reversal_defaults_to_the_current_period() -> None:
    """Posting into a closed period is not something a correction does quietly."""
    reversal = build_reversal(
        original(),
        reverses_id="txn-1",
        original_period_closed=True,
        current_period_date=SEPTEMBER,
    )

    assert reversal.transaction_date == SEPTEMBER


def test_restating_a_closed_period_is_available_and_explicit() -> None:
    """The default must be overridable (ADR-0030 § 4).

    Overriding it is a close-crossing: this returns the date, and the caller owns the reopen
    event and its recorded reason. The engine reads no period state and takes no clock.
    """
    reversal = build_reversal(
        original(),
        reverses_id="txn-1",
        original_period_closed=True,
        current_period_date=SEPTEMBER,
        restate_original_period=True,
    )

    assert reversal.transaction_date == MARCH


def test_restating_an_open_period_changes_nothing() -> None:
    """The flag only has meaning against a closed period."""
    reversal = build_reversal(
        original(),
        reverses_id="txn-1",
        original_period_closed=False,
        current_period_date=SEPTEMBER,
        restate_original_period=True,
    )

    assert reversal.transaction_date == MARCH


def test_description_is_the_callers_to_supply() -> None:
    """Copying the original's description would misdescribe the reversal as the thing it
    undoes, so it is not carried over."""
    reversal = build_reversal(
        original(),
        reverses_id="txn-1",
        original_period_closed=False,
        current_period_date=SEPTEMBER,
        description="Reversal of Invoice 1001",
    )

    assert reversal.description == "Reversal of Invoice 1001"

    without = build_reversal(
        original(),
        reverses_id="txn-1",
        original_period_closed=False,
        current_period_date=SEPTEMBER,
    )

    assert without.description is None


def test_reversing_a_multi_commodity_entry_balances_in_each() -> None:
    entry = Entry(
        transaction_date=MARCH,
        postings=(
            Posting(account_id="usd-cash", amount=Decimal("100.00"), commodity="USD"),
            Posting(account_id="usd-rev", amount=Decimal("-100.00"), commodity="USD"),
            Posting(account_id="eur-cash", amount=Decimal("80.00"), commodity="EUR"),
            Posting(account_id="eur-rev", amount=Decimal("-80.00"), commodity="EUR"),
        ),
    )

    reversal = build_reversal(
        entry,
        reverses_id="txn-1",
        original_period_closed=False,
        current_period_date=SEPTEMBER,
    )

    assert totals_by_commodity([*entry.postings, *reversal.postings]) == {
        "USD": Decimal("0"),
        "EUR": Decimal("0"),
    }
