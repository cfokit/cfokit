"""Opening a set of books with balances carried in (`LED-10`).

> "An entity's books can be opened with balances carried in from before CFOKit held them.
> Opening balances are ordinary postings, balance to zero against a single identified equity
> account, and are identifiable as opening balances."

The point of the equity account is that it should be reconciled away. A balance sitting in it
means the carried-in figures did not add up in the system CFOKit took over from, which is worth
seeing rather than hiding inside retained earnings.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

import psycopg
import pytest

from cfokit.ledger.engine.periods import period_of
from cfokit.ledger.errors import (
    AlreadyOpened,
    CommodityNotPermitted,
    NotAuthorised,
    OpeningBalanceAccountUnset,
    PeriodClosed,
    TransactionIncomplete,
)
from cfokit.ledger.presentation import present_balance_sheet, present_trial_balance
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.administration import create_account, grant_role
from cfokit.ledger.service.opening import CarriedBalance, open_balances
from cfokit.ledger.service.periods import close_period
from cfokit.ledger.service.principal import ActorClass, Principal
from cfokit.ledger.service.reports import balance_sheet, trial_balance

pytestmark = pytest.mark.integration

OPENED_AT = date(2025, 12, 31)
LATER = date(2026, 6, 30)
PERSON = Principal(id="user:geoff", actor_class=ActorClass.PERSON)


@pytest.fixture
def chart(database: Database, owned_books: tuple[str, str, str]) -> tuple[str, str, str, str]:
    """Cash and revenue from the fixture, plus a named opening balance equity account."""
    entity_id, cash, revenue = owned_books
    equity = create_account(
        database,
        entity_id=entity_id,
        principal=PERSON,
        request_id="req",
        code=f"3000-{uuid.uuid4().hex[:6]}",
        name="Opening balance equity",
        account_type="equity",
        opening_balance=True,
    )
    return entity_id, cash, revenue, equity


def carried(account_id: str, amount: str) -> CarriedBalance:
    return CarriedBalance(account_id=account_id, amount=Decimal(amount), commodity="USD")


def balance_of(conn: psycopg.Connection[Any], entity_id: str, account_id: str) -> Decimal:
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


def test_carried_balances_land_where_they_were_named(
    database: Database, chart: tuple[str, str, str, str], owner_conn: psycopg.Connection[Any]
) -> None:
    entity_id, cash, _, equity = chart

    open_balances(
        database,
        entity_id=entity_id,
        principal=PERSON,
        request_id="req",
        as_of=OPENED_AT,
        balances=[carried(cash, "1000.00")],
    )

    assert balance_of(owner_conn, entity_id, cash) == Decimal("1000.0000000000")
    assert balance_of(owner_conn, entity_id, equity) == Decimal("-1000.0000000000")


def test_the_equity_side_is_computed_not_supplied(
    database: Database, chart: tuple[str, str, str, str]
) -> None:
    """An entry that does not balance is impossible rather than refused.

    A caller states what each account carried; the ledger works out the counterweight.
    """
    entity_id, cash, revenue, _ = chart

    opened = open_balances(
        database,
        entity_id=entity_id,
        principal=PERSON,
        request_id="req",
        as_of=OPENED_AT,
        balances=[carried(cash, "1000.00"), carried(revenue, "-250.00")],
    )

    assert opened.equity_amount == Decimal("-750.00")


def test_balances_that_already_add_up_need_no_equity_posting(
    database: Database, chart: tuple[str, str, str, str], owner_conn: psycopg.Connection[Any]
) -> None:
    """The equity account exists to absorb what does not reconcile. When nothing needs
    absorbing, a posting of zero would be noise in a trail `RPT-08` has to resolve."""
    entity_id, cash, revenue, equity = chart

    open_balances(
        database,
        entity_id=entity_id,
        principal=PERSON,
        request_id="req",
        as_of=OPENED_AT,
        balances=[carried(cash, "1000.00"), carried(revenue, "-1000.00")],
    )

    assert balance_of(owner_conn, entity_id, equity) == Decimal(0)


def test_the_entry_is_identifiable_as_opening(
    database: Database, chart: tuple[str, str, str, str], owner_conn: psycopg.Connection[Any]
) -> None:
    """`LED-10`: "identifiable as opening balances"."""
    entity_id, cash, _, _ = chart

    opened = open_balances(
        database,
        entity_id=entity_id,
        principal=PERSON,
        request_id="req",
        as_of=OPENED_AT,
        balances=[carried(cash, "1000.00")],
    )

    with owner_conn.cursor() as cur:
        cur.execute(
            "SELECT entry_kind, status, transaction_date FROM ledger_transaction WHERE id = %s",
            (opened.transaction_id,),
        )
        assert cur.fetchall() == [("opening", "posted", OPENED_AT)]


def test_the_books_open_in_balance(
    database: Database, chart: tuple[str, str, str, str]
) -> None:
    """What opening the books is for: the statements are usable from the first day."""
    entity_id, cash, _, _ = chart
    open_balances(
        database,
        entity_id=entity_id,
        principal=PERSON,
        request_id="req",
        as_of=OPENED_AT,
        balances=[carried(cash, "1000.00")],
    )

    trial = present_trial_balance(
        trial_balance(database, entity_id=entity_id, principal=PERSON, as_of=LATER)
    )
    sheet = present_balance_sheet(
        balance_sheet(database, entity_id=entity_id, principal=PERSON, as_of=LATER)
    )

    assert trial.balances is True
    assert trial.total_debit == Decimal("1000.00")
    assert sheet.balances is True
    assert sheet.total_assets == Decimal("1000.00")


def test_the_books_are_opened_once(
    database: Database, chart: tuple[str, str, str, str]
) -> None:
    """Opening again would double every carried-in figure."""
    entity_id, cash, _, _ = chart
    open_balances(
        database,
        entity_id=entity_id,
        principal=PERSON,
        request_id="req",
        as_of=OPENED_AT,
        balances=[carried(cash, "1000.00")],
    )

    with pytest.raises(AlreadyOpened) as caught:
        open_balances(
            database,
            entity_id=entity_id,
            principal=PERSON,
            request_id="req",
            as_of=OPENED_AT,
            balances=[carried(cash, "1000.00")],
        )

    assert caught.value.code == "already_opened"


def test_opening_needs_a_named_equity_account(
    database: Database, owned_books: tuple[str, str, str]
) -> None:
    """Named rather than guessed, and deliberately not retained earnings."""
    entity_id, cash, _ = owned_books

    with pytest.raises(OpeningBalanceAccountUnset):
        open_balances(
            database,
            entity_id=entity_id,
            principal=PERSON,
            request_id="req",
            as_of=OPENED_AT,
            balances=[carried(cash, "1000.00")],
        )


def test_a_foreign_commodity_is_refused(
    database: Database, chart: tuple[str, str, str, str]
) -> None:
    """`LED-15`: the same refusal an ordinary posting gets, for the same reason."""
    entity_id, cash, _, _ = chart

    with pytest.raises(CommodityNotPermitted):
        open_balances(
            database,
            entity_id=entity_id,
            principal=PERSON,
            request_id="req",
            as_of=OPENED_AT,
            balances=[CarriedBalance(account_id=cash, amount=Decimal("10"), commodity="EUR")],
        )


def test_opening_into_a_closed_period_is_refused(
    database: Database, chart: tuple[str, str, str, str]
) -> None:
    """`LED-11`: a posting is a posting, whatever kind of entry it is."""
    entity_id, cash, _, _ = chart
    close_period(
        database,
        entity_id=entity_id,
        principal=PERSON,
        request_id="req",
        period=period_of(OPENED_AT),
    )

    with pytest.raises(PeriodClosed):
        open_balances(
            database,
            entity_id=entity_id,
            principal=PERSON,
            request_id="req",
            as_of=OPENED_AT,
            balances=[carried(cash, "1000.00")],
        )


def test_opening_with_nothing_is_refused(
    database: Database, chart: tuple[str, str, str, str]
) -> None:
    entity_id, _, _, _ = chart

    with pytest.raises(TransactionIncomplete):
        open_balances(
            database,
            entity_id=entity_id,
            principal=PERSON,
            request_id="req",
            as_of=OPENED_AT,
            balances=[],
        )


def test_opening_requires_the_post_privilege(
    database: Database, chart: tuple[str, str, str, str]
) -> None:
    """The caller chooses the amounts, which is what `POST` authorises."""
    entity_id, cash, _, _ = chart
    grant_role(
        database,
        entity_id=entity_id,
        principal=PERSON,
        request_id="req",
        to_principal="user:reader",
        role="reader",
    )

    with pytest.raises(NotAuthorised):
        open_balances(
            database,
            entity_id=entity_id,
            principal=Principal(id="user:reader", actor_class=ActorClass.PERSON),
            request_id="req",
            as_of=OPENED_AT,
            balances=[carried(cash, "1000.00")],
        )
