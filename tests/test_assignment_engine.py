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
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from cfokit.assignment import (
    Counterpart,
    CounterpartKind,
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
    counterpart_digest,
    decide,
    digest,
    evaluate,
    fits,
    render_order_key,
    rule_set_as_of,
    search,
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


# --- The search before the rules (ADR-0059) -----------------------------------------------
#
# Every expected value below is read off ADR-0059 § 2's table — the kinds, the exact facts, and
# the windows: an obligation the line is not dated before, a recorded transaction within 30
# days either side, the other side of a transfer within 7 — and dates are counted by hand on a
# calendar, never read off a run (ADR-0036 § 5).

BANK = ACCOUNT
SAVINGS = "33333333-3333-3333-3333-333333333333"
RECEIVABLE = "44444444-4444-4444-4444-444444444444"
MARCH_10 = date(2026, 3, 10)


def line(
    amount: str,
    *,
    on: date = MARCH_10,
    account: str = BANK,
    kind: SourceKind = SourceKind.FEED,
    commodity: str = "USD",
) -> Candidate:
    return Candidate(
        payee="Client A",
        amount=Decimal(amount),
        commodity=commodity,
        source_account_id=account,
        transaction_date=on,
        source_kind=kind,
        source_ref="statement:1:1",
    )


def owed(amount: str, *, arose: date, ident: str = "o-1") -> Counterpart:
    """An obligation outstanding for `amount`, carried by receivables."""
    return Counterpart(
        CounterpartKind.OBLIGATION, ident, RECEIVABLE, Decimal(amount), "USD", arose
    )


def entered(amount: str, *, on: date, ident: str = "t-1", account: str = BANK) -> Counterpart:
    """A transaction recorded ahead of the line, moving `amount` on `account`."""
    return Counterpart(CounterpartKind.TRANSACTION, ident, account, Decimal(amount), "USD", on)


def side(amount: str, *, on: date, ident: str = "d-1", account: str = SAVINGS) -> Counterpart:
    """Another line's open question, on `account`."""
    return Counterpart(CounterpartKind.TRANSFER, ident, account, Decimal(amount), "USD", on)


NO_RULES = rule_set_as_of([], LATER)


def test_a_deposit_equal_to_an_open_receivable_is_matched_to_it() -> None:
    """§ 2's own example: a deposit of 1,200.00 meets a receivable of 1,200.00, signed as
    postings are — a debit to the bank and an obligation carried as a debit."""
    invoice = owed("1200.00", arose=date(2026, 3, 1))

    fate = decide(line("1200.00"), search(line("1200.00"), [invoice]), NO_RULES)

    assert fate.outcome is Outcome.MATCHED
    assert fate.counterparts == (invoice,)


def test_a_sole_counterpart_consults_no_rule() -> None:
    """A rule would code the deposit to income and book the revenue twice; the counterpart is
    better evidence than a pattern, so no rule is consulted (§ 1)."""
    income = rule(
        index=1,
        precedence=10,
        day=0,
        predicates=(Predicate(1, Field.PAYEE, Operator.CONTAINS, "client"),),
    )
    invoice = owed("1200.00", arose=date(2026, 3, 1))

    fate = decide(
        line("1200.00"), search(line("1200.00"), [invoice]), rule_set_as_of([income], LATER)
    )

    assert fate.outcome is Outcome.MATCHED
    assert fate.resolution.winner is None
    assert fate.resolution.matches == ()


def test_two_counterparts_are_ambiguous_and_both_are_listed() -> None:
    """§ 4: no order among equals is stated, so choosing one is choosing whichever was found
    first. Of any kinds together."""
    invoice = owed("1200.00", arose=date(2026, 3, 1))
    deposit = entered("1200.00", on=date(2026, 3, 9))

    fate = decide(line("1200.00"), search(line("1200.00"), [invoice, deposit]), NO_RULES)

    assert fate.outcome is Outcome.AMBIGUOUS
    assert set(fate.counterparts) == {invoice, deposit}


def test_no_counterpart_falls_through_to_the_rules() -> None:
    income = rule(
        index=1,
        precedence=10,
        day=0,
        predicates=(Predicate(1, Field.PAYEE, Operator.CONTAINS, "client"),),
    )

    assigned = decide(line("1200.00"), (), rule_set_as_of([income], LATER))
    unmatched = decide(line("1200.00"), (), NO_RULES)

    assert assigned.outcome is Outcome.ASSIGNED
    assert assigned.resolution.winner == income
    assert unmatched.outcome is Outcome.UNMATCHED
    assert assigned.counterparts == unmatched.counterparts == ()


def test_an_uploaded_payment_of_an_obligation_is_proposed_not_matched() -> None:
    """§ 3: a settlement needs its transaction posted, and ADR-0047 forbids posting what the
    session that read the document asked for."""
    invoice = owed("1200.00", arose=date(2026, 3, 1))
    uploaded = line("1200.00", kind=SourceKind.UPLOAD)

    assert decide(uploaded, search(uploaded, [invoice]), NO_RULES).outcome is Outcome.PROPOSED


def test_an_uploaded_line_equal_to_a_recorded_entry_is_matched() -> None:
    """Nothing is written to the books, so there is nothing for a person to authorize (§ 3)."""
    uploaded = line("-45.50", kind=SourceKind.UPLOAD)
    bill = entered("-45.50", on=date(2026, 3, 8))

    assert decide(uploaded, search(uploaded, [bill]), NO_RULES).outcome is Outcome.MATCHED


@given(st.randoms())
def test_the_order_counterparts_arrive_in_changes_nothing(rng: random.Random) -> None:
    """The outcome — and the counterparts listed — are invariant to the order the books
    returned them in, so an ambiguous line lists the same candidates on every run."""
    pool = [
        owed("1200.00", arose=date(2026, 3, 1)),
        owed("1200.00", arose=date(2026, 3, 2), ident="o-2"),
        entered("1200.00", on=date(2026, 3, 9)),
        side("-1200.00", on=date(2026, 3, 11)),
        entered("99.00", on=date(2026, 3, 9), ident="t-noise"),
    ]
    shuffled = list(pool)
    rng.shuffle(shuffled)

    first = decide(line("1200.00"), search(line("1200.00"), pool), NO_RULES)
    again = decide(line("1200.00"), search(line("1200.00"), shuffled), NO_RULES)

    assert again == first
    assert counterpart_digest(again.counterparts) == counterpart_digest(first.counterparts)


# Each window's boundary, inclusive, counted on the calendar.


def test_an_obligation_counts_from_the_day_it_arose() -> None:
    """ "The line is not dated before the obligation arose": the same day is not before."""
    assert fits(line("1200.00"), owed("1200.00", arose=date(2026, 3, 10)))
    assert not fits(line("1200.00"), owed("1200.00", arose=date(2026, 3, 11)))


def test_a_recorded_transaction_counts_within_thirty_days_either_side() -> None:
    """March 10 less 30 days is February 8: ten days back reach February 28, and twenty more
    the 8th. Plus 30 is April 9: 21 days reach March 31, and nine more April 9."""
    payment = line("-500.00")

    assert fits(payment, entered("-500.00", on=date(2026, 2, 8)))
    assert not fits(payment, entered("-500.00", on=date(2026, 2, 7)))
    assert fits(payment, entered("-500.00", on=date(2026, 4, 9)))
    assert not fits(payment, entered("-500.00", on=date(2026, 4, 10)))


def test_the_other_side_of_a_transfer_counts_within_seven_days_either_side() -> None:
    """March 10 less 7 is March 3; plus 7 is March 17."""
    out = line("-500.00")

    assert fits(out, side("500.00", on=date(2026, 3, 3)))
    assert not fits(out, side("500.00", on=date(2026, 3, 2)))
    assert fits(out, side("500.00", on=date(2026, 3, 17)))
    assert not fits(out, side("500.00", on=date(2026, 3, 18)))


def test_a_person_is_held_to_the_facts_but_not_the_windows() -> None:
    """§ 4: a check that cleared after six weeks is answered by choosing the entry."""
    cleared = line("-500.00")
    check = entered("-500.00", on=date(2026, 1, 27))  # 42 days before March 10

    assert not fits(cleared, check)
    assert fits(cleared, check, windowed=False)
    assert not fits(cleared, entered("-500.01", on=date(2026, 1, 27)), windowed=False)


# The exact facts: no tolerance, and each kind compared where § 2 says.


def test_a_difference_of_a_cent_is_not_a_counterpart() -> None:
    """A match with a difference has to put the difference somewhere, and a holding account is
    what `BKP-12` rules out."""
    assert not fits(line("1200.00"), owed("1199.99", arose=date(2026, 3, 1)))
    assert not fits(line("-500.00"), entered("-500.01", on=MARCH_10))
    assert not fits(line("-500.00"), side("500.01", on=MARCH_10))


def test_the_same_amount_at_another_scale_is_the_same_amount() -> None:
    """`1200` and `1200.0000000000` are one number (ADR-0005)."""
    assert fits(line("1200"), owed("1200.0000000000", arose=date(2026, 3, 1)))


def test_another_commodity_is_not_a_counterpart() -> None:
    assert not fits(line("1200.00", commodity="EUR"), owed("1200.00", arose=date(2026, 3, 1)))


def test_a_recorded_transaction_is_on_the_line_s_own_account() -> None:
    assert not fits(line("-500.00"), entered("-500.00", on=MARCH_10, account=SAVINGS))


def test_a_transfer_s_other_side_is_on_another_account_for_the_negated_amount() -> None:
    """Out of checking, into savings: -500.00 on one meets +500.00 on the other."""
    assert fits(line("-500.00"), side("500.00", on=MARCH_10))
    assert not fits(line("-500.00"), side("-500.00", on=MARCH_10))
    assert not fits(line("-500.00"), side("500.00", on=MARCH_10, account=BANK))


def test_a_payment_is_not_matched_to_a_receivable_of_the_opposite_sign() -> None:
    """Signed as postings are: money out of the bank does not pay a customer's invoice."""
    assert not fits(line("-1200.00"), owed("1200.00", arose=date(2026, 3, 1)))


def test_nothing_found_has_a_digest_of_its_own() -> None:
    """None found is a fact replay checks too. sha256 of the empty rendering is the published
    digest of the empty string."""
    assert counterpart_digest(()) == (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )


def test_a_different_counterpart_is_a_different_digest() -> None:
    first = counterpart_digest((owed("1200.00", arose=date(2026, 3, 1)),))

    assert first != counterpart_digest((owed("1200.00", arose=date(2026, 3, 1), ident="o-2"),))
    assert first != counterpart_digest((owed("1200.01", arose=date(2026, 3, 1)),))
    assert first == counterpart_digest((owed("1200.0000000000", arose=date(2026, 3, 1)),))
