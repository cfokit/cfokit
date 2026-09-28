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

from cfokit.assignment import Field, Operator, Predicate
from cfokit.assignment.candidate import Candidate, SourceKind
from cfokit.assignment.service import apply_rules, approve, propose, replay
from cfokit.ledger.errors import LedgerError
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.principal import Principal

__all__ = ["register"]


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

        return _refusals(work)

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

        return _refusals(work)

    @server.tool(
        name="run_assignment",
        description=(
            "Book the supplied transactions against the approved rules. Anything no rule "
            "resolves is returned unresolved and nothing is posted for it — never guessed, "
            "never parked in a holding account. An uploaded transaction is only ever "
            "drafted, even where a rule resolves it: a person posts it. source_ref is the "
            "source's own name for the line; running a line again never books it twice."
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
                "booked": [
                    {
                        "source_ref": b.candidate.source_ref,
                        "transaction_id": b.transaction_id,
                        "rule": b.rule_label,
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

        return _refusals(work)

    @server.tool(
        name="replay_assignments",
        description=(
            "Re-decide every recorded assignment against the rule set that was in force "
            "when it was taken. Reports how many reproduced, and how many are not "
            "comparable because a rule changed since. Writes nothing."
        ),
    )
    def replay_tool(entity_id: str) -> dict[str, Any]:
        def work() -> dict[str, Any]:
            report = replay(database, entity_id=entity_id)
            return {
                "ok": True,
                "total": report.total,
                "compared": report.compared,
                "reproduced": report.reproduced,
                "rule_set_changed": report.rule_set_changed,
                "semantics_changed": report.semantics_changed,
                "diverged": list(report.diverged),
            }

        return _refusals(work)
