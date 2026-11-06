"""How finely a commodity's amounts are shown (`LED-06`, ADR-0025).

In the engine rather than in presentation because two layers need it: presentation rounds to
it, once, and the cash view allocates in it, never rounding (ADR-0080 § 1). One function, so a
registry replaces it in one place.
"""

from __future__ import annotations

__all__ = ["DEFAULT_DISPLAY_SCALE", "display_scale"]

DEFAULT_DISPLAY_SCALE = 2
"""Where a commodity's own scale is not known.

ADR-0025 names the registry this stands in for — "USD 2, JPY 0, some currencies 3" — and
defaults to 2 until one exists. Two is right for the currencies CFOKit holds today and wrong
for JPY, which is the cost that record accepted.
"""


def display_scale(commodity: str) -> int:
    """The number of decimal places `commodity`'s amounts are shown at (`LED-06`)."""
    return DEFAULT_DISPLAY_SCALE
