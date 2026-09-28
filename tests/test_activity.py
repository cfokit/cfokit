"""A statement proves itself before it is stored (ADR-0046). Layer 1 of ADR-0036: no database.

**Where the expected values come from.** A bank statement is an arithmetic identity the bank
prints — opening balance plus every line equals closing balance — and every case below takes its
expected outcome from that identity, not from running `prove`. The worked example's figures are
chosen by hand and checked by hand in its docstring.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from cfokit.activity import (
    Statement,
    StatementLine,
    content_digest,
    continuity,
    prove,
    source_ref,
)
from cfokit.activity.errors import (
    LineOutsidePeriod,
    StatementDoesNotBalance,
    StatementInvalid,
)

ACCOUNT = "00000000-0000-0000-0000-000000000001"


def march(*lines: StatementLine, opening: str = "1000.00", closing: str) -> Statement:
    return Statement(
        account_id=ACCOUNT,
        period_start=date(2026, 3, 1),
        period_end=date(2026, 3, 31),
        opening_balance=Decimal(opening),
        closing_balance=Decimal(closing),
        commodity="USD",
        lines=lines,
    )


def line(day: int, amount: str, payee: str = "Coffee House") -> StatementLine:
    return StatementLine(
        transaction_date=date(2026, 3, day), payee=payee, amount=Decimal(amount)
    )


# A worked statement. 1000.00 + 250.00 - 45.50 - 4.50 - 4.50 = 1195.50, by hand.
WORKED = (
    line(2, "250.00", "Client A"),
    line(9, "-45.50", "Utility"),
    line(12, "-4.50"),
    line(12, "-4.50"),
)


# --- The proof --------------------------------------------------------------------------------


def test_a_statement_whose_lines_account_for_its_balances_proves() -> None:
    prove(march(*WORKED, closing="1195.50"))


def test_a_misread_amount_is_refused() -> None:
    """45.50 read as 46.50: the statement is then a pound short of its own closing balance."""
    misread = (WORKED[0], line(9, "-46.50", "Utility"), *WORKED[2:])

    with pytest.raises(StatementDoesNotBalance):
        prove(march(*misread, closing="1195.50"))


def test_a_dropped_line_is_refused() -> None:
    """One of the two identical coffees missed — the transcription error most likely to pass
    unnoticed by eye, because what remains looks complete."""
    with pytest.raises(StatementDoesNotBalance):
        prove(march(*WORKED[:3], closing="1195.50"))


def test_the_refusal_names_the_difference() -> None:
    """A single misread line shows up as exactly its own error, which is the most useful thing
    a person correcting it can be told. A coffee of 4.50 read as 3.50: by hand, 1000.00 +
    250.00 - 45.50 - 4.50 - 3.50 = 1196.50, which is 1.00 over the stated 1195.50."""
    with pytest.raises(StatementDoesNotBalance, match=r": 1\.00 is unaccounted for"):
        prove(march(*WORKED[:3], line(12, "-3.50"), closing="1195.50"))


def test_a_statement_with_no_lines_proves_when_nothing_moved() -> None:
    """`BKP-21`: a month with no activity is a statement with no lines, not an absent one."""
    prove(march(closing="1000.00"))


def test_a_statement_with_no_lines_but_a_movement_is_refused() -> None:
    with pytest.raises(StatementDoesNotBalance):
        prove(march(closing="1010.00"))


def test_a_card_statement_is_signed_as_postings_are() -> None:
    """A card with 300.00 owed is a credit, -300.00. A 50.00 purchase adds to what is owed and
    a 100.00 payment reduces it: -300.00 - 50.00 + 100.00 = -250.00."""
    prove(
        march(
            line(3, "-50.00", "Hardware Store"),
            line(20, "100.00", "Payment received"),
            opening="-300.00",
            closing="-250.00",
        )
    )


@given(
    amounts=st.lists(
        st.decimals(min_value=-10_000, max_value=10_000, places=2, allow_nan=False).filter(
            lambda d: d != 0
        ),
        max_size=40,
    ),
    delta=st.decimals(min_value=-100, max_value=100, places=2, allow_nan=False).filter(
        lambda d: d != 0
    ),
    at=st.integers(min_value=0),
)
def test_any_single_misread_is_caught(amounts: list[Decimal], delta: Decimal, at: int) -> None:
    """The identity holds for any lines, and perturbing any one of them by any non-zero amount
    breaks it — so no single misread survives the proof, whatever the statement."""
    lines = tuple(line(1 + i % 28, str(a)) for i, a in enumerate(amounts))
    closing = Decimal("1000.00") + sum(amounts, Decimal(0))
    prove(march(*lines, closing=str(closing)))

    if not lines:
        return
    target = at % len(lines)
    perturbed = lines[target].amount + delta
    if perturbed == 0:
        return
    misread = tuple(
        replace(each, amount=perturbed) if i == target else each for i, each in enumerate(lines)
    )
    with pytest.raises(StatementDoesNotBalance):
        prove(march(*misread, closing=str(closing)))


# --- What else is refused ---------------------------------------------------------------------


def test_a_line_outside_the_period_is_refused() -> None:
    stray = StatementLine(
        transaction_date=date(2026, 4, 1), payee="Next month", amount=Decimal("10.00")
    )

    with pytest.raises(LineOutsidePeriod):
        prove(march(stray, closing="1010.00"))


@pytest.mark.parametrize(
    "broken",
    [
        replace(march(closing="1000.00"), period_end=date(2026, 2, 28)),
        replace(march(closing="1000.00"), commodity=" "),
        march(line(2, "0"), closing="1000.00"),
        march(line(2, "5.00", payee="  "), closing="1005.00"),
    ],
    ids=["period-backwards", "no-commodity", "zero-line", "no-payee"],
)
def test_a_statement_that_cannot_be_read_as_one_is_refused(broken: Statement) -> None:
    with pytest.raises(StatementInvalid):
        prove(broken)


# --- Identity ---------------------------------------------------------------------------------


def test_the_same_statement_has_the_same_digest() -> None:
    assert content_digest(march(*WORKED, closing="1195.50")) == content_digest(
        march(*WORKED, closing="1195.50")
    )


def test_a_statement_read_differently_has_a_different_digest() -> None:
    """Same figures, lines in another order: a second reading of the document, and a replay
    must not mistake it for the first."""
    reordered = (WORKED[1], WORKED[0], *WORKED[2:])

    assert content_digest(march(*WORKED, closing="1195.50")) != content_digest(
        march(*reordered, closing="1195.50")
    )


def test_identical_lines_have_distinct_references() -> None:
    """The two coffees in `WORKED` share every fact. Their position is what tells them apart,
    and the reference a transaction carries is built from it (ADR-0029)."""
    assert WORKED[2] == WORKED[3]
    assert source_ref("s", 3) != source_ref("s", 4)


# --- Continuity (BKP-21) ----------------------------------------------------------------------


def test_a_statement_following_on_is_contiguous_and_continuous() -> None:
    follows = continuity(
        march(closing="1000.00"),
        previous_statement_id="feb",
        previous_end=date(2026, 2, 28),
        previous_closing=Decimal("1000.00"),
    )

    assert follows.contiguous
    assert follows.balance_continues


def test_a_skipped_month_is_detected_against_the_coverage() -> None:
    """`BKP-21`'s acceptance: "a feed that skips a period is detected against the coverage it
    was expected to supply". January then March: February is missing, and says so."""
    follows = continuity(
        march(closing="1000.00"),
        previous_statement_id="jan",
        previous_end=date(2026, 1, 31),
        previous_closing=Decimal("900.00"),
    )

    assert not follows.contiguous
    assert not follows.balance_continues
