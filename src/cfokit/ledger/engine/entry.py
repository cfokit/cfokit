"""The shapes booking logic operates on.

These are the engine's own value types, not row mappers. They carry what booking semantics
need and nothing else, so a change to the schema does not propagate into the pure layer and
a test can construct one without a database (ADR-0008).

Identifiers are opaque strings. The engine never interprets one, which is what lets it stay
ignorant of what an account or an entity actually is (ADR-0022).

Money is `decimal.Decimal`, constructed from `str` (ADR-0005).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal

__all__ = ["Entry", "Posting"]


@dataclass(frozen=True, slots=True)
class Posting:
    """One side of a transaction: an amount, in a commodity, against an account.

    The amount is **signed**, and the sign is the whole of the debit/credit distinction:
    positive is a debit, negative is a credit. Storing one signed number rather than a pair
    of columns and a marker is what makes "every transaction balances" the statement that
    the postings sum to zero, checkable without knowing what any account is for.

    Amounts are never rounded here. A posting holds what it was given, to the full
    `NUMERIC(28,10)` the schema stores (ADR-0025).
    """

    account_id: str
    amount: Decimal
    commodity: str

    def negated(self) -> Posting:
        """The same posting on the other side. The basis of a reversal (ADR-0007)."""
        return replace(self, amount=-self.amount)


@dataclass(frozen=True, slots=True)
class Entry:
    """A candidate transaction: its postings, its date, and what it reverses if anything.

    Deliberately carries no status. Draft-versus-posted is a fact about a stored row and a
    one-way transition the database enforces (ADR-0007); an `Entry` is what is proposed, and
    whether it may be posted is answered by `postability.check_postable` rather than by a
    field that could disagree with the row.

    `recorded_at` is likewise absent, because it is server-assigned and no write path accepts
    it (ADR-0013). Only `transaction_date` — when the event economically occurred — is the
    caller's to state.
    """

    transaction_date: date
    postings: tuple[Posting, ...]
    description: str | None = None
    reverses_id: str | None = None

    @property
    def commodities(self) -> frozenset[str]:
        """Every commodity this entry touches. Balance is checked in each (ADR-0006)."""
        return frozenset(posting.commodity for posting in self.postings)
