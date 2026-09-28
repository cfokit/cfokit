"""Account activity: what arrives from a bank or card account, as the source stated it.

`BKP-03` makes an uploaded statement the path that must work with "no third-party account and
no credentials", and it is the first producer of account activity to exist. A fetched
statement and an unattended feed are the other two (ADR-0045 § 1); they are why this module is
named for the capability rather than for any one of them (ADR-0031).

**This module stores what the statement said, and decides nothing about where it belongs.**
Coding a line is assignment's (ADR-0045), and the two never import each other (ADR-0022). What
passes between them is a candidate shape over a published interface, carrying the line's
source reference — which is the whole of what one needs to know about the other.

**A statement is recorded only if it proves itself** (ADR-0046). Every figure here was read out
of a document by a model, and a model can misread one. A bank prints an opening balance, a
closing balance and every line between them, so the statement carries its own check: the lines
must account exactly for the movement between the two balances. `NFR-01` allows no tolerance,
so neither does this. The check is the source's arithmetic against the transcription — two
paths through one document, which is `IMP-08`'s argument applied to a statement.

What is here is pure: no I/O, no clock, no database. The service does the rest.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from cfokit.activity.errors import LineOutsidePeriod, StatementDoesNotBalance, StatementInvalid

__all__ = [
    "Continuity",
    "Statement",
    "StatementLine",
    "content_digest",
    "continuity",
    "prove",
    "source_ref",
]


@dataclass(frozen=True, slots=True)
class StatementLine:
    """One line as printed. Signed as a posting is signed: positive is a debit."""

    transaction_date: date
    payee: str
    amount: Decimal
    description: str | None = None


@dataclass(frozen=True, slots=True)
class Statement:
    """A statement for one account over one period, in the order its lines were printed.

    **Every figure is signed as a posting is signed** — positive is a debit. A bank account in
    credit has a positive balance and a deposit is positive; a card with a balance owed has a
    negative one and a purchase is negative. One convention for every figure is what lets the
    proof be one line of arithmetic rather than a case per account type.

    A line's position in `lines` is its identity. Two identical coffees are two lines because
    they are printed twice, and nothing else distinguishes them.
    """

    account_id: str
    period_start: date
    period_end: date
    opening_balance: Decimal
    closing_balance: Decimal
    commodity: str
    lines: tuple[StatementLine, ...]


@dataclass(frozen=True, slots=True)
class Continuity:
    """How a statement follows the one before it for the same account (`BKP-21`).

    Reported, never refused. The first statement for an account follows nothing, and a gap is
    a finding for the operator — a month nobody supplied — rather than a reason to lose the
    month somebody did.
    """

    previous_statement_id: str
    # The previous period ended the day before this one began.
    contiguous: bool
    # This statement opened where the previous one closed.
    balance_continues: bool


def prove(statement: Statement) -> None:
    """Refuse a statement that does not account for itself. Raises; returns nothing.

    Opening plus every line must equal closing, exactly. A misread amount, a dropped line or a
    line read twice all fail it, and each is the failure a transcription is prone to.

    Every line must fall inside the stated period, because the period is the coverage
    `BKP-21` records, and a line outside it is either misread or belongs to another statement.
    """
    if statement.period_start > statement.period_end:
        raise StatementInvalid(
            f"the period starts {statement.period_start} after it ends {statement.period_end}"
        )
    if not statement.commodity.strip():
        raise StatementInvalid("a statement needs the commodity its figures are in")

    for position, line in enumerate(statement.lines, start=1):
        if line.amount == 0:
            raise StatementInvalid(f"line {position} moves nothing")
        if not line.payee.strip():
            raise StatementInvalid(f"line {position} has no payee")
        if not statement.period_start <= line.transaction_date <= statement.period_end:
            raise LineOutsidePeriod(
                f"line {position} is dated {line.transaction_date}, outside "
                f"{statement.period_start} to {statement.period_end}"
            )

    movement = sum((line.amount for line in statement.lines), Decimal(0))
    difference = statement.opening_balance + movement - statement.closing_balance
    if difference != 0:
        # The difference is the most useful thing a reader can be told — a single misread
        # line usually shows up as exactly its own error — and it is not a posting amount,
        # so it is safe to say in a message that never reaches a log at info level.
        raise StatementDoesNotBalance(
            f"{len(statement.lines)} lines move {movement}, but the statement opens at "
            f"{statement.opening_balance} and closes at {statement.closing_balance}: "
            f"{difference} is unaccounted for"
        )


def content_digest(statement: Statement) -> str:
    """sha256 over a canonical rendering of everything the statement states.

    What tells a replay from a conflict: the same statement sent twice has the same digest,
    and a different statement for the same period does not. Decimals are rendered through
    `str`, so `10.00` and `10.0` differ — they were written differently, and a statement read
    two ways is two readings.
    """
    canonical = json.dumps(
        {
            "account_id": statement.account_id,
            "period": [statement.period_start.isoformat(), statement.period_end.isoformat()],
            "balances": [str(statement.opening_balance), str(statement.closing_balance)],
            "commodity": statement.commodity,
            "lines": [
                [
                    line.transaction_date.isoformat(),
                    line.payee,
                    line.description,
                    str(line.amount),
                ]
                for line in statement.lines
            ],
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def source_ref(statement_id: str, line: int) -> str:
    """The name a transaction carries for the line it was coded from (`BKP-19`).

    Built from the statement and the position, never from the line's content, so it is
    unique however alike two lines are — and stable, so running a line again replays.
    """
    return f"account-statement:{statement_id}:{line}"


def continuity(
    statement: Statement,
    *,
    previous_statement_id: str,
    previous_end: date,
    previous_closing: Decimal,
) -> Continuity:
    """How `statement` follows the latest earlier statement for its account."""
    return Continuity(
        previous_statement_id=previous_statement_id,
        contiguous=previous_end + timedelta(days=1) == statement.period_start,
        balance_continues=previous_closing == statement.opening_balance,
    )
