"""The assignment module's MCP surface.

**A second transport, not a second design.** The tools take the same shapes the REST routes
take and call the same service functions; what differs is only how a caller reaches them.
This module does not import `cfokit.ledger.mcp`'s models for the reason the two ledger
adapters do not import each other — they are siblings, and the duplication is on purpose.

**A refusal is returned, not raised.** The SDK would otherwise stringify away the published
`code` that callers branch on (ADR-0015).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from mcp.server import MCPServer
from pydantic import BaseModel

from cfokit.assignment import Counterpart, CounterpartKind, Field, Operator, Predicate
from cfokit.assignment.candidate import Candidate, SourceKind
from cfokit.assignment.errors import NotACounterpart
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
from cfokit.ledger.errors import LedgerError
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.principal import Principal
from cfokit.ledger.service.read import read_entity
from cfokit.ledger.service.write import WriteContext

__all__ = ["register"]


def _counterpart(found: Counterpart) -> dict[str, str]:
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


class PredicateArgument(BaseModel):
    field: Field
    operator: Operator
    value: str


class CandidateArgument(BaseModel):
    payee: str
    amount: str
    commodity: str
    source_account_id: str
    transaction_date: date
    source_kind: SourceKind
    source_ref: str
    description: str | None = None


def _refused(code: str, message: str) -> dict[str, Any]:
    return {"ok": False, "code": code, "message": message}


def _refusals(work: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    try:
        return work()
    except LedgerError as exc:
        return _refused(exc.code, exc.message)


def _naming(
    database: Database,
    acting: Callable[[], Principal],
    entity_id: str,
    work: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    """Run `work` for one company, and name that company on the result, as the ledger's tools
    do: the agent reads which books an answer came from rather than remembering it."""

    def named() -> dict[str, Any]:
        result = work()
        if not result["ok"]:
            return result
        try:
            found = read_entity(database, entity_id=entity_id, principal=acting())
        except LedgerError:
            # The work is done and may have committed; reporting it refused would be false.
            return result
        return {"ok": True, "company": {"id": found.id, "name": found.name}, **result}

    return _refusals(named)


def _decimal(raw: str) -> Decimal:
    try:
        return Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError(f"not a decimal amount: {raw!r}") from exc


def _predicates(models: list[PredicateArgument]) -> tuple[Predicate, ...]:
    return tuple(
        Predicate(
            position=position,
            field=model.field,
            operator=model.operator,
            value=_decimal(model.value) if model.field is Field.AMOUNT else model.value,
        )
        for position, model in enumerate(models, start=1)
    )


def _candidates(models: list[CandidateArgument]) -> tuple[Candidate, ...]:
    return tuple(
        Candidate(
            payee=model.payee,
            amount=_decimal(model.amount),
            commodity=model.commodity,
            source_account_id=model.source_account_id,
            transaction_date=model.transaction_date,
            source_kind=model.source_kind,
            source_ref=model.source_ref,
            description=model.description,
        )
        for model in models
    )


def register(server: MCPServer, database: Database, *, acting: Callable[[], Principal]) -> None:
    """Register the assignment tools on an existing server.

    `acting` is the ledger's own derivation of the caller from the bearer token, passed in
    rather than reimplemented: a principal is read from the credential and never from an
    argument (ADR-0033), and there must be exactly one place that does it.
    """

    @server.tool(
        name="propose_assignment_rule",
        description=(
            "See what a rule would do before approving it: which of the supplied "
            "transactions it would book, and which an existing rule already claims. Writes "
            "nothing."
        ),
    )
    def propose_tool(
        entity_id: str,
        label: str,
        precedence: int,
        account_id: str,
        predicates: list[PredicateArgument],
        candidates: list[CandidateArgument] | None = None,
    ) -> dict[str, Any]:
        def work() -> dict[str, Any]:
            proposal = propose(
                database,
                entity_id=entity_id,
                principal=acting(),
                label=label,
                precedence=precedence,
                account_id=account_id,
                predicates=_predicates(predicates),
                candidates=_candidates(candidates or []),
            )
            return {
                "ok": True,
                "would_book": [c.payee for c, _ in proposal.would_book],
                "would_contend_with": [
                    {"payee": c.payee, "existing_rule": label}
                    for c, label in proposal.would_contend_with
                ],
                "unaffected": len(proposal.unaffected),
            }

        return _naming(database, acting, entity_id, work)

    @server.tool(
        name="approve_assignment_rule",
        description=(
            "Approve a rule, an edit to one, or its retirement. A person's own act: a "
            "delegated session is refused. Pass rule_id to supersede an existing rule; the "
            "prior version stays, so what it already coded is untouched."
        ),
    )
    def approve_tool(
        entity_id: str,
        label: str,
        precedence: int,
        account_id: str | None = None,
        predicates: list[PredicateArgument] | None = None,
        rule_id: str | None = None,
        retire: bool = False,
    ) -> dict[str, Any]:
        def work() -> dict[str, Any]:
            return {
                "ok": True,
                "rule_version_id": approve(
                    database,
                    entity_id=entity_id,
                    principal=acting(),
                    label=label,
                    precedence=precedence,
                    account_id=account_id,
                    predicates=_predicates(predicates or []),
                    rule_id=rule_id,
                    retire=retire,
                ),
            }

        return _naming(database, acting, entity_id, work)

    @server.tool(
        name="run_assignment",
        description=(
            "Book the supplied transactions. Each is first matched to what the books already "
            "hold: exactly one counterpart — an open invoice it pays, an entry already "
            "recorded, or the other side of a transfer — and it comes back booked with "
            "outcome matched and no rule consulted. Two or more and it is ambiguous; an "
            "uploaded payment of an open invoice is proposed for a person to confirm; both "
            "come back unresolved with their counterparts. Otherwise the approved rules "
            "decide, and anything no rule resolves is returned unresolved and nothing is "
            "posted for it — never guessed, never parked in a holding account. An uploaded "
            "transaction is only ever drafted, even where a rule resolves it: a person posts "
            "it. source_ref is the source's own name for the line; running a line again never "
            "books it twice."
        ),
    )
    def run_tool(entity_id: str, candidates: list[CandidateArgument]) -> dict[str, Any]:
        def work() -> dict[str, Any]:
            applied = apply_rules(
                database,
                entity_id=entity_id,
                principal=acting(),
                request_id=f"mcp-{uuid.uuid4().hex}",
                candidates=_candidates(candidates),
            )
            return {
                "ok": True,
                "booked": [_booked(b) for b in applied.booked],
                "unresolved": [_booked(b) for b in applied.unresolved],
            }

        return _naming(database, acting, entity_id, work)

    @server.tool(
        name="answer_unresolved_transaction",
        description=(
            "Answer a line's question with what the person said it is: counterpart_kind and "
            "counterpart_id naming one record — an obligation, a transaction, or for a "
            "transfer the other line's decision_id — or none=true for none of those an "
            "ambiguous or proposed line was asked about, after which the rules decide. The "
            "person's own act: a delegated session is refused with not_a_person, so ask the "
            "person and have them answer. Naming an open obligation posts its settlement. "
            "Requires an idempotency key."
        ),
    )
    def answer_tool(
        entity_id: str,
        source_ref: str,
        idempotency_key: str,
        counterpart_kind: CounterpartKind | None = None,
        counterpart_id: str | None = None,
        none: bool = False,
    ) -> dict[str, Any]:
        def work() -> dict[str, Any]:
            named = counterpart_kind is not None and counterpart_id is not None
            if named == none:
                raise NotACounterpart(
                    "name one counterpart with counterpart_kind and counterpart_id, or answer "
                    "none=true — exactly one of the two"
                )
            answered = answer_question(
                database,
                WriteContext(
                    entity_id=entity_id,
                    principal=acting(),
                    request_id=f"mcp-{uuid.uuid4().hex}",
                    idempotency_key=idempotency_key,
                ),
                source_ref=source_ref,
                counterpart=(
                    (counterpart_kind, counterpart_id)
                    if counterpart_kind is not None and counterpart_id is not None
                    else None
                ),
            )
            return {
                "ok": True,
                "decision_id": answered.decision_id,
                "outcome": str(answered.outcome),
                "transaction_id": answered.transaction_id,
                "replayed": answered.replayed,
            }

        return _naming(database, acting, entity_id, work)

    @server.tool(
        name="replay_assignments",
        description=(
            "Re-decide every recorded assignment — the search of the books, then the rules — "
            "as the books and the rule set stood when it was taken. Reports how many "
            "reproduced, how many are not comparable because a rule or the books changed "
            "since, and how many were a person's choice. Writes nothing."
        ),
    )
    def replay_tool(entity_id: str) -> dict[str, Any]:
        def work() -> dict[str, Any]:
            report = replay(database, entity_id=entity_id, principal=acting())
            return {
                "ok": True,
                "total": report.total,
                "compared": report.compared,
                "reproduced": report.reproduced,
                "rule_set_changed": report.rule_set_changed,
                "semantics_changed": report.semantics_changed,
                "books_changed": report.books_changed,
                "chosen": report.chosen,
                "diverged": list(report.diverged),
            }

        return _naming(database, acting, entity_id, work)

    @server.tool(
        name="unresolved_transactions",
        description=(
            "Every line waiting on the person, oldest first: what to ask them about. outcome "
            "says what is asked. unmatched: no rule covers it — answered by proposing a rule, "
            "the person approving it, and running assignment again with the same source_ref, "
            "or by the person naming the record it is. ambiguous: every record it could be is "
            "in counterparts. proposed: an uploaded payment of the open obligation in "
            "counterparts, waiting for the person to confirm. The person answers those with "
            "answer_unresolved_transaction. Writes nothing."
        ),
    )
    def unresolved_tool(entity_id: str) -> dict[str, Any]:
        def work() -> dict[str, Any]:
            return {
                "ok": True,
                "unresolved": [
                    _question(q)
                    for q in open_questions(database, entity_id=entity_id, principal=acting())
                ],
            }

        return _naming(database, acting, entity_id, work)
