"""This module's refusals, subclassing the ledger's so both adapters render them alike.

Every code is published in `docs/contracts/error-codes.json` the moment the class exists —
`scripts/generate_contracts.py` walks the package tree rather than the composed surface, so
"a caller binding to CFOKit binds to the product rather than to today's routing table".
"""

from __future__ import annotations

from cfokit.ledger.errors import LedgerError

__all__ = [
    "NotACounterpart",
    "NothingToDecline",
    "PrecedenceTaken",
    "QuestionNotFound",
    "RuleNotFound",
]


class QuestionNotFound(LedgerError):
    """No open question about this line: it was never asked, or it is already answered."""

    code = "question_not_found"
    status = 404


class NotACounterpart(LedgerError):
    """The record a person named is not one this line could be (ADR-0059 § 4).

    Held to the same exact facts as the search — the amount, signed as a posting, and the
    commodity; the line's own account for a recorded transaction, another for a transfer — but
    not to its windows. A record no line has claimed, still open, and not reversed. A match with
    a difference has to put the difference somewhere, which is what `BKP-12` rules out.
    """

    code = "not_a_counterpart"
    status = 422


class NothingToDecline(LedgerError):
    """A line with candidates — an ambiguous or proposed one — is what "none" answers.

    A line no counterpart was found for is answered by approving a rule that covers it, or by
    naming the record it is.
    """

    code = "nothing_to_decline"
    status = 409


class RuleNotFound(LedgerError):
    """An edit or retirement named a rule this entity does not have."""

    code = "rule_not_found"
    status = 404


class PrecedenceTaken(LedgerError):
    """Another live rule already holds this precedence.

    Refused rather than allowed with a tiebreak, because `BKP-08` makes the order something
    the operator *states*: two live rules at one precedence means the order does not in fact
    say which wins, and the answer would fall to a tiebreak nobody chose.
    """

    code = "precedence_taken"
    status = 409
