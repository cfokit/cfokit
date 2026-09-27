"""Assignment: deciding which account an incoming transaction belongs to (`BKP-06` to `BKP-12`).

**A module under ADR-0022, and a sibling of the ledger.** The ledger owns the double-entry
primitive and knows nothing about payees; deciding that a card payment is office supplies is
exactly the domain knowledge that boundary keeps out.

**In-process, not a separate component.** ADR-0022 § 3's first criterion settles it: a
decision and the draft it coded must reach one `COMMIT`. A decision naming a transaction
that rolled back, or a draft whose coding no record explains, is the gap `RPT-08` exists to
close.

**Named for the capability, not the mechanism.** Not `rules`: four unrelated capabilities
have an equal claim to that word — compliance rules (`NFR-12`), alerting thresholds
(`PLT-07`), autonomy configuration (`SOC1-04`) — and it already means "invariant" throughout
this codebase. `assignment` is `BKP-06`'s own word (ADR-0031).

**What it does not do.** It stores no incoming transactions. The caller supplies candidates
and assignment returns decisions; what a decision produces is a draft, which the ledger
already stores and already keeps out of the books (`LED-07`). Letting this module hold a
queue of unassigned activity is how `connectors` would have gone wrong.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

__all__ = [
    "Field",
    "Match",
    "Operator",
    "Outcome",
    "Predicate",
    "Resolution",
    "ResolvedBy",
    "RuleSet",
    "RuleVersion",
    "Status",
]


class Field(StrEnum):
    """What a predicate may look at. A closed set, and the second half of the enforcement —
    migration 0012's `predicate_is_well_typed` is the first, so the two must agree and a test
    asserts it (ADR-0036 § 5: an expected value comes from a second enforcement point).

    Adding one is a migration and a code change together. That is the deliberate cost of a
    closed set, paid to keep clear of ADR-0012's custom-query-language gate (ADR-0045).
    """

    PAYEE = "payee"
    DESCRIPTION = "description"
    AMOUNT = "amount"
    DIRECTION = "direction"
    COMMODITY = "commodity"
    SOURCE_KIND = "source_kind"
    SOURCE_ACCOUNT_ID = "source_account_id"


class Operator(StrEnum):
    """How a predicate compares. Closed, for the same reason `Field` is."""

    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    CONTAINS = "contains"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    GREATER_THAN = "greater_than"
    GREATER_OR_EQUAL = "greater_or_equal"
    LESS_THAN = "less_than"
    LESS_OR_EQUAL = "less_or_equal"


class Status(StrEnum):
    """A version is in the rule set or it is a record that the rule left it. Retiring and
    editing are the same act from two angles, so they are one mechanism (`BKP-11`)."""

    ACTIVE = "active"
    RETIRED = "retired"


class Outcome(StrEnum):
    """Two, and nothing between. There is no `ambiguous`: `BKP-08` makes overlap a resolved
    case rather than a question."""

    ASSIGNED = "assigned"
    UNMATCHED = "unmatched"


class ResolvedBy(StrEnum):
    """Which level of the order key settled it (`BKP-08`).

    `RULE_ID` is the one that matters to an operator: it means the tiebreak decided, so the
    rule set does not state what they think it states. Recording it makes finding every such
    assignment a `WHERE` clause rather than an audit.
    """

    SOLE_MATCH = "sole_match"
    PRECEDENCE = "precedence"
    SENIORITY = "seniority"
    RULE_ID = "rule_id"


@dataclass(frozen=True, slots=True)
class Predicate:
    """One condition. Conditions are ANDed; there is no OR and no nesting.

    Where an operator needs a disjunction they write two rules — which is also the form
    `BKP-08` can order and `RPT-08` can attribute, so the constraint buys something rather
    than only costing.
    """

    position: int
    field: Field
    operator: Operator
    value: str | Decimal


@dataclass(frozen=True, slots=True)
class RuleVersion:
    """A rule as it stood from one moment onward. Immutable, as its row is.

    `seniority` is the rule's first version's `effective_from`, carried here so the order key
    is computable from one object. It is a property of the rule rather than the version,
    which is what stops an edit costing a rule its place in the order.
    """

    id: str
    rule_id: str
    version: int
    status: Status
    label: str
    account_id: str | None
    precedence: int
    effective_from: datetime
    seniority: datetime
    predicates: tuple[Predicate, ...]


@dataclass(frozen=True, slots=True)
class Match:
    """A rule that matched, and where it came in the order."""

    rule: RuleVersion
    rank: int
    order_key: str


@dataclass(frozen=True, slots=True)
class Resolution:
    """What one evaluation decided, and the contest behind it.

    `matches` is every rule that matched, in order, winner first — `BKP-08`'s "the operator
    can see which rule won and why". Empty for an unmatched candidate, which is `BKP-12`:
    nothing is guessed and nothing is parked.
    """

    outcome: Outcome
    winner: RuleVersion | None
    resolved_by: ResolvedBy | None
    matches: tuple[Match, ...]


@dataclass(frozen=True, slots=True)
class RuleSet:
    """The rules in force at a moment, already in resolution order.

    Ordering is a property of the set rather than of an evaluation, so it is established once
    and tested once. `evaluate` then walks in order and the first match wins, which is why
    there is no place for "whichever is found first" to creep back in (`BKP-08`).
    """

    rules: tuple[RuleVersion, ...]
    as_of: datetime
