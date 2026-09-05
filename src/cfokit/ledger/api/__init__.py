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
from collections.abc import Iterable
from datetime import date, datetime
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, Path, Query, Request, Response, status
from fastapi.responses import JSONResponse

from cfokit.ledger.api.models import (
    AccountComparisonModel,
    AccountCreatedResponse,
    AccountDetailResponse,
    AccountEntryModel,
    BalanceSheetResponse,
    ClosePeriodRequest,
    CloseYearRequest,
    ComparativeLineModel,
    ComparativeProfitAndLossResponse,
    CreateAccountRequest,
    CreateEntityRequest,
    EntityCreatedResponse,
    ErrorResponse,
    GrantResponse,
    GrantRoleRequest,
    IssuedStatementModel,
    IssuedStatementsResponse,
    IssueStatementRequest,
    ObligationDetailResponse,
    ObligationModel,
    OpenBalancesRequest,
    OpenedBooksResponse,
    OutstandingResponse,
    PeriodCloseResponse,
    PostingModel,
    ProfitAndLossResponse,
    ReconcileRequest,
    ReconciliationResponse,
    RecordTransactionRequest,
    ReopenPeriodRequest,
    SettlementModel,
    StatementLineModel,
    TransactionResponse,
    TrialBalanceLineModel,
    TrialBalanceResponse,
    WriteResponse,
    YearClosedResponse,
)
from cfokit.ledger.api.problems import status_for
from cfokit.ledger.config import Settings
from cfokit.ledger.engine import Entry, Posting
from cfokit.ledger.engine.periods import Period
from cfokit.ledger.errors import LedgerError
from cfokit.ledger.presentation import (
    ComparativeLine,
    PresentedReconciliation,
    SourceBalance,
    StatementLine,
    present_account_detail,
    present_balance_sheet,
    present_comparative_profit_and_loss,
    present_profit_and_loss,
    present_reconciliation,
    present_trial_balance,
)
from cfokit.ledger.repository.obligations import Obligation
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.administration import (
    create_account,
    create_entity,
    grant_role,
    revoke_grant,
)
from cfokit.ledger.service.authentication import (
    Authenticator,
    TokenAuthenticator,
    principal_from_claims,
)
from cfokit.ledger.service.interchange import export_interchange
from cfokit.ledger.service.issuance import Issued, issue_statement, issued, supersession
from cfokit.ledger.service.opening import CarriedBalance, open_balances
from cfokit.ledger.service.periods import close_period, reopen_period
from cfokit.ledger.service.principal import Principal
from cfokit.ledger.service.read import read_transaction
from cfokit.ledger.service.readiness import check_readiness
from cfokit.ledger.service.receivables import obligation_detail, outstanding_obligations
from cfokit.ledger.service.reports import (
    Comparative,
    account_detail,
    balance_sheet,
    comparative_profit_and_loss,
    profit_and_loss,
    trial_balance,
)
from cfokit.ledger.service.write import (
    Applied,
    WriteContext,
    post_transaction,
    record_transaction,
    reverse_transaction,
)
from cfokit.ledger.service.year_end import close_fiscal_year

__all__ = ["create_app"]


def _reconciliation(report: PresentedReconciliation) -> ReconciliationResponse:
    return ReconciliationResponse(
        as_of=report.as_of,
        watermark=report.watermark,
        accounting_basis=report.accounting_basis,
        commodity=report.commodity,
        source_is_rounded=report.source_is_rounded,
        agrees=report.agrees,
        comparisons=[
            AccountComparisonModel(
                account_code=comparison.account_code,
                ours=str(comparison.ours) if comparison.ours is not None else None,
                theirs=str(comparison.theirs) if comparison.theirs is not None else None,
                difference=str(comparison.difference),
                agrees=comparison.agrees,
            )
            for comparison in report.comparisons
        ],
    )


def _issued(record: Issued) -> IssuedStatementModel:
    return IssuedStatementModel(
        issuance_id=record.statement.issuance_id,
        report=record.statement.report,
        since=record.statement.since,
        as_of=record.statement.as_of,
        watermark=record.statement.watermark,
        issued_by=record.statement.issued_by,
        issued_at=record.statement.issued_at,
        issued_to=record.statement.issued_to,
        superseded=record.superseded,
        superseded_by=record.superseded_by,
        figures=record.statement.figures,
    )


def _obligation(found: Obligation) -> ObligationModel:
    """Render an obligation, with its derived outstanding figure."""
    return ObligationModel(
        obligation_id=found.obligation_id,
        transaction_id=found.transaction_id,
        transaction_date=found.transaction_date,
        amount=str(found.amount),
        settled=str(found.settled),
        outstanding=str(found.outstanding),
        commodity=found.commodity,
    )


def _comparative(line: ComparativeLine) -> ComparativeLineModel:
    return ComparativeLineModel(
        account_id=line.account_id,
        code=line.code,
        name=line.name,
        account_type=line.account_type,
        current=str(line.current),
        comparison=str(line.comparison),
        variance=str(line.variance),
    )


def _comparatives(lines: Iterable[ComparativeLine]) -> list[ComparativeLineModel]:
    return [_comparative(line) for line in lines]


def _lines(lines: Iterable[StatementLine]) -> list[StatementLineModel]:
    """Render statement lines, which every statement does the same way."""
    return [
        StatementLineModel(
            account_id=line.account_id,
            code=line.code,
            name=line.name,
            account_type=line.account_type,
            amount=str(line.amount),
        )
        for line in lines
    ]


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
    """The acting principal, from the credential and never from the body (ADR-0033).

    Verification and derivation are separate calls so the MCP adapter composes the same two
    (ADR-0019). A claim the caller sets never reaches this.
    """
    authenticator: Authenticator = request.app.state.authenticator
    return principal_from_claims(authenticator.claims_for(authorization))


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
    # Creating an entity is the exception: `IAM-06` makes it the one act requiring an
    # authenticated identity and no prior role, so the deployment is usable as it stands.
    # -----------------------------------------------------------------------------------

    @app.post(
        "/entities",
        tags=["administration"],
        summary="Create an entity and assign its first owner",
        status_code=status.HTTP_201_CREATED,
        responses=ERRORS,
    )
    def create(
        body: CreateEntityRequest,
        acting: Annotated[Principal, Depends(get_principal)],
        database: Annotated[Database, Depends(get_database)],
        request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
    ) -> EntityCreatedResponse:
        """Requires authentication and no prior role (`IAM-06`).

        The entity and its first owner are written in one transaction, or neither is
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
            owner=body.owner,
        )
        return EntityCreatedResponse(
            entity_id=created.entity_id,
            owner_grant_id=created.owner_grant_id,
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
        "/entities/{entity_id}/accounts",
        tags=["administration"],
        summary="Add an account to the chart",
        status_code=status.HTTP_201_CREATED,
        responses=ERRORS,
    )
    def add_account(
        entity_id: Annotated[str, Path()],
        body: CreateAccountRequest,
        acting: Annotated[Principal, Depends(get_principal)],
        database: Annotated[Database, Depends(get_database)],
        request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
    ) -> AccountCreatedResponse:
        """The chart is the shape of the books, so adding to it is administrative rather than
        a posting capability (`LED-01`)."""
        account_id = create_account(
            database,
            entity_id=entity_id,
            principal=acting,
            request_id=request_id or f"req-{uuid.uuid4().hex}",
            code=body.code,
            name=body.name,
            account_type=body.account_type,
            parent_id=body.parent_id,
            retained_earnings=body.retained_earnings,
            opening_balance=body.opening_balance,
        )
        return AccountCreatedResponse(account_id=account_id)

    @app.get(
        "/entities/{entity_id}/trial-balance",
        tags=["reports"],
        summary="Trial balance as of a date",
        responses=ERRORS,
    )
    def read_trial_balance(
        entity_id: Annotated[str, Path()],
        acting: Annotated[Principal, Depends(get_principal)],
        database: Annotated[Database, Depends(get_database)],
        as_of: Annotated[date | None, Query()] = None,
        watermark: Annotated[datetime | None, Query()] = None,
    ) -> TrialBalanceResponse:
        """Every account with a non-zero balance (`RPT-01`).

        `watermark` reproduces the books as they stood at that moment (`RPT-11`): the
        statement given to a lender in March is reproducible in December, unchanged by the
        corrections posted in between.

        Figures are rounded once here, at presentation, and the totals are computed from the
        unrounded values (`RPT-12`, ADR-0025). A column summed by hand may differ from the
        printed total by less than one unit of display scale; the printed total is correct.
        """
        report = present_trial_balance(
            trial_balance(
                database,
                entity_id=entity_id,
                principal=acting,
                as_of=as_of or date.today(),  # noqa: DTZ011
                watermark=watermark,
            )
        )
        return TrialBalanceResponse(
            as_of=report.as_of,
            watermark=report.watermark,
            accounting_basis=report.accounting_basis,
            commodity=report.commodity,
            lines=[
                TrialBalanceLineModel(
                    account_id=line.account_id,
                    code=line.code,
                    name=line.name,
                    account_type=line.account_type,
                    debit=str(line.debit) if line.debit is not None else None,
                    credit=str(line.credit) if line.credit is not None else None,
                )
                for line in report.lines
            ],
            total_debit=str(report.total_debit),
            total_credit=str(report.total_credit),
            balances=report.balances,
        )

    @app.get(
        "/entities/{entity_id}/profit-and-loss",
        tags=["reports"],
        summary="Profit and loss for a period",
        responses=ERRORS,
    )
    def read_profit_and_loss(
        entity_id: Annotated[str, Path()],
        since: Annotated[date, Query()],
        acting: Annotated[Principal, Depends(get_principal)],
        database: Annotated[Database, Depends(get_database)],
        as_of: Annotated[date | None, Query()] = None,
        watermark: Annotated[datetime | None, Query()] = None,
    ) -> ProfitAndLossResponse:
        """Income and expense between two dates, inclusive (`RPT-02`).

        A period rather than a point, which is the difference from a balance sheet: income and
        expense measure what happened between two dates; assets and liabilities are what stands
        at one.
        """
        report = present_profit_and_loss(
            profit_and_loss(
                database,
                entity_id=entity_id,
                principal=acting,
                since=since,
                as_of=as_of or date.today(),  # noqa: DTZ011
                watermark=watermark,
            )
        )
        return ProfitAndLossResponse(
            since=report.since,
            as_of=report.as_of,
            watermark=report.watermark,
            accounting_basis=report.accounting_basis,
            commodity=report.commodity,
            income=_lines(report.income),
            expenses=_lines(report.expenses),
            total_income=str(report.total_income),
            total_expenses=str(report.total_expenses),
            net_income=str(report.net_income),
        )

    @app.get(
        "/entities/{entity_id}/profit-and-loss/comparative",
        tags=["reports"],
        summary="Profit and loss beside a comparative period",
        responses=ERRORS,
    )
    def read_comparative_profit_and_loss(
        entity_id: Annotated[str, Path()],
        since: Annotated[date, Query()],
        acting: Annotated[Principal, Depends(get_principal)],
        database: Annotated[Database, Depends(get_database)],
        comparative: Annotated[Comparative, Query()] = Comparative.PRECEDING,
        as_of: Annotated[date | None, Query()] = None,
        watermark: Annotated[datetime | None, Query()] = None,
    ) -> ComparativeProfitAndLossResponse:
        """Two periods side by side, with the variance between them (`RPT-07`).

        A whole-month window compares against whole months, so March is set against February
        and a quarter against the quarter before it. Any other window compares against its own
        length in days, which is the only rule available with no month boundaries to follow.
        """
        report = present_comparative_profit_and_loss(
            comparative_profit_and_loss(
                database,
                entity_id=entity_id,
                principal=acting,
                since=since,
                as_of=as_of or date.today(),  # noqa: DTZ011
                comparative=comparative,
                watermark=watermark,
            )
        )
        return ComparativeProfitAndLossResponse(
            comparative=report.comparative,
            since=report.since,
            as_of=report.as_of,
            comparison_since=report.comparison_since,
            comparison_as_of=report.comparison_as_of,
            watermark=report.watermark,
            accounting_basis=report.accounting_basis,
            commodity=report.commodity,
            income=_comparatives(report.income),
            expenses=_comparatives(report.expenses),
            total_income=_comparative(report.total_income),
            total_expenses=_comparative(report.total_expenses),
            net_income=_comparative(report.net_income),
        )

    @app.get(
        "/entities/{entity_id}/balance-sheet",
        tags=["reports"],
        summary="Balance sheet as of a date",
        responses=ERRORS,
    )
    def read_balance_sheet(
        entity_id: Annotated[str, Path()],
        acting: Annotated[Principal, Depends(get_principal)],
        database: Annotated[Database, Depends(get_database)],
        as_of: Annotated[date | None, Query()] = None,
        watermark: Annotated[datetime | None, Query()] = None,
    ) -> BalanceSheetResponse:
        """Assets, liabilities and equity as of a date (`RPT-03`).

        Equity includes earnings not yet closed to retained earnings: `LED-12` moves those only
        at a fiscal year end, so mid-year they are equity that has not been moved. Leaving them
        out would make the statement fail to balance by exactly that amount.
        """
        report = present_balance_sheet(
            balance_sheet(
                database,
                entity_id=entity_id,
                principal=acting,
                as_of=as_of or date.today(),  # noqa: DTZ011
                watermark=watermark,
            )
        )
        return BalanceSheetResponse(
            as_of=report.as_of,
            watermark=report.watermark,
            accounting_basis=report.accounting_basis,
            commodity=report.commodity,
            assets=_lines(report.assets),
            liabilities=_lines(report.liabilities),
            equity=_lines(report.equity),
            unclosed_earnings=str(report.unclosed_earnings),
            total_assets=str(report.total_assets),
            total_liabilities=str(report.total_liabilities),
            total_equity=str(report.total_equity),
            balances=report.balances,
        )

    @app.get(
        "/entities/{entity_id}/accounts/{account_id}/detail",
        tags=["reports"],
        summary="Account detail for a period",
        responses=ERRORS,
    )
    def read_account_detail(
        entity_id: Annotated[str, Path()],
        account_id: Annotated[str, Path()],
        since: Annotated[date, Query()],
        acting: Annotated[Principal, Depends(get_principal)],
        database: Annotated[Database, Depends(get_database)],
        as_of: Annotated[date | None, Query()] = None,
        watermark: Annotated[datetime | None, Query()] = None,
    ) -> AccountDetailResponse:
        """Every posting against one account, in order, with a running balance (`RPT-05`).

        This is where `RPT-08` resolves to: from a figure on a statement to the postings that
        produced it, and from a posting to the transaction and the principal that wrote it.
        """
        report = present_account_detail(
            account_detail(
                database,
                entity_id=entity_id,
                principal=acting,
                account_id=account_id,
                since=since,
                as_of=as_of or date.today(),  # noqa: DTZ011
                watermark=watermark,
            )
        )
        return AccountDetailResponse(
            account_id=report.account_id,
            code=report.code,
            name=report.name,
            account_type=report.account_type,
            since=report.since,
            as_of=report.as_of,
            watermark=report.watermark,
            accounting_basis=report.accounting_basis,
            commodity=report.commodity,
            opening_balance=str(report.opening_balance),
            closing_balance=str(report.closing_balance),
            entries=[
                AccountEntryModel(
                    transaction_id=entry.transaction_id,
                    transaction_date=entry.transaction_date,
                    description=entry.description,
                    entry_kind=entry.entry_kind,
                    reverses_id=entry.reverses_id,
                    actor_principal_id=entry.actor_principal_id,
                    actor_class=entry.actor_class,
                    acting_for_principal_id=entry.acting_for_principal_id,
                    amount=str(entry.amount),
                    running_balance=str(entry.running_balance),
                )
                for entry in report.entries
            ],
        )

    @app.post(
        "/entities/{entity_id}/opening-balances",
        tags=["administration"],
        summary="Open the books with balances carried in",
        status_code=status.HTTP_201_CREATED,
        responses=ERRORS,
    )
    def open_the_books(
        entity_id: Annotated[str, Path()],
        body: OpenBalancesRequest,
        acting: Annotated[Principal, Depends(get_principal)],
        database: Annotated[Database, Depends(get_database)],
        request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
    ) -> OpenedBooksResponse:
        """Carry balances in from before CFOKit held the books (`LED-10`).

        The equity side is computed rather than supplied, so an entry that does not balance is
        impossible rather than refused. Books are opened once: opening them again would double
        every carried-in figure, and a wrong one is corrected with an ordinary entry.
        """
        opened = open_balances(
            database,
            entity_id=entity_id,
            principal=acting,
            request_id=request_id or f"req-{uuid.uuid4().hex}",
            as_of=body.as_of,
            balances=[
                CarriedBalance(
                    account_id=carried.account_id,
                    amount=carried.amount,
                    commodity=carried.commodity,
                )
                for carried in body.balances
            ],
        )
        return OpenedBooksResponse(
            transaction_id=opened.transaction_id,
            as_of=opened.as_of,
            equity_amount=str(opened.equity_amount),
        )

    @app.get(
        "/entities/{entity_id}/obligations",
        tags=["reports"],
        summary="Obligations and what is outstanding",
        responses=ERRORS,
    )
    def read_outstanding(
        entity_id: Annotated[str, Path()],
        acting: Annotated[Principal, Depends(get_principal)],
        database: Annotated[Database, Depends(get_database)],
        as_of: Annotated[date | None, Query()] = None,
        unsettled_only: Annotated[bool, Query()] = True,
    ) -> OutstandingResponse:
        """What is still owed, and what has been applied against it (`LED-17`)."""
        found = outstanding_obligations(
            database,
            entity_id=entity_id,
            principal=acting,
            as_of=as_of,
            unsettled_only=unsettled_only,
        )
        return OutstandingResponse(as_of=as_of, obligations=[_obligation(o) for o in found])

    @app.get(
        "/entities/{entity_id}/obligations/{obligation_id}",
        tags=["reports"],
        summary="One obligation, read as both events",
        responses=ERRORS,
    )
    def read_obligation(
        entity_id: Annotated[str, Path()],
        obligation_id: Annotated[str, Path()],
        acting: Annotated[Principal, Depends(get_principal)],
        database: Annotated[Database, Depends(get_database)],
    ) -> ObligationDetailResponse:
        """`LED-17`: recoverable as the commitment it was, or as what has settled it."""
        detail = obligation_detail(
            database, entity_id=entity_id, principal=acting, obligation_id=obligation_id
        )
        return ObligationDetailResponse(
            obligation=_obligation(detail.obligation),
            settlements=[
                SettlementModel(
                    settlement_id=applied.settlement_id,
                    transaction_id=applied.transaction_id,
                    transaction_date=applied.transaction_date,
                    amount=str(applied.amount),
                    commodity=applied.commodity,
                )
                for applied in detail.settlements
            ],
        )

    @app.post(
        "/entities/{entity_id}/issued-statements",
        tags=["reports"],
        summary="Mark a statement issued",
        status_code=status.HTTP_201_CREATED,
        responses=ERRORS,
    )
    def issue(
        entity_id: Annotated[str, Path()],
        body: IssueStatementRequest,
        acting: Annotated[Principal, Depends(get_principal)],
        database: Annotated[Database, Depends(get_database)],
        request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
    ) -> IssuedStatementModel:
        """Fix what was reported, to whom, and when (`RPT-17`).

        The watermark is taken now, so the statement reproduces from the books exactly as
        issued (`RPT-11`) — and a correction posted afterwards marks it superseded without
        anything having to remember (`SOC1-20`).
        """
        issuance_id = issue_statement(
            database,
            entity_id=entity_id,
            principal=acting,
            request_id=request_id or f"req-{uuid.uuid4().hex}",
            report=body.report,
            since=body.since,
            as_of=body.as_of,
            figures=body.figures,
            issued_to=body.issued_to,
        )
        return _issued(
            supersession(
                database, entity_id=entity_id, principal=acting, issuance_id=issuance_id
            )
        )

    @app.get(
        "/entities/{entity_id}/issued-statements",
        tags=["reports"],
        summary="Statements issued from these books",
        responses=ERRORS,
    )
    def read_issued(
        entity_id: Annotated[str, Path()],
        acting: Annotated[Principal, Depends(get_principal)],
        database: Annotated[Database, Depends(get_database)],
    ) -> IssuedStatementsResponse:
        """Each with whether the books have moved under it since (`SOC1-20`)."""
        return IssuedStatementsResponse(
            statements=[
                _issued(record)
                for record in issued(database, entity_id=entity_id, principal=acting)
            ]
        )

    @app.post(
        "/entities/{entity_id}/reconciliations",
        tags=["reports"],
        summary="Reconcile against a source system's figures",
        responses=ERRORS,
    )
    def reconcile(
        entity_id: Annotated[str, Path()],
        body: ReconcileRequest,
        acting: Annotated[Principal, Depends(get_principal)],
        database: Annotated[Database, Depends(get_database)],
    ) -> ReconciliationResponse:
        """Two figures per account and the difference between them (`IMP-08`).

        `POST` rather than `GET` because the source's figures are the request body and there is
        no sensible query string for a chart of accounts. Nothing is written.

        Says nothing about what a difference means: a comparison detects difference and cannot
        say which side is wrong. That determination is a person's.
        """
        return _reconciliation(
            present_reconciliation(
                trial_balance(
                    database,
                    entity_id=entity_id,
                    principal=acting,
                    as_of=body.as_of,
                    watermark=body.watermark,
                ),
                [
                    SourceBalance(account_code=b.account_code, balance=b.balance)
                    for b in body.balances
                ],
                source_is_rounded=body.source_is_rounded,
            )
        )

    @app.get(
        "/entities/{entity_id}/interchange-export",
        tags=["reports"],
        summary="Interchange export of the books",
        response_class=Response,
        responses={
            **ERRORS,
            200: {
                "content": {"application/zip": {}},
                "description": "A zip of accounts.csv, journal.csv and trial_balance.csv.",
            },
        },
    )
    def interchange_export(
        entity_id: Annotated[str, Path()],
        acting: Annotated[Principal, Depends(get_principal)],
        database: Annotated[Database, Depends(get_database)],
        as_of: Annotated[date | None, Query()] = None,
        watermark: Annotated[datetime | None, Query()] = None,
    ) -> Response:
        """The books in a form another accounting system can read (`EXP-01`).

        A single self-contained archive: it carries the journal *and* the trial balance, so a
        reader can derive the balances and check them against ours without asking us anything.

        `EXP-03` requires this available "at any time, in any entity state short of deletion,
        without asking anyone", so it needs only the ability to read the books.
        """
        exported = export_interchange(
            database,
            entity_id=entity_id,
            principal=acting,
            as_of=as_of or date.today(),  # noqa: DTZ011
            watermark=watermark,
        )
        return Response(
            content=exported.archive,
            media_type="application/zip",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="cfokit-{entity_id}-{exported.as_of}.zip"'
                ),
                # What the archive was produced from, on its face (`RPT-10`, `RPT-11`), so a
                # file separated from the request it came out of still says so.
                "X-CFOKit-Accounting-Basis": exported.accounting_basis,
                "X-CFOKit-As-Of": exported.as_of.isoformat(),
            },
        )

    # -----------------------------------------------------------------------------------
    # Periods. `LED-11` makes a closed period admit no posting except through a recorded
    # reopening, and ADR-0030 makes that reopening a person's act rather than a skill's.
    # -----------------------------------------------------------------------------------

    @app.post(
        "/entities/{entity_id}/period-closes",
        tags=["periods"],
        summary="Mark a period closed",
        status_code=status.HTTP_201_CREATED,
        responses=ERRORS,
    )
    def close(
        entity_id: Annotated[str, Path()],
        body: ClosePeriodRequest,
        acting: Annotated[Principal, Depends(get_principal)],
        database: Annotated[Database, Depends(get_database)],
        request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
    ) -> PeriodCloseResponse:
        """Signifies the period has been reviewed. An agent may do this."""
        close_id = close_period(
            database,
            entity_id=entity_id,
            principal=acting,
            request_id=request_id or f"req-{uuid.uuid4().hex}",
            period=Period(year=body.year, month=body.month),
        )
        return PeriodCloseResponse(close_id=close_id)

    @app.post(
        "/entities/{entity_id}/period-reopenings",
        tags=["periods"],
        summary="Reopen a closed period",
        status_code=status.HTTP_201_CREATED,
        responses=ERRORS,
    )
    def reopen(
        entity_id: Annotated[str, Path()],
        body: ReopenPeriodRequest,
        acting: Annotated[Principal, Depends(get_principal)],
        database: Annotated[Database, Depends(get_database)],
        request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
    ) -> PeriodCloseResponse:
        """A person's act. An agent is refused with `not_a_person`, whatever it holds.

        `POST` rather than `DELETE` on the close: the close row is never removed, and the
        reopening is itself a recorded event that `LED-11` requires to be identifiable.
        """
        close_id = reopen_period(
            database,
            entity_id=entity_id,
            principal=acting,
            request_id=request_id or f"req-{uuid.uuid4().hex}",
            period=Period(year=body.year, month=body.month),
            reason=body.reason,
        )
        return PeriodCloseResponse(close_id=close_id)

    @app.post(
        "/entities/{entity_id}/year-end-closes",
        tags=["periods"],
        summary="Close a fiscal year",
        status_code=status.HTTP_201_CREATED,
        responses=ERRORS,
    )
    def close_year(
        entity_id: Annotated[str, Path()],
        body: CloseYearRequest,
        acting: Annotated[Principal, Depends(get_principal)],
        database: Annotated[Database, Depends(get_database)],
        request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
    ) -> YearClosedResponse:
        """Income and expense to retained earnings, so the new year opens at zero (`LED-12`).

        Re-runs a close that a later posting made stale, reversing the old entries rather than
        editing them (ADR-0027, `LED-08`). A close that is still current is refused.
        """
        closed = close_fiscal_year(
            database,
            entity_id=entity_id,
            principal=acting,
            request_id=request_id or f"req-{uuid.uuid4().hex}",
            day_in_year=body.day_in_year,
        )
        return YearClosedResponse(
            fiscal_year=str(closed.fiscal_year),
            transaction_id=closed.transaction_id,
            reversed_transaction_ids=closed.reversed_transaction_ids,
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
        written = record_transaction(
            database,
            context,
            entry=entry,
            post=body.post,
            raises_obligation=body.raises_obligation,
            settles=tuple(
                Applied(obligation_id=a.obligation_id, amount=a.amount) for a in body.settles
            ),
        )
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

        Where the reversal lands follows ADR-0030 rule 4 and is decided by the ledger from
        the original's period state, not by this adapter: an open original period is restated
        in place, and a closed one is corrected in the current period so figures already
        reported stand.
        """
        written = reverse_transaction(
            database,
            context,
            transaction_id=transaction_id,
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
