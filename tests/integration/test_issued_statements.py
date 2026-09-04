"""Issued statements and supersession (`RPT-17`, `SOC1-20`).

> "A statement can be marked issued, fixing what was reported, to whom, and when."

> "Where a correction posted after a statement was issued changes that statement's figures, the
> issued statement is marked superseded, and both what was reported and what is now true remain
> retrievable."

This is what `RPT-11`'s reproducibility was for. Reproducing the books at an earlier moment is
only useful once there is a record of what was issued to compare against.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest

from cfokit.ledger.engine import Entry, Posting
from cfokit.ledger.errors import IssuedStatementNotFound, NotAuthorised
from cfokit.ledger.presentation import present_trial_balance
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.issuance import issue_statement, issued, supersession
from cfokit.ledger.service.principal import ActorClass, Principal
from cfokit.ledger.service.reports import trial_balance
from cfokit.ledger.service.write import WriteContext, record_transaction

pytestmark = pytest.mark.integration

MARCH = date(2026, 3, 14)
MARCH_END = date(2026, 3, 31)
APRIL = date(2026, 4, 10)
PERSON = Principal(id="user:geoff", actor_class=ActorClass.PERSON)


def book(
    database: Database, entity_id: str, cash: str, revenue: str, when: date, amount: str
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
                Posting(account_id=cash, amount=Decimal(amount), commodity="USD"),
                Posting(account_id=revenue, amount=-Decimal(amount), commodity="USD"),
            ),
            description="Entry",
        ),
        post=True,
    )


def issue(database: Database, entity_id: str, as_of: date = MARCH_END) -> str:
    """Render the trial balance and record it as given to a lender."""
    report = present_trial_balance(
        trial_balance(database, entity_id=entity_id, principal=PERSON, as_of=as_of)
    )
    return issue_statement(
        database,
        entity_id=entity_id,
        principal=PERSON,
        request_id="req",
        report="trial_balance",
        since=None,
        as_of=as_of,
        figures={"total_debit": str(report.total_debit)},
        issued_to="Northgate Bank",
    )


def test_an_issued_statement_records_what_and_to_whom(
    database: Database, owned_books: tuple[str, str, str]
) -> None:
    """`RPT-17`: what was reported, to whom, and when."""
    entity_id, cash, revenue = owned_books
    book(database, entity_id, cash, revenue, MARCH, "100.00")
    issuance_id = issue(database, entity_id)

    record = supersession(
        database, entity_id=entity_id, principal=PERSON, issuance_id=issuance_id
    )

    assert record.statement.report == "trial_balance"
    assert record.statement.issued_to == "Northgate Bank"
    assert record.statement.issued_by == "user:geoff"
    assert record.statement.figures == {"total_debit": "100.00"}


def test_a_fresh_statement_is_not_superseded(
    database: Database, owned_books: tuple[str, str, str]
) -> None:
    entity_id, cash, revenue = owned_books
    book(database, entity_id, cash, revenue, MARCH, "100.00")
    issuance_id = issue(database, entity_id)

    record = supersession(
        database, entity_id=entity_id, principal=PERSON, issuance_id=issuance_id
    )

    assert record.superseded is False


def test_a_correction_inside_the_window_supersedes_it(
    database: Database, owned_books: tuple[str, str, str]
) -> None:
    """**`SOC1-20`'s condition.** The lender's copy no longer matches the books."""
    entity_id, cash, revenue = owned_books
    book(database, entity_id, cash, revenue, MARCH, "100.00")
    issuance_id = issue(database, entity_id)

    book(database, entity_id, cash, revenue, MARCH, "40.00")

    record = supersession(
        database, entity_id=entity_id, principal=PERSON, issuance_id=issuance_id
    )
    assert record.superseded is True
    assert record.superseded_by == 1


def test_a_posting_outside_the_window_does_not_supersede_it(
    database: Database, owned_books: tuple[str, str, str]
) -> None:
    """A April entry changes nothing a March statement said, so the window bounds the query
    rather than the watermark alone."""
    entity_id, cash, revenue = owned_books
    book(database, entity_id, cash, revenue, MARCH, "100.00")
    issuance_id = issue(database, entity_id)

    book(database, entity_id, cash, revenue, APRIL, "40.00")

    record = supersession(
        database, entity_id=entity_id, principal=PERSON, issuance_id=issuance_id
    )
    assert record.superseded is False


def test_both_what_was_reported_and_what_is_now_true_are_retrievable(
    database: Database, owned_books: tuple[str, str, str]
) -> None:
    """`SOC1-20`'s other half, and the reason `RPT-11` exists.

    The stored figures are what the lender holds. Re-running the report at the statement's
    watermark reproduces them from the books; running it now gives what is true instead.
    """
    entity_id, cash, revenue = owned_books
    book(database, entity_id, cash, revenue, MARCH, "100.00")
    issuance_id = issue(database, entity_id)
    book(database, entity_id, cash, revenue, MARCH, "40.00")

    record = supersession(
        database, entity_id=entity_id, principal=PERSON, issuance_id=issuance_id
    )
    as_issued = present_trial_balance(
        trial_balance(
            database,
            entity_id=entity_id,
            principal=PERSON,
            as_of=MARCH_END,
            watermark=record.statement.watermark,
        )
    )
    as_now = present_trial_balance(
        trial_balance(database, entity_id=entity_id, principal=PERSON, as_of=MARCH_END)
    )

    assert record.statement.figures["total_debit"] == "100.00"
    assert as_issued.total_debit == Decimal("100.00")  # reproduced from the books
    assert as_now.total_debit == Decimal("140.00")  # what is true instead


def test_every_issued_statement_is_listed_newest_first(
    database: Database, owned_books: tuple[str, str, str]
) -> None:
    entity_id, cash, revenue = owned_books
    book(database, entity_id, cash, revenue, MARCH, "100.00")
    issue(database, entity_id, as_of=MARCH_END)
    issue(database, entity_id, as_of=date(2026, 4, 30))

    listed = issued(database, entity_id=entity_id, principal=PERSON)

    assert len(listed) == 2
    assert listed[0].statement.issued_at >= listed[1].statement.issued_at


def test_an_unknown_statement_is_refused(
    database: Database, owned_books: tuple[str, str, str]
) -> None:
    entity_id, _, _ = owned_books

    with pytest.raises(IssuedStatementNotFound) as caught:
        supersession(
            database,
            entity_id=entity_id,
            principal=PERSON,
            issuance_id=str(uuid.uuid4()),
        )

    assert caught.value.code == "issued_statement_not_found"


def test_issuing_requires_the_read_privilege(
    database: Database, owned_books: tuple[str, str, str]
) -> None:
    """Anyone who can read the books can already tell a lender what they say; what matters is
    that the act is recorded. Someone who cannot read them has nothing to issue."""
    entity_id, _, _ = owned_books

    with pytest.raises(NotAuthorised):
        issue_statement(
            database,
            entity_id=entity_id,
            principal=Principal(id="user:stranger", actor_class=ActorClass.PERSON),
            request_id="req",
            report="trial_balance",
            since=None,
            as_of=MARCH_END,
            figures={},
            issued_to="Nobody",
        )
