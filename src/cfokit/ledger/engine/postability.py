"""What makes a draft fit to post (`LED-07`).

> "A transaction is freely editable while it is a draft, and becomes permanent when it is
> posted. Posting is the point of no return."

Because posting is irreversible, everything checkable is checked before it rather than after.
A draft may be unbalanced, in a single commodity, or half-written while it is being worked on
(ADR-0006); none of that is an error until someone tries to post it.

The entity's declared accounting basis is deliberately **not** an input. The ledger is
intrinsically accrual and no posting path branches on the declared basis — the cash view is
derived at presentation from the stored obligation-to-settlement link (ADR-0037). A basis
parameter here would be the exact failure that record exists to prevent.
"""

from __future__ import annotations

from cfokit.ledger.engine.balance import assert_balanced
from cfokit.ledger.engine.entry import Entry
from cfokit.ledger.errors import CommodityNotPermitted, LedgerError, TransactionIncomplete

__all__ = ["check_postable", "is_postable"]

# Double entry: a transaction moves value between at least two places. One posting cannot do
# that, and an empty one sums to zero in every commodity, so it would pass a balance check
# while recording nothing.
MINIMUM_POSTINGS = 2


def check_postable(entry: Entry, *, functional_currency: str) -> None:
    """Raise the first reason `entry` may not be posted, or return.

    Checks run in order of how fundamental the problem is, so the error a caller sees is the
    one worth fixing first: a transaction that records nothing, then a commodity the entity
    cannot hold, then an imbalance.

    Each raises a `LedgerError` carrying a stable `code` (ADR-0015).
    """
    if len(entry.postings) < MINIMUM_POSTINGS:
        raise TransactionIncomplete(
            f"a transaction needs at least {MINIMUM_POSTINGS} postings, "
            f"got {len(entry.postings)}"
        )

    # LED-15: every amount carries its commodity, and anything other than the entity's
    # functional currency is refused rather than converted, for as long as LED-16 has not
    # activated for that entity. Activating LED-16 relaxes this refusal; it does not
    # contradict it, so this is the one place that changes when it does.
    for commodity in sorted(entry.commodities):
        if commodity != functional_currency:
            raise CommodityNotPermitted(
                f"{commodity} is not the entity's functional currency "
                f"({functional_currency}); conversion is not enabled"
            )

    assert_balanced(entry.postings)


def is_postable(entry: Entry, *, functional_currency: str) -> bool:
    """Whether `entry` may be posted. Use `check_postable` when the reason matters.

    Catches `LedgerError` rather than an enumerated tuple deliberately: every refusal
    `check_postable` can raise is one, and listing them here would mean a reason added later
    silently propagates out of a predicate whose whole contract is that it returns a bool.
    """
    try:
        check_postable(entry, functional_currency=functional_currency)
    except LedgerError:
        return False
    return True
