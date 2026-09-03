"""Turning a `LedgerError` into an HTTP response, in one place.

`code` is the contract and the status is not (ADR-0015), but a status that contradicts the
code is still a defect — a caller that retries on 5xx would retry an unbalanced transaction
forever. So the mapping is enumerated here rather than decided at each raise site, and a code
with no entry falls to 500, which is the safe direction: an unmapped code is a bug in this
table, not a client error to report as one.

**Both adapters surface the same code for the same condition** (ADR-0009). The MCP adapter
does not reuse the status, because MCP has no statuses — it reuses this module's codes.
"""

from __future__ import annotations

from http import HTTPStatus

from cfokit.ledger.errors import (
    AccountNotFound,
    AllocationInvalid,
    AlreadyOpened,
    CommodityNotPermitted,
    EntityNotFound,
    IdempotencyKeyRequired,
    IdempotencyKeyReused,
    LastOwner,
    LedgerError,
    NotAPerson,
    NotAuthenticated,
    NotAuthorised,
    NothingToClose,
    OpeningBalanceAccountUnset,
    PeriodClosed,
    PeriodNotClosed,
    RetainedEarningsUnset,
    TransactionAlreadyPosted,
    TransactionIncomplete,
    TransactionNotFound,
    UnbalancedTransaction,
    UnknownRole,
    YearAlreadyClosed,
)

__all__ = ["STATUS_FOR_CODE", "status_for"]

STATUS_FOR_CODE: dict[str, int] = {
    NotAuthenticated.code: HTTPStatus.UNAUTHORIZED,
    NotAuthorised.code: HTTPStatus.FORBIDDEN,
    # 409, not 403: the caller holds the capability, and this particular revocation would
    # leave the entity unheld (`IAM-04`).
    LastOwner.code: HTTPStatus.CONFLICT,
    UnknownRole.code: HTTPStatus.UNPROCESSABLE_ENTITY,
    # 409: the request was well-formed and the caller may post. The period is not open
    # to anyone, and reopening it is a separate act (`LED-11`, ADR-0030).
    PeriodClosed.code: HTTPStatus.CONFLICT,
    PeriodNotClosed.code: HTTPStatus.CONFLICT,
    YearAlreadyClosed.code: HTTPStatus.CONFLICT,
    NothingToClose.code: HTTPStatus.CONFLICT,
    RetainedEarningsUnset.code: HTTPStatus.UNPROCESSABLE_ENTITY,
    OpeningBalanceAccountUnset.code: HTTPStatus.UNPROCESSABLE_ENTITY,
    AlreadyOpened.code: HTTPStatus.CONFLICT,
    # 403: a capability reserved to people. No credential an agent can present changes it.
    NotAPerson.code: HTTPStatus.FORBIDDEN,
    EntityNotFound.code: HTTPStatus.NOT_FOUND,
    AccountNotFound.code: HTTPStatus.NOT_FOUND,
    TransactionNotFound.code: HTTPStatus.NOT_FOUND,
    # 409 rather than 422: the request is well-formed and would have been valid earlier. The
    # caller's remedy is a different operation, not a corrected body.
    TransactionAlreadyPosted.code: HTTPStatus.CONFLICT,
    IdempotencyKeyReused.code: HTTPStatus.CONFLICT,
    # 422 rather than 400: the body parsed, and what is wrong is what it says.
    IdempotencyKeyRequired.code: HTTPStatus.UNPROCESSABLE_ENTITY,
    UnbalancedTransaction.code: HTTPStatus.UNPROCESSABLE_ENTITY,
    CommodityNotPermitted.code: HTTPStatus.UNPROCESSABLE_ENTITY,
    TransactionIncomplete.code: HTTPStatus.UNPROCESSABLE_ENTITY,
    AllocationInvalid.code: HTTPStatus.UNPROCESSABLE_ENTITY,
}


def status_for(error: LedgerError) -> int:
    """The HTTP status for an error's stable code, defaulting to 500."""
    return STATUS_FOR_CODE.get(error.code, HTTPStatus.INTERNAL_SERVER_ERROR)
