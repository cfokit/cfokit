"""Marking a statement issued, and knowing when it stops being true (`RPT-17`, `SOC1-20`).

> "A statement can be marked issued, fixing what was reported, to whom, and when."

> "Where a correction posted after a statement was issued changes that statement's figures, the
> issued statement is marked superseded, and both what was reported and what is now true remain
> retrievable."

**Both halves are retrievable because nothing was overwritten.** What was reported is stored
with the statement; what is now true is the same report run again. `RPT-11` already made the
second possible, and this is what it was for — reproducibility is only useful once there is a
record of what was issued to compare against.

**Supersession is detected, not remembered.** A posting that entered the books after the
watermark and falls inside the statement's window changes its figures. A posting dated outside
the window changes nothing the statement said, which is why the window bounds the query rather
than the watermark alone.

**Reading is the whole requirement to issue.** Anyone who can read the books can already tell a
lender what they say; what matters is that the act is recorded, with who did it and to whom.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime

from cfokit.ledger.errors import IssuedStatementNotFound
from cfokit.ledger.repository.issuance import IssuedStatement
from cfokit.ledger.repository.unit_of_work import Database, EntityWrite
from cfokit.ledger.service.authorization import Capability, authorize
from cfokit.ledger.service.principal import Principal

__all__ = ["Issued", "issue_statement", "issued", "supersession"]


@dataclass(frozen=True, slots=True)
class Issued:
    """An issued statement, and whether the books have moved under it."""

    statement: IssuedStatement
    superseded_by: int

    @property
    def superseded(self) -> bool:
        return self.superseded_by > 0


def issue_statement(
    database: Database,
    *,
    entity_id: str,
    principal: Principal,
    request_id: str,
    report: str,
    since: date | None,
    as_of: date,
    figures: dict[str, object],
    issued_to: str,
) -> str:
    """Fix what was reported, to whom, and when (`RPT-17`).

    `figures` is the rendered statement as the recipient received it, stored rather than
    re-derived. Re-deriving assumes the presentation never changes, and it will — `RPT-12`'s
    display scale registry arrives later, and what a lender was told has to survive that.

    The watermark is now, so the statement reproduces from the books exactly as issued.
    """
    watermark = datetime.now(UTC)
    with database.entity_write(entity_id) as write:
        authorize(write, Capability.READ, principal)
        issuance_id = write.record_issuance(
            report=report,
            since=since,
            as_of=as_of,
            watermark=watermark,
            issued_by=principal.id,
            issued_to=issued_to,
            figures=json.dumps(figures),
        )
        write.record_audit(
            request_id=request_id,
            actor=principal.audit_actor,
            action="issue_statement",
            subject_type="issued_statement",
            subject_id=issuance_id,
            # The recipient and the report, never the figures (CLAUDE.md, Observability).
            detail={"report": report, "as_of": as_of.isoformat(), "issued_to": issued_to},
        )
    return issuance_id


def issued(database: Database, *, entity_id: str, principal: Principal) -> tuple[Issued, ...]:
    """Every statement issued from these books, newest first, each with its standing."""
    with database.entity_write(entity_id) as write:
        authorize(write, Capability.READ, principal)
        return tuple(
            _with_standing(write, statement) for statement in write.issued_statements()
        )


def supersession(
    database: Database, *, entity_id: str, principal: Principal, issuance_id: str
) -> Issued:
    """One issued statement, and whether a later posting changed what it said (`SOC1-20`)."""
    with database.entity_write(entity_id) as write:
        authorize(write, Capability.READ, principal)
        found = write.issued_statements(issuance_id)
        if not found:
            raise IssuedStatementNotFound(f"no issued statement {issuance_id} in this entity")
        return _with_standing(write, found[0])


def _with_standing(write: EntityWrite, statement: IssuedStatement) -> Issued:
    return Issued(
        statement=statement,
        superseded_by=write.postings_after(
            watermark=statement.watermark, since=statement.since, as_of=statement.as_of
        ),
    )
