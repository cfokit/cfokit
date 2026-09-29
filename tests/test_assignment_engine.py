"""The matcher's invariants (`BKP-06`, `BKP-08`, `BKP-11`), with no infrastructure.

ADR-0036 layer 1. `BKP-06`'s acceptance is about replaying a whole history, and that needs a
database — but what makes the replay *able* to succeed is proved here, over inputs nobody
thought of: the evaluation is a function of its arguments, the order is total, and a rule
added today is absent from yesterday's rule set as a matter of arithmetic.

The generators avoid `st.decimals` for the reason `test_engine_properties.py` does: money is
built from an integer and a scale, so no float is ever near it (ADR-0005).
"""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from cfokit.assignment import (
    Field,
    Operator,
    Outcome,
    Predicate,
    ResolvedBy,
    RuleVersion,
    Status,
)
from cfokit.assignment.candidate import Candidate, SourceKind, normalize
from cfokit.assignment.engine import (
    digest,
    evaluate,
    render_order_key,
    rule_set_as_of,
)

EPOCH = datetime(2026, 1, 1, tzinfo=UTC)
ACCOUNT = "11111111-1111-1111-1111-111111111111"

UNITS = st.integers(min_value=-(10**9), max_value=10**9).filter(lambda n: n != 0)
SCALES = st.integers(min_value=0, max_value=10)
WORDS = st.text(alphabet="abcdefg ", min_size=1, max_size=12).filter(lambda s: s.strip())


def money(units: int, scale: int) -> Decimal:
    return Decimal(units).scaleb(-scale)


@st.composite
def candidates(draw: st.DrawFn) -> Candidate:
    return Candidate(
        payee=draw(WORDS),
        amount=money(draw(UNITS), draw(SCALES)),
        commodity="USD",
        source_account_id=ACCOUNT,
        transaction_date=EPOCH.date(),
        source_kind=draw(st.sampled_from(list(SourceKind))),
        source_ref=draw(WORDS),
        description=draw(st.one_of(st.none(), WORDS)),
    )


@st.composite
def rules(draw: st.DrawFn, *, index: int = 0) -> RuleVersion:
    """One rule version. Precedences are drawn from a small range on purpose: ties are the
    interesting case, and a wide range would almost never produce one."""
    seniority = EPOCH + timedelta(days=draw(st.integers(min_value=0, max_value=3)))
    predicates = draw(
        st.lists(
            st.one_of(
                st.builds(
                    lambda word, op: Predicate(1, Field.PAYEE, op, normalize(word)),
                    WORDS,
                    st.sampled_from([Operator.CONTAINS, Operator.EQUALS, Operator.STARTS_WITH]),
                ),
                st.builds(
                    lambda units, scale, op: Predicate(
                        1, Field.AMOUNT, op, money(units, scale)
                    ),
                    UNITS,
                    SCALES,
                    st.sampled_from([Operator.GREATER_THAN, Operator.LESS_THAN]),
                ),
            ),
            min_size=1,
            max_size=3,
        )
    )
    return RuleVersion(
        id=f"{index:08d}-0000-0000-0000-000000000000",
        rule_id=f"{index:08d}-1111-0000-0000-000000000000",
        version=1,
        status=Status.ACTIVE,
        label=f"rule {index}",
        account_id=ACCOUNT,
        precedence=draw(st.integers(min_value=1, max_value=3)),
        effective_from=seniority,
        seniority=seniority,
        predicates=tuple(
            Predicate(position, p.field, p.operator, p.value)
            for position, p in enumerate(predicates, start=1)
        ),
    )


@st.composite
def rule_lists(draw: st.DrawFn) -> list[RuleVersion]:
    count = draw(st.integers(min_value=1, max_value=6))
    return [draw(rules(index=index)) for index in range(count)]


# --- BKP-06: the same transaction against the same rule set, always ----------------------


@given(candidates(), rule_lists())
def test_the_same_candidate_and_rules_resolve_the_same_way(
    candidate: Candidate, versions: list[RuleVersion]
) -> None:
    """The plainest reading of `BKP-06`, and the one everything else rests on."""
    first = evaluate(candidate, rule_set_as_of(versions, EPOCH + timedelta(days=9)))
    second = evaluate(candidate, rule_set_as_of(versions, EPOCH + timedelta(days=9)))

    assert first == second


@given(candidates(), rule_lists(), st.randoms())
def test_the_order_rows_arrive_in_changes_nothing(
    candidate: Candidate, versions: list[RuleVersion], rng: random.Random
) -> None:
    """**The failure this is really about.** A rule set read back in a different row order is
    the ordinary consequence of a query without an `ORDER BY`, and it must not be able to
    change an assignment — otherwise `BKP-06` holds only by accident of the planner."""
    shuffled = list(versions)
    rng.shuffle(shuffled)
    at = EPOCH + timedelta(days=9)

    assert evaluate(candidate, rule_set_as_of(versions, at)) == evaluate(
        candidate, rule_set_as_of(shuffled, at)
    )
    assert digest(rule_set_as_of(versions, at)) == digest(rule_set_as_of(shuffled, at))


# --- BKP-08: a stated order, and it is total ---------------------------------------------


@given(rule_lists())
def test_no_two_rules_ever_compare_equal(versions: list[RuleVersion]) -> None:
    """Totality is what lets `BKP-08` say "rather than by whichever is found first". If two
    rules could tie, the answer would fall back to row order, which is exactly the thing the
    requirement forbids."""
    keys = [render_order_key(rule) for rule in rule_set_as_of(versions, EPOCH).rules]

    assert len(keys) == len(set(keys))


@given(candidates(), rule_lists())
def test_the_winner_is_first_and_the_reason_is_the_level_that_decided(
    candidate: Candidate, versions: list[RuleVersion]
) -> None:
    """`BKP-08`'s "which rule won and why", checked against the order rather than against
    what the function happened to return."""
    resolution = evaluate(candidate, rule_set_as_of(versions, EPOCH + timedelta(days=9)))
    if resolution.outcome is Outcome.UNMATCHED:
        assert resolution.matches == ()
        return

    assert resolution.matches[0].rule == resolution.winner
    assert [m.rank for m in resolution.matches] == list(range(1, len(resolution.matches) + 1))

    if len(resolution.matches) == 1:
        assert resolution.resolved_by is ResolvedBy.SOLE_MATCH
        return

    winner, runner_up = resolution.matches[0].rule, resolution.matches[1].rule
    expected = (
        ResolvedBy.PRECEDENCE
        if winner.precedence != runner_up.precedence
        else ResolvedBy.SENIORITY
        if winner.seniority != runner_up.seniority
        else ResolvedBy.RULE_ID
    )
    assert resolution.resolved_by is expected


# --- BKP-11: a rule change reaches forwards only -----------------------------------------


@given(rule_lists())
def test_a_later_version_is_absent_from_an_earlier_rule_set(
    versions: list[RuleVersion],
) -> None:
    """**`BKP-11` as arithmetic rather than as a promise.** "Changing a rule affects future
    assignments only" is true here because a version with a later `effective_from` is not in
    the earlier set — not because any code path declines to apply it."""
    at = EPOCH + timedelta(days=9)
    before = digest(rule_set_as_of(versions, at))

    edited = versions[0]
    later = datetime(2027, 6, 1, tzinfo=UTC)
    successor = RuleVersion(
        id="99999999-0000-0000-0000-000000000000",
        rule_id=edited.rule_id,
        version=edited.version + 1,
        status=Status.ACTIVE,
        label="edited",
        account_id=ACCOUNT,
        precedence=edited.precedence + 100,
        effective_from=later,
        seniority=edited.seniority,
        predicates=edited.predicates,
    )

    assert digest(rule_set_as_of([*versions, successor], at)) == before
    assert digest(rule_set_as_of([*versions, successor], later)) != before


@given(rule_lists())
def test_retiring_a_rule_removes_it_and_nothing_else(versions: list[RuleVersion]) -> None:
    """Retirement is a version like any other, which is why it needs no second mechanism."""
    at = datetime(2027, 6, 1, tzinfo=UTC)
    retired = versions[0]
    tombstone = RuleVersion(
        id="88888888-0000-0000-0000-000000000000",
        rule_id=retired.rule_id,
        version=retired.version + 1,
        status=Status.RETIRED,
        label=retired.label,
        account_id=None,
        precedence=retired.precedence,
        effective_from=datetime(2026, 6, 1, tzinfo=UTC),
        seniority=retired.seniority,
        predicates=(),
    )

    after = rule_set_as_of([*versions, tombstone], at)
    others = {rule.rule_id for rule in rule_set_as_of(versions, at).rules} - {retired.rule_id}

    assert retired.rule_id not in {rule.rule_id for rule in after.rules}
    assert {rule.rule_id for rule in after.rules} == others


# --- Worked cases, computed by hand from the stated order --------------------------------
#
# The property tests above prove the engine is self-consistent, which is not the same as
# proving it is right: a matcher that always returned the last rule would satisfy every one
# of them. ADR-0036 § 5 — "recording what the code returned and asserting that is never a
# specification" — so each expected value below is worked out from `BKP-08`'s stated order
# and from `BKP-07`'s own example, and none of it was read off a run.


def rule(
    *,
    index: int,
    precedence: int,
    day: int,
    predicates: tuple[Predicate, ...],
    account: str = ACCOUNT,
) -> RuleVersion:
    when = EPOCH + timedelta(days=day)
    return RuleVersion(
        id=f"{index:08d}-0000-0000-0000-000000000000",
        rule_id=f"{index:08d}-1111-0000-0000-000000000000",
        version=1,
        status=Status.ACTIVE,
        label=f"rule {index}",
        account_id=account,
        precedence=precedence,
        effective_from=when,
        seniority=when,
        predicates=predicates,
    )


ACME = (Predicate(1, Field.PAYEE, Operator.CONTAINS, "acme"),)
LATER = EPOCH + timedelta(days=30)


def acme(amount: str) -> Candidate:
    return Candidate(
        payee="ACME Insurance Co",
        amount=Decimal(amount),
        commodity="USD",
        source_account_id=ACCOUNT,
        transaction_date=EPOCH.date(),
        source_kind=SourceKind.FEED,
        source_ref="feed-1",
    )


def test_a_lower_precedence_wins_and_says_so() -> None:
    """The operator stated the order, so the operator's order is the reason."""
    first = rule(index=1, precedence=10, day=0, predicates=ACME)
    second = rule(index=2, precedence=20, day=0, predicates=ACME)

    resolution = evaluate(acme("100"), rule_set_as_of([second, first], LATER))

    assert resolution.winner == first
    assert resolution.resolved_by is ResolvedBy.PRECEDENCE
    assert [m.rank for m in resolution.matches] == [1, 2]


def test_at_equal_precedence_the_older_rule_keeps_its_ground() -> None:
    """Which is what makes `BKP-09`'s "an approved pattern is never asked about again" hold
    as the rule set grows: a rule added today cannot take a transaction from one that
    already had it."""
    established = rule(index=1, precedence=10, day=0, predicates=ACME)
    newcomer = rule(index=2, precedence=10, day=5, predicates=ACME)

    resolution = evaluate(acme("100"), rule_set_as_of([newcomer, established], LATER))

    assert resolution.winner == established
    assert resolution.resolved_by is ResolvedBy.SENIORITY


def test_a_tie_resolves_and_is_flagged_as_one() -> None:
    """Determinism is preserved — some rule wins, every time — and `resolved_by` says the
    rule set did not state which. That is the flag an operator acts on."""
    one = rule(index=1, precedence=10, day=0, predicates=ACME)
    two = rule(index=2, precedence=10, day=0, predicates=ACME)

    resolution = evaluate(acme("100"), rule_set_as_of([two, one], LATER))

    assert resolution.winner == one  # "00000001…" sorts before "00000002…"
    assert resolution.resolved_by is ResolvedBy.RULE_ID


def test_one_payee_reaching_two_accounts_is_the_point_of_bkp_07() -> None:
    """`BKP-07` in its own words: "One payee legitimately maps to several accounts depending
    on other properties of the transaction." Here the property is the amount — a large
    premium is prepaid, a small one is expensed — and matching on the payee alone could not
    express it."""
    prepaid = "22222222-2222-2222-2222-222222222222"
    large = rule(
        index=1,
        precedence=10,
        day=0,
        account=prepaid,
        predicates=(*ACME, Predicate(2, Field.AMOUNT, Operator.GREATER_THAN, Decimal("1000"))),
    )
    ordinary = rule(index=2, precedence=20, day=0, predicates=ACME)
    rule_set = rule_set_as_of([large, ordinary], LATER)

    assert evaluate(acme("2400"), rule_set).winner == large
    assert evaluate(acme("240"), rule_set).winner == ordinary


def test_nothing_matching_is_an_answer_rather_than_a_guess() -> None:
    """`BKP-12` and `NFR-16`: never assigned speculatively, never parked."""
    resolution = evaluate(
        acme("100"),
        rule_set_as_of(
            [
                rule(
                    index=1,
                    precedence=10,
                    day=0,
                    predicates=(Predicate(1, Field.PAYEE, Operator.CONTAINS, "different"),),
                )
            ],
            LATER,
        ),
    )

    assert resolution.outcome is Outcome.UNMATCHED
    assert resolution.winner is None
    assert resolution.matches == ()


def test_a_rule_with_no_conditions_matches_nothing() -> None:
    """An empty predicate list read as "match everything" is a catch-all nobody wrote, and
    it would swallow every candidate `BKP-12` exists to ask about."""
    catch_all = rule(index=1, precedence=10, day=0, predicates=())

    assert (
        evaluate(acme("100"), rule_set_as_of([catch_all], LATER)).outcome is Outcome.UNMATCHED
    )
