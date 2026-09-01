"""Zero-sum, per commodity (`LED-03`, ADR-0006).

**This check is for ergonomics, not for correctness.** The guarantee lives in a deferred
constraint trigger in the schema, because a check that lives on one code path is only as
reliable as every future code path — and ADR-0006 is explicit that there is no bypass and
none should be added. What this module buys is a good error with a stable `code` before the
database produces a blunt one.

Checked **per commodity**, never against a summed total across commodities: a transaction in
two currencies must balance in each independently, and netting them would let a shortfall in
one hide a surplus in the other.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from decimal import Decimal

from cfokit.ledger.engine.entry import Posting
from cfokit.ledger.errors import UnbalancedTransaction

__all__ = ["assert_balanced", "is_balanced", "totals_by_commodity"]


def totals_by_commodity(postings: Iterable[Posting]) -> dict[str, Decimal]:
    """Sum the postings in each commodity separately.

    Exact addition of `Decimal`, so the total carries no representation error and no drift —
    `LED-04` allows neither, and admits no tolerance.
    """
    totals: dict[str, Decimal] = defaultdict(lambda: Decimal(0))
    for posting in postings:
        totals[posting.commodity] += posting.amount
    return dict(totals)


def is_balanced(postings: Iterable[Posting]) -> bool:
    """True when every commodity sums to exactly zero.

    Exactly zero. `NFR-01` states it for the ledger as "exactness, not accuracy within a
    tolerance — a tolerance is a defect, not a target", which is a deliberate divergence from
    Beancount, where tolerances are inferred (ADR-0025).
    """
    return all(total == 0 for total in totals_by_commodity(postings).values())


def assert_balanced(postings: Iterable[Posting]) -> None:
    """Raise `UnbalancedTransaction` naming one commodity that does not sum to zero.

    Reports the first offending commodity in sorted order rather than an arbitrary one, so
    the same unbalanced input always produces the same message.

    The message carries an amount, so it is an error detail and not something to log at info
    level (CLAUDE.md, Observability). Callers depend on `code`, never on the wording
    (ADR-0015).
    """
    totals = totals_by_commodity(postings)
    for commodity in sorted(totals):
        if totals[commodity] != 0:
            raise UnbalancedTransaction(
                f"postings do not sum to zero in {commodity}: off by {totals[commodity]}"
            )
