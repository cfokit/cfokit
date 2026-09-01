"""Building the entry that undoes a posted one (`LED-08`, ADR-0007).

> "A posted transaction is never altered or removed. Corrections are new entries that reverse
> the original, leaving both visible."

ADR-0007 requires this to be a **first-class operation** rather than something a caller
assembles by hand, on the grounds that a policy which is laborious to follow is a policy that
gets worked around. So the whole of a reversal is one call.

The engine takes no clock and reads no period state (ADR-0008). Whether the original's period
is closed, and what today's open period is, both arrive as arguments — which is also what makes
the dating rule testable without a database.
"""

from __future__ import annotations

from datetime import date

from cfokit.ledger.engine.entry import Entry

__all__ = ["build_reversal"]


def build_reversal(
    original: Entry,
    *,
    reverses_id: str,
    original_period_closed: bool,
    current_period_date: date,
    restate_original_period: bool = False,
    description: str | None = None,
) -> Entry:
    """Return the entry that reverses `original`.

    Every posting is negated and nothing else changes, so the pair sums to zero in every
    commodity and the balance of every account it touched returns to exactly what it was.

    **Dating follows the period state (ADR-0030 § 4):**

    - Original period **open** — the reversal takes the original transaction date, so the
      correction lands where the error was and the period's figures come out right.
    - Original period **closed** — it defaults to `current_period_date`, because posting into
      a closed period is not something a correction gets to do quietly. Restating the original
      period is available through `restate_original_period`, and is itself a reopen: this
      function only returns the date, and the caller is responsible for the reopen event and
      its recorded reason, which is a human capability and never a skill's (ADR-0030).

    `reverses_id` is the identifier of the transaction being reversed. The engine does not
    interpret it; it only carries it, so both entries stay visible and linked.
    """
    if original_period_closed and not restate_original_period:
        transaction_date = current_period_date
    else:
        transaction_date = original.transaction_date

    return Entry(
        transaction_date=transaction_date,
        postings=tuple(posting.negated() for posting in original.postings),
        description=description,
        reverses_id=reverses_id,
    )
