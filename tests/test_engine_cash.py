"""The cash view derived from obligations and their settlements (`AR-16`, ADR-0080).

Layer 1 of ADR-0036: no protocol, no model, no database. The worked figures come from ADR-0080
§ 1 and § 2, which state them; the properties are the ones its Confirmation names — cash-view
recognition equals the amounts settled, in proportion; an obligation fully settled recognizes
exactly the postings that raised it; and every transaction the view changes balances.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import date
from decimal import Decimal
from itertools import pairwise

from hypothesis import given
from hypothesis import strategies as st

from cfokit.ledger.engine import (
    UNAPPLIED_PAID,
    UNAPPLIED_RECEIVED,
    Adjustment,
    Line,
    Raised,
    Reversal,
    Settled,
    cash_adjustments,
)

ISSUED = date(2026, 3, 14)
PAID = date(2026, 5, 2)
LATER = date(2026, 7, 1)

RECEIVABLE = "1200"
BANK = "1000"
DESIGN = "4000"
WORKSHOPS = "4100"
PAYABLE = "2000"
SUPPLIES = "6000"
RETURNS = "4900"
BAD_DEBTS = "6900"


def invoice(amount: str, *lines: tuple[str, str], obligation: str = "inv") -> Raised:
    """An invoice debiting receivables and crediting each income line (`AR-03`)."""
    return Raised(
        obligation_id=obligation,
        transaction_id=f"{obligation}-tx",
        transaction_date=ISSUED,
        account_id=RECEIVABLE,
        amount=Decimal(amount),
        commodity="USD",
        lines=(
            Line(account_id=RECEIVABLE, amount=Decimal(amount)),
            *(Line(account_id=account, amount=-Decimal(each)) for account, each in lines),
        ),
    )


def paid(
    transaction_id: str, amount: str, when: date = PAID, obligation: str = "inv"
) -> Settled:
    return Settled(
        obligation_id=obligation,
        transaction_id=transaction_id,
        transaction_date=when,
        amount=Decimal(amount),
    )


def on_account(
    transaction_id: str,
    amount: str,
    when: date = PAID,
    account: str = RECEIVABLE,
    obligation: str = "credit",
) -> Raised:
    """Money on account, raised by the payment that brought it in (§ 2). Its lines are the
    payment's, which the view does not read."""
    return Raised(
        obligation_id=obligation,
        transaction_id=transaction_id,
        transaction_date=when,
        account_id=account,
        amount=Decimal(amount),
        commodity="USD",
        lines=(),
        on_account=True,
    )


def cash_view(
    posted: Iterable[tuple[str, str, str]], adjustments: Iterable[Adjustment]
) -> dict[str, Decimal]:
    """Each account's cash-basis figure: the posted amounts, as (transaction, account, amount),
    plus the view's adjustments, with the accounts that come to nothing left out."""
    figures: defaultdict[str, Decimal] = defaultdict(Decimal)
    for _, account, amount in posted:
        figures[account] += Decimal(amount)
    for adjustment in adjustments:
        figures[adjustment.account_id] += adjustment.amount
    return {account: amount for account, amount in figures.items() if amount != 0}


INVOICE_POSTED = (
    ("inv-tx", RECEIVABLE, "1000.00"),
    ("inv-tx", DESIGN, "-600.00"),
    ("inv-tx", WORKSHOPS, "-400.00"),
)


def by_transaction(adjustments: Iterable[Adjustment]) -> dict[str, dict[str, Decimal]]:
    found: defaultdict[str, defaultdict[str, Decimal]] = defaultdict(
        lambda: defaultdict(Decimal)
    )
    for adjustment in adjustments:
        found[adjustment.transaction_id][adjustment.account_id] += adjustment.amount
    return {tx: dict(amounts) for tx, amounts in found.items()}


def test_an_unpaid_invoice_recognizes_nothing() -> None:
    """§ 1: a transaction raising an obligation contributes nothing by itself."""
    raised = invoice("1000.00", (DESIGN, "600.00"), (WORKSHOPS, "400.00"))

    adjustments = by_transaction(cash_adjustments([raised], [], []))

    # Taken out whole: the receivable and both income lines.
    assert adjustments == {
        "inv-tx": {
            RECEIVABLE: Decimal("-1000.00"),
            DESIGN: Decimal("600.00"),
            WORKSHOPS: Decimal("400.00"),
        }
    }


def test_a_partial_payment_recognizes_its_share_of_each_line() -> None:
    """ADR-0080 § 1's own example: 1,000.00 of 600.00 design and 400.00 workshops, paid 400.00,
    recognizes 240.00 and 160.00 on the payment's date. The payment's credit to receivables is
    not presented; its debit to the bank stands as posted."""
    raised = invoice("1000.00", (DESIGN, "600.00"), (WORKSHOPS, "400.00"))

    adjustments = by_transaction(cash_adjustments([raised], [paid("pay", "400.00")], []))

    assert adjustments["pay"] == {
        RECEIVABLE: Decimal("400.00"),
        DESIGN: Decimal("-240.00"),
        WORKSHOPS: Decimal("-160.00"),
    }


def test_a_settlement_recognizes_on_its_own_date() -> None:
    """§ 1: a settlement in a later period recognizes in that period (`LED-17`)."""
    raised = invoice("1000.00", (DESIGN, "1000.00"))

    [first, *_] = [
        a
        for a in cash_adjustments([raised], [paid("pay", "1000.00", when=LATER)], [])
        if a.transaction_id == "pay"
    ]

    assert first.transaction_date == LATER


def test_full_settlement_in_pieces_recognizes_exactly_what_raised_it() -> None:
    """Three payments of a third each do not divide evenly, and the cumulative shares still
    land every line exactly on what the invoice raised (§ 1)."""
    raised = invoice("100.00", (DESIGN, "33.33"), (WORKSHOPS, "66.67"))
    payments = [paid("p1", "33.33"), paid("p2", "33.33"), paid("p3", "33.34")]

    adjustments = by_transaction(cash_adjustments([raised], payments, []))

    recognized: defaultdict[str, Decimal] = defaultdict(Decimal)
    for tx in ("p1", "p2", "p3"):
        for account, amount in adjustments[tx].items():
            recognized[account] += amount
    assert recognized == {
        RECEIVABLE: Decimal("100.00"),
        DESIGN: Decimal("-33.33"),
        WORKSHOPS: Decimal("-66.67"),
    }


def test_a_voided_invoice_recognizes_nothing() -> None:
    """§ 2: a reversal is deferred with its original, so the pair recognizes nothing."""
    raised = invoice("1000.00", (DESIGN, "1000.00"))
    voided = Reversal(transaction_id="void", transaction_date=PAID, reverses_id="inv-tx")

    adjustments = by_transaction(cash_adjustments([raised], [], [voided]))

    assert adjustments["void"] == {RECEIVABLE: Decimal("1000.00"), DESIGN: Decimal("-1000.00")}


def test_a_payment_that_bounces_takes_back_what_it_recognized() -> None:
    """§ 2: the reversal of a payment is the negation of what the payment recognized."""
    raised = invoice("1000.00", (DESIGN, "1000.00"))
    bounced = Reversal(transaction_id="bounce", transaction_date=LATER, reverses_id="pay")

    adjustments = by_transaction(
        cash_adjustments([raised], [paid("pay", "1000.00")], [bounced])
    )

    assert adjustments["bounce"] == {
        RECEIVABLE: Decimal("-1000.00"),
        DESIGN: Decimal("1000.00"),
    }


def test_a_bill_is_recognized_when_it_is_paid() -> None:
    """Payables inherit the rule unchanged (ADR-0037): a bill's obligation is negative, its
    expense line positive, and paying half expenses half."""
    bill = Raised(
        obligation_id="bill",
        transaction_id="bill-tx",
        transaction_date=ISSUED,
        account_id=PAYABLE,
        amount=Decimal("-500.00"),
        commodity="USD",
        lines=(
            Line(account_id=SUPPLIES, amount=Decimal("500.00")),
            Line(account_id=PAYABLE, amount=Decimal("-500.00")),
        ),
    )
    payment = Settled(
        obligation_id="bill",
        transaction_id="pay",
        transaction_date=PAID,
        amount=Decimal("-250.00"),
    )

    adjustments = by_transaction(cash_adjustments([bill], [payment], []))

    assert adjustments["pay"] == {PAYABLE: Decimal("-250.00"), SUPPLIES: Decimal("250.00")}


def test_a_discount_line_is_recognized_in_proportion_too() -> None:
    """1,100.00 of work less a 100.00 discount, half paid: half of each line (§ 1)."""
    raised = invoice("1000.00", (DESIGN, "1100.00"), (WORKSHOPS, "-100.00"))

    adjustments = by_transaction(cash_adjustments([raised], [paid("pay", "500.00")], []))

    assert adjustments["pay"] == {
        RECEIVABLE: Decimal("500.00"),
        DESIGN: Decimal("-550.00"),
        WORKSHOPS: Decimal("50.00"),
    }


def test_a_settlement_of_an_obligation_not_given_changes_nothing() -> None:
    """Nothing says what it recognizes, and nothing is guessed (`NFR-16`)."""
    assert cash_adjustments([], [paid("pay", "100.00")], []) == []


def test_an_overpayment_recognizes_the_invoice_and_its_excess_on_receipt() -> None:
    """§ 2: 1,200.00 paid on the 1,000.00 invoice settles it and leaves 200.00 on account,
    which is income when it arrives, on a line of its own."""
    raised = invoice("1000.00", (DESIGN, "600.00"), (WORKSHOPS, "400.00"))
    credit = on_account("pay", "-200.00")

    adjustments = by_transaction(
        cash_adjustments([raised, credit], [paid("pay", "1000.00")], [])
    )

    assert adjustments["pay"] == {
        RECEIVABLE: Decimal("1200.00"),
        DESIGN: Decimal("-600.00"),
        WORKSHOPS: Decimal("-400.00"),
        UNAPPLIED_RECEIVED: Decimal("-200.00"),
    }


def test_money_applied_to_a_later_invoice_moves_off_unapplied_payments() -> None:
    """§ 2: applied to an invoice, the credit recognizes the invoice's share and takes the same
    amount off unapplied payments, so the income is counted once."""
    credit = on_account("pay", "-500.00", when=ISSUED)
    later = invoice("300.00", (DESIGN, "300.00"), obligation="inv2")
    applied = [
        paid("apply", "300.00", obligation="inv2"),
        paid("apply", "-300.00", obligation="credit"),
    ]

    adjustments = by_transaction(cash_adjustments([credit, later], applied, []))

    assert adjustments["pay"] == {
        RECEIVABLE: Decimal("500.00"),
        UNAPPLIED_RECEIVED: Decimal("-500.00"),
    }
    assert adjustments["apply"] == {
        DESIGN: Decimal("-300.00"),
        UNAPPLIED_RECEIVED: Decimal("300.00"),
    }


def test_a_refund_takes_the_credit_off_unapplied_payments_as_the_cash_leaves() -> None:
    credit = on_account("pay", "-200.00")
    refund = paid("refund", "-200.00", when=LATER, obligation="credit")

    adjustments = by_transaction(cash_adjustments([credit], [refund], []))

    assert adjustments["refund"] == {
        RECEIVABLE: Decimal("-200.00"),
        UNAPPLIED_RECEIVED: Decimal("200.00"),
    }


def test_an_overpayment_that_bounces_takes_back_all_it_recognized() -> None:
    raised = invoice("1000.00", (DESIGN, "1000.00"))
    credit = on_account("pay", "-200.00")
    bounced = Reversal(transaction_id="bounce", transaction_date=LATER, reverses_id="pay")

    adjustments = by_transaction(
        cash_adjustments([raised, credit], [paid("pay", "1000.00")], [bounced])
    )

    assert adjustments["bounce"] == {
        RECEIVABLE: Decimal("-1200.00"),
        DESIGN: Decimal("1000.00"),
        UNAPPLIED_RECEIVED: Decimal("200.00"),
    }


def test_money_paid_to_a_vendor_ahead_of_any_bill_is_expense_when_it_leaves() -> None:
    """Payables inherit § 2 unchanged: a deposit with a vendor is positive on the payable,
    and reads as unapplied bill payments until a bill takes it."""
    deposit = on_account("pay", "300.00", account=PAYABLE)

    adjustments = by_transaction(cash_adjustments([deposit], [], []))

    assert adjustments["pay"] == {
        PAYABLE: Decimal("-300.00"),
        UNAPPLIED_PAID: Decimal("300.00"),
    }


def test_a_credit_note_settles_the_invoice_it_corrects_and_recognizes_nothing() -> None:
    """§ 2: a credit note settles the invoice it corrects. Its own debit to income and the share
    it recognizes cancel, so a credited invoice recognizes nothing on a cash basis (`AR-14`)."""
    raised = invoice("1000.00", (DESIGN, "600.00"), (WORKSHOPS, "400.00"))
    credited = (
        ("credit-tx", DESIGN, "600.00"),
        ("credit-tx", WORKSHOPS, "400.00"),
        ("credit-tx", RECEIVABLE, "-1000.00"),
    )

    adjustments = cash_adjustments([raised], [paid("credit-tx", "1000.00")], [])

    assert cash_view([*INVOICE_POSTED, *credited], adjustments) == {}


def test_a_write_off_settles_what_is_left_and_nets_to_nothing() -> None:
    """§ 2: paid 400.00 and the rest written off, the invoice recognizes 400.00 on the payment
    and the write-off's bad-debt expense nets against the share it settles, so profit is the
    cash received and the write-off is no expense on a cash basis (`AR-18`, Treas. Reg.
    § 1.166-1(e))."""
    raised = invoice("1000.00", (DESIGN, "600.00"), (WORKSHOPS, "400.00"))
    payment = (("pay", BANK, "400.00"), ("pay", RECEIVABLE, "-400.00"))
    written_off = (("write-off", BAD_DEBTS, "600.00"), ("write-off", RECEIVABLE, "-600.00"))
    settled = [paid("pay", "400.00"), paid("write-off", "600.00", when=LATER)]

    adjustments = cash_adjustments([raised], settled, [])
    view = cash_view([*INVOICE_POSTED, *payment, *written_off], adjustments)

    assert view == {
        BANK: Decimal("400.00"),
        DESIGN: Decimal("-600.00"),
        WORKSHOPS: Decimal("-400.00"),
        BAD_DEBTS: Decimal("600.00"),
    }
    assert by_transaction(adjustments)["write-off"] == {
        RECEIVABLE: Decimal("600.00"),
        DESIGN: Decimal("-360.00"),
        WORKSHOPS: Decimal("-240.00"),
    }


def test_a_credit_note_on_a_paid_invoice_waits_for_the_refund() -> None:
    """§ 2: a credit note on an invoice already paid raises an obligation owed to the customer.
    It recognizes nothing until the refund settles it, and the refund takes the income back on
    its own date, as the cash leaves."""
    credit_note = Raised(
        obligation_id="credit",
        transaction_id="credit-tx",
        transaction_date=PAID,
        account_id=RECEIVABLE,
        amount=Decimal("-1000.00"),
        commodity="USD",
        lines=(
            Line(account_id=DESIGN, amount=Decimal("600.00")),
            Line(account_id=WORKSHOPS, amount=Decimal("400.00")),
            Line(account_id=RECEIVABLE, amount=Decimal("-1000.00")),
        ),
    )
    refund = paid("refund", "-1000.00", when=LATER, obligation="credit")

    adjustments = by_transaction(cash_adjustments([credit_note], [refund], []))

    assert adjustments["credit-tx"] == {
        DESIGN: Decimal("-600.00"),
        WORKSHOPS: Decimal("-400.00"),
        RECEIVABLE: Decimal("1000.00"),
    }
    assert adjustments["refund"] == {
        RECEIVABLE: Decimal("-1000.00"),
        DESIGN: Decimal("600.00"),
        WORKSHOPS: Decimal("400.00"),
    }


def test_a_credit_note_applied_to_a_later_invoice_moves_no_income() -> None:
    """§ 2: applied to a later invoice, the credit note's reduction and the invoice's share land
    on the same date and net to nothing, because no cash moved."""
    credit_note = Raised(
        obligation_id="credit",
        transaction_id="credit-tx",
        transaction_date=PAID,
        account_id=RECEIVABLE,
        amount=Decimal("-500.00"),
        commodity="USD",
        lines=(
            Line(account_id=DESIGN, amount=Decimal("500.00")),
            Line(account_id=RECEIVABLE, amount=Decimal("-500.00")),
        ),
    )
    later = invoice("300.00", (WORKSHOPS, "300.00"), obligation="inv2")
    applied = [
        paid("apply", "300.00", when=LATER, obligation="inv2"),
        paid("apply", "-300.00", when=LATER, obligation="credit"),
    ]

    adjustments = by_transaction(cash_adjustments([credit_note, later], applied, []))

    assert adjustments["apply"] == {DESIGN: Decimal("300.00"), WORKSHOPS: Decimal("-300.00")}


# --- Properties --------------------------------------------------------------------------

LINE_CENTS = st.lists(
    st.integers(min_value=-500_000, max_value=5_000_000), min_size=1, max_size=6
).filter(lambda cents: sum(cents) > 0)


def cents(units: int) -> Decimal:
    return Decimal(units).scaleb(-2)


@st.composite
def settled_invoices(draw: st.DrawFn) -> tuple[Raised, list[Settled]]:
    """An invoice of some lines, of either sign, settled in full by some payments."""
    lines = draw(LINE_CENTS)
    total = sum(lines)
    cuts = sorted(draw(st.lists(st.integers(min_value=1, max_value=total), max_size=6)))
    bounds = [0, *cuts, total]
    pieces = [b - a for a, b in pairwise(bounds) if b > a]
    raised = Raised(
        obligation_id="inv",
        transaction_id="inv-tx",
        transaction_date=ISSUED,
        account_id=RECEIVABLE,
        amount=cents(total),
        commodity="USD",
        lines=(
            Line(account_id=RECEIVABLE, amount=cents(total)),
            *(
                Line(account_id=f"4{i:03d}", amount=-cents(each))
                for i, each in enumerate(lines)
            ),
        ),
    )
    payments = [paid(f"p{i}", str(cents(piece))) for i, piece in enumerate(pieces)]
    return raised, payments


@given(settled_invoices())
def test_every_transaction_the_view_changes_still_balances(
    case: tuple[Raised, list[Settled]],
) -> None:
    raised, payments = case
    for amounts in by_transaction(cash_adjustments([raised], payments, [])).values():
        assert sum(amounts.values(), start=Decimal(0)) == 0


@given(settled_invoices())
def test_each_settlement_recognizes_what_it_settled(case: tuple[Raised, list[Settled]]) -> None:
    raised, payments = case
    adjustments = by_transaction(cash_adjustments([raised], payments, []))
    for payment in payments:
        recognized = sum(
            (v for k, v in adjustments[payment.transaction_id].items() if k != RECEIVABLE),
            start=Decimal(0),
        )
        assert recognized == -payment.amount


@given(settled_invoices())
def test_an_obligation_fully_settled_recognizes_exactly_what_raised_it(
    case: tuple[Raised, list[Settled]],
) -> None:
    raised, payments = case
    adjustments = by_transaction(cash_adjustments([raised], payments, []))

    recognized: defaultdict[str, Decimal] = defaultdict(Decimal)
    for payment in payments:
        for account, amount in adjustments[payment.transaction_id].items():
            recognized[account] += amount

    for line in raised.lines:
        if line.account_id != RECEIVABLE:
            assert recognized[line.account_id] == line.amount


@given(settled_invoices())
def test_each_share_is_within_a_cent_of_its_proportion(
    case: tuple[Raised, list[Settled]],
) -> None:
    raised, payments = case
    adjustments = by_transaction(cash_adjustments([raised], payments, []))

    cumulative = Decimal(0)
    through: defaultdict[str, Decimal] = defaultdict(Decimal)
    for payment in payments:
        cumulative += payment.amount
        for account, amount in adjustments[payment.transaction_id].items():
            through[account] += amount
        for line in raised.lines:
            if line.account_id == RECEIVABLE:
                continue
            exact = line.amount * cumulative / raised.amount
            assert abs(through[line.account_id] - exact) < Decimal("0.01")


@given(settled_invoices())
def test_reversing_everything_restores_the_posted_figures(
    case: tuple[Raised, list[Settled]],
) -> None:
    """A voided invoice and its bounced payments together recognize nothing at all."""
    raised, payments = case
    reversals = [
        Reversal(transaction_id=f"r-{tx}", transaction_date=LATER, reverses_id=tx)
        for tx in [*(p.transaction_id for p in payments), "inv-tx"]
    ]

    net: defaultdict[str, Decimal] = defaultdict(Decimal)
    for adjustment in cash_adjustments([raised], payments, reversals):
        net[adjustment.account_id] += adjustment.amount

    assert all(amount == 0 for amount in net.values())


@st.composite
def overpaid_invoices(draw: st.DrawFn) -> tuple[Raised, list[Settled], Raised]:
    """An invoice settled in full, the last payment bringing in more than it settled (§ 2)."""
    raised, payments = draw(settled_invoices())
    excess = draw(st.integers(min_value=1, max_value=5_000_000))
    return raised, payments, on_account(payments[-1].transaction_id, str(-cents(excess)))


@given(overpaid_invoices())
def test_an_overpayment_recognizes_what_was_received(
    case: tuple[Raised, list[Settled], Raised],
) -> None:
    """Cash method: income is what was received, so each payment recognizes its whole amount,
    and the transaction still balances."""
    raised, payments, credit = case
    adjustments = by_transaction(cash_adjustments([raised, credit], payments, []))
    for payment in payments:
        amounts = adjustments[payment.transaction_id]
        assert sum(amounts.values(), start=Decimal(0)) == 0
        received = payment.amount
        if payment.transaction_id == credit.transaction_id:
            received -= credit.amount
        recognized = sum((v for k, v in amounts.items() if k != RECEIVABLE), start=Decimal(0))
        assert recognized == -received


# What each kind of settling transaction posts against the receivable: a payment the bank, a
# credit note income, and a write-off bad-debt expense (§ 2).
COUNTER = {"payment": BANK, "credit note": RETURNS, "write-off": BAD_DEBTS}


@st.composite
def settled_any_way(
    draw: st.DrawFn,
) -> tuple[Raised, list[Settled], dict[str, str]]:
    """An invoice settled in full by some mix of payments, credit notes and write-offs."""
    raised, settlements = draw(settled_invoices())
    kinds = {
        settlement.transaction_id: draw(st.sampled_from(sorted(COUNTER)))
        for settlement in settlements
    }
    return raised, settlements, kinds


@given(settled_any_way())
def test_cash_basis_profit_is_the_cash_received_however_the_invoice_is_settled(
    case: tuple[Raised, list[Settled], dict[str, str]],
) -> None:
    """§ 2: a payment, a credit note and a write-off are the same rule. Whatever mix settles an
    invoice, its cash-basis profit is what was paid, and a credit note or a write-off nets to
    nothing in profit on its own date."""
    raised, settlements, kinds = case
    posted = [("inv-tx", line.account_id, str(line.amount)) for line in raised.lines]
    for settlement in settlements:
        tx, amount = settlement.transaction_id, str(settlement.amount)
        posted += [(tx, COUNTER[kinds[tx]], amount), (tx, RECEIVABLE, f"-{amount}")]
    adjustments = cash_adjustments([raised], settlements, [])

    def profit(view: dict[str, Decimal]) -> Decimal:
        return -sum(
            (amount for account, amount in view.items() if account not in {BANK, RECEIVABLE}),
            start=Decimal(0),
        )

    view = cash_view(posted, adjustments)
    received = sum(
        (s.amount for s in settlements if kinds[s.transaction_id] == "payment"),
        start=Decimal(0),
    )
    assert RECEIVABLE not in view
    assert profit(view) == received

    for tx, kind in kinds.items():
        if kind != "payment":
            own = cash_view(
                [each for each in posted if each[0] == tx],
                [each for each in adjustments if each.transaction_id == tx],
            )
            assert profit(own) == 0
