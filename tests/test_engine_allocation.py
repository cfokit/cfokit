"""Allocation divides an amount so the parts sum exactly to it (`LED-05`, ADR-0025).

Layer 1 of ADR-0036: no protocol, no model, no database.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from cfokit.ledger.engine import allocate, allocate_evenly
from cfokit.ledger.errors import AllocationInvalid


def test_ten_dollars_three_ways() -> None:
    """`LED-04`'s acceptance case, stated verbatim in requirements.md.

    "Divide $10.00 three ways: the three resulting postings sum to exactly $10.00, with no
    residual and no drift."

    The odd cent goes to the first line because largest remainder breaks ties by line order
    (ADR-0025). Which line receives it matters less than that the same line always does.
    """
    parts = allocate_evenly(Decimal("10.00"), 3, scale=2)

    assert parts == [Decimal("3.34"), Decimal("3.33"), Decimal("3.33")]
    assert sum(parts) == Decimal("10.00")


def test_no_drift_under_repetition() -> None:
    """The second half of `LED-04`: repetition introduces no drift.

    Ten thousand rather than the requirement's million, because `Decimal` is exact and drift
    is structurally impossible rather than merely unobserved — the count buys demonstration,
    not confidence, and the suite has to stay fast. The general case is the property test.
    """
    running = Decimal(0)
    for _ in range(10_000):
        running += sum(allocate_evenly(Decimal("10.00"), 3, scale=2), start=Decimal(0))

    assert running == Decimal("100000.00")


def test_the_same_division_always_produces_the_same_parts() -> None:
    """`LED-05` requires determinism by name."""
    first = allocate(Decimal("100.00"), [1, 1, 1, 1, 1, 1, 1], scale=2)
    second = allocate(Decimal("100.00"), [1, 1, 1, 1, 1, 1, 1], scale=2)

    assert first == second
    assert sum(first) == Decimal("100.00")


def test_weighted_split_is_proportional() -> None:
    """`BKP-05`: a transaction split across accounts, parts summing exactly to the whole."""
    parts = allocate(Decimal("100.00"), [50, 30, 20], scale=2)

    assert parts == [Decimal("50.00"), Decimal("30.00"), Decimal("20.00")]


def test_ties_break_by_line_order_not_by_weight() -> None:
    """Equal remainders resolve to the earlier line, so the result is reproducible."""
    parts = allocate(Decimal("1.00"), [1, 1, 1], scale=2)

    assert parts == [Decimal("0.34"), Decimal("0.33"), Decimal("0.33")]


def test_negative_total_allocates_the_same_way() -> None:
    """A reversal allocates its negation, so the parts must mirror exactly (`LED-08`)."""
    forward = allocate_evenly(Decimal("10.00"), 3, scale=2)
    backward = allocate_evenly(Decimal("-10.00"), 3, scale=2)

    assert sum(backward) == Decimal("-10.00")
    assert [-part for part in backward] == [Decimal("3.33"), Decimal("3.33"), Decimal("3.34")]
    assert sum(forward) + sum(backward) == 0


def test_scale_zero_allocates_whole_units() -> None:
    """A commodity with no minor unit, JPY being the usual example (`LED-06`)."""
    parts = allocate_evenly(Decimal("100"), 3, scale=0)

    assert parts == [Decimal("34"), Decimal("33"), Decimal("33")]
    assert sum(parts) == Decimal("100")


def test_a_total_finer_than_the_scale_is_refused_not_rounded() -> None:
    """Rounding it would make the parts sum to something other than what was asked for.

    ADR-0025 forbids the ledger to round at all, so the only honest answer is a refusal with
    a stable code.
    """
    with pytest.raises(AllocationInvalid) as caught:
        allocate_evenly(Decimal("10.005"), 3, scale=2)

    assert caught.value.code == "allocation_invalid"


@pytest.mark.parametrize(
    ("total", "weights", "scale"),
    [
        (Decimal("10.00"), [], 2),
        (Decimal("10.00"), [1, -1], 2),
        (Decimal("10.00"), [0, 0], 2),
        (Decimal("10.00"), [1, 1], -1),
    ],
    ids=["no weights", "negative weight", "weights sum to zero", "negative scale"],
)
def test_unsatisfiable_requests_are_refused(
    total: Decimal, weights: list[int], scale: int
) -> None:
    with pytest.raises(AllocationInvalid):
        allocate(total, weights, scale)


def test_allocate_evenly_needs_at_least_one_part() -> None:
    with pytest.raises(AllocationInvalid):
        allocate_evenly(Decimal("10.00"), 0, scale=2)
