"""Profit and loss, and balance sheet (`RPT-02`, `RPT-03`, `RPT-09`).

Both are views over the same balance query the trial balance uses, which is what `RPT-09` asks
for: the same books produce the same figures however the question is phrased.

The relationship between them is what these tests are really about. A balance sheet mid-year
balances only because it carries the earnings `LED-12` has not moved yet; after a year-end
close it balances because they have been moved. Both must hold, and the same number does the
work in each.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest

from cfokit.ledger.engine import Entry, Posting
from cfokit.ledger.presentation import (
    PresentedBalanceSheet,
    PresentedComparative,
    PresentedProfitAndLoss,
    present_balance_sheet,
    present_comparative_profit_and_loss,
    present_profit_and_loss,
)
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.administration import create_account
from cfokit.ledger.service.principal import ActorClass, Principal
from cfokit.ledger.service.reports import (
    Comparative,
    balance_sheet,
    comparative_profit_and_loss,
    profit_and_loss,
)
from cfokit.ledger.service.write import WriteContext, record_transaction
from cfokit.ledger.service.year_end import close_fiscal_year

pytestmark = pytest.mark.integration

MARCH = date(2026, 3, 14)
AUGUST = date(2026, 8, 20)
YEAR_END = date(2026, 12, 31)
PERSON = Principal(id="user:geoff", actor_class=ActorClass.PERSON)


@pytest.fixture
def chart(
    database: Database, owned_books: tuple[str, str, str]
) -> tuple[str, str, str, str, str]:
    """Cash and revenue from the fixture, plus an expense account and retained earnings."""
    entity_id, cash, revenue = owned_books
    suffix = uuid.uuid4().hex[:6]
    expense = create_account(
        database,
        entity_id=entity_id,
        principal=PERSON,
        request_id="req",
        code=f"5000-{suffix}",
        name="Rent",
        account_type="expense",
    )
    retained = create_account(
        database,
        entity_id=entity_id,
        principal=PERSON,
        request_id="req",
        code=f"3900-{suffix}",
        name="Retained earnings",
        account_type="equity",
        retained_earnings=True,
    )
    return entity_id, cash, revenue, expense, retained


def book(
    database: Database, entity_id: str, debit: str, credit: str, when: date, amount: str
) -> None:
    record_transaction(
        database,
        WriteContext(
            entity_id=entity_id,
            principal=PERSON,
            request_id=f"req-{uuid.uuid4().hex[:8]}",
            idempotency_key=uuid.uuid4().hex,
        ),
        entry=Entry(
            transaction_date=when,
            postings=(
                Posting(account_id=debit, amount=Decimal(amount), commodity="USD"),
                Posting(account_id=credit, amount=-Decimal(amount), commodity="USD"),
            ),
            description="Entry",
        ),
        post=True,
    )


def statements(
    database: Database, entity_id: str, *, since: date = MARCH, as_of: date = YEAR_END
) -> tuple[PresentedProfitAndLoss, PresentedBalanceSheet]:
    pl = present_profit_and_loss(
        profit_and_loss(
            database, entity_id=entity_id, principal=PERSON, since=since, as_of=as_of
        )
    )
    bs = present_balance_sheet(
        balance_sheet(database, entity_id=entity_id, principal=PERSON, as_of=as_of)
    )
    return pl, bs


def test_profit_and_loss_reports_the_period(
    database: Database, chart: tuple[str, str, str, str, str]
) -> None:
    """`RPT-02`: for any period, which is what distinguishes it from a balance sheet."""
    entity_id, cash, revenue, expense, _ = chart
    book(database, entity_id, cash, revenue, MARCH, "100.00")
    book(database, entity_id, expense, cash, AUGUST, "30.00")

    report = present_profit_and_loss(
        profit_and_loss(
            database, entity_id=entity_id, principal=PERSON, since=MARCH, as_of=YEAR_END
        )
    )

    assert report.total_income == Decimal("100.00")
    assert report.total_expenses == Decimal("30.00")
    assert report.net_income == Decimal("70.00")


def test_a_narrower_period_excludes_what_falls_outside_it(
    database: Database, chart: tuple[str, str, str, str, str]
) -> None:
    """The window is the point: a month's profit is not the year's."""
    entity_id, cash, revenue, expense, _ = chart
    book(database, entity_id, cash, revenue, MARCH, "100.00")
    book(database, entity_id, expense, cash, AUGUST, "30.00")

    report = present_profit_and_loss(
        profit_and_loss(
            database,
            entity_id=entity_id,
            principal=PERSON,
            since=MARCH,
            as_of=date(2026, 3, 31),
        )
    )

    assert report.total_income == Decimal("100.00")
    assert report.total_expenses == Decimal("0.00")


def test_the_balance_sheet_balances_mid_year(
    database: Database, chart: tuple[str, str, str, str, str]
) -> None:
    """**The case a naive implementation gets wrong.**

    Nothing has been closed, so the earnings are still sitting in income and expense. Equity
    has to carry them or the statement is short by exactly the net income — which looks like an
    accounting error and is a reporting bug.
    """
    entity_id, cash, revenue, expense, _ = chart
    book(database, entity_id, cash, revenue, MARCH, "100.00")
    book(database, entity_id, expense, cash, AUGUST, "30.00")

    _, sheet = statements(database, entity_id)

    assert sheet.total_assets == Decimal("70.00")
    assert sheet.unclosed_earnings == Decimal("70.00")
    assert sheet.balances is True


def test_net_income_is_the_earnings_the_balance_sheet_carries(
    database: Database, chart: tuple[str, str, str, str, str]
) -> None:
    """The two statements agree about the same number, which is the tie between them."""
    entity_id, cash, revenue, expense, _ = chart
    book(database, entity_id, cash, revenue, MARCH, "100.00")
    book(database, entity_id, expense, cash, AUGUST, "30.00")

    pl, sheet = statements(database, entity_id, since=date(2026, 1, 1))

    assert pl.net_income == sheet.unclosed_earnings


def test_the_balance_sheet_still_balances_after_the_year_is_closed(
    database: Database, chart: tuple[str, str, str, str, str]
) -> None:
    """After `LED-12` runs, the same earnings are in retained earnings instead.

    Equity is unchanged and the statement still balances — the close moved the figure, it did
    not create or destroy one.
    """
    entity_id, cash, revenue, expense, retained = chart
    book(database, entity_id, cash, revenue, MARCH, "100.00")
    book(database, entity_id, expense, cash, AUGUST, "30.00")
    before = present_balance_sheet(
        balance_sheet(database, entity_id=entity_id, principal=PERSON, as_of=YEAR_END)
    )

    close_fiscal_year(
        database, entity_id=entity_id, principal=PERSON, request_id="req", day_in_year=MARCH
    )

    after = present_balance_sheet(
        balance_sheet(database, entity_id=entity_id, principal=PERSON, as_of=YEAR_END)
    )
    assert after.balances is True
    assert after.unclosed_earnings == Decimal("0.00")
    assert after.total_equity == before.total_equity == Decimal("70.00")
    assert [(line.account_id, line.amount) for line in after.equity] == [
        (retained, Decimal("70.00"))
    ]


def test_the_profit_and_loss_is_empty_after_the_close(
    database: Database, chart: tuple[str, str, str, str, str]
) -> None:
    """`LED-12`'s acceptance seen from the statement: the new year opens at zero."""
    entity_id, cash, revenue, expense, _ = chart
    book(database, entity_id, cash, revenue, MARCH, "100.00")
    book(database, entity_id, expense, cash, AUGUST, "30.00")
    close_fiscal_year(
        database, entity_id=entity_id, principal=PERSON, request_id="req", day_in_year=MARCH
    )

    next_year = present_profit_and_loss(
        profit_and_loss(
            database,
            entity_id=entity_id,
            principal=PERSON,
            since=date(2027, 1, 1),
            as_of=date(2027, 12, 31),
        )
    )

    assert next_year.total_income == Decimal("0.00")
    assert next_year.total_expenses == Decimal("0.00")


def test_both_statements_state_the_basis(
    database: Database, chart: tuple[str, str, str, str, str]
) -> None:
    """`RPT-10`: on the face of every report, read from the entity."""
    entity_id, cash, revenue, _, _ = chart
    book(database, entity_id, cash, revenue, MARCH, "100.00")

    pl, sheet = statements(database, entity_id)

    assert pl.accounting_basis == "accrual"
    assert sheet.accounting_basis == "accrual"


# --- Comparative periods (RPT-07) ---------------------------------------------------------


def comparative(
    database: Database, entity_id: str, *, since: date, as_of: date, against: Comparative
) -> PresentedComparative:
    return present_comparative_profit_and_loss(
        comparative_profit_and_loss(
            database,
            entity_id=entity_id,
            principal=PERSON,
            since=since,
            as_of=as_of,
            comparative=against,
        )
    )


def test_a_month_is_compared_against_the_month_before(
    database: Database, chart: tuple[str, str, str, str, str]
) -> None:
    """`RPT-07`: "alongside a comparative period — the preceding one"."""
    entity_id, cash, revenue, _, _ = chart
    book(database, entity_id, cash, revenue, date(2026, 2, 10), "100.00")
    book(database, entity_id, cash, revenue, date(2026, 3, 10), "130.00")

    report = comparative(
        database,
        entity_id,
        since=date(2026, 3, 1),
        as_of=date(2026, 3, 31),
        against=Comparative.PRECEDING,
    )

    assert report.comparison_since == date(2026, 2, 1)
    assert report.comparison_as_of == date(2026, 2, 28)
    assert report.total_income.current == Decimal("130.00")
    assert report.total_income.comparison == Decimal("100.00")
    assert report.total_income.variance == Decimal("30.00")


def test_the_same_period_a_year_earlier(
    database: Database, chart: tuple[str, str, str, str, str]
) -> None:
    entity_id, cash, revenue, _, _ = chart
    book(database, entity_id, cash, revenue, date(2025, 3, 10), "80.00")
    book(database, entity_id, cash, revenue, date(2026, 3, 10), "130.00")

    report = comparative(
        database,
        entity_id,
        since=date(2026, 3, 1),
        as_of=date(2026, 3, 31),
        against=Comparative.YEAR_EARLIER,
    )

    assert (report.comparison_since, report.comparison_as_of) == (
        date(2025, 3, 1),
        date(2025, 3, 31),
    )
    assert report.total_income.variance == Decimal("50.00")


def test_an_account_new_this_period_shows_its_whole_amount_as_the_variance(
    database: Database, chart: tuple[str, str, str, str, str]
) -> None:
    """**The line a reader most wants**, and the one a naive join drops.

    An account absent from the comparison counts as zero there rather than as a missing row —
    a cost that started this month is exactly the variance worth seeing.
    """
    entity_id, cash, revenue, expense, _ = chart
    book(database, entity_id, cash, revenue, date(2026, 2, 10), "100.00")
    book(database, entity_id, expense, cash, date(2026, 3, 10), "25.00")

    report = comparative(
        database,
        entity_id,
        since=date(2026, 3, 1),
        as_of=date(2026, 3, 31),
        against=Comparative.PRECEDING,
    )

    assert [(line.current, line.comparison, line.variance) for line in report.expenses] == [
        (Decimal("25.00"), Decimal("0.00"), Decimal("25.00"))
    ]


def test_a_revenue_stream_that_stopped_shows_as_a_negative_variance(
    database: Database, chart: tuple[str, str, str, str, str]
) -> None:
    """The mirror case: present in the comparison and absent now."""
    entity_id, cash, revenue, _, _ = chart
    book(database, entity_id, cash, revenue, date(2026, 2, 10), "100.00")

    report = comparative(
        database,
        entity_id,
        since=date(2026, 3, 1),
        as_of=date(2026, 3, 31),
        against=Comparative.PRECEDING,
    )

    assert [(line.current, line.variance) for line in report.income] == [
        (Decimal("0.00"), Decimal("-100.00"))
    ]


def test_the_net_income_variance_matches_the_two_periods(
    database: Database, chart: tuple[str, str, str, str, str]
) -> None:
    entity_id, cash, revenue, expense, _ = chart
    book(database, entity_id, cash, revenue, date(2026, 2, 10), "100.00")
    book(database, entity_id, expense, cash, date(2026, 2, 15), "40.00")
    book(database, entity_id, cash, revenue, date(2026, 3, 10), "130.00")

    report = comparative(
        database,
        entity_id,
        since=date(2026, 3, 1),
        as_of=date(2026, 3, 31),
        against=Comparative.PRECEDING,
    )

    assert report.net_income.current == Decimal("130.00")
    assert report.net_income.comparison == Decimal("60.00")
    assert report.net_income.variance == Decimal("70.00")
