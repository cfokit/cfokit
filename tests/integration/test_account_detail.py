"""Account detail (`RPT-05`), which is where `RPT-08` resolves to.

> "Account detail for any account and period — every transaction against it, in order, with a
> running balance."

The opening balance is what makes the running one true. A March statement starting from zero
would show the right movements against the wrong figures, which is the failure that looks like
correct output.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest

from cfokit.ledger.engine import Entry, Posting
from cfokit.ledger.errors import AccountNotFound
from cfokit.ledger.presentation import PresentedAccountDetail, present_account_detail
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.administration import grant_role
from cfokit.ledger.service.principal import ActorClass, Principal
from cfokit.ledger.service.reports import account_detail
from cfokit.ledger.service.write import WriteContext, record_transaction, reverse_transaction

pytestmark = pytest.mark.integration

JANUARY = date(2026, 1, 10)
MARCH_START = date(2026, 3, 1)
MARCH = date(2026, 3, 14)
MARCH_END = date(2026, 3, 31)
PERSON = Principal(id="user:geoff", actor_class=ActorClass.PERSON)
AGENT = Principal(id="skill:bookkeeper", actor_class=ActorClass.AGENT, acting_for="user:geoff")


def book(
    database: Database,
    entity_id: str,
    debit: str,
    credit: str,
    when: date,
    amount: str,
    principal: Principal = PERSON,
) -> str:
    return record_transaction(
        database,
        WriteContext(
            entity_id=entity_id,
            principal=principal,
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
    ).transaction_id


def detail(
    database: Database,
    entity_id: str,
    account_id: str,
    *,
    since: date = MARCH_START,
    as_of: date = MARCH_END,
) -> PresentedAccountDetail:
    return present_account_detail(
        account_detail(
            database,
            entity_id=entity_id,
            principal=PERSON,
            account_id=account_id,
            since=since,
            as_of=as_of,
        )
    )


def test_the_period_opens_at_what_stood_before_it(
    database: Database, owned_books: tuple[str, str, str]
) -> None:
    """The figure that makes the running balance mean anything."""
    entity_id, cash, revenue = owned_books
    book(database, entity_id, cash, revenue, JANUARY, "100.00")
    book(database, entity_id, cash, revenue, MARCH, "40.00")

    report = detail(database, entity_id, cash)

    assert report.opening_balance == Decimal("100.00")
    assert [entry.amount for entry in report.entries] == [Decimal("40.00")]
    assert report.closing_balance == Decimal("140.00")


def test_the_running_balance_accumulates_in_order(
    database: Database, owned_books: tuple[str, str, str]
) -> None:
    entity_id, cash, revenue = owned_books
    for amount in ("100.00", "40.00", "7.00"):
        book(database, entity_id, cash, revenue, MARCH, amount)

    report = detail(database, entity_id, cash)

    assert [entry.running_balance for entry in report.entries] == [
        Decimal("100.00"),
        Decimal("140.00"),
        Decimal("147.00"),
    ]
    assert report.closing_balance == Decimal("147.00")


def test_a_credit_normal_account_reads_positive(
    database: Database, owned_books: tuple[str, str, str]
) -> None:
    """`LED-02`: the type determines the sign convention, so revenue reads as revenue.

    The same postings viewed from the income account are positive where the cash side is
    positive too — both accounts grew.
    """
    entity_id, cash, revenue = owned_books
    book(database, entity_id, cash, revenue, MARCH, "100.00")

    report = detail(database, entity_id, revenue)

    assert report.account_type == "income"
    assert [entry.amount for entry in report.entries] == [Decimal("100.00")]
    assert report.closing_balance == Decimal("100.00")


def test_nothing_outside_the_period_appears(
    database: Database, owned_books: tuple[str, str, str]
) -> None:
    entity_id, cash, revenue = owned_books
    book(database, entity_id, cash, revenue, JANUARY, "100.00")
    book(database, entity_id, cash, revenue, date(2026, 4, 2), "9.00")

    report = detail(database, entity_id, cash)

    assert report.entries == ()
    assert report.opening_balance == report.closing_balance == Decimal("100.00")


def test_each_entry_names_what_wrote_it(
    database: Database, owned_books: tuple[str, str, str]
) -> None:
    """`LED-20` and `RPT-08`: from a posting to its transaction and its principal.

    An agent's write records both principals, so a reader can tell a skill's entry from a
    person's without composing a query.
    """
    entity_id, cash, revenue = owned_books
    # `owner` is the only role carrying `post` today, so a test about an agent's writes has to
    # grant it. The attribution is what is under test, not the breadth of the grant.
    grant_role(
        database,
        entity_id=entity_id,
        principal=PERSON,
        request_id="req",
        to_principal=AGENT.id,
        role="owner",
    )
    transaction_id = book(database, entity_id, cash, revenue, MARCH, "100.00", principal=AGENT)

    entry = detail(database, entity_id, cash).entries[0]

    assert entry.transaction_id == transaction_id
    assert entry.actor_principal_id == "skill:bookkeeper"
    assert entry.actor_class == "agent"
    assert entry.acting_for_principal_id == "user:geoff"


def test_a_reversal_shows_as_a_movement_naming_its_original(
    database: Database, owned_books: tuple[str, str, str]
) -> None:
    """`LED-08`: both stay visible, and the correction is legible as a correction."""
    entity_id, cash, revenue = owned_books
    original = book(database, entity_id, cash, revenue, MARCH, "100.00")
    reverse_transaction(
        database,
        WriteContext(
            entity_id=entity_id,
            principal=PERSON,
            request_id="req",
            idempotency_key=uuid.uuid4().hex,
        ),
        transaction_id=original,
        current_period_date=MARCH,
    )

    report = detail(database, entity_id, cash)

    assert [entry.amount for entry in report.entries] == [
        Decimal("100.00"),
        Decimal("-100.00"),
    ]
    assert report.entries[1].reverses_id == original
    assert report.closing_balance == Decimal("0.00")


def test_an_unknown_account_is_refused(
    database: Database, owned_books: tuple[str, str, str]
) -> None:
    """Not distinguished from another entity's account: telling them apart would leak that
    entity's chart (`NFR-04`)."""
    entity_id, _, _ = owned_books

    with pytest.raises(AccountNotFound) as caught:
        detail(database, entity_id, str(uuid.uuid4()))

    assert caught.value.code == "account_not_found"


def test_an_account_with_no_movements_still_reports(
    database: Database, owned_books: tuple[str, str, str]
) -> None:
    """A quiet account is a report, not an error, and its balance is what it was."""
    entity_id, cash, revenue = owned_books
    book(database, entity_id, cash, revenue, JANUARY, "100.00")

    report = detail(database, entity_id, revenue, since=MARCH_START, as_of=MARCH_END)

    assert report.entries == ()
    assert report.opening_balance == Decimal("100.00")
