"""Pure booking engine — the bottom layer (ADR-0008).

No I/O, no configuration, no database, no clock. Every input arrives as an argument
and every output is a return value, so booking semantics are testable in isolation and
differentially against the Beancount oracle (ADR-0010).

Money is `decimal.Decimal`, never `float` (ADR-0005).
"""

from cfokit.ledger.engine.accounts import (
    AccountType,
    NormalBalance,
    Statement,
    increases,
    normal_balance,
    statement,
)
from cfokit.ledger.engine.allocation import allocate, allocate_evenly
from cfokit.ledger.engine.balance import assert_balanced, is_balanced, totals_by_commodity
from cfokit.ledger.engine.entry import Entry, Posting
from cfokit.ledger.engine.postability import check_postable, is_postable
from cfokit.ledger.engine.reversal import build_reversal

__all__ = [
    "AccountType",
    "Entry",
    "NormalBalance",
    "Posting",
    "Statement",
    "allocate",
    "allocate_evenly",
    "assert_balanced",
    "build_reversal",
    "check_postable",
    "increases",
    "is_balanced",
    "is_postable",
    "normal_balance",
    "statement",
    "totals_by_commodity",
]
