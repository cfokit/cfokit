"""The pure period model (`LED-11`, ADR-0030).

No database, no entity, no clock: which period a date falls in is a total function of the date.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from cfokit.ledger.engine.periods import (
    Period,
    fiscal_year_of,
    period_of,
    preceding_window,
    year_earlier_window,
)


def test_a_period_is_the_calendar_month_of_the_date() -> None:
    assert period_of(date(2026, 3, 14)) == Period(2026, 3)


def test_the_boundaries_are_the_whole_month() -> None:
    march = Period(2026, 3)

    assert march.start == date(2026, 3, 1)
    assert march.end == date(2026, 3, 31)


def test_february_in_a_leap_year_ends_on_the_29th() -> None:
    """The month length comes from the calendar, not from a table someone maintains."""
    assert Period(2028, 2).end == date(2028, 2, 29)
    assert Period(2027, 2).end == date(2027, 2, 28)


def test_periods_order_by_year_then_month() -> None:
    """Ordered so "up to and including this period" is a comparison, not a date calculation."""
    assert Period(2025, 12) < Period(2026, 1) < Period(2026, 2)


def test_a_month_outside_the_calendar_is_refused() -> None:
    with pytest.raises(ValueError, match="month must be 1-12"):
        Period(2026, 13)


def test_a_period_reads_as_the_month_it_is() -> None:
    """It appears in refusal messages and in the audit trail, so it has to be legible."""
    assert str(Period(2026, 3)) == "2026-03"


@given(st.dates())
def test_every_date_falls_in_exactly_its_own_period(day: date) -> None:
    """Total, and self-consistent: the period a date is assigned to is one that contains it."""
    period = period_of(day)

    assert period.contains(day)
    assert period.start <= day <= period.end


@given(st.dates(), st.dates())
def test_two_dates_share_a_period_exactly_when_they_share_a_month(
    first: date, second: date
) -> None:
    same_month = (first.year, first.month) == (second.year, second.month)

    assert (period_of(first) == period_of(second)) is same_month


# --- Fiscal years (LED-12, ADR-0027) ------------------------------------------------------


def test_a_calendar_fiscal_year_is_the_calendar_year() -> None:
    year = fiscal_year_of(date(2026, 3, 14), end_month=12, end_day=31)

    assert year.start == date(2026, 1, 1)
    assert year.end == date(2026, 12, 31)


def test_a_year_is_named_by_the_calendar_year_its_end_falls_in() -> None:
    """The convention accounting uses: a year ending 30 June 2027 is FY2027."""
    year = fiscal_year_of(date(2026, 7, 1), end_month=6, end_day=30)

    assert year.start == date(2026, 7, 1)
    assert year.end == date(2027, 6, 30)
    assert str(year) == "FY2027"


def test_the_last_day_of_a_year_belongs_to_it_and_the_next_day_does_not() -> None:
    """The boundary case, which is where a year-end close either lands or does not."""
    assert fiscal_year_of(date(2026, 6, 30), end_month=6, end_day=30).end == date(2026, 6, 30)
    assert fiscal_year_of(date(2026, 7, 1), end_month=6, end_day=30).end == date(2027, 6, 30)


def test_a_declared_day_past_the_end_of_its_month_is_clamped() -> None:
    """The schema permits day 31 with any month, and February moves between 28 and 29.

    Clamping keeps the boundary a total function of what the entity declared, rather than a
    validation someone has to have done earlier.
    """
    assert fiscal_year_of(date(2027, 1, 1), end_month=2, end_day=31).end == date(2027, 2, 28)
    assert fiscal_year_of(date(2028, 1, 1), end_month=2, end_day=31).end == date(2028, 2, 29)
    assert fiscal_year_of(date(2026, 1, 1), end_month=4, end_day=31).end == date(2026, 4, 30)


@given(st.dates(min_value=date(1900, 1, 1), max_value=date(2200, 12, 31)), st.integers(1, 12))
def test_every_date_falls_in_exactly_one_fiscal_year(day: date, end_month: int) -> None:
    """Total and contiguous: a date is inside its own year, and the year before ends the day
    before this one starts, so no date falls between two years or in both."""
    year = fiscal_year_of(day, end_month=end_month, end_day=28)

    assert year.contains(day)
    assert year.start <= year.end
    previous = fiscal_year_of(year.start - timedelta(days=1), end_month=end_month, end_day=28)
    assert previous.end == year.start - timedelta(days=1)


# --- Comparative windows (RPT-07) ---------------------------------------------------------


def test_a_month_compares_against_the_month_before() -> None:
    """Not the 31 days before, which would end mid-February — not a period anyone reports on."""
    assert preceding_window(date(2026, 3, 1), date(2026, 3, 31)) == (
        date(2026, 2, 1),
        date(2026, 2, 28),
    )


def test_a_quarter_compares_against_the_quarter_before_it() -> None:
    """Including across a year boundary, where the preceding quarter is in the previous year."""
    assert preceding_window(date(2026, 1, 1), date(2026, 3, 31)) == (
        date(2025, 10, 1),
        date(2025, 12, 31),
    )


def test_a_window_that_is_not_whole_months_shifts_by_its_own_length() -> None:
    """The only rule available when there are no month boundaries to follow."""
    assert preceding_window(date(2026, 3, 5), date(2026, 3, 20)) == (
        date(2026, 2, 17),
        date(2026, 3, 4),
    )


def test_a_year_earlier_is_the_same_dates_one_year_back() -> None:
    assert year_earlier_window(date(2026, 3, 1), date(2026, 3, 31)) == (
        date(2025, 3, 1),
        date(2025, 3, 31),
    )


def test_a_leap_day_compares_against_the_end_of_february() -> None:
    """29 February has no counterpart, so the day clamps rather than failing to exist."""
    assert year_earlier_window(date(2028, 2, 1), date(2028, 2, 29)) == (
        date(2027, 2, 1),
        date(2027, 2, 28),
    )


@given(st.dates(min_value=date(1900, 1, 1), max_value=date(2200, 1, 1)), st.integers(0, 400))
def test_a_preceding_window_ends_the_day_before_the_current_one_starts(
    since: date, length: int
) -> None:
    """Contiguous and never overlapping, whichever rule applied."""
    as_of = since + timedelta(days=length)
    start, end = preceding_window(since, as_of)

    assert end == since - timedelta(days=1)
    assert start <= end
