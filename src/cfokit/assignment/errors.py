"""This module's refusals, subclassing the ledger's so both adapters render them alike.

Every code is published in `docs/contracts/error-codes.json` the moment the class exists —
`scripts/generate_contracts.py` walks the package tree rather than the composed surface, so
"a caller binding to CFOKit binds to the product rather than to today's routing table".
"""

from __future__ import annotations

from cfokit.ledger.errors import LedgerError

__all__ = ["PrecedenceTaken", "RuleNotFound"]


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
