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

Before any rule, `search` finds what the books already hold that the line could be, and
`decide` turns that and the rules into the line's whole fate (ADR-0059). The facts compared are
exact and the windows are constants here, so both are covered by `EVALUATOR_VERSION`.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from datetime import datetime, timedelta
from decimal import Decimal

from cfokit.assignment import (
    Counterpart,
    CounterpartKind,
    Fate,
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
from cfokit.assignment.candidate import Candidate, SourceKind

# The semantics these functions implement. Stored on every decision, because determinism has
# three inputs and not two: the rule set, the candidate's facts, and what the operators mean.
# A change here makes older decisions non-comparable, and a replay that ignored that would
# report a semantic change as a determinism failure — or quietly paper over one. Bumping it
# is a deliberate act and needs a record (ADR-0045).
#
# 2: a line is searched against the books before any rule is consulted, under the windows
# below (ADR-0059). A decision taken under 1 consulted the rules alone.
EVALUATOR_VERSION = 2

# How far either side of a line a recorded transaction may be dated and still be its
# counterpart, inclusive. A check clears weeks after it was entered, and an exact amount on one
# account, unclaimed, is strong evidence across a month (ADR-0059 § 2).
TRANSACTION_WINDOW = timedelta(days=30)

# How far apart the two sides of a transfer may be dated, inclusive. Two unexplained lines on
# two accounts are weaker evidence, and a transfer between banks settles within days.
TRANSFER_WINDOW = timedelta(days=7)

_NONE_FOUND = Resolution(outcome=Outcome.UNMATCHED, winner=None, resolved_by=None, matches=())

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

    Text arrives normalized, which is the whole of why matching is here and not in SQL.
    """
    match field:
        case Field.PAYEE:
            return candidate.normalized_payee
        case Field.DESCRIPTION:
            return candidate.normalized_description
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


# --- The search before the rules (ADR-0059) -------------------------------------------------


def fits(candidate: Candidate, counterpart: Counterpart, *, windowed: bool = True) -> bool:
    """Whether `counterpart` is one this line could be, on exact facts (ADR-0059 § 2).

    Amounts compare as the numbers they are, so `1200.00` and `1200.0000000000` are equal; a
    difference of any size is not a counterpart, because a match with a difference has to put
    the difference somewhere and a holding account is what `BKP-12` rules out.

    `windowed=False` is a person's choice (§ 4): held to the same facts, but not to the dates,
    so a check that cleared after six weeks is answered by choosing the entry.
    """
    if counterpart.commodity != candidate.commodity:
        return False
    apart = abs(candidate.transaction_date - counterpart.on)
    match counterpart.kind:
        case CounterpartKind.OBLIGATION:
            # Outstanding for exactly the line's amount, and the line not dated before the
            # obligation arose. The line's account is not compared: the obligation sits on the
            # account that carries it, and the line on the one the money moved through.
            return counterpart.amount == candidate.amount and (
                not windowed or candidate.transaction_date >= counterpart.on
            )
        case CounterpartKind.TRANSACTION:
            return (
                counterpart.account_id == candidate.source_account_id
                and counterpart.amount == candidate.amount
                and (not windowed or apart <= TRANSACTION_WINDOW)
            )
        case CounterpartKind.TRANSFER:
            return (
                counterpart.account_id != candidate.source_account_id
                and counterpart.amount == -candidate.amount
                and (not windowed or apart <= TRANSFER_WINDOW)
            )


def canonical(counterparts: Iterable[Counterpart]) -> tuple[Counterpart, ...]:
    """Counterparts in the one order they are stored and digested in.

    Total — kind, then date, then id — so what the search found reads the same whatever order
    the books returned it in. It states nothing about which is better: an order among equal
    counterparts is exactly what `ambiguous` declines to invent.
    """
    return tuple(sorted(counterparts, key=lambda c: (str(c.kind), c.on, c.id)))


def search(candidate: Candidate, pool: Iterable[Counterpart]) -> tuple[Counterpart, ...]:
    """Every counterpart in `pool` this line could be, in canonical order.

    `pool` is what the books held that could be one — the reader leaves out what a line has
    already claimed — and this applies the exact facts and the windows, which is why they are
    constants of this module rather than clauses of a query (ADR-0059).
    """
    return canonical(c for c in pool if fits(candidate, c))


def decide(candidate: Candidate, found: tuple[Counterpart, ...], rule_set: RuleSet) -> Fate:
    """A line's whole fate: what the search found, and the rules only where it found nothing.

    Exactly one counterpart and the line is matched to it, unless the line was uploaded and the
    counterpart is an obligation: a settlement needs its transaction posted, and ADR-0047
    forbids posting what the session that read the document asked for, so that one is
    `proposed` for a person to confirm. Two or more and it is `ambiguous`, because choosing
    among equals is choosing whichever was found first (`BKP-08`). None, and the rules decide.
    """
    if len(found) > 1:
        return Fate(outcome=Outcome.AMBIGUOUS, counterparts=found, resolution=_NONE_FOUND)
    if len(found) == 1:
        settles_uploaded = (
            found[0].kind is CounterpartKind.OBLIGATION
            and candidate.source_kind is SourceKind.UPLOAD
        )
        return Fate(
            outcome=Outcome.PROPOSED if settles_uploaded else Outcome.MATCHED,
            counterparts=found,
            resolution=_NONE_FOUND,
        )
    resolution = evaluate(candidate, rule_set)
    return Fate(outcome=resolution.outcome, counterparts=(), resolution=resolution)


def counterpart_digest(counterparts: Iterable[Counterpart]) -> str:
    """A canonical digest of counterparts, and so the definition of "the books unchanged".

    Over every fact the search compared, in canonical order, with amounts at the stored scale
    so `1200` and `1200.00` render alike. None found digests too: a line booked by a rule while
    a counterpart sat in the books is exactly what replay has to be able to catch.
    """
    lines = [
        f"{c.kind}|{c.id}|{c.account_id}|{c.amount.quantize(_SCALE)}|{c.commodity}|"
        f"{c.on.isoformat()}"
        for c in canonical(counterparts)
    ]
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()
