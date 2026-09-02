"""Which period a date falls in. Pure, like everything else in the engine (ADR-0008).

`LED-11` makes a period something that can be marked closed, and ADR-0030 makes reopening one
reopen that period alone — "reopening March reopens March. April stays closed". That requires
periods to be discrete and independent, which rules out the simpler design of a single
closed-through watermark: a watermark cannot express March open while April is closed.

**A period is a calendar month.** Nothing in the requirements names the unit, and ADR-0030
assumes months throughout. The fiscal year is separate and does not divide the months: an
entity whose year ends 30 June still closes June and then July.

Period assignment needs no time zone. `PLT-08` determines period boundaries in the entity's
zone, and that matters when a *timestamp* becomes a date; a transaction date is already a date
by the time it reaches here, so the assignment is total and needs nothing but the date.
"""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, timedelta

__all__ = ["FiscalYear", "Period", "fiscal_year_of", "period_of"]


@dataclass(frozen=True, slots=True, order=True)
class Period:
    """One calendar month of an entity's books.

    Ordered, so "every period up to and including this one" is a comparison rather than a
    date calculation.
    """

    year: int
    month: int

    def __post_init__(self) -> None:
        if not 1 <= self.month <= 12:
            raise ValueError(f"month must be 1-12, not {self.month}")

    @property
    def start(self) -> date:
        return date(self.year, self.month, 1)

    @property
    def end(self) -> date:
        """The last day of the period, inclusive."""
        return date(self.year, self.month, monthrange(self.year, self.month)[1])

    def contains(self, day: date) -> bool:
        return self.start <= day <= self.end

    def __str__(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"


def period_of(day: date) -> Period:
    """The period a transaction dated `day` belongs to."""
    return Period(year=day.year, month=day.month)


@dataclass(frozen=True, slots=True, order=True)
class FiscalYear:
    """One fiscal year of an entity's books, bounded by dates rather than by month count.

    Named by the calendar year its **end** falls in, which is the convention accounting uses:
    a year ending 30 June 2027 is FY2027 whatever it started in.
    """

    start: date
    end: date

    @property
    def name(self) -> int:
        return self.end.year

    def contains(self, day: date) -> bool:
        return self.start <= day <= self.end

    def __str__(self) -> str:
        return f"FY{self.end.year}"


def _year_end(year: int, month: int, day: int) -> date:
    """The fiscal year end falling in `year`, with the day clamped to the month.

    An entity may declare the 31st and have a year end in a 30-day month, and February moves
    between 28 and 29. Clamping keeps the boundary a total function of the declaration rather
    than a validation someone has to have done earlier.
    """
    return date(year, month, min(day, monthrange(year, month)[1]))


def fiscal_year_of(day: date, *, end_month: int, end_day: int) -> FiscalYear:
    """The fiscal year `day` falls in, for an entity whose year ends on `end_month`/`end_day`.

    `PLT-08` puts fiscal year ends in the entity's time zone; like period assignment this
    takes a date that has already been resolved there, so it needs no zone of its own.
    """
    end = _year_end(day.year, end_month, end_day)
    if day > end:
        end = _year_end(day.year + 1, end_month, end_day)
    return FiscalYear(
        start=_year_end(end.year - 1, end_month, end_day) + timedelta(days=1), end=end
    )
