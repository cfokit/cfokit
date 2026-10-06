"""Which account carries an obligation (`LED-17`, ADR-0059 § 3).

An obligation records the account that carries it, signed as its posting there: an invoice's
receivable is a debit, so its obligation is positive; a bill's payable is a credit, so negative.
The account is read from the raising entry's own postings rather than stated beside them, so the
two cannot disagree — and a payment matched to the obligation later is settled against it.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from cfokit.ledger.engine.entry import Entry

__all__ = ["carrying_account"]


def carrying_account(entry: Entry, amount: Decimal, commodity: str) -> str | None:
    """The one account whose postings in `commodity` sum to exactly `amount`, or `None`.

    `None` when no account does, and when more than one does: two accounts carrying the same
    figure leave which one is owed unstated, and choosing one would be a guess (`NFR-16`).
    """
    sums: defaultdict[str, Decimal] = defaultdict(Decimal)
    for posting in entry.postings:
        if posting.commodity == commodity:
            sums[posting.account_id] += posting.amount
    carrying = [account for account, total in sums.items() if total == amount]
    return carrying[0] if len(carrying) == 1 else None
