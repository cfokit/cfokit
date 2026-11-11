"""Obligations and settlements as linked events (`LED-17`, ADR-0037).

> "An obligation and its settlement are recorded as two related events rather than one. An
> invoice raised in one period and paid in another is recoverable as either, depending on the
> basis in force."

**The link is stored, never inferred.** ADR-0037 § 3 calls this the decision's whole substance,
and the reason is what happens without it: the incumbents derive the relationship from account
and transaction type at report time, so a journal entry touching receivables lands in a
cash-basis report that should not contain it. Nothing here infers anything.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest

from cfokit.ledger.engine import Entry, Posting
from cfokit.ledger.errors import (
    NotAuthorized,
    ObligationNotCarried,
    ObligationNotFound,
    OneObligationPerTransaction,
    RaisingTransactionSettles,
    SettlementExceedsOutstanding,
    TransactionIncomplete,
)
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.administration import create_account, grant_role
from cfokit.ledger.service.principal import ActorClass, Principal
from cfokit.ledger.service.receivables import obligation_detail, outstanding_obligations
from cfokit.ledger.service.write import Applied, WriteContext, record_transaction

pytestmark = pytest.mark.integration

ISSUED = date(2026, 3, 14)
PAID = date(2026, 5, 2)
PERSON = Principal(id="user:geoff", actor_class=ActorClass.PERSON)


@pytest.fixture
def chart(database: Database, owned_books: tuple[str, str, str]) -> tuple[str, str, str, str]:
    """Cash and revenue from the fixture, plus receivables — where an invoice sits."""
    entity_id, cash, revenue = owned_books
    receivable = create_account(
        database,
        entity_id=entity_id,
        principal=PERSON,
        request_id="req",
        code=f"1200-{uuid.uuid4().hex[:6]}",
        name="Accounts receivable",
        account_type="asset",
    )
    return entity_id, cash, revenue, receivable


def write(
    database: Database,
    entity_id: str,
    debit: str,
    credit: str,
    when: date,
    amount: str,
    *,
    post: bool = True,
    raises: str | None = None,
    settles: tuple[Applied, ...] = (),
    on_account: str | None = None,
) -> str:
    return record_transaction(
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
        post=post,
        raises_obligation=Decimal(raises) if raises is not None else None,
        settles=settles,
        on_account=Decimal(on_account) if on_account is not None else None,
    ).transaction_id


def issue(
    database: Database, entity_id: str, receivable: str, revenue: str, amount: str
) -> str:
    """An invoice: income credited and receivables debited at issue (`AR-03`)."""
    write(database, entity_id, receivable, revenue, ISSUED, amount, raises=amount)
    return outstanding_obligations(database, entity_id=entity_id, principal=PERSON)[
        0
    ].obligation_id


def issue_later(
    database: Database, entity_id: str, receivable: str, revenue: str, amount: str
) -> str:
    """An invoice issued after whatever else the test recorded, by its obligation's id."""
    before = {
        o.obligation_id
        for o in outstanding_obligations(database, entity_id=entity_id, principal=PERSON)
    }
    write(database, entity_id, receivable, revenue, ISSUED, amount, raises=amount)
    [found] = [
        o.obligation_id
        for o in outstanding_obligations(database, entity_id=entity_id, principal=PERSON)
        if o.obligation_id not in before
    ]
    return found


def test_an_invoice_is_owed_until_it_is_settled(
    database: Database, chart: tuple[str, str, str, str]
) -> None:
    entity_id, _, revenue, receivable = chart
    issue(database, entity_id, receivable, revenue, "100.00")

    owed = outstanding_obligations(database, entity_id=entity_id, principal=PERSON)

    assert [(o.amount, o.settled, o.outstanding) for o in owed] == [
        (Decimal("100.0000000000"), Decimal(0), Decimal("100.0000000000"))
    ]


def test_an_obligation_records_the_account_that_carries_it(
    database: Database, chart: tuple[str, str, str, str]
) -> None:
    """ADR-0059 § 3: signed as its posting there. A payment matched to it later is settled
    against this account, and a settling leg cannot be inferred from one that does not say."""
    entity_id, _, revenue, receivable = chart
    issue(database, entity_id, receivable, revenue, "100.00")

    [owed] = outstanding_obligations(database, entity_id=entity_id, principal=PERSON)

    assert owed.account_id == receivable


def test_an_obligation_no_account_carries_is_refused(
    database: Database, chart: tuple[str, str, str, str]
) -> None:
    """Neither leg of a 100.00 invoice is 90.00, so which account is owed is unstated."""
    entity_id, _, revenue, receivable = chart

    with pytest.raises(ObligationNotCarried) as caught:
        write(database, entity_id, receivable, revenue, ISSUED, "100.00", raises="90.00")

    assert caught.value.code == "obligation_not_carried"
    assert outstanding_obligations(database, entity_id=entity_id, principal=PERSON) == ()


def test_a_payment_settles_it(database: Database, chart: tuple[str, str, str, str]) -> None:
    """The two events, linked. Nothing inferred the relationship from the accounts touched."""
    entity_id, cash, revenue, receivable = chart
    obligation_id = issue(database, entity_id, receivable, revenue, "100.00")

    write(
        database,
        entity_id,
        cash,
        receivable,
        PAID,
        "100.00",
        settles=(Applied(obligation_id=obligation_id, amount=Decimal("100.00")),),
    )

    assert outstanding_obligations(database, entity_id=entity_id, principal=PERSON) == ()


def test_partial_payment_leaves_the_rest_owed(
    database: Database, chart: tuple[str, str, str, str]
) -> None:
    """`AR-12`: partial payment is representable."""
    entity_id, cash, revenue, receivable = chart
    obligation_id = issue(database, entity_id, receivable, revenue, "100.00")

    write(
        database,
        entity_id,
        cash,
        receivable,
        PAID,
        "40.00",
        settles=(Applied(obligation_id=obligation_id, amount=Decimal("40.00")),),
    )

    owed = outstanding_obligations(database, entity_id=entity_id, principal=PERSON)
    assert [o.outstanding for o in owed] == [Decimal("60.0000000000")]


def test_more_than_one_payment_settles_one_invoice(
    database: Database, chart: tuple[str, str, str, str]
) -> None:
    """`AR-12`: "an invoice can be settled by more than one payment"."""
    entity_id, cash, revenue, receivable = chart
    obligation_id = issue(database, entity_id, receivable, revenue, "100.00")
    for amount in ("40.00", "60.00"):
        write(
            database,
            entity_id,
            cash,
            receivable,
            PAID,
            amount,
            settles=(Applied(obligation_id=obligation_id, amount=Decimal(amount)),),
        )

    detail = obligation_detail(
        database, entity_id=entity_id, principal=PERSON, obligation_id=obligation_id
    )

    assert [s.amount for s in detail.settlements] == [
        Decimal("40.0000000000"),
        Decimal("60.0000000000"),
    ]
    assert detail.obligation.outstanding == Decimal(0)


def test_one_payment_settles_more_than_one_invoice(
    database: Database, chart: tuple[str, str, str, str]
) -> None:
    """`AR-12`: "a payment is applied to one or more invoices".

    Applied as the payer meant it rather than split by a rule the system invented — no rule
    would be right more often than being told.
    """
    entity_id, cash, revenue, receivable = chart
    first = issue(database, entity_id, receivable, revenue, "100.00")
    write(database, entity_id, receivable, revenue, ISSUED, "50.00", raises="50.00")
    second = next(
        o.obligation_id
        for o in outstanding_obligations(database, entity_id=entity_id, principal=PERSON)
        if o.obligation_id != first
    )

    write(
        database,
        entity_id,
        cash,
        receivable,
        PAID,
        "150.00",
        settles=(
            Applied(obligation_id=first, amount=Decimal("100.00")),
            Applied(obligation_id=second, amount=Decimal("50.00")),
        ),
    )

    assert outstanding_obligations(database, entity_id=entity_id, principal=PERSON) == ()


def test_overpayment_is_representable(
    database: Database, chart: tuple[str, str, str, str]
) -> None:
    """`AR-12` says so, and refusing it would make the books unable to state what happened.

    ADR-0080 § 2 says how: the invoice is settled for what it was owed, and the excess is money
    on account, owed back to the customer on the same receivable, signed as its posting there.
    """
    entity_id, cash, revenue, receivable = chart
    obligation_id = issue(database, entity_id, receivable, revenue, "100.00")

    payment = write(
        database,
        entity_id,
        cash,
        receivable,
        PAID,
        "120.00",
        settles=(Applied(obligation_id=obligation_id, amount=Decimal("100.00")),),
        on_account="-20.00",
    )

    [credit] = outstanding_obligations(database, entity_id=entity_id, principal=PERSON)
    assert (credit.transaction_id, credit.account_id, credit.amount, credit.on_account) == (
        payment,
        receivable,
        Decimal("-20.0000000000"),
        True,
    )


def test_a_settlement_past_what_is_outstanding_is_refused(
    database: Database, chart: tuple[str, str, str, str]
) -> None:
    """ADR-0080 § 2: paid past zero, the invoice would recognize more than it raised, and the
    credit could not be applied to anything else."""
    entity_id, cash, revenue, receivable = chart
    obligation_id = issue(database, entity_id, receivable, revenue, "100.00")

    with pytest.raises(SettlementExceedsOutstanding):
        write(
            database,
            entity_id,
            cash,
            receivable,
            PAID,
            "120.00",
            settles=(Applied(obligation_id=obligation_id, amount=Decimal("120.00")),),
        )

    [owed] = outstanding_obligations(database, entity_id=entity_id, principal=PERSON)
    assert owed.outstanding == Decimal("100.0000000000")


def test_a_payment_before_any_invoice_is_held_on_account_and_applied_later(
    database: Database, chart: tuple[str, str, str, str]
) -> None:
    """`AR-12`: money received ahead of the invoice is the customer's until an invoice takes
    it. Applying it settles both, and leaves nothing owed either way."""
    entity_id, cash, revenue, receivable = chart
    write(database, entity_id, cash, receivable, ISSUED, "50.00", on_account="-50.00")
    [credit] = outstanding_obligations(database, entity_id=entity_id, principal=PERSON)
    invoice = issue_later(database, entity_id, receivable, revenue, "50.00")

    record_transaction(
        database,
        WriteContext(
            entity_id=entity_id,
            principal=PERSON,
            request_id="apply",
            idempotency_key=uuid.uuid4().hex,
        ),
        entry=Entry(
            transaction_date=PAID,
            postings=(
                Posting(account_id=receivable, amount=Decimal("-50.00"), commodity="USD"),
                Posting(account_id=receivable, amount=Decimal("50.00"), commodity="USD"),
            ),
            description="Apply credit",
        ),
        post=True,
        settles=(
            Applied(obligation_id=invoice, amount=Decimal("50.00")),
            Applied(obligation_id=credit.obligation_id, amount=Decimal("-50.00")),
        ),
    )

    assert outstanding_obligations(database, entity_id=entity_id, principal=PERSON) == ()


def test_money_on_account_needs_an_account_carrying_it(
    database: Database, chart: tuple[str, str, str, str]
) -> None:
    """Paid exactly, nothing is left on the receivable to hold, and nothing is guessed."""
    entity_id, cash, revenue, receivable = chart
    obligation_id = issue(database, entity_id, receivable, revenue, "100.00")

    with pytest.raises(ObligationNotCarried):
        write(
            database,
            entity_id,
            cash,
            receivable,
            PAID,
            "100.00",
            settles=(Applied(obligation_id=obligation_id, amount=Decimal("100.00")),),
            on_account="-100.00",
        )


def test_an_invoice_is_not_also_money_on_account(
    database: Database, chart: tuple[str, str, str, str]
) -> None:
    entity_id, _, revenue, receivable = chart

    with pytest.raises(OneObligationPerTransaction):
        write(
            database,
            entity_id,
            receivable,
            revenue,
            ISSUED,
            "100.00",
            raises="100.00",
            on_account="100.00",
        )


def test_a_transaction_that_raises_an_obligation_settles_none(
    database: Database, chart: tuple[str, str, str, str]
) -> None:
    """A credit note for the whole of a 100.00 invoice partly paid would settle the 60.00
    outstanding and owe 40.00 back. Raising and settling in one transaction is refused, because
    a cash view defers a raising transaction whole (ADR-0080 § 1), and nothing is written: it is
    two transactions."""
    entity_id, cash, revenue, receivable = chart
    obligation_id = issue(database, entity_id, receivable, revenue, "100.00")
    write(
        database,
        entity_id,
        cash,
        receivable,
        PAID,
        "40.00",
        settles=(Applied(obligation_id=obligation_id, amount=Decimal("40.00")),),
    )

    with pytest.raises(RaisingTransactionSettles):
        write(
            database,
            entity_id,
            revenue,
            receivable,
            PAID,
            "100.00",
            raises="-40.00",
            settles=(Applied(obligation_id=obligation_id, amount=Decimal("60.00")),),
        )

    [owed] = outstanding_obligations(database, entity_id=entity_id, principal=PERSON)
    assert (owed.obligation_id, Decimal(owed.outstanding)) == (obligation_id, Decimal("60.00"))


def test_it_is_recoverable_as_either_event(
    database: Database, chart: tuple[str, str, str, str]
) -> None:
    """`LED-17`: "recoverable as either, depending on the basis in force".

    Raised in March and paid in May. Both dates are retrievable from the one record, which is
    what a cash view and an accrual view each need — and neither is inferred.
    """
    entity_id, cash, revenue, receivable = chart
    obligation_id = issue(database, entity_id, receivable, revenue, "100.00")
    write(
        database,
        entity_id,
        cash,
        receivable,
        PAID,
        "100.00",
        settles=(Applied(obligation_id=obligation_id, amount=Decimal("100.00")),),
    )

    detail = obligation_detail(
        database, entity_id=entity_id, principal=PERSON, obligation_id=obligation_id
    )

    assert detail.obligation.transaction_date == ISSUED
    assert [s.transaction_date for s in detail.settlements] == [PAID]


def test_an_obligation_arising_later_is_excluded_as_of_an_earlier_date(
    database: Database, chart: tuple[str, str, str, str]
) -> None:
    entity_id, _, revenue, receivable = chart
    issue(database, entity_id, receivable, revenue, "100.00")

    assert (
        outstanding_obligations(
            database, entity_id=entity_id, principal=PERSON, as_of=date(2026, 1, 31)
        )
        == ()
    )


def test_a_draft_cannot_raise_an_obligation(
    database: Database, chart: tuple[str, str, str, str]
) -> None:
    """A draft is not in the books (`LED-07`), so it would be owed by nobody."""
    entity_id, _, revenue, receivable = chart

    with pytest.raises(TransactionIncomplete):
        write(
            database,
            entity_id,
            receivable,
            revenue,
            ISSUED,
            "100.00",
            post=False,
            raises="100.00",
        )


def test_settling_an_obligation_that_does_not_exist_is_refused(
    database: Database, chart: tuple[str, str, str, str]
) -> None:
    entity_id, cash, _, receivable = chart

    with pytest.raises(ObligationNotFound) as caught:
        write(
            database,
            entity_id,
            cash,
            receivable,
            PAID,
            "100.00",
            settles=(Applied(obligation_id=str(uuid.uuid4()), amount=Decimal("100.00")),),
        )

    assert caught.value.code == "obligation_not_found"


def test_reading_obligations_requires_the_read_privilege(
    database: Database, chart: tuple[str, str, str, str]
) -> None:
    entity_id, _, _, _ = chart

    with pytest.raises(NotAuthorized):
        outstanding_obligations(
            database,
            entity_id=entity_id,
            principal=Principal(id="user:stranger", actor_class=ActorClass.PERSON),
        )


def test_a_reader_can_read_them(database: Database, chart: tuple[str, str, str, str]) -> None:
    """The positive control: a rule refusing everyone would pass the test above."""
    entity_id, _, revenue, receivable = chart
    issue(database, entity_id, receivable, revenue, "100.00")
    grant_role(
        database,
        entity_id=entity_id,
        principal=PERSON,
        request_id="req",
        to_principal="user:reader",
        role="reader",
    )

    owed = outstanding_obligations(
        database,
        entity_id=entity_id,
        principal=Principal(id="user:reader", actor_class=ActorClass.PERSON),
    )

    assert len(owed) == 1
