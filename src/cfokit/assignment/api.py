"""The assignment module's REST surface.

**A router the module owns**, included by `cfokit.server`. The ledger's adapter cannot mount
it — "the ledger depends on no module" is an `import-linter` contract, and a ledger adapter
importing this would be exactly that dependency (ADR-0022).

**Candidates arrive in the body and are not stored.** Assignment keeps no queue; whatever
gets transactions in will post the same shape here. Amounts are strings for the reason every
other surface takes them as strings: a JSON number cannot carry the scale it was written at.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Path, status
from pydantic import BaseModel
from pydantic import Field as Body

from cfokit.assignment import Field, Operator, Predicate
from cfokit.assignment.candidate import Candidate, SourceKind
from cfokit.assignment.service import apply_rules, approve, propose, replay
from cfokit.ledger.api import ERRORS, get_database, get_principal
from cfokit.ledger.api.models import Money
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.principal import Principal

router = APIRouter(tags=["assignment"])


class PredicateModel(BaseModel):
    """One condition. Conditions are ANDed; there is no OR and no nesting, so where an
    operator needs a disjunction they approve two rules (ADR-0045)."""

    field: Field
    operator: Operator
    value: str = Body(
        description="Compared as text, or as a decimal where the field is an amount. A "
        "string either way, so an amount keeps the scale it was written at."
    )


class CandidateModel(BaseModel):
    """One incoming transaction, before anything has decided where it belongs."""

    payee: str
    amount: Money = Body(description="Signed as a posting is signed: positive is a debit.")
    commodity: str
    source_account_id: str = Body(description="The entity's own account it appeared on.")
    transaction_date: date
    source_kind: SourceKind
    source_ref: str = Body(
        description="The source's own name for this line. Its identity: running the same "
        "line again replays rather than booking it twice, and two identical lines are two "
        "lines."
    )
    description: str | None = None


class ProposeRequest(BaseModel):
    """What a rule would do, before it exists. Nothing is written."""

    label: str
    precedence: int = Body(description="Lower wins. Two live rules may not share one.")
    account_id: str
    predicates: list[PredicateModel]
    candidates: list[CandidateModel] = []


class ApproveRequest(BaseModel):
    """Approve a rule, an edit to one, or its retirement. A person's own act."""

    label: str
    precedence: int
    account_id: str | None = None
    predicates: list[PredicateModel] = []
    rule_id: str | None = Body(
        default=None, description="The rule this supersedes. Omit to create a new one."
    )
    retire: bool = False


class ApplyRequest(BaseModel):
    candidates: list[CandidateModel]


def _predicates(models: list[PredicateModel]) -> tuple[Predicate, ...]:
    return tuple(
        Predicate(
            position=position,
            field=model.field,
            operator=model.operator,
            value=_value(model),
        )
        for position, model in enumerate(models, start=1)
    )


def _value(model: PredicateModel) -> Any:
    from decimal import Decimal

    return Decimal(model.value) if model.field is Field.AMOUNT else model.value


def _candidates(models: list[CandidateModel]) -> tuple[Candidate, ...]:
    return tuple(
        Candidate(
            payee=model.payee,
            amount=model.amount,
            commodity=model.commodity,
            source_account_id=model.source_account_id,
            transaction_date=model.transaction_date,
            source_kind=model.source_kind,
            source_ref=model.source_ref,
            description=model.description,
        )
        for model in models
    )


@router.post(
    "/entities/{entity_id}/assignment-rules/proposals",
    summary="See what a rule would do before approving it",
    responses=ERRORS,
)
def propose_rule(
    body: ProposeRequest,
    entity_id: Annotated[str, Path()],
    principal: Annotated[Principal, Depends(get_principal)],
    database: Annotated[Database, Depends(get_database)],
) -> dict[str, Any]:
    """`BKP-08`: the operator sees which rule would win, and why, before approving either.

    A read. It writes nothing, so a delegated agent may call it — proposing is not the
    reserved act, approving is.
    """
    proposal = propose(
        database,
        entity_id=entity_id,
        principal=principal,
        label=body.label,
        precedence=body.precedence,
        account_id=body.account_id,
        predicates=_predicates(body.predicates),
        candidates=_candidates(body.candidates),
    )
    return {
        "would_book": [
            {"payee": c.payee, "amount": str(c.amount)} for c, _ in proposal.would_book
        ],
        "would_contend_with": [
            {"payee": c.payee, "amount": str(c.amount), "existing_rule": label}
            for c, label in proposal.would_contend_with
        ],
        "unaffected": len(proposal.unaffected),
    }


@router.post(
    "/entities/{entity_id}/assignment-rules",
    status_code=status.HTTP_201_CREATED,
    summary="Approve a rule, an edit to one, or its retirement",
    responses=ERRORS,
)
def approve_rule(
    body: ApproveRequest,
    entity_id: Annotated[str, Path()],
    principal: Annotated[Principal, Depends(get_principal)],
    database: Annotated[Database, Depends(get_database)],
) -> dict[str, str]:
    """`BKP-09`. A person's own act, and refused for a delegated session (ADR-0042)."""
    return {
        "rule_version_id": approve(
            database,
            entity_id=entity_id,
            principal=principal,
            label=body.label,
            precedence=body.precedence,
            account_id=body.account_id,
            predicates=_predicates(body.predicates),
            rule_id=body.rule_id,
            retire=body.retire,
        )
    }


@router.post(
    "/entities/{entity_id}/assignment-runs",
    summary="Book what the rules resolve, and report what they do not",
    responses=ERRORS,
)
def run_assignment(
    body: ApplyRequest,
    entity_id: Annotated[str, Path()],
    principal: Annotated[Principal, Depends(get_principal)],
    database: Annotated[Database, Depends(get_database)],
    request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> dict[str, Any]:
    """`BKP-06` and `BKP-12`. `unresolved` is the operator's worklist, and nothing in it was
    guessed at or parked in a holding account. An uploaded candidate is drafted even where a
    rule resolves it: a person posts it (ADR-0047)."""
    applied = apply_rules(
        database,
        entity_id=entity_id,
        principal=principal,
        request_id=request_id or f"req-{uuid.uuid4().hex}",
        candidates=_candidates(body.candidates),
    )
    return {
        "booked": [
            {
                "source_ref": b.candidate.source_ref,
                "transaction_id": b.transaction_id,
                "rule": b.rule_label,
                "payee": b.candidate.payee,
            }
            for b in applied.booked
        ],
        "unresolved": [
            {
                "source_ref": b.candidate.source_ref,
                "transaction_id": b.transaction_id,
                "payee": b.candidate.payee,
            }
            for b in applied.unresolved
        ],
    }


@router.get(
    "/entities/{entity_id}/assignment-replay",
    summary="Re-decide every recorded decision against the rule set in force at the time",
    responses=ERRORS,
)
def assignment_replay(
    entity_id: Annotated[str, Path()],
    principal: Annotated[Principal, Depends(get_principal)],
    database: Annotated[Database, Depends(get_database)],
) -> dict[str, Any]:
    """`BKP-06`'s acceptance, as a call rather than only as a test.

    Published because a control an auditor can run is worth more than one only CI runs
    (ADR-0033 § 3). It writes nothing.
    """
    report = replay(database, entity_id=entity_id)
    return {
        "total": report.total,
        "compared": report.compared,
        "reproduced": report.reproduced,
        "rule_set_changed": report.rule_set_changed,
        "semantics_changed": report.semantics_changed,
        "diverged": list(report.diverged),
    }
