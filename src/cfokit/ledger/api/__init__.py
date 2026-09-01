"""REST adapter — one of two protocol adapters over one service layer (ADR-0009).

A published interface with stability obligations; the generated OpenAPI document is
committed and a diff means a contract change requiring review (ADR-0015).

**Handlers are synchronous `def`, never `async def`** (ADR-0024). FastAPI is used for its
OpenAPI generation and validation; the event loop lives in the server, not in this code.
`scripts/check_async.py` fails the build if that slips.

Adapters stay thin. Logic here is a defect, because it is then present in one protocol and
absent from the other (ADR-0008). Every handler below translates a request into one service
call and back, and does nothing else.

Dependencies are module-level functions reading `app.state`, rather than closures over
`create_app`. That is not a style preference: with `from __future__ import annotations` the
annotations are strings, and pydantic can only resolve them against module globals — a
dependency defined inside `create_app` produces an unresolvable forward reference and the
OpenAPI document fails to generate.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, Path, Request, Response, status
from fastapi.responses import JSONResponse

from cfokit.ledger.api.auth import Authenticator, DenyAll
from cfokit.ledger.api.models import (
    ErrorResponse,
    PostingModel,
    RecordTransactionRequest,
    TransactionResponse,
    WriteResponse,
)
from cfokit.ledger.api.problems import status_for
from cfokit.ledger.config import Settings
from cfokit.ledger.engine import Entry, Posting
from cfokit.ledger.errors import LedgerError, TransactionNotFound
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.principal import Principal
from cfokit.ledger.service.readiness import check_readiness
from cfokit.ledger.service.write import (
    WriteContext,
    post_transaction,
    record_transaction,
    reverse_transaction,
)

__all__ = ["create_app"]

# Documented on every operation so the published OpenAPI says what a caller can expect, and
# so a new error code shows up as a contract diff (ADR-0015).
ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}


def get_database(request: Request) -> Database:
    return request.app.state.database  # type: ignore[no-any-return]


def get_principal(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> Principal:
    """The acting principal, from the credential and never from the body (ADR-0033)."""
    authenticator: Authenticator = request.app.state.authenticator
    return authenticator.principal_for(authorization)


def get_write_context(
    entity_id: Annotated[str, Path()],
    acting: Annotated[Principal, Depends(get_principal)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")] = "",
    request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> WriteContext:
    """The four things every write carries (ADR-0011, ADR-0029, ADR-0033).

    `Idempotency-Key` is required, and its absence is refused by the service rather than here,
    so the MCP surface produces the same refusal with the same code.
    """
    return WriteContext(
        entity_id=entity_id,
        principal=acting,
        request_id=request_id or f"req-{uuid.uuid4().hex}",
        idempotency_key=idempotency_key,
    )


def create_app(settings: Settings, authenticator: Authenticator | None = None) -> FastAPI:
    """Build the REST application.

    Takes settings as an argument rather than reading the environment, so the app is
    constructible in a test without one (ADR-0004 keeps `config` the only reader).

    `authenticator` defaults to denying everything, so a deployment that has not wired
    authentication returns 401 rather than booking for an anonymous caller — see `auth.py`.
    """
    app = FastAPI(
        title="CFOKit Ledger",
        version="0.0.0",
        summary="Multi-tenant double-entry accounting engine.",
    )
    app.state.authenticator = DenyAll() if authenticator is None else authenticator
    app.state.database = Database(settings.database_url)

    @app.exception_handler(LedgerError)
    def ledger_error(_request: Request, exc: LedgerError) -> JSONResponse:
        """Every error leaves through here carrying its stable `code` (ADR-0015).

        The message is not contractual and may be reworded; the code is what callers branch
        on, and it is identical on the MCP surface for the same condition.
        """
        return JSONResponse(
            status_code=status_for(exc), content={"code": exc.code, "message": exc.message}
        )

    @app.get("/healthz", tags=["operations"], summary="Liveness")
    def healthz() -> dict[str, str]:
        """Liveness only. Deliberately touches nothing.

        If this checked the database, a database blip would restart every healthy
        container — turning a recoverable outage into a rolling one.
        """
        return {"status": "ok"}

    @app.get("/readyz", tags=["operations"], summary="Readiness")
    def readyz(response: Response) -> dict[str, object]:
        """Database reachable, and migrations current.

        Returns 503 when not ready, so a rollout stops rather than serving traffic
        against a schema older than the code.
        """
        result = check_readiness(settings.database_url)
        if not result.ready:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "ready" if result.ready else "not_ready",
            "database_reachable": result.database_reachable,
            "migrations_current": result.migrations_current,
            "detail": result.detail,
        }

    @app.post(
        "/entities/{entity_id}/transactions",
        tags=["transactions"],
        summary="Record a transaction",
        status_code=status.HTTP_201_CREATED,
        responses=ERRORS,
    )
    def record(
        body: RecordTransactionRequest,
        context: Annotated[WriteContext, Depends(get_write_context)],
        database: Annotated[Database, Depends(get_database)],
    ) -> WriteResponse:
        """Record a transaction as a draft, or post it straight through.

        Requires an `Idempotency-Key` header. Replaying one returns the original result and
        books nothing further (ADR-0029).
        """
        entry = Entry(
            transaction_date=body.transaction_date,
            postings=tuple(
                Posting(account_id=p.account_id, amount=p.amount, commodity=p.commodity)
                for p in body.postings
            ),
            description=body.description,
        )
        written = record_transaction(database, context, entry=entry, post=body.post)
        return WriteResponse(
            transaction_id=written.transaction_id,
            status=written.status,
            replayed=written.replayed,
        )

    @app.post(
        "/entities/{entity_id}/transactions/{transaction_id}/post",
        tags=["transactions"],
        summary="Post a draft",
        responses=ERRORS,
    )
    def post_draft(
        transaction_id: Annotated[str, Path()],
        context: Annotated[WriteContext, Depends(get_write_context)],
        database: Annotated[Database, Depends(get_database)],
    ) -> WriteResponse:
        """Move a draft to posted. The point of no return (`LED-07`)."""
        written = post_transaction(database, context, transaction_id=transaction_id)
        return WriteResponse(
            transaction_id=written.transaction_id,
            status=written.status,
            replayed=written.replayed,
        )

    @app.post(
        "/entities/{entity_id}/transactions/{transaction_id}/reversal",
        tags=["transactions"],
        summary="Reverse a posted transaction",
        status_code=status.HTTP_201_CREATED,
        responses=ERRORS,
    )
    def reverse(
        transaction_id: Annotated[str, Path()],
        context: Annotated[WriteContext, Depends(get_write_context)],
        database: Annotated[Database, Depends(get_database)],
        description: str | None = None,
    ) -> WriteResponse:
        """Correct a posted transaction by reversing it, leaving both visible (`LED-08`).

        There is deliberately no endpoint that edits or deletes a posted transaction. The
        schema refuses both, and offering the route would be offering a way to find out.

        `original_period_closed` is hardcoded false because period close does not exist yet
        (ADR-0030). When it does, this is where the reopen question is asked.
        """
        written = reverse_transaction(
            database,
            context,
            transaction_id=transaction_id,
            original_period_closed=False,
            current_period_date=date.today(),  # noqa: DTZ011
            description=description,
        )
        return WriteResponse(
            transaction_id=written.transaction_id,
            status=written.status,
            replayed=written.replayed,
        )

    @app.get(
        "/entities/{entity_id}/transactions/{transaction_id}",
        tags=["transactions"],
        summary="Read a transaction",
        responses=ERRORS,
    )
    def read(
        entity_id: Annotated[str, Path()],
        transaction_id: Annotated[str, Path()],
        database: Annotated[Database, Depends(get_database)],
        _acting: Annotated[Principal, Depends(get_principal)],
    ) -> TransactionResponse:
        """Read a transaction and its postings.

        A transaction belonging to another entity is reported as not found rather than as
        forbidden: row-level security makes absent and invisible the same answer, and
        distinguishing them would leak the other entity's existence (`NFR-04`).
        """
        with database.entity_write(entity_id) as write:
            stored = write.load_transaction(transaction_id)
        if stored is None:
            raise TransactionNotFound(f"no transaction {transaction_id}")
        return TransactionResponse(
            id=stored.id,
            status=stored.status,
            transaction_date=stored.transaction_date,
            description=stored.description,
            reverses_id=stored.reverses_id,
            entry_kind=stored.entry_kind,
            actor_principal_id=stored.actor_principal_id,
            actor_class=stored.actor_class,
            acting_for_principal_id=stored.acting_for_principal_id,
            postings=[
                PostingModel(account_id=p.account_id, amount=p.amount, commodity=p.commodity)
                for p in stored.postings
            ],
        )

    return app
