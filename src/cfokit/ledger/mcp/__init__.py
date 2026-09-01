"""MCP adapter — the second protocol adapter, calling the service layer in-process
rather than looping back through HTTP (ADR-0009).

Tool descriptions are a published interface; the committed descriptions and the
generated ones must match (ADR-0015).

**This module may use async; nothing it calls may** (ADR-0024). The MCP SDK is async and is
the sole reason async exists in this codebase. The tools below are ordinary synchronous
functions calling synchronous service code, which is what the record permits: this adapter
owns its event loop and may block it, and no coroutine crosses into `service`.

**It does not import `cfokit.ledger.api`.** The two adapters are siblings and `import-linter`
forbids either importing the other, so the wire models here are this module's own. That is
duplication on purpose — a shared model would couple two published contracts that are allowed
to evolve separately.

**A refusal is returned, not raised**, and this is a deliberate departure from the idiomatic
MCP shape. ADR-0015 makes the error `code` a published contract that callers branch on. The
SDK wraps a raised exception in `ToolError` and renders it as `str(exception)` behind a
prefix, so the only way a caller could recover the code would be to substring-parse a message
the SDK formats — and a contract that requires that is not a contract.

So every tool returns a result carrying `ok`. On success the payload; on a ledger refusal
`{"ok": false, "code": ..., "message": ...}`, with the same code the REST surface returns for
the same condition (ADR-0009). The cost is that a client checking only MCP's `isError` sees a
refusal as a success, which the tool descriptions and the server instructions both state.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from mcp.server import MCPServer
from pydantic import BaseModel, Field

from cfokit.ledger.config import Settings
from cfokit.ledger.engine import Entry, Posting
from cfokit.ledger.errors import LedgerError
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.principal import Principal
from cfokit.ledger.service.read import read_transaction
from cfokit.ledger.service.write import (
    WriteContext,
    post_transaction,
    record_transaction,
    reverse_transaction,
)

__all__ = ["LedgerToolError", "create_server", "refused"]


class LedgerToolError(Exception):
    """A refusal raised inside a tool, before it is turned into a result.

    Never escapes a tool: `refusals()` converts it. It exists so the code that detects a
    refusal does not also have to know the result shape.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(json.dumps({"code": code, "message": message}))
        self.code = code
        self.detail = message


def refused(code: str, message: str) -> dict[str, Any]:
    """The refusal shape every tool returns. `ok` is the discriminator."""
    return {"ok": False, "code": code, "message": message}


class PostingArgument(BaseModel):
    """One side of a transaction.

    `amount` is a string for the same reason it is on REST: a JSON number cannot carry the
    scale the amount was written at, and `100.00` would arrive as `100`.
    """

    account_id: str = Field(description="The account this posting hits.")
    amount: str = Field(description="Signed decimal string. Positive debits the account.")
    commodity: str = Field(description="The unit the amount is denominated in, e.g. USD.")


def _to_posting(argument: PostingArgument) -> Posting:
    try:
        amount = Decimal(argument.amount)
    except InvalidOperation as exc:
        raise LedgerToolError(
            "invalid_amount", f"not a decimal amount: {argument.amount!r}"
        ) from exc
    return Posting(account_id=argument.account_id, amount=amount, commodity=argument.commodity)


def _refusals(work: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    """Run `work`, converting any ledger refusal into the structured refusal shape."""
    try:
        return work()
    except LedgerToolError as exc:
        return refused(exc.code, exc.detail)
    except LedgerError as exc:
        return refused(exc.code, exc.message)


def create_server(settings: Settings, principal: Principal | None = None) -> MCPServer:
    """Build the MCP server.

    `principal` is injected rather than derived, and defaults to `None`, which refuses every
    tool call. Authentication is not built (see `api/auth.py`), and an MCP surface that booked
    transactions for an unidentified caller would be worse than one that refuses: `LED-20`
    requires every transaction to record what wrote it, and there would be nothing true to
    record.
    """
    database = Database(settings.database_url)
    server = MCPServer(
        name="cfokit-ledger",
        instructions=(
            "The double-entry ledger. Every write names the entity it acts on and carries an "
            "idempotency key; replaying a key returns the original result rather than booking "
            "again. Amounts are decimal strings. A posted transaction is never edited — "
            "correct it with reverse_transaction. Every tool returns an 'ok' field: false "
            "means the ledger refused the operation and 'code' says why."
        ),
    )

    def acting() -> Principal:
        if principal is None:
            raise LedgerToolError(
                "not_authenticated", "no principal is configured; this server cannot write"
            )
        return principal

    def context(entity_id: str, idempotency_key: str) -> WriteContext:
        return WriteContext(
            entity_id=entity_id,
            principal=acting(),
            request_id=f"mcp-{uuid.uuid4().hex}",
            idempotency_key=idempotency_key,
        )

    @server.tool(
        name="record_transaction",
        description=(
            "Record a transaction in an entity's books, as a draft or posted straight "
            "through. Postings must sum to zero per commodity to post. Requires an "
            "idempotency key; replaying one books nothing further."
        ),
    )
    def record(
        entity_id: str,
        transaction_date: date,
        postings: list[PostingArgument],
        idempotency_key: str,
        description: str | None = None,
        post: bool = False,
    ) -> dict[str, Any]:
        def work() -> dict[str, Any]:
            entry = Entry(
                transaction_date=transaction_date,
                postings=tuple(_to_posting(p) for p in postings),
                description=description,
            )
            written = record_transaction(
                database, context(entity_id, idempotency_key), entry=entry, post=post
            )
            return {
                "ok": True,
                "transaction_id": written.transaction_id,
                "status": written.status,
                "replayed": written.replayed,
            }

        return _refusals(work)

    @server.tool(
        name="post_transaction",
        description=(
            "Post a draft transaction. Posting is the point of no return: a posted "
            "transaction is never edited or deleted, only reversed."
        ),
    )
    def post_draft(entity_id: str, transaction_id: str, idempotency_key: str) -> dict[str, Any]:
        def work() -> dict[str, Any]:
            written = post_transaction(
                database, context(entity_id, idempotency_key), transaction_id=transaction_id
            )
            return {
                "ok": True,
                "transaction_id": written.transaction_id,
                "status": written.status,
                "replayed": written.replayed,
            }

        return _refusals(work)

    @server.tool(
        name="reverse_transaction",
        description=(
            "Correct a posted transaction by reversing it. Both the original and the "
            "reversal remain visible; nothing is edited or removed."
        ),
    )
    def reverse(
        entity_id: str,
        transaction_id: str,
        idempotency_key: str,
        description: str | None = None,
    ) -> dict[str, Any]:
        def work() -> dict[str, Any]:
            written = reverse_transaction(
                database,
                context(entity_id, idempotency_key),
                transaction_id=transaction_id,
                original_period_closed=False,
                current_period_date=date.today(),  # noqa: DTZ011
                description=description,
            )
            return {
                "ok": True,
                "transaction_id": written.transaction_id,
                "status": written.status,
                "replayed": written.replayed,
            }

        return _refusals(work)

    @server.tool(
        name="read_transaction",
        description="Read a transaction and its postings, including what wrote it.",
    )
    def read(entity_id: str, transaction_id: str) -> dict[str, Any]:
        def work() -> dict[str, Any]:
            stored = read_transaction(
                database,
                entity_id=entity_id,
                principal=acting(),
                transaction_id=transaction_id,
            )
            return {
                "ok": True,
                "id": stored.id,
                "status": stored.status,
                "transaction_date": stored.transaction_date.isoformat(),
                "description": stored.description,
                "reverses_id": stored.reverses_id,
                "entry_kind": stored.entry_kind,
                "actor_principal_id": stored.actor_principal_id,
                "actor_class": stored.actor_class,
                "acting_for_principal_id": stored.acting_for_principal_id,
                "postings": [
                    {
                        "account_id": p.account_id,
                        "amount": str(p.amount),
                        "commodity": p.commodity,
                    }
                    for p in stored.postings
                ],
            }

        return _refusals(work)

    return server
