"""Reports on a cash basis, derived from the stored obligation links (`AR-16`, ADR-0080).

> `AR-16`: an entity on a cash basis "recognizes the revenue on settlement rather than on
> issue".

Layer 3 of ADR-0036 against the service, with the database. The figures are ADR-0080 § 1's own
worked example: an invoice of 1,000.00, 600.00 design and 400.00 workshops, paid 400.00 in a
later period, recognizes 240.00 and 160.00 on the payment's date. Everything else follows from
the decision's Confirmation: money paid that no invoice takes is income on receipt, on a line of
its own (§ 2), a voided invoice recognizes nothing, what no link reaches reads as
posted and is counted on the report's face (`NFR-16`), a watermark reproduces the links as they
stood (`RPT-11`), and an accrual entity's reports are unchanged.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest

from cfokit.ledger.engine import UNAPPLIED_RECEIVED, Entry, Posting
from cfokit.ledger.repository.cash import Unlinked
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.administration import create_account, create_entity
from cfokit.ledger.service.principal import ActorClass, Principal
from cfokit.ledger.service.receivables import outstanding_obligations
from cfokit.ledger.service.reports import (
    account_detail,
    balance_sheet,
    profit_and_loss,
    trial_balance,
)
from cfokit.ledger.service.write import (
    Applied,
    WriteContext,
    record_transaction,
    reverse_transaction,
)

pytestmark = pytest.mark.integration

PERSON = Principal(id="user:geoff", actor_class=ActorClass.PERSON)

ISSUED = date(2026, 3, 14)
PAID = date(2026, 5, 2)
Q1 = (date(2026, 1, 1), date(2026, 3, 31))
Q2 = (date(2026, 4, 1), date(2026, 6, 30))
YEAR_END = date(2026, 12, 31)

CHART = (
    ("1000", "Cash", "asset"),
    ("1200", "Accounts receivable", "asset"),
    ("4000", "Design", "income"),
    ("4100", "Workshops", "income"),
)


def entity(database: Database, basis: str) -> tuple[str, dict[str, str]]:
    """An entity on `basis` with the chart above, built the way a customer builds one."""
    entity_id = create_entity(
        database,
        principal=PERSON,
        request_id="fixture",
        slug=f"{basis}-{uuid.uuid4().hex[:12]}",
        name="Studio",
        accounting_basis=basis,
        fiscal_year_end_month=12,
        fiscal_year_end_day=31,
        functional_currency="USD",
        time_zone="UTC",
    ).entity_id
    accounts = {
        code: create_account(
            database,
            entity_id=entity_id,
            principal=PERSON,
            request_id="fixture",
            code=code,
            name=name,
            account_type=account_type,
        )
        for code, name, account_type in CHART
    }
    return entity_id, accounts


@pytest.fixture
def cash_books(database: Database) -> tuple[str, dict[str, str]]:
    return entity(database, "cash")


def context(entity_id: str) -> WriteContext:
    return WriteContext(
        entity_id=entity_id,
        principal=PERSON,
        request_id=f"req-{uuid.uuid4().hex[:8]}",
        idempotency_key=uuid.uuid4().hex,
    )


def write(
    database: Database,
    entity_id: str,
    when: date,
    *postings: tuple[str, str],
    raises: str | None = None,
    settles: tuple[Applied, ...] = (),
    on_account: str | None = None,
    derived_from: dict[str, Any] | None = None,
) -> str:
    return record_transaction(
        database,
        context(entity_id),
        entry=Entry(
            transaction_date=when,
            postings=tuple(
                Posting(account_id=account, amount=Decimal(amount), commodity="USD")
                for account, amount in postings
            ),
            description="Entry",
        ),
        post=True,
        raises_obligation=Decimal(raises) if raises is not None else None,
        settles=settles,
        on_account=Decimal(on_account) if on_account is not None else None,
        derived_from=derived_from,
    ).transaction_id


def invoice(database: Database, entity_id: str, accounts: dict[str, str]) -> str:
    """ADR-0080 § 1's invoice: 1,000.00, of 600.00 design and 400.00 workshops."""
    write(
        database,
        entity_id,
        ISSUED,
        (accounts["1200"], "1000.00"),
        (accounts["4000"], "-600.00"),
        (accounts["4100"], "-400.00"),
        raises="1000.00",
    )
    [owed] = outstanding_obligations(database, entity_id=entity_id, principal=PERSON)
    return owed.obligation_id


def pay(
    database: Database, entity_id: str, accounts: dict[str, str], obligation: str, amount: str
) -> str:
    return write(
        database,
        entity_id,
        PAID,
        (accounts["1000"], amount),
        (accounts["1200"], f"-{amount}"),
        settles=(Applied(obligation_id=obligation, amount=Decimal(amount)),),
    )


def balances(rows: Any) -> dict[str, Decimal]:
    return {row.code: row.balance for row in rows}


def test_an_invoice_paid_in_part_recognizes_its_share_when_it_is_paid(
    database: Database, cash_books: tuple[str, dict[str, str]]
) -> None:
    """ADR-0080 § 1: nothing in the quarter it was issued, 240.00 and 160.00 in the quarter
    the 400.00 arrived."""
    entity_id, accounts = cash_books
    pay(database, entity_id, accounts, invoice(database, entity_id, accounts), "400.00")

    first = profit_and_loss(
        database, entity_id=entity_id, principal=PERSON, since=Q1[0], as_of=Q1[1]
    )
    second = profit_and_loss(
        database, entity_id=entity_id, principal=PERSON, since=Q2[0], as_of=Q2[1]
    )

    assert first.accounting_basis == "cash"
    assert balances(first.rows) == {}
    assert balances(second.rows) == {"4000": Decimal("-240.00"), "4100": Decimal("-160.00")}


def test_a_cash_trial_balance_shows_no_receivable_and_still_balances(
    database: Database, cash_books: tuple[str, dict[str, str]]
) -> None:
    """The 600.00 still owed is not presented anywhere on a cash basis (§ 1)."""
    entity_id, accounts = cash_books
    pay(database, entity_id, accounts, invoice(database, entity_id, accounts), "400.00")

    report = trial_balance(database, entity_id=entity_id, principal=PERSON, as_of=YEAR_END)

    assert balances(report.rows) == {
        "1000": Decimal("400.0000000000"),
        "4000": Decimal("-240.00"),
        "4100": Decimal("-160.00"),
    }
    assert sum(row.balance for row in report.rows) == 0


def test_a_cash_balance_sheet_balances_with_its_unclosed_earnings(
    database: Database, cash_books: tuple[str, dict[str, str]]
) -> None:
    entity_id, accounts = cash_books
    pay(database, entity_id, accounts, invoice(database, entity_id, accounts), "400.00")

    report = balance_sheet(database, entity_id=entity_id, principal=PERSON, as_of=YEAR_END)

    assert balances(report.rows) == {"1000": Decimal("400.0000000000")}
    assert sum(row.balance for row in report.unclosed) == Decimal("-400.00")


def test_account_detail_shows_the_recognition_on_the_payment(
    database: Database, cash_books: tuple[str, dict[str, str]]
) -> None:
    """`RPT-05` on a cash basis: the design line moves on the payment, not the invoice, and
    receivables show nothing at all."""
    entity_id, accounts = cash_books
    obligation = invoice(database, entity_id, accounts)
    payment = pay(database, entity_id, accounts, obligation, "400.00")

    design = account_detail(
        database,
        entity_id=entity_id,
        principal=PERSON,
        account_id=accounts["4000"],
        since=Q1[0],
        as_of=YEAR_END,
    )
    receivable = account_detail(
        database,
        entity_id=entity_id,
        principal=PERSON,
        account_id=accounts["1200"],
        since=Q1[0],
        as_of=YEAR_END,
    )

    assert [(e.transaction_id, e.transaction_date, e.amount) for e in design.entries] == [
        (payment, PAID, Decimal("-240.00"))
    ]
    assert design.closing_balance == Decimal("-240.00")
    assert receivable.entries == ()
    assert receivable.closing_balance == 0


def test_a_payment_settling_in_full_recognizes_exactly_what_was_invoiced(
    database: Database, cash_books: tuple[str, dict[str, str]]
) -> None:
    entity_id, accounts = cash_books
    obligation = invoice(database, entity_id, accounts)
    pay(database, entity_id, accounts, obligation, "400.00")
    pay(database, entity_id, accounts, obligation, "600.00")

    report = trial_balance(database, entity_id=entity_id, principal=PERSON, as_of=YEAR_END)

    assert balances(report.rows) == {
        "1000": Decimal("1000.0000000000"),
        "4000": Decimal("-600.0000000000"),
        "4100": Decimal("-400.0000000000"),
    }


def test_a_voided_invoice_recognizes_nothing(
    database: Database, cash_books: tuple[str, dict[str, str]]
) -> None:
    """§ 2: the void is deferred with the invoice it reverses."""
    entity_id, accounts = cash_books
    invoice(database, entity_id, accounts)
    [original] = outstanding_obligations(database, entity_id=entity_id, principal=PERSON)
    reverse_transaction(
        database,
        context(entity_id),
        transaction_id=original.transaction_id,
        current_period_date=PAID,
    )

    report = trial_balance(database, entity_id=entity_id, principal=PERSON, as_of=YEAR_END)

    assert balances(report.rows) == {}
    assert report.unlinked == Unlinked(postings=0, imported_transactions=0)


def test_what_no_link_reaches_reads_as_posted_and_is_counted(
    database: Database, cash_books: tuple[str, dict[str, str]]
) -> None:
    """§ 3 and `NFR-16`: a journal entry to receivables is presented as posted, and the report
    says so on its face rather than guessing what it was."""
    entity_id, accounts = cash_books
    invoice(database, entity_id, accounts)
    write(database, entity_id, PAID, (accounts["1200"], "50.00"), (accounts["4000"], "-50.00"))

    report = trial_balance(database, entity_id=entity_id, principal=PERSON, as_of=YEAR_END)

    assert balances(report.rows) == {
        "1200": Decimal("50.0000000000"),
        "4000": Decimal("-50.0000000000"),
    }
    assert report.unlinked == Unlinked(postings=1, imported_transactions=0)


def test_imported_history_is_counted(
    database: Database, cash_books: tuple[str, dict[str, str]]
) -> None:
    """No import records payment links yet, so what one landed reads as posted (§ 3)."""
    entity_id, accounts = cash_books
    write(
        database,
        entity_id,
        ISSUED,
        (accounts["1000"], "75.00"),
        (accounts["4000"], "-75.00"),
        derived_from={"system": "quickbooks", "import_id": str(uuid.uuid4()), "reference": "1"},
    )

    report = profit_and_loss(
        database, entity_id=entity_id, principal=PERSON, since=Q1[0], as_of=Q1[1]
    )

    assert balances(report.rows) == {"4000": Decimal("-75.0000000000")}
    assert report.unlinked == Unlinked(postings=0, imported_transactions=1)


def test_a_watermark_reproduces_the_cash_view_as_it_stood(
    database: Database, cash_books: tuple[str, dict[str, str]]
) -> None:
    """`RPT-11`: a payment posted after the watermark recognizes nothing as of it."""
    entity_id, accounts = cash_books
    obligation = invoice(database, entity_id, accounts)
    taken = datetime.now(UTC)
    pay(database, entity_id, accounts, obligation, "400.00")

    then = trial_balance(
        database, entity_id=entity_id, principal=PERSON, as_of=YEAR_END, watermark=taken
    )

    assert balances(then.rows) == {}


def test_an_accrual_entity_is_unchanged(database: Database) -> None:
    """ADR-0037: basis is presentation, and accrual is the posted figures as they stand."""
    entity_id, accounts = entity(database, "accrual")
    pay(database, entity_id, accounts, invoice(database, entity_id, accounts), "400.00")

    report = trial_balance(database, entity_id=entity_id, principal=PERSON, as_of=YEAR_END)

    assert balances(report.rows) == {
        "1000": Decimal("400.0000000000"),
        "1200": Decimal("600.0000000000"),
        "4000": Decimal("-600.0000000000"),
        "4100": Decimal("-400.0000000000"),
    }
    assert report.unlinked is None


def test_an_overpayment_s_excess_is_income_on_receipt_as_unapplied_payments(
    database: Database, cash_books: tuple[str, dict[str, str]]
) -> None:
    """§ 2: 1,200.00 received on the 1,000.00 invoice recognizes the invoice and 200.00 of
    unapplied payments, on the payment's date, and the receivable reads nothing."""
    entity_id, accounts = cash_books
    obligation = invoice(database, entity_id, accounts)
    write(
        database,
        entity_id,
        PAID,
        (accounts["1000"], "1200.00"),
        (accounts["1200"], "-1200.00"),
        settles=(Applied(obligation_id=obligation, amount=Decimal("1000.00")),),
        on_account="-200.00",
    )

    report = profit_and_loss(
        database, entity_id=entity_id, principal=PERSON, since=Q2[0], as_of=Q2[1]
    )
    whole = trial_balance(database, entity_id=entity_id, principal=PERSON, as_of=YEAR_END)

    assert [(row.account_id, row.name, row.balance) for row in report.rows] == [
        (accounts["4000"], "Design", Decimal("-600.0000000000")),
        (accounts["4100"], "Workshops", Decimal("-400.0000000000")),
        (UNAPPLIED_RECEIVED, "Unapplied payments", Decimal("-200.00")),
    ]
    assert "1200" not in balances(whole.rows)
    assert sum(row.balance for row in whole.rows) == 0


def test_a_credit_applied_to_a_later_invoice_counts_its_income_once(
    database: Database, cash_books: tuple[str, dict[str, str]]
) -> None:
    """§ 2: 500.00 received before any invoice is income when it arrives. Applied to a 300.00
    invoice later, the invoice's income is recognized and the same 300.00 leaves unapplied
    payments, so the year's income is still the 500.00 received."""
    entity_id, accounts = cash_books
    write(
        database,
        entity_id,
        ISSUED,
        (accounts["1000"], "500.00"),
        (accounts["1200"], "-500.00"),
        on_account="-500.00",
    )
    [credit] = outstanding_obligations(database, entity_id=entity_id, principal=PERSON)
    write(
        database,
        entity_id,
        PAID,
        (accounts["1200"], "300.00"),
        (accounts["4000"], "-300.00"),
        raises="300.00",
    )
    owed = next(
        o
        for o in outstanding_obligations(database, entity_id=entity_id, principal=PERSON)
        if not o.on_account
    )
    write(
        database,
        entity_id,
        PAID,
        (accounts["1200"], "-300.00"),
        (accounts["1200"], "300.00"),
        settles=(
            Applied(obligation_id=owed.obligation_id, amount=Decimal("300.00")),
            Applied(obligation_id=credit.obligation_id, amount=Decimal("-300.00")),
        ),
    )

    first = profit_and_loss(
        database, entity_id=entity_id, principal=PERSON, since=Q1[0], as_of=Q1[1]
    )
    second = profit_and_loss(
        database, entity_id=entity_id, principal=PERSON, since=Q2[0], as_of=Q2[1]
    )
    year = profit_and_loss(
        database, entity_id=entity_id, principal=PERSON, since=Q1[0], as_of=YEAR_END
    )

    assert balances(first.rows) == {"": Decimal("-500.00")}
    assert balances(second.rows) == {"": Decimal("300.00"), "4000": Decimal("-300.00")}
    assert sum(row.balance for row in year.rows) == Decimal("-500.00")
