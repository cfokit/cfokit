"""This module's refusals, subclassing the ledger's so both adapters render them alike.

Every code is published in `docs/contracts/error-codes.json` the moment the class exists.
"""

from __future__ import annotations

from cfokit.ledger.errors import LedgerError

__all__ = [
    "LineOutsidePeriod",
    "StatementDoesNotBalance",
    "StatementInvalid",
    "StatementNotFound",
    "StatementOverlaps",
]


class StatementInvalid(LedgerError):
    """A statement that cannot be read as one: a period ending before it starts, a line
    moving nothing, a line with no payee."""

    code = "statement_invalid"
    status = 422


class StatementDoesNotBalance(LedgerError):
    """The lines do not account exactly for the movement from opening to closing balance.

    The check that catches a misread figure. Every amount on an uploaded statement was
    transcribed, and the statement's own balances are the only independent evidence of what
    it said (ADR-0046). No tolerance, because `NFR-01` allows none.
    """

    code = "statement_does_not_balance"
    status = 422


class LineOutsidePeriod(LedgerError):
    """A line is dated outside the period the statement says it covers."""

    code = "line_outside_period"
    status = 422


class StatementOverlaps(LedgerError):
    """Another statement for this account already covers part of this period.

    Refused rather than merged. Two statements over one day each claim that day's activity,
    and telling a line that appears on both from two genuinely identical lines is matching
    against what the books already hold — `BKP-13`, which this does not attempt. The same
    statement sent again is not this: it is a replay, and records nothing.
    """

    code = "statement_overlaps"
    status = 409


class StatementNotFound(LedgerError):
    """No statement with this id in this entity."""

    code = "statement_not_found"
    status = 404
