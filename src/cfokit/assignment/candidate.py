"""What assignment needs to know about an incoming transaction.

**Not "what arrives".** Getting transactions in is a separate capability with three
producers in three places — a PDF parsed in the agent runtime, a skill that fetches one, and
an unattended feed — and whichever module receives them will produce one of these, the way a
reader produces a `SourceBooks`. This is assignment's *input*, and keeping it that way is
what stops this module becoming the one that stores account activity (ADR-0031, ADR-0022).

**Shaped against the poorest producer.** Two of the three are PDF statements, which carry a
date, an amount, a description and the account they belong to and nothing else. `BKP-03`
makes that path the one that must work with "no third-party account and no credentials", so
it is the path the shape is fitted to; a richer feed supplies more and this ignores it until
a requirement asks otherwise.

**Signed the way a posting is signed: positive is a debit.** A producer is responsible for
that translation and for nothing else, as `imports.source` already requires of a reader.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum


class SourceKind(StrEnum):
    """How a candidate reached us. Matchable, because it is a legitimate discriminator:
    a figure keyed by hand and one delivered by a feed are not equally trusted."""

    FEED = "feed"
    UPLOAD = "upload"
    MANUAL = "manual"


class Direction(StrEnum):
    """Derived from the amount's sign, never stored beside it. Two fields that must agree
    eventually will not."""

    DEBIT = "debit"
    CREDIT = "credit"


def normalise(text: str) -> str:
    """The form matching compares, and the only one it compares.

    NFC, case-folded, whitespace collapsed. Defined by the Unicode standard rather than by a
    database's collation, which is why matching happens here and never in SQL: `lower()` and
    `ILIKE` follow the collation, so the same rule against the same transaction could resolve
    differently on two deployments. That would break `BKP-06` outright, and `EXP-04`'s
    promise that a receiving deployment resolves every posting to the same rule.

    `casefold` rather than `lower`, because `lower` leaves ß alone and casefold maps it to
    ss — a payee differing only in that would otherwise be two payees on one deployment and
    one on another.
    """
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


@dataclass(frozen=True, slots=True)
class Candidate:
    """One incoming transaction, before anything has decided where it belongs."""

    payee: str
    amount: Decimal
    commodity: str
    source_account_id: str
    transaction_date: date
    source_kind: SourceKind
    # The source's own name for this line — a statement line, a feed's transaction id. **The
    # candidate's identity**, and the only thing its idempotency key is derived from: two
    # identical coffees on one statement are two lines, and a key built from their content
    # would replay the second as the first (ADR-0029, ADR-0046). Opaque here; what it names
    # belongs to whoever produced the candidate. Never matched on.
    source_ref: str
    description: str | None = None

    @property
    def direction(self) -> Direction:
        return Direction.DEBIT if self.amount > 0 else Direction.CREDIT

    @property
    def normalised_payee(self) -> str:
        return normalise(self.payee)

    @property
    def normalised_description(self) -> str:
        return normalise(self.description) if self.description else ""
