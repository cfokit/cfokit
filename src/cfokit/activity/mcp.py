"""The activity module's MCP surface — how a statement read in Claude Desktop reaches the books.

**A second transport, not a second design.** The tools take the shapes the REST routes take and
call the same service functions. The rendering is duplicated rather than imported from `api`,
for the reason the ledger's two adapters do not import each other.

**The model is the bridge, and it is checked twice.** It reads the statement out of a PDF and
sends every figure here; the statement's own balances refuse a misreading before anything is
stored (ADR-0046). It then sends the returned candidates to assignment, and
`account_statement_agreement` compares the books with the statement once they are posted.

**A refusal is returned, not raised**, so the published `code` survives the SDK (ADR-0015).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from mcp.server import MCPServer
from pydantic import BaseModel

from cfokit.activity import Statement, StatementLine, source_ref
from cfokit.activity.errors import StatementInvalid
from cfokit.activity.service import Recorded, record_statement, statement_agreement
from cfokit.ledger.errors import LedgerError
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.principal import Principal

__all__ = ["register"]


class StatementLineArgument(BaseModel):
    transaction_date: date
    payee: str
    amount: str
    description: str | None = None


def _refusals(work: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    try:
        return work()
    except LedgerError as exc:
        return {"ok": False, "code": exc.code, "message": exc.message}


def _decimal(raw: str, where: str) -> Decimal:
    try:
        return Decimal(raw)
    except InvalidOperation as exc:
        raise StatementInvalid(f"{where}: not a decimal amount: {raw!r}") from exc


def _rendered(recorded: Recorded) -> dict[str, Any]:
    stored = recorded.stored
    statement = stored.statement
    follows = recorded.continuity
    return {
        "ok": True,
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


def register(server: MCPServer, database: Database, *, acting: Callable[[], Principal]) -> None:
    """Register the activity tools. `acting` is the ledger's derivation of the caller from the
    bearer token, passed in so there is exactly one place that does it (ADR-0033)."""

    @server.tool(
        name="record_account_statement",
        description=(
            "Record a bank or card statement for one of the entity's accounts. Every figure "
            "is signed as a posting is: positive is a debit, so a deposit is positive and a "
            "card purchase or a card's balance owed is negative. Lines go in printed order. "
            "Refused with statement_does_not_balance unless opening balance plus every line "
            "equals closing balance exactly. Posts nothing: returns each line as a candidate "
            "to pass unchanged to run_assignment. Sending the same statement again replays; "
            "one overlapping a recorded period is refused."
        ),
    )
    def record_tool(
        entity_id: str,
        account_id: str,
        period_start: date,
        period_end: date,
        opening_balance: str,
        closing_balance: str,
        commodity: str,
        lines: list[StatementLineArgument],
    ) -> dict[str, Any]:
        def work() -> dict[str, Any]:
            statement = Statement(
                account_id=account_id,
                period_start=period_start,
                period_end=period_end,
                opening_balance=_decimal(opening_balance, "opening_balance"),
                closing_balance=_decimal(closing_balance, "closing_balance"),
                commodity=commodity,
                lines=tuple(
                    StatementLine(
                        transaction_date=line.transaction_date,
                        payee=line.payee,
                        amount=_decimal(line.amount, f"line {position}"),
                        description=line.description,
                    )
                    for position, line in enumerate(lines, start=1)
                ),
            )
            return _rendered(
                record_statement(
                    database,
                    entity_id=entity_id,
                    principal=acting(),
                    request_id=f"mcp-{uuid.uuid4().hex}",
                    statement=statement,
                )
            )

        return _refusals(work)

    @server.tool(
        name="account_statement_agreement",
        description=(
            "Compare a recorded statement's opening and closing balances with the books' "
            "posted balances for that account over the same period. Drafts are not in the "
            "books, so a statement whose lines are still drafts disagrees by what is waiting "
            "to be posted. Writes nothing."
        ),
    )
    def agreement_tool(entity_id: str, statement_id: str) -> dict[str, Any]:
        def work() -> dict[str, Any]:
            found = statement_agreement(
                database, entity_id=entity_id, principal=acting(), statement_id=statement_id
            )
            return {
                "ok": True,
                "statement_id": found.statement_id,
                "agrees": found.agrees,
                "opening": {
                    "stated": str(found.stated_opening),
                    "books": str(found.books_opening),
                },
                "closing": {
                    "stated": str(found.stated_closing),
                    "books": str(found.books_closing),
                },
            }

        return _refusals(work)
