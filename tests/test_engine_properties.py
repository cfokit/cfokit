"""The arithmetic invariants ADR-0036 § layer 1 names, as properties.

> "Property tests carry the arithmetic invariants: postings sum to zero for any transaction,
> allocation parts sum to the whole for any total and any line count, a reversal restores the
> prior balance exactly, and the trial balance ties after any sequence of operations."

All four are here, one section each.

**No `float` reaches a `Decimal`, including in the generators.** Amounts are drawn as
integers and shifted with `scaleb`, which moves the exponent and cannot introduce a
representation error. `st.decimals` is deliberately not used: ADR-0005 puts fixtures in scope
and requires construction from `str` or `int`, never from a binary float.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from cfokit.ledger.engine import (
    Entry,
    Posting,
    allocate,
    build_reversal,
    is_balanced,
    totals_by_commodity,
)

# NUMERIC(28,10) is the storage type (ADR-0005), so ten is the finest scale the ledger can
# hold. Magnitudes stay well inside the eighteen integer digits.
SCALES = st.integers(min_value=0, max_value=10)
UNITS = st.integers(min_value=-(10**12), max_value=10**12)
COMMODITIES = st.sampled_from(["USD", "EUR", "JPY", "GBP"])


def amount(units: int, scale: int) -> Decimal:
    """Build a Decimal from an integer count of quanta. Never from a float (ADR-0005)."""
    return Decimal(units).scaleb(-scale)


WEIGHTS = st.lists(st.integers(min_value=0, max_value=10_000), min_size=1, max_size=24).filter(
    lambda weights: sum(weights) > 0
)


# --- Allocation: the parts sum to the whole, for any total and any line count -------------


@given(units=UNITS, scale=SCALES, weights=WEIGHTS)
def test_allocation_parts_sum_to_the_whole(units: int, scale: int, weights: list[int]) -> None:
    """`LED-05`, and the invariant ADR-0025 requires allocation to be property-tested for."""
    total = amount(units, scale)

    parts = allocate(total, weights, scale)

    assert sum(parts, start=Decimal(0)) == total
    assert len(parts) == len(weights)


@given(units=UNITS, scale=SCALES, weights=WEIGHTS)
def test_allocation_is_deterministic(units: int, scale: int, weights: list[int]) -> None:
    """`LED-05`: "the same division always produces the same parts"."""
    total = amount(units, scale)

    assert allocate(total, weights, scale) == allocate(total, weights, scale)


@given(units=UNITS, scale=SCALES, weights=WEIGHTS)
def test_every_part_is_expressible_at_the_requested_scale(
    units: int, scale: int, weights: list[int]
) -> None:
    """A part finer than the increment would be unstorable and unpresentable (`LED-06`)."""
    quantum = Decimal(1).scaleb(-scale)

    for part in allocate(amount(units, scale), weights, scale):
        assert (part / quantum) == (part / quantum).to_integral_value()


@given(units=UNITS, scale=SCALES, weights=WEIGHTS)
def test_no_part_is_more_than_one_quantum_from_its_exact_share(
    units: int, scale: int, weights: list[int]
) -> None:
    """Largest remainder distributes the shortfall, so nobody absorbs all of it.

    This is what distinguishes a real allocation from giving the remainder to the last line.
    """
    total = amount(units, scale)
    total_weight = sum(weights)
    quantum = Decimal(1).scaleb(-scale)

    for part, weight in zip(allocate(total, weights, scale), weights, strict=True):
        exact_share = total * Decimal(weight) / Decimal(total_weight)
        assert abs(part - exact_share) < quantum


@given(units=UNITS, scale=SCALES, weights=WEIGHTS)
def test_allocating_a_negation_mirrors_the_original(
    units: int, scale: int, weights: list[int]
) -> None:
    """A reversal allocates the negation, so the two must cancel exactly (`LED-08`)."""
    total = amount(units, scale)

    forward = allocate(total, weights, scale)
    backward = allocate(-total, weights, scale)

    assert sum(forward, start=Decimal(0)) + sum(backward, start=Decimal(0)) == 0


# --- Postings sum to zero for any transaction --------------------------------------------


@st.composite
def balanced_postings(draw: st.DrawFn) -> list[Posting]:
    """Any number of postings across any commodities, balanced in each independently.

    Built by construction rather than by search: a balancing posting per commodity is what
    the service layer will do, and generating candidates until one happens to balance would
    test the generator rather than the engine.
    """
    scale = draw(SCALES)
    commodities = draw(st.lists(COMMODITIES, min_size=1, max_size=3, unique=True))

    postings: list[Posting] = []
    for commodity in commodities:
        counts = draw(st.lists(UNITS, min_size=1, max_size=6))
        for index, units in enumerate(counts):
            postings.append(Posting(f"{commodity}-{index}", amount(units, scale), commodity))
        postings.append(
            Posting(f"{commodity}-balancing", amount(-sum(counts), scale), commodity)
        )
    return postings


@given(postings=balanced_postings())
def test_postings_sum_to_zero_for_any_transaction(postings: list[Posting]) -> None:
    """`LED-03`, checked per commodity and never netted across them (ADR-0006)."""
    assert is_balanced(postings)
    assert all(total == 0 for total in totals_by_commodity(postings).values())


@given(postings=balanced_postings(), units=UNITS, scale=SCALES)
def test_perturbing_one_posting_unbalances_it(
    postings: list[Posting], units: int, scale: int
) -> None:
    """The check has to be able to fail, or it asserts nothing.

    `NFR-01` admits no tolerance, so any non-zero perturbation is an imbalance however small.
    """
    drift = amount(units, scale)
    if drift == 0:
        return

    first = postings[0]
    perturbed = [
        Posting(first.account_id, first.amount + drift, first.commodity),
        *postings[1:],
    ]

    assert not is_balanced(perturbed)


# --- A reversal restores the prior balance exactly ---------------------------------------


@given(postings=balanced_postings(), original_closed=st.booleans())
def test_a_reversal_restores_the_prior_balance_exactly(
    postings: list[Posting], original_closed: bool
) -> None:
    """ADR-0036 names this one. Exactly, in every commodity, with no residue."""
    entry = Entry(transaction_date=date(2026, 3, 15), postings=tuple(postings))

    reversal = build_reversal(
        entry,
        reverses_id="txn-1",
        original_period_closed=original_closed,
        current_period_date=date(2026, 9, 1),
    )

    combined = totals_by_commodity([*entry.postings, *reversal.postings])

    assert all(total == 0 for total in combined.values())


@given(postings=balanced_postings())
def test_a_reversal_restores_every_account_not_merely_the_total(
    postings: list[Posting],
) -> None:
    """A pair that nets to zero overall while leaving two accounts wrong would pass a total.

    Balances are per account, so the invariant is per account.
    """
    entry = Entry(transaction_date=date(2026, 3, 15), postings=tuple(postings))
    reversal = build_reversal(
        entry,
        reverses_id="txn-1",
        original_period_closed=False,
        current_period_date=date(2026, 9, 1),
    )

    balances: dict[tuple[str, str], Decimal] = defaultdict(lambda: Decimal(0))
    for posting in [*entry.postings, *reversal.postings]:
        balances[posting.account_id, posting.commodity] += posting.amount

    assert all(balance == 0 for balance in balances.values())


# --- The trial balance ties after any sequence of operations ------------------------------


@given(
    entries=st.lists(balanced_postings(), min_size=1, max_size=8),
    reverse_flags=st.lists(st.booleans(), min_size=1, max_size=8),
)
def test_the_trial_balance_ties_after_any_sequence(
    entries: list[list[Posting]], reverse_flags: list[bool]
) -> None:
    """ADR-0036's fourth invariant.

    A sequence of postings and reversals, in any order and any mix, and the books still sum
    to zero in every commodity. This is the trial balance tying, computed from the postings
    themselves rather than from a stored total — ADR-0003 derives balances by aggregation,
    and there is deliberately no second implementation to disagree with it.
    """
    ledger: list[Posting] = []

    for index, postings in enumerate(entries):
        entry = Entry(transaction_date=date(2026, 3, 15), postings=tuple(postings))
        ledger.extend(entry.postings)

        if index < len(reverse_flags) and reverse_flags[index]:
            reversal = build_reversal(
                entry,
                reverses_id=f"txn-{index}",
                original_period_closed=False,
                current_period_date=date(2026, 9, 1),
            )
            ledger.extend(reversal.postings)

    assert all(total == 0 for total in totals_by_commodity(ledger).values())
