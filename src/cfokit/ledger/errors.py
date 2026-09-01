"""Errors carry a stable, machine-readable ``code``. Callers depend on it (ADR-0015).

Adding a code is a contract change. Renaming one is a breaking change.
"""

from __future__ import annotations


class LedgerError(Exception):
    """Base for every error the ledger raises across a published interface."""

    code: str = "internal_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ConfigError(LedgerError):
    """Configuration is missing or unusable. Never carries the offending value."""

    code = "config_invalid"


class MigrationError(LedgerError):
    """A migration could not be applied."""

    code = "migration_failed"


# --- Booking ---------------------------------------------------------------------------
# Raised by the pure engine, so both adapters surface the same code for the same condition
# (ADR-0009). Messages carry amounts and commodities and are therefore error detail, not
# something to log at info level (CLAUDE.md, Observability).


class UnbalancedTransaction(LedgerError):
    """Postings do not sum to zero in some commodity (`LED-03`).

    Raised before the write reaches the database. The deferred constraint trigger is what
    actually guarantees this, on every code path including future ones; this exists so the
    common case gets a message worth reading (ADR-0006).
    """

    code = "unbalanced_transaction"


class CommodityNotPermitted(LedgerError):
    """An amount in a commodity the entity cannot hold (`LED-15`).

    Refused rather than converted, and refused with a reason. Conversion is `LED-16`, which is
    deferred until an entity first transacts in another currency.
    """

    code = "commodity_not_permitted"


class TransactionIncomplete(LedgerError):
    """Too few postings to record a movement of value.

    Distinct from `unbalanced_transaction` on purpose: an empty set of postings sums to zero
    in every commodity, so it would pass a balance check while recording nothing at all.
    """

    code = "transaction_incomplete"


class AllocationInvalid(LedgerError):
    """An allocation was asked for that cannot be satisfied exactly (`LED-05`).

    Includes a total carrying more precision than the requested increment can express. That
    is a refusal rather than a rounding, because rounding it would make the parts sum to
    something other than the amount asked for.
    """

    code = "allocation_invalid"
