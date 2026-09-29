"""The basis-free half of `IMP-08` (ADR-0050).

Every report in an accounting export is run on whichever basis the company keeps, so a
per-account comparison against one diverges on the obligation accounts by exactly what is
unsettled. The journal prints no basis, because it is the record rather than a view of one — so
its stated total is the one figure that holds whatever the reports say.

These tests are about what the total *catches*, because a check that cannot fail is worse than
none: a dropped row and an altered amount are the two ways an import goes wrong that the total
sees, and a transposition is the one it does not.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest

from cfokit.imports import check_total, nets_to_zero, open_books, post_entries
from cfokit.imports.source import (
    SourceAccount,
    SourceBooks,
    SourceEntry,
    SourceLine,
    StatedTotal,
)
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.administration import create_entity
from cfokit.ledger.service.principal import ActorClass, Principal
from cfokit.ledger.service.reports import trial_balance

pytestmark = pytest.mark.integration

PERSON = Principal(id="user:geoff", actor_class=ActorClass.PERSON)
FINGERPRINT = "d" * 64

CHART = (
    SourceAccount(code="Checking", name="Checking", account_type="asset"),
    SourceAccount(code="Receivable", name="Receivable", account_type="asset"),
    SourceAccount(code="Income", name="Income", account_type="income"),
)


def shape(total: StatedTotal | None = None) -> SourceBooks:
    return SourceBooks(
        system="QuickBooks Online",
        fingerprint=FINGERPRINT,
        basis="unknown",
        balances_basis="cash",
        commodity="USD",
        accounts=CHART,
        journal_total=total,
    )


def entry(reference: str, debit: str, amount: str, credit: str = "Income") -> SourceEntry:
    return SourceEntry(
        reference=reference,
        transaction_date=date(2026, 1, 15),
        description="",
        lines=(
            SourceLine(debit, Decimal(amount), "USD"),
            SourceLine(credit, -Decimal(amount), "USD"),
        ),
    )


@pytest.fixture
def entity(database: Database) -> str:
    return create_entity(
        database,
        principal=PERSON,
        request_id="fixture",
        slug=f"totals-{uuid.uuid4().hex[:8]}",
        name="Synthetic Co",
        accounting_basis="accrual",
        fiscal_year_end_month=12,
        fiscal_year_end_day=31,
        functional_currency="USD",
        time_zone="UTC",
    ).entity_id


def landed(database: Database, entity: str, *entries: SourceEntry) -> None:
    open_books(database, entity_id=entity, principal=PERSON, request_id="r", books=shape())
    post_entries(
        database,
        entity_id=entity,
        principal=PERSON,
        request_id="r",
        system="QuickBooks Online",
        fingerprint=FINGERPRINT,
        entries=entries,
    )


# --- what the total catches -------------------------------------------------------------


def test_a_complete_import_agrees_with_the_stated_total(
    database: Database, entity: str
) -> None:
    """The source's arithmetic over the rows we imported, against ours."""
    landed(database, entity, entry("1", "Checking", "100.00"), entry("2", "Checking", "50.00"))

    total = check_total(
        database,
        entity_id=entity,
        principal=PERSON,
        books=shape(StatedTotal(debits=Decimal("150.00"), credits=Decimal("150.00"))),
    )

    assert total is not None
    assert total.agrees
    assert total.our_debits == Decimal("150.00")
    assert total.difference == 0


def test_a_dropped_row_is_caught(database: Database, entity: str) -> None:
    """**The failure an import actually has.** The source states a total over rows we did not
    all land, and the difference is what is missing."""
    landed(database, entity, entry("1", "Checking", "100.00"))

    total = check_total(
        database,
        entity_id=entity,
        principal=PERSON,
        books=shape(StatedTotal(debits=Decimal("150.00"), credits=Decimal("150.00"))),
    )

    assert total is not None
    assert not total.agrees
    assert total.difference == Decimal("-50.00")


def test_an_altered_amount_is_caught(database: Database, entity: str) -> None:
    landed(database, entity, entry("1", "Checking", "100.00"), entry("2", "Checking", "49.00"))

    total = check_total(
        database,
        entity_id=entity,
        principal=PERSON,
        books=shape(StatedTotal(debits=Decimal("150.00"), credits=Decimal("150.00"))),
    )

    assert total is not None
    assert not total.agrees
    assert total.difference == Decimal("-1.00")


def test_the_total_is_gross_volume_and_not_a_trial_balance(
    database: Database, entity: str
) -> None:
    """**The distinction this check turns on, and the bug it had.**

    A trial balance nets within each account: money paid into Checking and straight back out
    again leaves nothing behind, so the account does not appear at all. A journal total is the
    volume that moved, which is what a source states about its own journal — on a
    real export the two figures are 2,616,030.82 and 8,480,703.91 over the same books.
    two figures are 2,616,030.82 and 8,480,703.91 over the same books.

    Written against a case where they differ, because the first implementation summed the trial
    balance and agreed with itself on every fixture where an account was touched once.
    """
    landed(
        database,
        entity,
        entry("1", "Checking", "100.00"),
        entry("2", "Income", "100.00", credit="Checking"),
    )

    total = check_total(
        database,
        entity_id=entity,
        principal=PERSON,
        books=shape(StatedTotal(debits=Decimal("200.00"), credits=Decimal("200.00"))),
    )

    assert total is not None
    assert total.our_debits == Decimal("200.00")  # gross: both transactions moved 100
    assert total.agrees

    # And the trial balance, over the same books, nets Checking to nothing.
    netted = trial_balance(database, entity_id=entity, principal=PERSON, as_of=date.max)
    assert "Checking" not in {row.code for row in netted.rows}


def test_a_transposition_is_not_caught_and_the_record_says_so(
    database: Database, entity: str
) -> None:
    """**The limit, asserted rather than left to be discovered.** Two accounts swapped total the
    same. This is why the per-account comparison is not replaced by the total, and why ADR-0050
    claims completeness and magnitude rather than correctness."""
    landed(database, entity, entry("1", "Receivable", "100.00"))

    total = check_total(
        database,
        entity_id=entity,
        principal=PERSON,
        books=shape(StatedTotal(debits=Decimal("100.00"), credits=Decimal("100.00"))),
    )

    assert total is not None
    assert total.agrees  # the wrong account, and the total cannot see it


def test_a_source_stating_no_total_reports_none(database: Database, entity: str) -> None:
    """Never computed in that case. Summing the rows ourselves and comparing that against the
    books we loaded them into would be our arithmetic against itself (`NFR-01`)."""
    landed(database, entity, entry("1", "Checking", "100.00"))

    assert check_total(database, entity_id=entity, principal=PERSON, books=shape()) is None


# --- the basis difference is adjudicated rather than explained ---------------------------


def test_a_basis_difference_nets_to_zero() -> None:
    """Cash basis excludes whole transactions — an unpaid invoice is a debit to receivables and
    a credit to income — so the difference is composed of balanced transactions.

    The figures are the real ones from a QuickBooks export: 25,469.00 appearing as both the
    receivable and the income not yet recognised against it.
    """
    assert nets_to_zero(
        [
            ("Accounts Receivable (A/R)", Decimal("25469.00"), Decimal("0")),
            ("Services", Decimal("-2518417.04"), Decimal("-2492948.04")),
        ]
    )


def test_a_difference_that_is_not_the_basis_fails() -> None:
    """**The case a real export does not produce**, and therefore the one that would never be
    exercised if it were not written. A single account out on its own is not a basis
    difference, whatever a note beside it says."""
    assert not nets_to_zero([("Checking", Decimal("100.00"), Decimal("90.00"))])


def test_agreement_nets_to_zero_vacuously() -> None:
    """No divergences is not a failure to net."""
    assert nets_to_zero([])
