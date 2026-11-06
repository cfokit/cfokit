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
