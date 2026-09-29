"""Customers and draft invoices (`AR-01` to `AR-06`).

Everything up to the point of no return. Issuing — which assigns a number, posts the entry and
raises the obligation in one transaction — is a separate act and is not built yet.

**The append-only trigger is tested directly as well as through the service.** ADR-0007 puts
the guarantee in the database because a rule only the application honors is a rule the next
bulk-import script will not, so a test that only drove the service would prove the application
polite rather than the books safe.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

import psycopg
import pytest

from cfokit.ledger.errors import NotAuthorised
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.principal import ActorClass, Principal
from cfokit.receivables import LineInput, total_of
from cfokit.receivables.service import (
    CustomerNotFound,
    InvoiceNotDraft,
    LineWithoutIncome,
    create_customer,
    draft_invoice,
    invoice,
    list_customers,
    replace_lines,
    update_customer,
)

pytestmark = pytest.mark.integration

PERSON = Principal(id="user:geoff", actor_class=ActorClass.PERSON)


@pytest.fixture
def customer(database: Database, owned_books: tuple[str, str, str]) -> tuple[str, str, str]:
    """An entity, its revenue account, and one customer. Returns (entity, revenue, customer)."""
    entity_id, _, revenue = owned_books
    customer_id = create_customer(
        database,
        entity_id=entity_id,
        principal=PERSON,
        request_id="req",
        name="Milton Park",
        email="ap@example.invalid",
    )
    return entity_id, revenue, customer_id


def line(account_id: str, amount: str, quantity: str = "1") -> LineInput:
    return LineInput(
        description="Consulting",
        account_id=account_id,
        unit_amount=Decimal(amount),
        quantity=Decimal(quantity),
    )


# --- AR-01: customers exist as records -------------------------------------------------------


def test_a_customer_is_a_record_against_an_entity(
    database: Database, customer: tuple[str, str, str]
) -> None:
    entity_id, _, customer_id = customer

    listed = list_customers(database, entity_id=entity_id, principal=PERSON)

    assert [c.id for c in listed] == [customer_id]
    assert listed[0].name == "Milton Park"


def test_two_customers_may_share_a_name(
    database: Database, customer: tuple[str, str, str]
) -> None:
    """A uniqueness constraint would force an operator to invent a distinction that does not
    exist in their world. Two businesses really are called the same thing."""
    entity_id, _, _ = customer
    create_customer(
        database, entity_id=entity_id, principal=PERSON, request_id="req", name="Milton Park"
    )

    assert len(list_customers(database, entity_id=entity_id, principal=PERSON)) == 2


def test_a_customer_is_archived_rather_than_deleted(
    database: Database, customer: tuple[str, str, str]
) -> None:
    """An invoice names its customer for as long as the invoice exists (`AR-14`), so the
    customer has to stay reachable — out of the working list, not out of the books."""
    entity_id, _, customer_id = customer

    update_customer(
        database,
        entity_id=entity_id,
        principal=PERSON,
        request_id="req",
        customer_id=customer_id,
        archived=True,
    )

    assert list_customers(database, entity_id=entity_id, principal=PERSON) == []
    still_there = list_customers(
        database, entity_id=entity_id, principal=PERSON, include_archived=True
    )
    assert [c.id for c in still_there] == [customer_id]


def test_correcting_a_customer_that_does_not_exist_is_refused(
    database: Database, customer: tuple[str, str, str]
) -> None:
    entity_id, _, _ = customer

    with pytest.raises(CustomerNotFound):
        update_customer(
            database,
            entity_id=entity_id,
            principal=PERSON,
            request_id="req",
            customer_id=str(uuid.uuid4()),
            name="Nobody",
        )


# --- AR-02, AR-03: invoices with lines that name an income account ---------------------------


def test_a_draft_invoice_carries_its_lines(
    database: Database, customer: tuple[str, str, str]
) -> None:
    entity_id, revenue, customer_id = customer

    invoice_id = draft_invoice(
        database,
        entity_id=entity_id,
        principal=PERSON,
        request_id="req",
        customer_id=customer_id,
        lines=[line(revenue, "3500.00"), line(revenue, "150.50", quantity="2")],
        terms="Net 30",
    )
    drafted = invoice(database, entity_id=entity_id, principal=PERSON, invoice_id=invoice_id)

    assert drafted.status == "draft"
    assert drafted.number is None  # a draft consumes no number (`AR-05`)
    assert [line.position for line in drafted.lines] == [1, 2]
    assert drafted.total == Decimal("3801.00")


def test_a_line_naming_something_other_than_income_is_refused(
    database: Database, owned_books: tuple[str, str, str], customer: tuple[str, str, str]
) -> None:
    """`AR-03`: a line credits income, which is what makes an issued invoice a posting rather
    than a document. An expense account would produce an entry that balances and says
    something false."""
    entity_id, cash, _ = owned_books
    _, _, customer_id = customer

    with pytest.raises(LineWithoutIncome):
        draft_invoice(
            database,
            entity_id=entity_id,
            principal=PERSON,
            request_id="req",
            customer_id=customer_id,
            lines=[line(cash, "100.00")],
        )


def test_a_line_naming_no_account_at_all_is_refused(
    database: Database, customer: tuple[str, str, str]
) -> None:
    entity_id, _, customer_id = customer

    with pytest.raises(LineWithoutIncome):
        draft_invoice(
            database,
            entity_id=entity_id,
            principal=PERSON,
            request_id="req",
            customer_id=customer_id,
            lines=[line(str(uuid.uuid4()), "100.00")],
        )


def test_an_invoice_against_an_unknown_customer_is_refused(
    database: Database, customer: tuple[str, str, str]
) -> None:
    entity_id, revenue, _ = customer

    with pytest.raises(CustomerNotFound):
        draft_invoice(
            database,
            entity_id=entity_id,
            principal=PERSON,
            request_id="req",
            customer_id=str(uuid.uuid4()),
            lines=[line(revenue, "100.00")],
        )


def test_the_commodity_comes_from_the_entity_and_not_the_caller(
    database: Database, customer: tuple[str, str, str]
) -> None:
    """A caller who could state it could state their way past `LED-15`'s refusal of a foreign
    amount, which is why the ledger reads it the same way."""
    entity_id, revenue, customer_id = customer

    invoice_id = draft_invoice(
        database,
        entity_id=entity_id,
        principal=PERSON,
        request_id="req",
        customer_id=customer_id,
        lines=[line(revenue, "100.00")],
    )

    assert (
        invoice(
            database, entity_id=entity_id, principal=PERSON, invoice_id=invoice_id
        ).commodity
        == "USD"
    )


# --- AR-04: freely editable while a draft ----------------------------------------------------


def test_a_drafts_lines_can_be_rewritten(
    database: Database, customer: tuple[str, str, str]
) -> None:
    entity_id, revenue, customer_id = customer
    invoice_id = draft_invoice(
        database,
        entity_id=entity_id,
        principal=PERSON,
        request_id="req",
        customer_id=customer_id,
        lines=[line(revenue, "100.00")],
    )

    replace_lines(
        database,
        entity_id=entity_id,
        principal=PERSON,
        request_id="req",
        invoice_id=invoice_id,
        lines=[line(revenue, "250.00"), line(revenue, "50.00")],
    )
    rewritten = invoice(database, entity_id=entity_id, principal=PERSON, invoice_id=invoice_id)

    assert rewritten.total == Decimal("300.00")
    assert [line.position for line in rewritten.lines] == [1, 2]


def test_an_issued_invoices_lines_are_refused_by_the_database(
    database: Database, owner_conn: psycopg.Connection[Any], customer: tuple[str, str, str]
) -> None:
    """**Through the trigger, not the service** (ADR-0007, `AR-14`).

    Arranged with the owner connection so the invoice reaches `issued` without the issue path,
    which is not built. What is under test is that the guarantee holds against SQL that never
    asked the application's permission — which is the case the service layer cannot cover.
    """
    entity_id, revenue, customer_id = customer
    invoice_id = draft_invoice(
        database,
        entity_id=entity_id,
        principal=PERSON,
        request_id="req",
        customer_id=customer_id,
        lines=[line(revenue, "100.00")],
    )
    with owner_conn.cursor() as cur:
        # `issued_is_complete` refuses a partial issue, so this arranges a whole one: a
        # transaction to point at, then the invoice pointing at it.
        cur.execute(
            "INSERT INTO ledger_transaction"
            " (entity_id, status, transaction_date, actor_principal_id, actor_class)"
            " VALUES (%s, 'draft', current_date, 'test', 'person') RETURNING id",
            (entity_id,),
        )
        posted = cur.fetchone()
        assert posted is not None
        cur.execute(
            "UPDATE invoice SET status = 'issued', number = 1, issue_date = current_date,"
            " issued_at = now(), transaction_id = %s WHERE id = %s",
            (posted[0], invoice_id),
        )

    with pytest.raises(psycopg.errors.RestrictViolation), owner_conn.cursor() as cur:
        cur.execute("DELETE FROM invoice_line WHERE invoice_id = %s", (invoice_id,))

    with pytest.raises(InvoiceNotDraft):
        replace_lines(
            database,
            entity_id=entity_id,
            principal=PERSON,
            request_id="req",
            invoice_id=invoice_id,
            lines=[line(revenue, "999.00")],
        )


def test_an_invoice_is_never_deleted(
    database: Database, owner_conn: psycopg.Connection[Any], customer: tuple[str, str, str]
) -> None:
    entity_id, revenue, customer_id = customer
    invoice_id = draft_invoice(
        database,
        entity_id=entity_id,
        principal=PERSON,
        request_id="req",
        customer_id=customer_id,
        lines=[line(revenue, "100.00")],
    )

    with pytest.raises(psycopg.errors.RestrictViolation), owner_conn.cursor() as cur:
        cur.execute("DELETE FROM invoice WHERE id = %s", (invoice_id,))


# --- amounts ---------------------------------------------------------------------------------


def test_a_total_is_never_rounded(database: Database, customer: tuple[str, str, str]) -> None:
    """ADR-0025: rounding happens once, at presentation. A third of a unit is worth what it is
    worth, and what a document shows is decided at the edge."""
    entity_id, revenue, customer_id = customer
    third = LineInput(
        description="A third",
        account_id=revenue,
        unit_amount=Decimal("100"),
        quantity=Decimal("0.3333333333"),
    )

    invoice_id = draft_invoice(
        database,
        entity_id=entity_id,
        principal=PERSON,
        request_id="req",
        customer_id=customer_id,
        lines=[third],
    )
    stored = invoice(database, entity_id=entity_id, principal=PERSON, invoice_id=invoice_id)

    # 100 x 0.3333333333, exactly. Not 33.33, which is what a document would show.
    assert total_of([third]) == Decimal("33.3333333300")
    assert stored.total == total_of([third])
    assert stored.total != Decimal("33.33")


# --- authorisation is the ledger's ------------------------------------------------------------


def test_a_stranger_reads_nothing(database: Database, customer: tuple[str, str, str]) -> None:
    """`IAM-01`: holding no role in an entity means being able to do nothing with it — and a
    customer list is exactly the sort of thing a stranger must not enumerate."""
    entity_id, _, _ = customer
    stranger = Principal(id="user:nobody", actor_class=ActorClass.PERSON)

    with pytest.raises(NotAuthorised):
        list_customers(database, entity_id=entity_id, principal=stranger)
