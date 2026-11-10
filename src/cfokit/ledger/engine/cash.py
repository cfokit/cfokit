"""The cash view, derived from the stored link between an obligation and its settlements.

`AR-16`: an entity on a cash basis *"recognizes the revenue on settlement rather than on
issue"*. The ledger is accrual whatever the entity declared (ADR-0037), so the cash view is a
presentation of the same postings, and this is where it is derived (ADR-0080 § 4).

> A cash-basis report is the ledger's postings, except that a transaction raising an obligation
> is deferred to its settlements. Each settlement recognizes, on its own date, its share of the
> raising transaction's other postings, in place of its own posting on the carrying account.

**What comes out is adjustments, not a second set of books.** Each says how one transaction's
postings on one account read differently on a cash basis. Added to the posted figures, they
are the cash view; every transaction they touch still balances, because each set of
adjustments for a transaction sums to zero.

* **A raising transaction** is taken out whole, in the obligation's commodity: an invoice's
  receivable and its income lines wait for settlement (§ 1).
* **A settlement** puts back, on the settling transaction's date, the share of the raising
  transaction's other lines that the amount settled stands for, and takes out the settling
  transaction's own posting on the carrying account to the amount settled (§ 1).
* **Money on account** is recognized when it moves, on a line of the view's own rather than an
  account in the chart (§ 2): money received on `UNAPPLIED_RECEIVED`, money paid on
  `UNAPPLIED_PAID`. Its settlements are the same rule as any other, applying it to an invoice or
  refunding it, and what each takes off that line is what it recognizes elsewhere.
* **A reversal** of either reads as the negation of what it reverses, on its own date (§ 2): a
  voided invoice is deferred with its original, and a payment that bounces takes back what it
  recognized.

**The shares are an allocation** (ADR-0025): largest remainder, ties broken by line order. They
are cumulative, so an obligation fully settled recognizes exactly the lines that raised it, in
one payment or seven. The increment is the commodity's display scale, or finer wherever the
amounts are, so a share is never rounded and full settlement is always exact.

Pure: no I/O and no clock. What no link reaches is not here, because it reads as posted (§ 3).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from cfokit.ledger.engine.allocation import allocate
from cfokit.ledger.engine.commodity import display_scale

__all__ = [
    "UNAPPLIED_PAID",
    "UNAPPLIED_RECEIVED",
    "Adjustment",
    "Line",
    "Raised",
    "Reversal",
    "Settled",
    "cash_adjustments",
]

# The view's own lines for money on account, which nothing is posted to (ADR-0080 § 2). Not
# account ids, so a chart can never hold one: money received that no invoice takes is income
# when it arrives, and money paid that no bill takes is expense when it leaves.
UNAPPLIED_RECEIVED = "unapplied-payments"
UNAPPLIED_PAID = "unapplied-bill-payments"


@dataclass(frozen=True, slots=True)
class Line:
    """One posting of a transaction that raised an obligation, in the obligation's commodity."""

    account_id: str
    amount: Decimal


@dataclass(frozen=True, slots=True)
class Raised:
    """An obligation, and the postings of the transaction that raised it, in line order.

    `amount` is signed as its posting on `account_id`, the account that carries it: a
    receivable positive, a payable negative.

    `on_account` marks money already moved that no obligation took (ADR-0080 § 2): a customer's
    credit, negative on a receivable, or a deposit with a vendor, positive on a payable. Its
    raising transaction is the payment, and only the part of it on the carrying account to the
    obligation's amount reads differently, so its `lines` are not read.
    """

    obligation_id: str
    transaction_id: str
    transaction_date: date
    account_id: str
    amount: Decimal
    commodity: str
    lines: tuple[Line, ...]
    on_account: bool = False


@dataclass(frozen=True, slots=True)
class Settled:
    """A settlement, signed as the obligation it settles."""

    obligation_id: str
    transaction_id: str
    transaction_date: date
    amount: Decimal


@dataclass(frozen=True, slots=True)
class Reversal:
    """A transaction that reverses another (`LED-08`)."""

    transaction_id: str
    transaction_date: date
    reverses_id: str


@dataclass(frozen=True, slots=True)
class Adjustment:
    """How one transaction's postings on one account read on a cash basis.

    Dated with the transaction it belongs to, so a report includes it exactly when it includes
    that transaction.
    """

    transaction_id: str
    transaction_date: date
    account_id: str
    commodity: str
    amount: Decimal


def cash_adjustments(
    raised: Iterable[Raised],
    settled: Iterable[Settled],
    reversals: Iterable[Reversal],
) -> list[Adjustment]:
    """What turns the posted figures into the cash view (ADR-0080).

    `settled` is taken in the order given, which is the order the cumulative shares accrue
    in, so the caller passes it in the order the settlements happened. `reversals` likewise,
    so a reversal of a reversal finds what it negates. A share is allocated in the
    commodity's display scale, or finer where the amounts are.

    A settlement of an obligation not in `raised` is ignored: nothing says what it recognizes.
    """
    by_obligation: defaultdict[str, list[Settled]] = defaultdict(list)
    for settlement in settled:
        by_obligation[settlement.obligation_id].append(settlement)

    # Each transaction's own adjustments, by (account, commodity), and its date. A reversal
    # negates exactly these, so they are kept per transaction rather than flattened.
    own: dict[str, defaultdict[tuple[str, str], Decimal]] = {}
    dated: dict[str, date] = {}

    def add(
        transaction_id: str, when: date, account_id: str, commodity: str, amount: Decimal
    ) -> None:
        dated[transaction_id] = when
        own.setdefault(transaction_id, defaultdict(Decimal))[(account_id, commodity)] += amount

    for obligation in raised:
        if obligation.on_account:
            # Recognized on receipt, in place of the carrying posting it stands for. What it
            # recognizes is one line, which its settlements take back as they apply it.
            others = [Line(account_id=_unapplied(obligation.amount), amount=-obligation.amount)]
            for line in (Line(obligation.account_id, obligation.amount), *others):
                add(
                    obligation.transaction_id,
                    obligation.transaction_date,
                    line.account_id,
                    obligation.commodity,
                    -line.amount,
                )
        else:
            # Deferred whole: the carrying posting is never presented, and the other lines
            # wait.
            for line in obligation.lines:
                add(
                    obligation.transaction_id,
                    obligation.transaction_date,
                    line.account_id,
                    obligation.commodity,
                    -line.amount,
                )
            others = [
                line for line in obligation.lines if line.account_id != obligation.account_id
            ]
        # The other lines sum to minus the obligation in a balanced transaction. Lines that sum
        # to nothing give no proportion to recognize by, and nothing is guessed (`NFR-16`).
        if sum((line.amount for line in others), start=Decimal(0)) == 0:
            continue
        cumulative = Decimal(0)
        before = [Decimal(0)] * len(others)
        for settlement in by_obligation.get(obligation.obligation_id, ()):
            cumulative += settlement.amount
            through = _shares(cumulative, others, display_scale(obligation.commodity))
            # The settling transaction's posting on the carrying account, to the amount
            # settled, is not presented. It is signed against the obligation, so taking it out
            # adds the settlement back.
            add(
                settlement.transaction_id,
                settlement.transaction_date,
                obligation.account_id,
                obligation.commodity,
                settlement.amount,
            )
            for line, now, earlier in zip(others, through, before, strict=True):
                add(
                    settlement.transaction_id,
                    settlement.transaction_date,
                    line.account_id,
                    obligation.commodity,
                    now - earlier,
                )
            before = through

    for reversal in reversals:
        negated = own.get(reversal.reverses_id)
        if negated is None:
            continue
        for (account_id, commodity), amount in list(negated.items()):
            add(
                reversal.transaction_id,
                reversal.transaction_date,
                account_id,
                commodity,
                -amount,
            )

    return [
        Adjustment(
            transaction_id=transaction_id,
            transaction_date=dated[transaction_id],
            account_id=account_id,
            commodity=commodity,
            amount=amount,
        )
        for transaction_id, amounts in own.items()
        for (account_id, commodity), amount in amounts.items()
        if amount != 0
    ]


def _unapplied(amount: Decimal) -> str:
    """The view's line for money on account. A credit on the carrying account is money the
    counterparty paid in, and a debit is money paid out to them."""
    return UNAPPLIED_RECEIVED if amount < 0 else UNAPPLIED_PAID


def _shares(settled: Decimal, others: Sequence[Line], scale: int) -> list[Decimal]:
    """Each line's share of what `settled` stands for out of what is owed, summing to
    `-settled`.

    The other lines sum to `-owed`, because the raising transaction balances, so each line's
    exact share is `line * settled / owed`. Allocating `-settled` by the lines themselves as
    weights is that proportion, made exact by largest remainder (ADR-0025).
    """
    places = max(scale, _places(settled), *(_places(line.amount) for line in others))
    factor = Decimal(1).scaleb(places)
    weights = [int(line.amount * factor) for line in others]
    return allocate(-settled, weights, places)


def _places(amount: Decimal) -> int:
    """How many decimal places `amount` needs, ignoring trailing zeros a column carries."""
    exponent = amount.normalize().as_tuple().exponent
    return max(0, -exponent) if isinstance(exponent, int) else 0
