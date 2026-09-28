"""The activity module's REST surface: a router the module owns, included by `cfokit.server`.

The ledger's adapter cannot mount it — "the ledger depends on no module" is an `import-linter`
contract (ADR-0022). Amounts are strings, as on every other surface, because a JSON number
cannot carry the scale it was written at.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Path, status
from pydantic import BaseModel
from pydantic import Field as Body

from cfokit.activity import Statement, StatementLine, source_ref
from cfokit.activity.service import Recorded, record_statement, statement_agreement
from cfokit.ledger.api import ERRORS, get_database, get_principal
from cfokit.ledger.api.models import Money
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.principal import Principal

router = APIRouter(tags=["activity"])


class StatementLineModel(BaseModel):
    """One line, as printed."""

    transaction_date: date
    payee: str
    amount: Money = Body(description="Signed as a posting is signed: positive is a debit.")
    description: str | None = None


class StatementModel(BaseModel):
    """An account statement. Every figure signed as a posting is signed: positive is a debit,
    so a card's balance owed is negative."""

    account_id: str = Body(description="The entity's own account the statement is for.")
    period_start: date
    period_end: date = Body(description="Inclusive, as the statement prints it.")
    opening_balance: Money
    closing_balance: Money
    commodity: str
    lines: list[StatementLineModel] = Body(description="In the order they were printed.")


def _rendered(recorded: Recorded) -> dict[str, Any]:
    """The statement, and each line as the candidate assignment takes."""
    stored = recorded.stored
    statement = stored.statement
    follows = recorded.continuity
    return {
        "statement_id": stored.id,
        "replayed": recorded.replayed,
        "lines": len(statement.lines),
        "continuity": (
            None
            if follows is None
            else {
                "previous_statement_id": follows.previous_statement_id,
                "contiguous": follows.contiguous,
                "balance_continues": follows.balance_continues,
            }
        ),
        "candidates": [
            {
                "payee": line.payee,
                "amount": str(line.amount),
                "commodity": statement.commodity,
                "source_account_id": statement.account_id,
                "transaction_date": line.transaction_date.isoformat(),
                "source_kind": "upload",
                "source_ref": source_ref(stored.id, position),
                "description": line.description,
            }
            for position, line in enumerate(statement.lines, start=1)
        ],
    }


@router.post(
    "/entities/{entity_id}/account-statements",
    status_code=status.HTTP_201_CREATED,
    summary="Record an account statement, refused unless its lines account for its balances",
    responses=ERRORS,
)
def record_account_statement(
    body: StatementModel,
    entity_id: Annotated[str, Path()],
    principal: Annotated[Principal, Depends(get_principal)],
    database: Annotated[Database, Depends(get_database)],
    request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> dict[str, Any]:
    """`BKP-03`. Posts nothing and codes nothing: `candidates` is what to send to assignment,
    each carrying the reference its transaction will record (`BKP-19`). The same statement
    sent again replays; a different one overlapping it is refused."""
    recorded = record_statement(
        database,
        entity_id=entity_id,
        principal=principal,
        request_id=request_id or f"req-{uuid.uuid4().hex}",
        statement=Statement(
            account_id=body.account_id,
            period_start=body.period_start,
            period_end=body.period_end,
            opening_balance=body.opening_balance,
            closing_balance=body.closing_balance,
            commodity=body.commodity,
            lines=tuple(
                StatementLine(
                    transaction_date=line.transaction_date,
                    payee=line.payee,
                    amount=line.amount,
                    description=line.description,
                )
                for line in body.lines
            ),
        ),
    )
    return _rendered(recorded)


@router.get(
    "/entities/{entity_id}/account-statements/{statement_id}/agreement",
    summary="Whether the books' posted balances match the statement's",
    responses=ERRORS,
)
def account_statement_agreement(
    entity_id: Annotated[str, Path()],
    statement_id: Annotated[str, Path()],
    principal: Annotated[Principal, Depends(get_principal)],
    database: Annotated[Database, Depends(get_database)],
) -> dict[str, Any]:
    """Two figures and whether they agree, for the opening and the closing balance. Drafts are
    not in the books, so a statement whose lines await posting disagrees by what is waiting."""
    found = statement_agreement(
        database, entity_id=entity_id, principal=principal, statement_id=statement_id
    )
    return {
        "statement_id": found.statement_id,
        "agrees": found.agrees,
        "opening": {"stated": str(found.stated_opening), "books": str(found.books_opening)},
        "closing": {"stated": str(found.stated_closing), "books": str(found.books_closing)},
    }
