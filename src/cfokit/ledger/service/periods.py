"""Closing a period, and reopening one (`LED-11`, ADR-0030, ADR-0027).

> "A period can be marked closed, signifying it has been reviewed. Once closed, no posting
> enters the period except through a recorded reopening, and anything so recorded is
> identifiable as such."

**Reopening is a person's act, never a skill's**, and ADR-0030 calls this the load-bearing
rule. Most entities have one person, so segregation of duties is impossible and `IAM-17` says
not to raise it — which leaves person against agent as the only control there is. An
acknowledgement parameter could not do this work: an agent that auto-acknowledges defeats it,
and nothing about a parameter stops one. **A capability the agent does not hold cannot be
auto-acknowledged**, so the check is on what the principal *is* rather than on what it holds.

That is why an agent acting for a person is refused even though `IAM-11`'s intersection would
hand it that person's privileges. The intersection governs authority; this governs kind.

**Reopening does not cascade.** ADR-0027: reopening March reopens March, and April stays
closed, because balances are `SUM()` over postings rather than stored values — there is no
April opening figure to invalidate.
"""

from __future__ import annotations

from cfokit.ledger.engine.periods import Period
from cfokit.ledger.errors import NotAPerson, PeriodClosed, PeriodNotClosed
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.authorisation import Capability, authorise
from cfokit.ledger.service.principal import ActorClass, Principal

__all__ = ["close_period", "reopen_period"]


def close_period(
    database: Database,
    *,
    entity_id: str,
    principal: Principal,
    request_id: str,
    period: Period,
) -> str:
    """Mark a period reviewed. Requires `CLOSE`.

    An agent may close: closing asserts the books have been reviewed, and a skill that has
    reconciled a month has done exactly that. It is *reopening* that a skill must not reach,
    because that is the act which lets a write into a period someone has already reported on.
    """
    with database.entity_write(entity_id) as write:
        authorise(write, Capability.CLOSE, principal)

        if write.close_in_force(period) is not None:
            raise PeriodClosed(f"period {period} is already closed")

        close_id = write.close_period(period, closed_by=principal.id)
        write.record_audit(
            request_id=request_id,
            actor=principal.audit_actor,
            action="close_period",
            subject_type="period_close",
            subject_id=close_id,
            detail={"period": str(period)},
        )
    return close_id


def reopen_period(
    database: Database,
    *,
    entity_id: str,
    principal: Principal,
    request_id: str,
    period: Period,
    reason: str,
) -> str:
    """Reopen a closed period. Requires `CLOSE`, and requires being a person.

    `reason` is mandatory because `SOC1-17` requires the reopen to capture one. A reopen with
    no reason is indistinguishable from a mistake once the person who made it has forgotten.
    """
    if not reason.strip():
        raise PeriodNotClosed("a reopen must state a reason")

    with database.entity_write(entity_id) as write:
        authorise(write, Capability.CLOSE, principal)
        _require_person(principal)

        close_id = write.close_in_force(period)
        if close_id is None:
            raise PeriodNotClosed(f"period {period} is not closed")

        if not write.reopen_close(close_id, reopened_by=principal.id, reason=reason):
            # Another transaction reopened it between the read and the write. The advisory
            # lock makes this unreachable; the check is here because relying on that from two
            # modules away is how it stops being true.
            raise PeriodNotClosed(f"period {period} is not closed")  # pragma: no cover

        write.record_audit(
            request_id=request_id,
            actor=principal.audit_actor,
            action="reopen_period",
            subject_type="period_close",
            subject_id=close_id,
            # The reason belongs in the trail: SOC1-17 asks for it, and it is a stated
            # justification rather than an amount, a name, or an account number.
            detail={"period": str(period), "reason": reason},
        )
    return close_id


def _require_person(principal: Principal) -> None:
    """ADR-0030: the reopen is a human capability, never a skill's.

    Checked on `actor_class`, which comes from the shape of the token and never from a claim
    the caller sets (ADR-0033). A skill cannot describe itself as a person.
    """
    if principal.actor_class is not ActorClass.PERSON:
        raise NotAPerson(
            "reopening a closed period is a person's act; ask the person you act for"
        )
