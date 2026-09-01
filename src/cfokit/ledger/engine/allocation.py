"""Dividing an amount so the parts sum exactly to the whole (`LED-05`, ADR-0025).

> "Where an amount must be divided and does not divide evenly, the parts sum exactly to the
> original and the distribution is deterministic. The same division always produces the same
> parts."

**Largest remainder, ties broken by line order.** Every part gets the floor of its exact
share; whatever is left over is one quantum each to the parts with the largest discarded
remainder, and where two remainders are equal the earlier line wins. Ties broken by position
rather than by value is what makes this reproducible: the same call always returns the same
list, so re-running an allocation never silently moves a cent between lines.

**This is not rounding.** ADR-0025 forbids a rounding call anywhere in `engine`, and none
happens here — nothing is discarded. `scale` is the increment the parts must be expressible
in, and the arithmetic is done in whole units of that increment using integers, so the
result is exact by construction rather than exact within a tolerance.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from cfokit.ledger.errors import AllocationInvalid

__all__ = ["allocate", "allocate_evenly"]


def allocate(total: Decimal, weights: Sequence[int], scale: int) -> list[Decimal]:
    """Divide `total` across `weights`, in increments of 10**-`scale`.

    Returns one `Decimal` per weight, in the order the weights were given, summing to exactly
    `total`. Handles negative totals — a reversal allocates the same way the original did.

    Raises `AllocationInvalid` when the request cannot be satisfied exactly: no weights, a
    negative weight, weights summing to zero, a negative scale, or a `total` carrying more
    precision than `scale` can express. That last case is a refusal rather than a rounding,
    because rounding it would make the parts sum to something other than what was asked for.
    """
    if scale < 0:
        raise AllocationInvalid(f"scale must not be negative, got {scale}")
    if not weights:
        raise AllocationInvalid("allocation needs at least one weight")
    if any(weight < 0 for weight in weights):
        raise AllocationInvalid("weights must not be negative")

    total_weight = sum(weights)
    if total_weight == 0:
        raise AllocationInvalid("weights must not sum to zero")

    # Shift into whole units of the target increment rather than dividing by it: scaleb only
    # moves the exponent, so nothing can be lost on the way in.
    shifted = total.scaleb(scale)
    if shifted != shifted.to_integral_value():
        raise AllocationInvalid(
            f"{total} carries more precision than scale {scale} can express exactly"
        )
    units = int(shifted)

    # Integer arithmetic from here, so "the parts sum to the whole" is arithmetic rather than
    # something to verify afterwards. Floor division leaves a non-negative shortfall smaller
    # than the number of parts, for negative totals as well as positive ones.
    floors: list[int] = []
    remainders: list[int] = []
    for weight in weights:
        quotient, remainder = divmod(units * weight, total_weight)
        floors.append(quotient)
        remainders.append(remainder)

    shortfall = units - sum(floors)
    ranked = sorted(range(len(weights)), key=lambda index: (-remainders[index], index))
    for index in ranked[:shortfall]:
        floors[index] += 1

    quantum = Decimal(1).scaleb(-scale)
    return [Decimal(part) * quantum for part in floors]


def allocate_evenly(total: Decimal, parts: int, scale: int) -> list[Decimal]:
    """Divide `total` into `parts` equal shares, to the nearest expressible increment.

    The `LED-04` acceptance case: ten dollars three ways is 3.34, 3.33, 3.33 — summing to
    exactly 10.00, with the odd cent going to the first line because ties break by order.
    """
    if parts < 1:
        raise AllocationInvalid(f"need at least one part, got {parts}")
    return allocate(total, [1] * parts, scale)
