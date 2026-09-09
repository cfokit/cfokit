"""Reading obligations and what has settled them (`LED-17`, ADR-0037).

> "An invoice raised in one period and paid in another is recoverable as either, depending on
> the basis in force."

This is the recoverability half. Both events are stored and linked, so an obligation can be
read as the commitment it was when it arose, or as the settlements applied to it since — the
same facts, asked for differently, rather than two records that could disagree.

**Outstanding is derived**, never stored, for the same reason balances are (ADR-0003). A stored
figure would be a second place the truth lives, and the two would part company the first time a
settlement was recorded and the update was missed.

Deriving the cash *view* from these events is `RPT-19`, which is deferred. What is here is the
record that makes the derivation exact when it is built, which is ADR-0037 § 3's point: the
incumbents infer the link at report time and it does not hold.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from cfokit.ledger.errors import ObligationNotFound
from cfokit.ledger.repository.obligations import Obligation, Settlement
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.authorisation import Capability, authorise
from cfokit.ledger.service.principal import Principal

__all__ = ["ObligationDetail", "obligation_detail", "outstanding_obligations"]


@dataclass(frozen=True, slots=True)
class ObligationDetail:
    """One obligation, and every settlement applied to it."""

    obligation: Obligation
    settlements: tuple[Settlement, ...]


def outstanding_obligations(
    database: Database,
    *,
    entity_id: str,
    principal: Principal,
    as_of: date | None = None,
    unsettled_only: bool = True,
) -> tuple[Obligation, ...]:
    """Obligations arisen by `as_of`, with what has been applied to each.

    `unsettled_only` by default, because the question this answers is almost always "what is
    still owed". Passing false gives the full history, settled ones included.
    """
    with database.entity_write(entity_id) as write:
        authorise(write, Capability.READ, principal)
        return tuple(write.outstanding(as_of=as_of, unsettled_only=unsettled_only))


def obligation_detail(
    database: Database, *, entity_id: str, principal: Principal, obligation_id: str
) -> ObligationDetail:
    """One obligation read as both events: what was committed, and what has settled it."""
    with database.entity_write(entity_id) as write:
        authorise(write, Capability.READ, principal)
        found = write.outstanding(obligation_id=obligation_id)
        if not found:
            raise ObligationNotFound(f"no obligation {obligation_id} in this entity")
        return ObligationDetail(
            obligation=found[0], settlements=tuple(write.settlements_for(obligation_id))
        )
