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

from cfokit.ledger.api.models import (
    CreateEntityRequest,
    EntityCreatedResponse,
    ErrorResponse,
    GrantResponse,
    GrantRoleRequest,
    PostingModel,
    RecordTransactionRequest,
    TransactionResponse,
    WriteResponse,
)
from cfokit.ledger.api.problems import status_for
from cfokit.ledger.config import Settings
from cfokit.ledger.engine import Entry, Posting
from cfokit.ledger.errors import LedgerError
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.administration import create_entity, grant_role, revoke_grant
from cfokit.ledger.service.authentication import Authenticator, TokenAuthenticator
from cfokit.ledger.service.principal import Principal
from cfokit.ledger.service.read import read_transaction
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
    403: {"model": ErrorResponse},
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

    `authenticator` defaults to validating bearer tokens against the configured issuer
    (ADR-0019). It is injectable so a test can supply a principal without an issuer, never so
    a caller can.
    """
    app = FastAPI(
        title="CFOKit Ledger",
        version="0.0.0",
        summary="Multi-tenant double-entry accounting engine.",
    )
    app.state.authenticator = (
        TokenAuthenticator(settings.auth_issuer_url, settings.auth_audience)
        if authenticator is None
        else authenticator
    )
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

    # -----------------------------------------------------------------------------------
    # Administration. `IAM-03` makes granting, revoking and changing a role assignment
    # administrative capabilities "available to no other role", and `IAM-13` requires every
    # one of them recorded with who made it and when — which the service layer does.
    #
    # There is deliberately no route that establishes a deployment administrator. That act
    # requires no prior role, so it is unreachable from the network by construction rather
    # than guarded: `python -m cfokit.ledger.bootstrap` (ADR-0038).
    # -----------------------------------------------------------------------------------

    @app.post(
        "/entities",
        tags=["administration"],
        summary="Create an entity and assign its first administrator",
        status_code=status.HTTP_201_CREATED,
        responses=ERRORS,
    )
    def create(
        body: CreateEntityRequest,
        acting: Annotated[Principal, Depends(get_principal)],
        database: Annotated[Database, Depends(get_database)],
        request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
    ) -> EntityCreatedResponse:
        """Requires a deployment-scoped administrative role (`IAM-18`, ADR-0038).

        The entity and its first administrator are written in one transaction, or neither is
        (`IAM-05`).
        """
        created = create_entity(
            database,
            principal=acting,
            request_id=request_id or f"req-{uuid.uuid4().hex}",
            slug=body.slug,
            name=body.name,
            accounting_basis=body.accounting_basis,
            fiscal_year_end_month=body.fiscal_year_end_month,
            fiscal_year_end_day=body.fiscal_year_end_day,
            functional_currency=body.functional_currency,
            time_zone=body.time_zone,
            administrator=body.administrator,
        )
        return EntityCreatedResponse(
            entity_id=created.entity_id,
            administrator_grant_id=created.administrator_grant_id,
        )

    @app.post(
        "/entities/{entity_id}/grants",
        tags=["administration"],
        summary="Grant a role in this entity",
        status_code=status.HTTP_201_CREATED,
        responses=ERRORS,
    )
    def grant(
        entity_id: Annotated[str, Path()],
        body: GrantRoleRequest,
        acting: Annotated[Principal, Depends(get_principal)],
        database: Annotated[Database, Depends(get_database)],
        request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
    ) -> GrantResponse:
        grant_id = grant_role(
            database,
            entity_id=entity_id,
            principal=acting,
            request_id=request_id or f"req-{uuid.uuid4().hex}",
            to_principal=body.principal_id,
            role=body.role,
            lapses_at=body.lapses_at,
        )
        return GrantResponse(grant_id=grant_id)

    @app.delete(
        "/entities/{entity_id}/grants/{grant_id}",
        tags=["administration"],
        summary="Revoke a grant",
        status_code=status.HTTP_204_NO_CONTENT,
        responses=ERRORS,
    )
    def revoke(
        entity_id: Annotated[str, Path()],
        grant_id: Annotated[str, Path()],
        acting: Annotated[Principal, Depends(get_principal)],
        database: Annotated[Database, Depends(get_database)],
        request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
    ) -> None:
        """Revoking is `DELETE` on the route and an update in the schema.

        The grant row is never removed — `IAM-14` has to be able to report what was held before
        it ended — so the verb describes the effect on access rather than on storage.
        """
        revoke_grant(
            database,
            entity_id=entity_id,
            principal=acting,
            request_id=request_id or f"req-{uuid.uuid4().hex}",
            grant_id=grant_id,
        )

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
        acting: Annotated[Principal, Depends(get_principal)],
    ) -> TransactionResponse:
        """Read a transaction and its postings.

        A transaction belonging to another entity is reported as not found rather than as
        forbidden: row-level security makes absent and invisible the same answer, and
        distinguishing them would leak the other entity's existence (`NFR-04`).
        """
        stored = read_transaction(
            database, entity_id=entity_id, principal=acting, transaction_id=transaction_id
        )
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
