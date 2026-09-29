"""Trial balance (`RPT-01`, `RPT-10`, `RPT-11`).

The figures come from `SUM()` over postings and are never stored (ADR-0003, ADR-0006), which is
what makes `RPT-11` free: reproducing an earlier moment is a filter, not a snapshot anyone had
to take at the time.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from cfokit.ledger.engine import Entry, Posting
from cfokit.ledger.errors import NotAuthorized
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.administration import grant_role
from cfokit.ledger.service.principal import ActorClass, Principal
from cfokit.ledger.service.reports import trial_balance
from cfokit.ledger.service.write import WriteContext, record_transaction

pytestmark = pytest.mark.integration

MARCH = date(2026, 3, 14)
SEPTEMBER = date(2026, 9, 1)
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
            description="Invoice",
        ),
        post=True,
    )


def figures(database: Database, entity_id: str, **kwargs: object) -> dict[str, Decimal]:
    report = trial_balance(
        database,
        entity_id=entity_id,
        principal=PERSON,
        **kwargs,  # type: ignore[arg-type]
    )
    return {row.code: row.balance for row in report.rows}


def test_a_balanced_entry_shows_on_both_sides(
    database: Database, owned_books: tuple[str, str, str]
) -> None:
    entity_id, cash, revenue = owned_books
    book(database, entity_id, cash, revenue, MARCH, "100.00")

    assert figures(database, entity_id, as_of=SEPTEMBER) == {
        "1000": Decimal("100.0000000000"),
        "4000": Decimal("-100.0000000000"),
    }


def test_the_balances_sum_to_zero(
    database: Database, owned_books: tuple[str, str, str]
) -> None:
    """Every transaction balances (`LED-03`), so every trial balance does.

    Nothing checks it here — it holds because the deferred zero-sum trigger refuses anything
    else (ADR-0006). Asserting it is how a break in that would show up as a report that does
    not add up rather than as a silent one.
    """
    entity_id, cash, revenue = owned_books
    for amount in ("100.00", "33.33", "0.01"):
        book(database, entity_id, cash, revenue, MARCH, amount)

    balances = figures(database, entity_id, as_of=SEPTEMBER)

    assert sum(balances.values()) == Decimal(0)


def test_nothing_later_than_the_date_is_included(
    database: Database, owned_books: tuple[str, str, str]
) -> None:
    """ "As of any date" is about when the events occurred (`RPT-01`, `LED-09`)."""
    entity_id, cash, revenue = owned_books
    book(database, entity_id, cash, revenue, MARCH, "100.00")
    book(database, entity_id, cash, revenue, SEPTEMBER, "40.00")

    assert figures(database, entity_id, as_of=MARCH)["1000"] == Decimal("100.0000000000")


def test_a_draft_is_not_in_the_books(
    database: Database, owned_books: tuple[str, str, str]
) -> None:
    """`LED-07`: a draft is freely editable and is not part of the books."""
    entity_id, cash, revenue = owned_books
    record_transaction(
        database,
        WriteContext(
            entity_id=entity_id,
            principal=PERSON,
            request_id="req",
            idempotency_key=uuid.uuid4().hex,
        ),
        entry=Entry(
            transaction_date=MARCH,
            postings=(
                Posting(account_id=cash, amount=Decimal("100.00"), commodity="USD"),
                Posting(account_id=revenue, amount=Decimal("-100.00"), commodity="USD"),
            ),
            description="Not yet",
        ),
        post=False,
    )

    assert figures(database, entity_id, as_of=SEPTEMBER) == {}


def test_an_account_at_zero_is_omitted(
    database: Database, owned_books: tuple[str, str, str]
) -> None:
    """A trial balance lists what has a balance; a zero line is noise a reader scans past."""
    entity_id, cash, revenue = owned_books
    book(database, entity_id, cash, revenue, MARCH, "100.00")
    book(database, entity_id, cash, revenue, MARCH, "-100.00")

    assert figures(database, entity_id, as_of=SEPTEMBER) == {}


def test_the_report_states_the_basis_it_was_produced_on(
    database: Database, owned_books: tuple[str, str, str]
) -> None:
    """`RPT-10`, and read from the entity: a caller who could state the basis could label a
    report as something it is not."""
    entity_id, cash, revenue = owned_books
    book(database, entity_id, cash, revenue, MARCH, "100.00")

    report = trial_balance(database, entity_id=entity_id, principal=PERSON, as_of=SEPTEMBER)

    assert report.accounting_basis == "accrual"
    assert report.functional_currency == "USD"


def test_reading_requires_the_read_privilege(
    database: Database, owned_books: tuple[str, str, str]
) -> None:
    """`IAM-01`: an identity holding no role can do nothing with the entity."""
    entity_id, _, _ = owned_books

    with pytest.raises(NotAuthorized):
        trial_balance(
            database,
            entity_id=entity_id,
            principal=Principal(id="user:stranger", actor_class=ActorClass.PERSON),
            as_of=SEPTEMBER,
        )


def test_a_reader_can_read_it(database: Database, owned_books: tuple[str, str, str]) -> None:
    """The positive control: a rule refusing everyone would pass the test above."""
    entity_id, cash, revenue = owned_books
    book(database, entity_id, cash, revenue, MARCH, "100.00")
    grant_role(
        database,
        entity_id=entity_id,
        principal=PERSON,
        request_id="req",
        to_principal="user:reader",
        role="reader",
    )

    report = trial_balance(
        database,
        entity_id=entity_id,
        principal=Principal(id="user:reader", actor_class=ActorClass.PERSON),
        as_of=SEPTEMBER,
    )

    assert len(report.rows) == 2


# --- Reproducing an earlier moment (RPT-11) -----------------------------------------------


def test_an_earlier_watermark_excludes_what_was_posted_after_it(
    database: Database, owned_books: tuple[str, str, str]
) -> None:
    """`RPT-11`'s acceptance: "The statement given to a lender in March is reproducible in
    December, unchanged by the corrections posted in between."

    Both entries are dated in March, so `as_of` cannot separate them. Only the watermark can,
    which is the whole reason the two dates exist (ADR-0013).
    """
    entity_id, cash, revenue = owned_books
    book(database, entity_id, cash, revenue, MARCH, "100.00")
    taken = datetime.now(UTC)
    book(database, entity_id, cash, revenue, MARCH, "40.00")

    assert figures(database, entity_id, as_of=SEPTEMBER)["1000"] == Decimal("140.0000000000")
    assert figures(database, entity_id, as_of=SEPTEMBER, watermark=taken)["1000"] == Decimal(
        "100.0000000000"
    )


def test_two_runs_at_the_same_watermark_agree(
    database: Database, owned_books: tuple[str, str, str]
) -> None:
    """`RPT-09`: the same books queried twice produce identical figures."""
    entity_id, cash, revenue = owned_books
    book(database, entity_id, cash, revenue, MARCH, "100.00")
    taken = datetime.now(UTC)
    book(database, entity_id, cash, revenue, MARCH, "40.00")

    first = figures(database, entity_id, as_of=SEPTEMBER, watermark=taken)
    second = figures(database, entity_id, as_of=SEPTEMBER, watermark=taken)

    assert first == second


def test_two_runs_differ_by_exactly_what_was_posted_between_them(
    database: Database, owned_books: tuple[str, str, str]
) -> None:
    """`RPT-11` states this as the property, not just as reproducibility."""
    entity_id, cash, revenue = owned_books
    book(database, entity_id, cash, revenue, MARCH, "100.00")
    taken = datetime.now(UTC)
    book(database, entity_id, cash, revenue, MARCH, "40.00")

    before = figures(database, entity_id, as_of=SEPTEMBER, watermark=taken)
    after = figures(database, entity_id, as_of=SEPTEMBER)

    assert after["1000"] - before["1000"] == Decimal("40.0000000000")
    assert after["4000"] - before["4000"] == Decimal("-40.0000000000")
