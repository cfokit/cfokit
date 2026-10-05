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

from cfokit.assignment import Counterpart, CounterpartKind, Field, Operator, Predicate
from cfokit.assignment.candidate import Candidate, SourceKind
from cfokit.assignment.repository import StoredDecision
from cfokit.assignment.service import (
    Booked,
    answer_question,
    apply_rules,
    approve,
    open_questions,
    propose,
    replay,
)
from cfokit.ledger.api import ERRORS, get_database, get_principal, get_write_context
from cfokit.ledger.api.models import Money
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.principal import Principal
from cfokit.ledger.service.write import WriteContext

router = APIRouter(tags=["assignment"])


def _counterpart(found: Counterpart) -> dict[str, str]:
    """A counterpart as a person is shown it: what kind of record, which, and its figures."""
    return {
        "kind": str(found.kind),
        "id": found.id,
        "account_id": found.account_id,
        "amount": str(found.amount),
        "commodity": found.commodity,
        "date": found.on.isoformat(),
    }


def _booked(booked: Booked) -> dict[str, Any]:
    return {
        "source_ref": booked.candidate.source_ref,
        "transaction_id": booked.transaction_id,
        "decision_id": booked.decision_id,
        "outcome": str(booked.outcome),
        "rule": booked.rule_label,
        "payee": booked.candidate.payee,
        "counterparts": [_counterpart(c) for c in booked.counterparts],
    }


def _question(question: StoredDecision) -> dict[str, Any]:
    line = question.candidate
    return {
        "source_ref": line.source_ref,
        "transaction_id": question.transaction_id,
        "decision_id": question.id,
        "outcome": str(question.outcome),
        "payee": line.payee,
        "description": line.description,
        "amount": str(line.amount),
        "commodity": line.commodity,
        "source_account_id": line.source_account_id,
        "transaction_date": line.transaction_date.isoformat(),
        "source_kind": str(line.source_kind),
        "counterparts": [_counterpart(c) for c in question.counterparts],
    }


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


class CounterpartChoice(BaseModel):
    """A record the books hold, named by kind and id, as a question lists it."""

    kind: CounterpartKind
    id: str = Body(
        description="An obligation's id, a transaction's id, or — for the other side of a "
        "transfer — the other line's decision_id."
    )


class AnswerRequest(BaseModel):
    """A person's answer to a line's question. Their own act (ADR-0042)."""

    source_ref: str = Body(description="The line the question is about.")
    counterpart: CounterpartChoice | None = Body(
        description="The record this line is. Null for none of those it was asked about, "
        "after which the rules decide it; only an ambiguous or proposed line has those."
    )


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
    summary="Match each line to the books, book what the rules resolve, and report the rest",
    responses=ERRORS,
)
def run_assignment(
    body: ApplyRequest,
    entity_id: Annotated[str, Path()],
    principal: Annotated[Principal, Depends(get_principal)],
    database: Annotated[Database, Depends(get_database)],
    request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> dict[str, Any]:
    """`BKP-06`, `BKP-12`, `BKP-13` and `BKP-14`. Each line is first searched against the books:
    one counterpart and it is `matched` — an open invoice settled, an entry already recorded,
    or the other side of a transfer — with no rule consulted. Two or more and it is
    `ambiguous`, an uploaded payment of an open invoice is `proposed`, and both are in
    `unresolved` with their `counterparts`, as is a line no rule resolves. Nothing there was
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
        "booked": [_booked(b) for b in applied.booked],
        "unresolved": [_booked(b) for b in applied.unresolved],
    }


@router.post(
    "/entities/{entity_id}/unresolved-transactions/answers",
    status_code=status.HTTP_201_CREATED,
    summary="Answer a line's question: the record it is, or none of those it was asked about",
    responses=ERRORS,
)
def answer_unresolved_transaction(
    body: AnswerRequest,
    context: Annotated[WriteContext, Depends(get_write_context)],
    database: Annotated[Database, Depends(get_database)],
) -> dict[str, Any]:
    """A person's own act, refused for a delegated session with `not_a_person` (ADR-0042,
    ADR-0059 § 4). Naming an open obligation posts its settlement; naming a recorded
    transaction writes nothing new; naming another line's question pairs them as a transfer.
    Held to the same exact facts as the search, but not to its dates. Requires an
    `Idempotency-Key` header."""
    answered = answer_question(
        database,
        context,
        source_ref=body.source_ref,
        counterpart=(
            None if body.counterpart is None else (body.counterpart.kind, body.counterpart.id)
        ),
    )
    return {
        "decision_id": answered.decision_id,
        "outcome": str(answered.outcome),
        "transaction_id": answered.transaction_id,
        "replayed": answered.replayed,
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
    report = replay(database, entity_id=entity_id, principal=principal)
    return {
        "total": report.total,
        "compared": report.compared,
        "reproduced": report.reproduced,
        "rule_set_changed": report.rule_set_changed,
        "semantics_changed": report.semantics_changed,
        "books_changed": report.books_changed,
        "chosen": report.chosen,
        "diverged": list(report.diverged),
    }


@router.get(
    "/entities/{entity_id}/unresolved-transactions",
    summary="Every line waiting on a person, with what it is asked about",
    responses=ERRORS,
)
def unresolved_transactions(
    entity_id: Annotated[str, Path()],
    principal: Annotated[Principal, Depends(get_principal)],
    database: Annotated[Database, Depends(get_database)],
) -> dict[str, Any]:
    """`BKP-12`'s worklist, in the order the activity happened. `outcome` says what is asked:
    `unmatched`, no rule covers the line — answered by approving one and running assignment
    again (`BKP-09`), or by naming the record it is; `ambiguous`, every record it could be is in
    `counterparts`; `proposed`, an uploaded payment of the open obligation in `counterparts`,
    waiting for a person to confirm. `source_ref` is what its `unresolved_transaction`
    notification is about."""
    return {
        "unresolved": [
            _question(q)
            for q in open_questions(database, entity_id=entity_id, principal=principal)
        ]
    }
