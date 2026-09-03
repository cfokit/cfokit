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


class NotAuthenticated(LedgerError):
    """The caller was not authenticated.

    Distinct from an authorisation failure by design: ADR-0030 requires "period closed" to be
    distinguishable from "not permitted" so a skill can surface the right question, and the
    same reasoning applies here — "log in" and "you may not" are different answers.
    """

    code = "not_authenticated"


class NotAuthorised(LedgerError):
    """The caller is known and holds no role permitting this (`IAM-01`).

    Distinct from `not_authenticated` on purpose: "log in" and "you may not" are different
    answers, and ADR-0030 applies the same reasoning to a closed period so a skill can surface
    the right question rather than a generic refusal.

    It reveals that the entity exists, which is a deliberate trade. A caller who has named an
    entity and holds nothing in it is far more often someone whose access lapsed (`IAM-09`)
    or was revoked (`IAM-15`) than someone probing for entity ids, and telling the first group
    "not found" sends them to support instead of to an administrator.
    """

    code = "not_authorised"


class PeriodClosed(LedgerError):
    """The transaction's period is closed (`LED-11`, ADR-0030).

    Distinct from `not_authorised`: the caller may post, and this period is not open to
    anyone. Reopening it is a separate, recorded act — telling them "not permitted" would send
    them to ask for a capability that would not help.
    """

    code = "period_closed"


class PeriodNotClosed(LedgerError):
    """A reopen was asked for on a period that is not closed (`LED-11`)."""

    code = "period_not_closed"


class NotAPerson(LedgerError):
    """A capability reserved to people, attempted by an agent (ADR-0030, `SOC1-17`).

    Reopening a closed period is the case: the control only survives a single-operator entity
    because it is a capability the agent does not hold, so it cannot auto-acknowledge its way
    through. Distinct from `not_authorised`, which would be false — the person it acts for may
    well hold it, and saying otherwise would send them to fix the wrong thing.
    """

    code = "not_a_person"


class AccountNotFound(LedgerError):
    """No such account in this entity.

    Not distinguished from an account in another entity: row-level security makes those the
    same answer, and telling them apart would leak the other entity's chart (`NFR-04`).
    """

    code = "account_not_found"


class OpeningBalanceAccountUnset(LedgerError):
    """No opening balance equity account is named, so books cannot be opened (`LED-10`)."""

    code = "opening_balance_account_unset"


class AlreadyOpened(LedgerError):
    """These books already carry opening balances (`LED-10`).

    Opening them again would double every carried-in figure. A balance that was wrong, or an
    account missed at the time, is corrected the way every other posted mistake is: an ordinary
    entry against the same equity account (`LED-08`).
    """

    code = "already_opened"


class ObligationNotFound(LedgerError):
    """No such obligation in this entity (`LED-17`).

    Not distinguished from another entity's: row-level security makes those the same answer,
    and telling them apart would leak that entity's receivables (`NFR-04`).
    """

    code = "obligation_not_found"


class RetainedEarningsUnset(LedgerError):
    """No retained earnings account is named, so a year cannot be closed (`LED-12`)."""

    code = "retained_earnings_unset"


class YearAlreadyClosed(LedgerError):
    """The fiscal year is closed and its close is current (`LED-12`, ADR-0027).

    A close that a later posting made stale is not this: it is re-run rather than refused.
    """

    code = "year_already_closed"


class NothingToClose(LedgerError):
    """The fiscal year has no income or expense balance to close.

    `LED-12`'s outcome — the new year opens with them at zero — already holds, so there is
    nothing to post and a closing entry of zero would be noise in the trail.
    """

    code = "nothing_to_close"


class UnknownRole(LedgerError):
    """No such role in the catalogue (`IAM-01`, ADR-0039).

    Roles are rows, so the set of valid names is not fixed at build time and the API cannot
    enumerate them in its schema. This is what a caller gets instead of a constraint violation.
    """

    code = "unknown_role"


class LastOwner(LedgerError):
    """The last owner cannot be revoked or demoted (`IAM-04`, `IAM-21`).

    Distinct from `not_authorised`: the caller is permitted to revoke grants, and this
    particular one would leave the entity unheld. Telling them "not permitted" would send them
    to ask for a capability they already hold.
    """

    code = "last_owner"


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


# --- The write path ----------------------------------------------------------------------
# Raised by the service layer, so both adapters surface the same code for the same condition
# (ADR-0009). Each is a contract addition under ADR-0015.


class IdempotencyKeyRequired(LedgerError):
    """A write arrived without an idempotency key (ADR-0029).

    Mandatory rather than optional, because "the write that omits a key is the write that
    double-books" — making it required moves the decision from runtime judgement to a
    property every write path can assume.
    """

    code = "idempotency_key_required"


class IdempotencyKeyReused(LedgerError):
    """A key was replayed with different parameters (ADR-0029).

    A client error rather than a replay. ADR-0029 requires that a repeated key "must not
    silently succeed with a different one" — two five-dollar coffees on the same day are two
    transactions, and the way a caller says so is a second key.
    """

    code = "idempotency_key_reused"


class EntityNotFound(LedgerError):
    """No entity with that id is visible.

    Deliberately not distinguished from "exists but you cannot see it": row-level security
    scopes reads to the entity on the connection, so another entity's rows are indistinguishable
    from absent ones, and saying otherwise would leak their existence (`NFR-04`).
    """

    code = "entity_not_found"


class TransactionNotFound(LedgerError):
    """No transaction with that id is visible to this entity."""

    code = "transaction_not_found"


class TransactionAlreadyPosted(LedgerError):
    """Posting is the point of no return, and it has already been passed (`LED-07`).

    Distinct from `unbalanced_transaction`: nothing is wrong with the entry, it is simply no
    longer a draft. The correction for a posted entry is a reversal (ADR-0007).
    """

    code = "transaction_already_posted"


class AllocationInvalid(LedgerError):
    """An allocation was asked for that cannot be satisfied exactly (`LED-05`).

    Includes a total carrying more precision than the requested increment can express. That
    is a refusal rather than a rounding, because rounding it would make the parts sum to
    something other than the amount asked for.
    """

    code = "allocation_invalid"
