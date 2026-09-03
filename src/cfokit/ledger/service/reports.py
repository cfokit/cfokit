"""Reports over the books (`RPT-01`, `RPT-10`, `RPT-11`).

**Every figure here is exact.** Rounding is a presentation act and happens once, in
`cfokit.ledger.presentation`, which the adapters call — a rounding call in this layer would
mean the boundary has been misplaced (ADR-0025).

**A report states the basis it was produced on** (`RPT-10`). It is read from the entity rather
than taken from the caller, for the same reason the functional currency is: a caller who could
state the basis could label a report as something it is not.

**A report is reproducible as the books stood at an earlier moment** (`RPT-11`). That is a
parameter here rather than a separate code path, because a report that reproduces the past by
different machinery than it reports the present is two reports that can disagree.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime

from cfokit.ledger.repository.reports import AccountBalance
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.authorisation import Capability, require
from cfokit.ledger.service.principal import Principal

__all__ = ["TrialBalance", "trial_balance"]


@dataclass(frozen=True, slots=True)
class TrialBalance:
    """A trial balance, with what it was produced on stated on its face."""

    as_of: date
    watermark: datetime | None
    accounting_basis: str
    functional_currency: str
    rows: tuple[AccountBalance, ...]


def trial_balance(
    database: Database,
    *,
    entity_id: str,
    principal: Principal,
    as_of: date,
    watermark: datetime | None = None,
) -> TrialBalance:
    """Every account with a non-zero balance as of `as_of` (`RPT-01`).

    `watermark` reproduces the books as they stood then (`RPT-11`). Two runs over the same
    watermark return the same figures; two runs over different ones differ by exactly the
    transactions posted between them, because nothing is stored and every figure is derived
    from the postings that were in the books at that moment.
    """
    now = datetime.now(UTC)
    with database.entity_write(entity_id) as write:
        actor = write.privileges_in_force(principal.id, now)
        acted_for = (
            write.privileges_in_force(principal.acting_for, now)
            if principal.acting_for is not None
            else frozenset()
        )
        require(Capability.READ, principal, actor, acted_for)

        settings = write.settings
        rows = write.trial_balance(as_of=as_of, watermark=watermark)

    return TrialBalance(
        as_of=as_of,
        watermark=watermark,
        accounting_basis=settings.accounting_basis,
        functional_currency=settings.functional_currency,
        rows=tuple(rows),
    )
