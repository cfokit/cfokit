"""Fiscal year-end close (`LED-12`, ADR-0027).

> "At fiscal year end, income and expense balances are closed to retained earnings so the new
> year opens with them at zero. The closing entries are ordinary postings and are identifiable
> as such."

ADR-0027's Confirmation is the center of this file: a posting into a closed year makes the
close stale, and `LED-12`'s outcome holds again only once it is re-run.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

import psycopg
import pytest

from cfokit.ledger.engine import Entry, Posting
from cfokit.ledger.errors import (
    NotAuthorized,
    NothingToClose,
    RetainedEarningsUnset,
    YearAlreadyClosed,
)
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.administration import create_account, grant_role
from cfokit.ledger.service.principal import ActorClass, Principal
from cfokit.ledger.service.write import WriteContext, record_transaction
from cfokit.ledger.service.year_end import close_fiscal_year, is_close_stale

pytestmark = pytest.mark.integration

IN_YEAR = date(2026, 5, 20)
LATER_IN_YEAR = date(2026, 8, 3)
YEAR_END = date(2026, 12, 31)
PERSON = Principal(id="user:geoff", actor_class=ActorClass.PERSON)


def context(entity_id: str, principal: Principal = PERSON) -> WriteContext:
    return WriteContext(
        entity_id=entity_id,
        principal=principal,
        request_id=f"req-{uuid.uuid4().hex[:8]}",
        idempotency_key=uuid.uuid4().hex,
    )


@pytest.fixture
def chart(database: Database, owned_books: tuple[str, str, str]) -> tuple[str, str, str, str]:
    """The fixture entity, plus a retained earnings account created the ordinary way.

    Through `create_account` rather than fixture SQL, because `LED-12` closes to an account in
    the entity's own chart and a path only the tests can reach is not a path.
    """
    entity_id, cash, revenue = owned_books
    retained = create_account(
        database,
        entity_id=entity_id,
        principal=PERSON,
        request_id="req",
        code=f"3900-{uuid.uuid4().hex[:6]}",
        name="Retained earnings",
        account_type="equity",
        retained_earnings=True,
    )
    return entity_id, cash, revenue, retained


def earn(
    database: Database, entity_id: str, cash: str, revenue: str, when: date, amount: str
) -> None:
    record_transaction(
        database,
        context(entity_id),
        entry=Entry(
            transaction_date=when,
            postings=(
                Posting(account_id=cash, amount=Decimal(amount), commodity="USD"),
                Posting(account_id=revenue, amount=-Decimal(amount), commodity="USD"),
            ),
            description="Invoice",
        ),
        post=True,
    )


def balance(conn: psycopg.Connection[Any], entity_id: str, account_id: str) -> Decimal:
    """Balance as `SUM()` over postings — never stored, which is what ADR-0027 rests on."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COALESCE(SUM(p.amount), 0) FROM posting p"
            "  JOIN ledger_transaction t ON t.id = p.transaction_id"
            " WHERE p.entity_id = %s AND p.account_id = %s AND t.status = 'posted'",
            (entity_id, account_id),
        )
        row = cur.fetchone()
    assert row is not None
    return Decimal(row[0])


# --- The close (LED-12) -------------------------------------------------------------------


def test_income_closes_to_retained_earnings(
    database: Database, chart: tuple[str, str, str, str], owner_conn: psycopg.Connection[Any]
) -> None:
    """`LED-12`'s acceptance: the new year opens with income and expense at zero."""
    entity_id, cash, revenue, retained = chart
    earn(database, entity_id, cash, revenue, IN_YEAR, "100.00")

    close_fiscal_year(
        database, entity_id=entity_id, principal=PERSON, request_id="req", day_in_year=IN_YEAR
    )

    assert balance(owner_conn, entity_id, revenue) == Decimal(0)
    # Income is credit-normal, so a profit leaves retained earnings carrying a credit.
    assert balance(owner_conn, entity_id, retained) == Decimal("-100.0000000000")


def test_the_closing_entries_are_identifiable(
    database: Database, chart: tuple[str, str, str, str], owner_conn: psycopg.Connection[Any]
) -> None:
    """`LED-12`: "The closing entries are ordinary postings and are identifiable as such"."""
    entity_id, cash, revenue, _ = chart
    earn(database, entity_id, cash, revenue, IN_YEAR, "100.00")

    closed = close_fiscal_year(
        database, entity_id=entity_id, principal=PERSON, request_id="req", day_in_year=IN_YEAR
    )

    with owner_conn.cursor() as cur:
        cur.execute(
            "SELECT entry_kind, status, transaction_date FROM ledger_transaction WHERE id = %s",
            (closed.transaction_id,),
        )
        assert cur.fetchall() == [("closing", "posted", YEAR_END)]


def test_a_year_with_nothing_in_it_has_nothing_to_close(
    database: Database, chart: tuple[str, str, str, str]
) -> None:
    """`LED-12`'s outcome already holds, so a closing entry of zero would be noise."""
    entity_id, _, _, _ = chart

    with pytest.raises(NothingToClose):
        close_fiscal_year(
            database,
            entity_id=entity_id,
            principal=PERSON,
            request_id="req",
            day_in_year=IN_YEAR,
        )


def test_closing_needs_a_retained_earnings_account(
    database: Database, owned_books: tuple[str, str, str]
) -> None:
    """Named rather than guessed: closing income anywhere else is not closing it to retained
    earnings."""
    entity_id, cash, revenue = owned_books
    earn(database, entity_id, cash, revenue, IN_YEAR, "100.00")

    with pytest.raises(RetainedEarningsUnset):
        close_fiscal_year(
            database,
            entity_id=entity_id,
            principal=PERSON,
            request_id="req",
            day_in_year=IN_YEAR,
        )


def test_retained_earnings_must_be_an_equity_account(
    database: Database, owned_books: tuple[str, str, str]
) -> None:
    entity_id, _, _ = owned_books

    with pytest.raises(NotAuthorized, match="equity"):
        create_account(
            database,
            entity_id=entity_id,
            principal=PERSON,
            request_id="req",
            code=f"4900-{uuid.uuid4().hex[:6]}",
            name="Not equity",
            account_type="income",
            retained_earnings=True,
        )


def test_closing_a_year_requires_the_close_privilege(
    database: Database, chart: tuple[str, str, str, str]
) -> None:
    entity_id, cash, revenue, _ = chart
    earn(database, entity_id, cash, revenue, IN_YEAR, "100.00")
    grant_role(
        database,
        entity_id=entity_id,
        principal=PERSON,
        request_id="req",
        to_principal="user:poster",
        role="poster",
    )

    with pytest.raises(NotAuthorized):
        close_fiscal_year(
            database,
            entity_id=entity_id,
            principal=Principal(id="user:poster", actor_class=ActorClass.PERSON),
            request_id="req",
            day_in_year=IN_YEAR,
        )


def test_closing_a_current_close_again_is_refused(
    database: Database, chart: tuple[str, str, str, str]
) -> None:
    """Distinct from a stale close, which is re-run rather than refused."""
    entity_id, cash, revenue, _ = chart
    earn(database, entity_id, cash, revenue, IN_YEAR, "100.00")
    close_fiscal_year(
        database, entity_id=entity_id, principal=PERSON, request_id="req", day_in_year=IN_YEAR
    )

    with pytest.raises(YearAlreadyClosed):
        close_fiscal_year(
            database,
            entity_id=entity_id,
            principal=PERSON,
            request_id="req",
            day_in_year=IN_YEAR,
        )


# --- Staleness and the re-run (ADR-0027) --------------------------------------------------


def test_a_sound_close_is_not_stale(
    database: Database, chart: tuple[str, str, str, str]
) -> None:
    entity_id, cash, revenue, _ = chart
    earn(database, entity_id, cash, revenue, IN_YEAR, "100.00")
    close_fiscal_year(
        database, entity_id=entity_id, principal=PERSON, request_id="req", day_in_year=IN_YEAR
    )

    assert is_close_stale(database, entity_id=entity_id, day_in_year=IN_YEAR) is False


def test_a_year_that_was_never_closed_is_not_stale(
    database: Database, chart: tuple[str, str, str, str]
) -> None:
    """There is no claim to have gone stale."""
    entity_id, cash, revenue, _ = chart
    earn(database, entity_id, cash, revenue, IN_YEAR, "100.00")

    assert is_close_stale(database, entity_id=entity_id, day_in_year=IN_YEAR) is False


def test_a_posting_into_a_closed_year_makes_the_close_stale(
    database: Database, chart: tuple[str, str, str, str], owner_conn: psycopg.Connection[Any]
) -> None:
    """**ADR-0027's Confirmation.** The close moved the wrong amount, and `LED-12`'s acceptance
    no longer holds — income is not at zero — until the close is re-run.

    Detected, not remembered: nothing set a flag. The closing entry's `recorded_at` is the
    watermark and this is a comparison against it.
    """
    entity_id, cash, revenue, _ = chart
    earn(database, entity_id, cash, revenue, IN_YEAR, "100.00")
    close_fiscal_year(
        database, entity_id=entity_id, principal=PERSON, request_id="req", day_in_year=IN_YEAR
    )

    earn(database, entity_id, cash, revenue, LATER_IN_YEAR, "40.00")

    assert is_close_stale(database, entity_id=entity_id, day_in_year=IN_YEAR) is True
    assert balance(owner_conn, entity_id, revenue) == Decimal("-40.0000000000")


def test_re_running_a_stale_close_restores_the_acceptance(
    database: Database, chart: tuple[str, str, str, str], owner_conn: psycopg.Connection[Any]
) -> None:
    """The other half of ADR-0027's Confirmation, and the reason the re-run exists."""
    entity_id, cash, revenue, retained = chart
    earn(database, entity_id, cash, revenue, IN_YEAR, "100.00")
    close_fiscal_year(
        database, entity_id=entity_id, principal=PERSON, request_id="req", day_in_year=IN_YEAR
    )
    earn(database, entity_id, cash, revenue, LATER_IN_YEAR, "40.00")

    rerun = close_fiscal_year(
        database, entity_id=entity_id, principal=PERSON, request_id="req", day_in_year=IN_YEAR
    )

    assert rerun.reversed_transaction_ids  # the stale entries, not edited
    assert is_close_stale(database, entity_id=entity_id, day_in_year=IN_YEAR) is False
    assert balance(owner_conn, entity_id, revenue) == Decimal(0)
    assert balance(owner_conn, entity_id, retained) == Decimal("-140.0000000000")


def test_the_stale_close_is_reversed_rather_than_edited(
    database: Database, chart: tuple[str, str, str, str], owner_conn: psycopg.Connection[Any]
) -> None:
    """`LED-08`: what retained earnings was believed to be, and what it is now, both stay
    retrievable."""
    entity_id, cash, revenue, _ = chart
    earn(database, entity_id, cash, revenue, IN_YEAR, "100.00")
    first = close_fiscal_year(
        database, entity_id=entity_id, principal=PERSON, request_id="req", day_in_year=IN_YEAR
    )
    earn(database, entity_id, cash, revenue, LATER_IN_YEAR, "40.00")
    close_fiscal_year(
        database, entity_id=entity_id, principal=PERSON, request_id="req", day_in_year=IN_YEAR
    )

    with owner_conn.cursor() as cur:
        cur.execute(
            "SELECT status FROM ledger_transaction WHERE id = %s", (first.transaction_id,)
        )
        assert cur.fetchall() == [("posted",)]  # still there, still posted

        cur.execute(
            "SELECT count(*) FROM ledger_transaction WHERE entity_id = %s AND reverses_id = %s",
            (entity_id, first.transaction_id),
        )
        row = cur.fetchone()
    assert row is not None
    assert row[0] == 1


def test_the_reversal_stays_inside_the_year_it_restates(
    database: Database, chart: tuple[str, str, str, str], owner_conn: psycopg.Connection[Any]
) -> None:
    """A close reversed into the current period would leave the year not netting to zero.

    This is why the re-run does not use the ordinary reversal dating rule, which sends a
    closed period's correction forward (ADR-0030 § 4).
    """
    entity_id, cash, revenue, _ = chart
    earn(database, entity_id, cash, revenue, IN_YEAR, "100.00")
    close_fiscal_year(
        database, entity_id=entity_id, principal=PERSON, request_id="req", day_in_year=IN_YEAR
    )
    earn(database, entity_id, cash, revenue, LATER_IN_YEAR, "40.00")
    rerun = close_fiscal_year(
        database, entity_id=entity_id, principal=PERSON, request_id="req", day_in_year=IN_YEAR
    )

    with owner_conn.cursor() as cur:
        cur.execute(
            "SELECT transaction_date FROM ledger_transaction WHERE id = ANY(%s)",
            (rerun.reversed_transaction_ids,),
        )
        assert cur.fetchall() == [(YEAR_END,)]


def test_a_second_re_run_after_a_second_late_posting(
    database: Database, chart: tuple[str, str, str, str], owner_conn: psycopg.Connection[Any]
) -> None:
    """The chain has to survive more than once, or the reversal of a reversal gets re-reversed.

    A closing entry that is itself a reversal is skipped when reversing, which is what stops
    the re-run undoing its own correction.
    """
    entity_id, cash, revenue, retained = chart
    earn(database, entity_id, cash, revenue, IN_YEAR, "100.00")
    close_fiscal_year(
        database, entity_id=entity_id, principal=PERSON, request_id="req", day_in_year=IN_YEAR
    )
    earn(database, entity_id, cash, revenue, LATER_IN_YEAR, "40.00")
    close_fiscal_year(
        database, entity_id=entity_id, principal=PERSON, request_id="req", day_in_year=IN_YEAR
    )
    earn(database, entity_id, cash, revenue, LATER_IN_YEAR, "7.00")

    close_fiscal_year(
        database, entity_id=entity_id, principal=PERSON, request_id="req", day_in_year=IN_YEAR
    )

    assert is_close_stale(database, entity_id=entity_id, day_in_year=IN_YEAR) is False
    assert balance(owner_conn, entity_id, revenue) == Decimal(0)
    assert balance(owner_conn, entity_id, retained) == Decimal("-147.0000000000")
