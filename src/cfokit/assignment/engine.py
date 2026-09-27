"""The matcher. Pure by construction: no I/O, no clock, no configuration.

`BKP-06`'s determinism lives here — "the same transaction against the same rule set produces
the same account, always" — and it is property-tested here, the way `cfokit.ledger.engine`
is under ADR-0008. Everything this file needs arrives as an argument, so the whole of the
determinism argument is testable with no infrastructure.

Three functions carry the design:

`rule_set_as_of` reconstructs the set in force at a moment. There is no "current rules"
query, because there is no current-rules table: ADR-0013's argument transfers unchanged —
nothing is mutated, so a point in time is a filter rather than a subsystem, and
"bitemporality is free, so nothing is built for it".

`digest` renders a rule set canonically and hashes it, which is what makes "an unchanged
rule set" a checkable claim rather than an intuition. Without it a failed replay cannot tell
a determinism defect from an operator legitimately editing a rule under `BKP-11`.

`evaluate` walks the set in order and the first match wins. Ordering is settled when the set
is built, so there is nowhere for "whichever is found first" to creep back in (`BKP-08`).
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from datetime import datetime
from decimal import Decimal

from cfokit.assignment import (
    Field,
    Match,
    Operator,
    Outcome,
    Predicate,
    Resolution,
    ResolvedBy,
    RuleSet,
    RuleVersion,
    Status,
)
from cfokit.assignment.candidate import Candidate

# The semantics these functions implement. Stored on every decision, because determinism has
# three inputs and not two: the rule set, the candidate's facts, and what the operators mean.
# A change here makes older decisions non-comparable, and a replay that ignored that would
# report a semantic change as a determinism failure — or quietly paper over one. Bumping it
# is a deliberate act and needs a record (ADR-0045).
EVALUATOR_VERSION = 1

# The amount is compared at the scale it is stored at, so a rule written as 1000 and a
# posting of 1000.0000000000 are the same number rather than nearly the same one (ADR-0005).
_SCALE = Decimal("0.0000000001")


def rule_set_as_of(versions: Iterable[RuleVersion], at: datetime) -> RuleSet:
    """The rules in force at `at`, in resolution order.

    For each rule, the version with the greatest `effective_from` not after `at`, kept only
    if it is active. A retirement is a version like any other, so a retired rule simply has
    no active latest version and falls out.

    **The order key is `(precedence, seniority, rule_id)`, and it is total.** Each level
    earns its place:

    *Precedence* is what `BKP-08` calls stated — the operator's own answer to which rule
    wins.

    *Seniority* is the rule's first appearance, not this version's. At equal precedence the
    rule approved first keeps its ground, so **adding a rule can never silently take a
    transaction away from one that already had it** — which is what makes `BKP-09`'s "an
    approved pattern is never asked about again" hold as a rule set grows. On the rule
    rather than the version, so editing a rule does not cost it its place.

    *Rule id* guarantees totality, and is never the intended discriminator, which is why a
    resolution that reaches it is recorded as such. A uuid rather than an insertion counter
    because `EXP-04` requires a receiving deployment to "resolve every posting to the same
    rule": a uuid survives an export and import unchanged, where a per-entity counter is
    reassigned on insert into a fresh database and some assignments would silently differ.
    """
    latest: dict[str, RuleVersion] = {}
    for version in versions:
        if version.effective_from > at:
            continue
        held = latest.get(version.rule_id)
        if held is None or (version.effective_from, version.version) > (
            held.effective_from,
            held.version,
        ):
            latest[version.rule_id] = version

    in_force = [rule for rule in latest.values() if rule.status is Status.ACTIVE]
    return RuleSet(rules=tuple(sorted(in_force, key=_order_key)), as_of=at)


def _order_key(rule: RuleVersion) -> tuple[int, datetime, str]:
    return (rule.precedence, rule.seniority, rule.rule_id)


def render_order_key(rule: RuleVersion) -> str:
    """The order key as an operator reads it, stored on every recorded match.

    Rendered rather than derived at read time, for the reason `issued_statement` stores its
    figures: what somebody was told has to survive a later change in how we would say it.
    """
    precedence, seniority, rule_id = _order_key(rule)
    return f"{precedence}|{seniority.isoformat()}|{rule_id}"


def digest(rule_set: RuleSet) -> str:
    """A canonical digest of a rule set, and so the definition of "unchanged".

    Over the rules and their predicates only — never over `as_of`, or two evaluations a
    second apart against identical rules would disagree about whether anything changed.

    Decimals are quantised to the stored scale so that a rule written as `1000` and one
    written as `1000.00` render identically, because they are the same rule.
    """
    lines: list[str] = []
    for rule in rule_set.rules:
        lines.append(
            f"{rule.rule_id}|{rule.version}|{rule.precedence}|{rule.account_id}|"
            f"{rule.seniority.isoformat()}"
        )
        for predicate in sorted(rule.predicates, key=lambda p: p.position):
            lines.append(f"  {predicate.field}:{predicate.operator}:{_render(predicate.value)}")
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def _render(value: str | Decimal) -> str:
    return str(value.quantize(_SCALE)) if isinstance(value, Decimal) else value


def evaluate(candidate: Candidate, rule_set: RuleSet) -> Resolution:
    """Which rule assigns this candidate, and what else matched.

    Returns `UNMATCHED` when nothing does. That is `BKP-12` and `NFR-16`: the caller asks the
    operator, and nothing is guessed or parked in a holding account on the way.
    """
    matched = [rule for rule in rule_set.rules if matches(candidate, rule)]
    if not matched:
        return Resolution(outcome=Outcome.UNMATCHED, winner=None, resolved_by=None, matches=())

    winner = matched[0]
    return Resolution(
        outcome=Outcome.ASSIGNED,
        winner=winner,
        resolved_by=_resolved_by(matched),
        matches=tuple(
            Match(rule=rule, rank=rank, order_key=render_order_key(rule))
            for rank, rule in enumerate(matched, start=1)
        ),
    )


def _resolved_by(matched: list[RuleVersion]) -> ResolvedBy:
    """Which level of the order key actually settled it.

    Compares the winner against the runner-up, because that is the only comparison that
    decided anything — the rules below them lost to the runner-up, not to the winner.
    """
    if len(matched) == 1:
        return ResolvedBy.SOLE_MATCH

    winner, runner_up = matched[0], matched[1]
    if winner.precedence != runner_up.precedence:
        return ResolvedBy.PRECEDENCE
    if winner.seniority != runner_up.seniority:
        return ResolvedBy.SENIORITY
    return ResolvedBy.RULE_ID


def matches(candidate: Candidate, rule: RuleVersion) -> bool:
    """Whether every one of a rule's predicates holds. A rule with none matches nothing.

    An empty predicate list would otherwise match every transaction, which is a catch-all
    nobody wrote deliberately and which `BKP-12` would never then get to refuse.
    """
    return bool(rule.predicates) and all(
        _holds(candidate, predicate) for predicate in rule.predicates
    )


def _holds(candidate: Candidate, predicate: Predicate) -> bool:
    actual = _fact(candidate, predicate.field)
    expected = predicate.value

    if isinstance(actual, Decimal) and isinstance(expected, Decimal):
        return _compares(actual, predicate.operator, expected)
    if isinstance(actual, str) and isinstance(expected, str):
        return _texts(actual, predicate.operator, expected)
    # A predicate whose value kind does not match its field's is one migration 0012's
    # `predicate_is_well_typed` refuses, so reaching here means a row bypassed the database.
    return False


def _fact(candidate: Candidate, field: Field) -> str | Decimal:
    """The candidate's value for a field, in the form matching compares.

    Text arrives normalised, which is the whole of why matching is here and not in SQL.
    """
    match field:
        case Field.PAYEE:
            return candidate.normalised_payee
        case Field.DESCRIPTION:
            return candidate.normalised_description
        case Field.AMOUNT:
            return candidate.amount
        case Field.DIRECTION:
            return str(candidate.direction)
        case Field.COMMODITY:
            return candidate.commodity
        case Field.SOURCE_KIND:
            return str(candidate.source_kind)
        case Field.SOURCE_ACCOUNT_ID:
            return candidate.source_account_id


def _texts(actual: str, operator: Operator, expected: str) -> bool:
    match operator:
        case Operator.EQUALS:
            return actual == expected
        case Operator.NOT_EQUALS:
            return actual != expected
        case Operator.CONTAINS:
            return expected in actual
        case Operator.STARTS_WITH:
            return actual.startswith(expected)
        case Operator.ENDS_WITH:
            return actual.endswith(expected)
        case _:
            return False


def _compares(actual: Decimal, operator: Operator, expected: Decimal) -> bool:
    match operator:
        case Operator.EQUALS:
            return actual == expected
        case Operator.NOT_EQUALS:
            return actual != expected
        case Operator.GREATER_THAN:
            return actual > expected
        case Operator.GREATER_OR_EQUAL:
            return actual >= expected
        case Operator.LESS_THAN:
            return actual < expected
        case Operator.LESS_OR_EQUAL:
            return actual <= expected
        case _:
            return False
