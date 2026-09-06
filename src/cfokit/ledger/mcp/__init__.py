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

**Neither export is a tool here, and the complete one deliberately never will be.** `EXP-03`
requires both available "without asking anyone", which is about needing no human gatekeeper
rather than about every protocol carrying them. An export is a file a person downloads; the
complete one is every posting amount, payee and audit row the entity holds, and putting that
through a model's context is the thing the observability rules exist to prevent. The REST
surface serves both.

So every tool returns a result carrying `ok`. On success the payload; on a ledger refusal
`{"ok": false, "code": ..., "message": ...}`, with the same code the REST surface returns for
the same condition (ADR-0009). The cost is that a client checking only MCP's `isError` sees a
refusal as a success, which the tool descriptions and the server instructions both state.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Iterable
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from http import HTTPStatus
from typing import Any

from mcp.server import MCPServer
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.settings import AuthSettings
from pydantic import AnyHttpUrl, BaseModel, Field
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from cfokit.ledger.config import Settings
from cfokit.ledger.engine import Entry, Posting
from cfokit.ledger.errors import LedgerError, NotAuthenticated
from cfokit.ledger.mcp.auth import LedgerTokenVerifier
from cfokit.ledger.presentation import (
    ComparativeLine,
    PresentedAccountDetail,
    PresentedBalanceSheet,
    PresentedProfitAndLoss,
    PresentedTrialBalance,
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
from cfokit.ledger.service.administration import create_entity
from cfokit.ledger.service.authentication import (
    Authenticator,
    TokenAuthenticator,
    principal_from_claims,
)
from cfokit.ledger.service.issuance import Issued, issue_statement, issued
from cfokit.ledger.service.opening import CarriedBalance, open_balances
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


class AppliedArgument(BaseModel):
    """How much of a settlement goes against one obligation."""

    obligation_id: str = Field(description="The obligation this payment is applied to.")
    amount: str = Field(description="Signed decimal string, in the entity's currency.")


class SourceBalanceArgument(BaseModel):
    """One account's balance as the source system states it."""

    account_code: str = Field(description="The account code both systems agree on.")
    balance: str = Field(
        description="Signed decimal string, positive for a debit. Converting a foreign "
        "export's sign convention is the caller's job."
    )


class CarriedBalanceArgument(BaseModel):
    """One account's balance as it stood in the system CFOKit is taking over from.

    `amount` is a string for the same reason a posting's is: a JSON number cannot carry the
    scale the balance was written at, and `100.00` would arrive as `100`.
    """

    account_id: str = Field(description="The account carrying this balance.")
    amount: str = Field(description="Signed decimal string. Positive debits the account.")
    commodity: str = Field(description="The unit the amount is denominated in, e.g. USD.")


def _statement_lines(lines: Iterable[StatementLine]) -> list[dict[str, Any]]:
    return [
        {
            "account_id": line.account_id,
            "code": line.code,
            "name": line.name,
            "account_type": line.account_type,
            "amount": str(line.amount),
        }
        for line in lines
    ]


def _comparative_line(line: ComparativeLine) -> dict[str, Any]:
    return {
        "account_id": line.account_id,
        "code": line.code,
        "name": line.name,
        "account_type": line.account_type,
        "current": str(line.current),
        "comparison": str(line.comparison),
        "variance": str(line.variance),
    }


def _comparative_lines(lines: Iterable[ComparativeLine]) -> list[dict[str, Any]]:
    return [_comparative_line(line) for line in lines]


def _issued(record: Issued) -> dict[str, Any]:
    return {
        "issuance_id": record.statement.issuance_id,
        "report": record.statement.report,
        "since": record.statement.since.isoformat() if record.statement.since else None,
        "as_of": record.statement.as_of.isoformat(),
        "watermark": record.statement.watermark.isoformat(),
        "issued_by": record.statement.issued_by,
        "issued_at": record.statement.issued_at.isoformat(),
        "issued_to": record.statement.issued_to,
        "superseded": record.superseded,
        "superseded_by": record.superseded_by,
    }


def _obligation(found: Obligation) -> dict[str, Any]:
    return {
        "obligation_id": found.obligation_id,
        "transaction_id": found.transaction_id,
        "transaction_date": found.transaction_date.isoformat(),
        "amount": str(found.amount),
        "settled": str(found.settled),
        "outstanding": str(found.outstanding),
        "commodity": found.commodity,
    }


def _produced_on(
    report: PresentedAccountDetail
    | PresentedTrialBalance
    | PresentedProfitAndLoss
    | PresentedBalanceSheet,
) -> dict[str, Any]:
    """What every report states on its face (`RPT-10`, `RPT-11`)."""
    return {
        "ok": True,
        "as_of": report.as_of.isoformat(),
        "watermark": report.watermark.isoformat() if report.watermark else None,
        "accounting_basis": report.accounting_basis,
        "commodity": report.commodity,
    }


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


def _to_decimal(raw: str) -> Decimal:
    """Parse an amount, refusing a malformed one with a code rather than a stack trace."""
    try:
        return Decimal(raw)
    except InvalidOperation as exc:
        raise LedgerToolError("invalid_amount", f"not a decimal amount: {raw!r}") from exc


def _to_posting(argument: PostingArgument) -> Posting:
    return Posting(
        account_id=argument.account_id,
        amount=_to_decimal(argument.amount),
        commodity=argument.commodity,
    )


def acting() -> Principal:
    """The caller, from the verified token on this request.

    The SDK's bearer middleware has already rejected an absent or invalid token with a 401, so
    reaching here without one means the server is running on a transport that carries no
    credential. Refusing is the only safe answer: `LED-20` requires every transaction to record
    what wrote it, and there would be nothing true to record.

    Module level rather than a closure inside `create_server`, so a module registering its own
    tools onto the same server derives a principal exactly one way (ADR-0033, ADR-0040). It
    closes over nothing — the token comes from the request's own context.
    """
    token = get_access_token()
    if token is None or token.claims is None:
        raise LedgerToolError(
            "not_authenticated", "this request carries no verified credential"
        )
    try:
        return principal_from_claims(token.claims)
    except NotAuthenticated as exc:
        raise LedgerToolError(exc.code, exc.message) from exc


def _refusals(work: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    """Run `work`, converting any ledger refusal into the structured refusal shape."""
    try:
        return work()
    except LedgerToolError as exc:
        return refused(exc.code, exc.detail)
    except LedgerError as exc:
        return refused(exc.code, exc.message)


def create_server(settings: Settings, authenticator: Authenticator | None = None) -> MCPServer:
    """Build the MCP server.

    The caller is derived from the bearer token on the request, never injected and never taken
    from a tool argument (ADR-0033). `authenticator` exists so a test can supply verification
    without an issuer; a deployment gets `TokenAuthenticator` against `AUTH_ISSUER_URL` and
    `AUTH_AUDIENCE`, which is the same issuer and the same audience the REST surface uses
    (ADR-0019).

    `resource_server_url` comes from `PUBLIC_BASE_URL` and never from a request header. Behind
    a proxy or a tunnel the headers lie, and this URL is what a client fetches metadata from
    (ADR-0004).
    """
    database = Database(settings.database_url)
    verifier = LedgerTokenVerifier(
        authenticator or TokenAuthenticator(settings.auth_issuer_url, settings.auth_audience)
    )
    server = MCPServer(
        name="cfokit-ledger",
        token_verifier=verifier,
        auth=AuthSettings(
            issuer_url=AnyHttpUrl(settings.auth_issuer_url),
            resource_server_url=AnyHttpUrl(settings.public_base_url),
        ),
        instructions=(
            "The double-entry ledger. Every write names the entity it acts on and carries an "
            "idempotency key; replaying a key returns the original result rather than booking "
            "again. Amounts are decimal strings. A posted transaction is never edited — "
            "correct it with reverse_transaction. Every tool returns an 'ok' field: false "
            "means the ledger refused the operation and 'code' says why."
        ),
    )

    # Liveness and readiness, unauthenticated on both surfaces: a platform probe holds no
    # token, and a readiness check that could fail for want of one would report the wrong
    # thing. `custom_route` is outside the bearer middleware for exactly this reason.
    #
    # The same two questions the REST surface answers, through the same service call, so a
    # deployment cannot have one surface ready and the other silently not (ADR-0008).

    # The SDK's decorator is untyped, so mypy --strict would infer these as untyped.
    @server.custom_route("/healthz", methods=["GET"])  # type: ignore[untyped-decorator]
    async def healthz(request: Request) -> Response:
        """Liveness only. Deliberately touches nothing.

        If this checked the database, a database blip would restart every healthy container —
        turning a recoverable outage into a rolling one.
        """
        return JSONResponse({"status": "ok"})

    @server.custom_route("/readyz", methods=["GET"])  # type: ignore[untyped-decorator]
    async def readyz(request: Request) -> Response:
        """Database reachable, and migrations current.

        503 when not ready, so a rollout stops rather than serving traffic against a schema
        older than the code.
        """
        result = check_readiness(settings.database_url)
        return JSONResponse(
            {
                "status": "ready" if result.ready else "not_ready",
                "database_reachable": result.database_reachable,
                "migrations_current": result.migrations_current,
                "detail": result.detail,
            },
            status_code=HTTPStatus.OK if result.ready else HTTPStatus.SERVICE_UNAVAILABLE,
        )

    def context(entity_id: str, idempotency_key: str) -> WriteContext:
        return WriteContext(
            entity_id=entity_id,
            principal=acting(),
            request_id=f"mcp-{uuid.uuid4().hex}",
            idempotency_key=idempotency_key,
        )

    @server.tool(
        name="create_entity",
        description=(
            "Create a set of books and become its owner. Needs only an authenticated caller "
            "and no prior role — this is the one act with that property, and it is what makes "
            "a running deployment usable without anything being provisioned into it first. "
            "Every declaration is required and none has a default: the accounting basis, the "
            "fiscal year end, the functional currency and the time zone are what every report "
            "is computed against, and a default would be an undeclared state wearing a value."
        ),
    )
    def make_entity(
        slug: str,
        name: str,
        accounting_basis: str,
        fiscal_year_end_month: int,
        fiscal_year_end_day: int,
        functional_currency: str,
        time_zone: str,
    ) -> dict[str, Any]:
        """`IAM-06`, on the surface a person actually reaches.

        The other administration acts stay off this surface. Granting a role is handing the
        entity away, which `IAM-21` reserves to owners; the chart is the shape of the books,
        which someone able to record a transaction is not thereby deciding. Creating an entity
        is different in kind: there is no entity to hold a role in yet, and the act of creating
        one is what confers the first (`IAM-05`).

        **No `owner` argument.** The REST surface has one, for the case where a person
        provisions on another's behalf. Here the caller is a person at a prompt, and an
        argument naming someone else would be a way to create books nobody in the room owns.
        """

        def work() -> dict[str, Any]:
            if accounting_basis not in {"cash", "accrual"}:
                raise LedgerToolError(
                    "invalid_argument", "accounting_basis is 'cash' or 'accrual'"
                )
            created = create_entity(
                database,
                principal=acting(),
                request_id=f"mcp-{uuid.uuid4().hex}",
                slug=slug,
                name=name,
                accounting_basis=accounting_basis,
                fiscal_year_end_month=fiscal_year_end_month,
                fiscal_year_end_day=fiscal_year_end_day,
                functional_currency=functional_currency,
                time_zone=time_zone,
            )
            return {
                "ok": True,
                "entity_id": created.entity_id,
                "owner_grant_id": created.owner_grant_id,
            }

        return _refusals(work)

    @server.tool(
        name="record_transaction",
        description=(
            "Record a transaction in an entity's books, as a draft or posted straight "
            "through. Postings must sum to zero per commodity to post. Requires an "
            "idempotency key; replaying one books nothing further. Pass raises_obligation to "
            "record it as an invoice or anything else owed, and settles to apply it against "
            "obligations — both need post."
        ),
    )
    def record(
        entity_id: str,
        transaction_date: date,
        postings: list[PostingArgument],
        idempotency_key: str,
        description: str | None = None,
        post: bool = False,
        raises_obligation: str | None = None,
        settles: list[AppliedArgument] | None = None,
    ) -> dict[str, Any]:
        def work() -> dict[str, Any]:
            entry = Entry(
                transaction_date=transaction_date,
                postings=tuple(_to_posting(p) for p in postings),
                description=description,
            )
            written = record_transaction(
                database,
                context(entity_id, idempotency_key),
                entry=entry,
                post=post,
                raises_obligation=(
                    _to_decimal(raises_obligation) if raises_obligation is not None else None
                ),
                settles=tuple(
                    Applied(
                        obligation_id=applied.obligation_id,
                        amount=_to_decimal(applied.amount),
                    )
                    for applied in settles or ()
                ),
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

    def _at(as_of: str | None, watermark: str | None) -> tuple[date, datetime | None]:
        """Parse the two moments a report is produced at, refusing a malformed one clearly."""
        try:
            when = date.fromisoformat(as_of) if as_of else date.today()  # noqa: DTZ011
            taken = datetime.fromisoformat(watermark) if watermark else None
        except ValueError as exc:
            raise LedgerToolError("invalid_date", str(exc)) from exc
        return when, taken

    @server.tool(
        name="open_balances",
        description=(
            "Open the books with balances carried in from before CFOKit held them. Do not "
            "supply the equity side: the ledger computes the counterweight, so the entry "
            "cannot fail to balance. Books are opened once — opening them again would double "
            "every figure, and a wrong one is corrected with an ordinary entry."
        ),
    )
    def open_the_books(
        entity_id: str, as_of: str, balances: list[CarriedBalanceArgument]
    ) -> dict[str, Any]:
        def work() -> dict[str, Any]:
            when, _ = _at(as_of, None)
            opened = open_balances(
                database,
                entity_id=entity_id,
                principal=acting(),
                request_id=f"mcp-{uuid.uuid4().hex}",
                as_of=when,
                balances=[
                    CarriedBalance(
                        account_id=carried.account_id,
                        amount=_to_decimal(carried.amount),
                        commodity=carried.commodity,
                    )
                    for carried in balances
                ],
            )
            return {
                "ok": True,
                "transaction_id": opened.transaction_id,
                "as_of": opened.as_of.isoformat(),
                "equity_amount": str(opened.equity_amount),
            }

        return _refusals(work)

    @server.tool(
        name="issue_statement",
        description=(
            "Mark a statement issued, fixing what was reported, to whom, and when. Pass the "
            "rendered figures you gave the recipient: they are stored rather than re-derived, "
            "because re-deriving assumes the presentation never changes. A correction posted "
            "afterwards marks the statement superseded, with no flag to maintain."
        ),
    )
    def issue(
        entity_id: str,
        report: str,
        as_of: str,
        issued_to: str,
        figures: dict[str, Any],
        since: str | None = None,
    ) -> dict[str, Any]:
        def work() -> dict[str, Any]:
            when, _ = _at(as_of, None)
            start = _at(since, None)[0] if since else None
            issuance_id = issue_statement(
                database,
                entity_id=entity_id,
                principal=acting(),
                request_id=f"mcp-{uuid.uuid4().hex}",
                report=report,
                since=start,
                as_of=when,
                figures=figures,
                issued_to=issued_to,
            )
            return {"ok": True, "issuance_id": issuance_id}

        return _refusals(work)

    @server.tool(
        name="issued_statements",
        description=(
            "Every statement issued from these books, newest first, each saying whether a "
            "posting has entered its window since — which means what a recipient holds no "
            "longer matches the books."
        ),
    )
    def read_issued(entity_id: str) -> dict[str, Any]:
        def work() -> dict[str, Any]:
            return {
                "ok": True,
                "statements": [
                    _issued(record)
                    for record in issued(database, entity_id=entity_id, principal=acting())
                ],
            }

        return _refusals(work)

    @server.tool(
        name="outstanding_obligations",
        description=(
            "What is still owed, and how much has been applied against each. Outstanding is "
            "derived from the obligation less its settlements, never stored. Pass "
            "unsettled_only=false for the full history including what has been paid."
        ),
    )
    def read_outstanding(
        entity_id: str, as_of: str | None = None, unsettled_only: bool = True
    ) -> dict[str, Any]:
        def work() -> dict[str, Any]:
            when = _at(as_of, None)[0] if as_of else None
            found = outstanding_obligations(
                database,
                entity_id=entity_id,
                principal=acting(),
                as_of=when,
                unsettled_only=unsettled_only,
            )
            return {
                "ok": True,
                "as_of": when.isoformat() if when else None,
                "obligations": [_obligation(o) for o in found],
            }

        return _refusals(work)

    @server.tool(
        name="obligation_detail",
        description=(
            "One obligation read as both events: the commitment as it arose, and every "
            "settlement applied to it since."
        ),
    )
    def read_obligation(entity_id: str, obligation_id: str) -> dict[str, Any]:
        def work() -> dict[str, Any]:
            detail = obligation_detail(
                database,
                entity_id=entity_id,
                principal=acting(),
                obligation_id=obligation_id,
            )
            return {
                "ok": True,
                "obligation": _obligation(detail.obligation),
                "settlements": [
                    {
                        "settlement_id": applied.settlement_id,
                        "transaction_id": applied.transaction_id,
                        "transaction_date": applied.transaction_date.isoformat(),
                        "amount": str(applied.amount),
                        "commodity": applied.commodity,
                    }
                    for applied in detail.settlements
                ],
            }

        return _refusals(work)

    @server.tool(
        name="reconcile",
        description=(
            "Compare the books against a source system's own trial balance, account by "
            "account, matched on account code. Reports two figures and a difference and says "
            "nothing about what a difference means — a comparison detects difference and "
            "cannot say which side is wrong. An account present on one side only is reported, "
            "never dropped. Set source_is_rounded when the source's figures are already "
            "rounded, which most exports are."
        ),
    )
    def reconcile(
        entity_id: str,
        as_of: str,
        balances: list[SourceBalanceArgument],
        source_is_rounded: bool = False,
        watermark: str | None = None,
    ) -> dict[str, Any]:
        def work() -> dict[str, Any]:
            when, taken = _at(as_of, watermark)
            report = present_reconciliation(
                trial_balance(
                    database,
                    entity_id=entity_id,
                    principal=acting(),
                    as_of=when,
                    watermark=taken,
                ),
                [
                    SourceBalance(
                        account_code=balance.account_code,
                        balance=_to_decimal(balance.balance),
                    )
                    for balance in balances
                ],
                source_is_rounded=source_is_rounded,
            )
            return {
                "ok": True,
                "as_of": report.as_of.isoformat(),
                "watermark": report.watermark.isoformat() if report.watermark else None,
                "accounting_basis": report.accounting_basis,
                "commodity": report.commodity,
                "source_is_rounded": report.source_is_rounded,
                "agrees": report.agrees,
                "comparisons": [
                    {
                        "account_code": comparison.account_code,
                        "ours": str(comparison.ours) if comparison.ours is not None else None,
                        "theirs": (
                            str(comparison.theirs) if comparison.theirs is not None else None
                        ),
                        "difference": str(comparison.difference),
                        "agrees": comparison.agrees,
                    }
                    for comparison in report.comparisons
                ],
            }

        return _refusals(work)

    @server.tool(
        name="trial_balance",
        description=(
            "Every account with a non-zero balance as of a date. Pass watermark to reproduce "
            "the books as they stood at an earlier moment, unchanged by anything posted since. "
            "Figures are decimal strings rounded for display; totals are computed unrounded, "
            "so a column summed by hand may differ from the printed total."
        ),
    )
    def read_trial_balance(
        entity_id: str, as_of: str | None = None, watermark: str | None = None
    ) -> dict[str, Any]:
        def work() -> dict[str, Any]:
            when, taken = _at(as_of, watermark)
            report = present_trial_balance(
                trial_balance(
                    database,
                    entity_id=entity_id,
                    principal=acting(),
                    as_of=when,
                    watermark=taken,
                )
            )
            return {
                **_produced_on(report),
                "lines": [
                    {
                        "account_id": line.account_id,
                        "code": line.code,
                        "name": line.name,
                        "account_type": line.account_type,
                        "debit": str(line.debit) if line.debit is not None else None,
                        "credit": str(line.credit) if line.credit is not None else None,
                    }
                    for line in report.lines
                ],
                "total_debit": str(report.total_debit),
                "total_credit": str(report.total_credit),
                "balances": report.balances,
            }

        return _refusals(work)

    @server.tool(
        name="profit_and_loss",
        description=(
            "Income and expense between two dates, inclusive. Amounts are signed so positive "
            "means more of what the account is: revenue reads as a positive figure. Net income "
            "is computed from the unrounded totals rather than by subtracting the printed ones."
        ),
    )
    def read_profit_and_loss(
        entity_id: str, since: str, as_of: str | None = None, watermark: str | None = None
    ) -> dict[str, Any]:
        def work() -> dict[str, Any]:
            when, taken = _at(as_of, watermark)
            start, _ = _at(since, None)
            report = present_profit_and_loss(
                profit_and_loss(
                    database,
                    entity_id=entity_id,
                    principal=acting(),
                    since=start,
                    as_of=when,
                    watermark=taken,
                )
            )
            return {
                **_produced_on(report),
                "since": report.since.isoformat(),
                "income": _statement_lines(report.income),
                "expenses": _statement_lines(report.expenses),
                "total_income": str(report.total_income),
                "total_expenses": str(report.total_expenses),
                "net_income": str(report.net_income),
            }

        return _refusals(work)

    @server.tool(
        name="comparative_profit_and_loss",
        description=(
            "A profit and loss beside another period, with the variance on every line. "
            "comparative is 'preceding' or 'year_earlier'. A whole-month window compares "
            "against whole months, so March is set against February and a quarter against the "
            "quarter before it. An account absent from one period counts as zero there, so a "
            "cost that started or a revenue stream that stopped shows as the variance it is."
        ),
    )
    def read_comparative_profit_and_loss(
        entity_id: str,
        since: str,
        comparative: str = "preceding",
        as_of: str | None = None,
        watermark: str | None = None,
    ) -> dict[str, Any]:
        def work() -> dict[str, Any]:
            try:
                against = Comparative(comparative)
            except ValueError as exc:
                raise LedgerToolError(
                    "invalid_comparative", "comparative is 'preceding' or 'year_earlier'"
                ) from exc
            when, taken = _at(as_of, watermark)
            start, _ = _at(since, None)
            report = present_comparative_profit_and_loss(
                comparative_profit_and_loss(
                    database,
                    entity_id=entity_id,
                    principal=acting(),
                    since=start,
                    as_of=when,
                    comparative=against,
                    watermark=taken,
                )
            )
            return {
                "ok": True,
                "comparative": report.comparative.value,
                "since": report.since.isoformat(),
                "as_of": report.as_of.isoformat(),
                "comparison_since": report.comparison_since.isoformat(),
                "comparison_as_of": report.comparison_as_of.isoformat(),
                "watermark": report.watermark.isoformat() if report.watermark else None,
                "accounting_basis": report.accounting_basis,
                "commodity": report.commodity,
                "income": _comparative_lines(report.income),
                "expenses": _comparative_lines(report.expenses),
                "total_income": _comparative_line(report.total_income),
                "total_expenses": _comparative_line(report.total_expenses),
                "net_income": _comparative_line(report.net_income),
            }

        return _refusals(work)

    @server.tool(
        name="balance_sheet",
        description=(
            "Assets, liabilities and equity as of a date. Equity includes unclosed_earnings — "
            "income and expense not yet closed to retained earnings, which happens only at a "
            "fiscal year end — so the statement balances mid-year as well as after a close."
        ),
    )
    def read_balance_sheet(
        entity_id: str, as_of: str | None = None, watermark: str | None = None
    ) -> dict[str, Any]:
        def work() -> dict[str, Any]:
            when, taken = _at(as_of, watermark)
            report = present_balance_sheet(
                balance_sheet(
                    database,
                    entity_id=entity_id,
                    principal=acting(),
                    as_of=when,
                    watermark=taken,
                )
            )
            return {
                **_produced_on(report),
                "assets": _statement_lines(report.assets),
                "liabilities": _statement_lines(report.liabilities),
                "equity": _statement_lines(report.equity),
                "unclosed_earnings": str(report.unclosed_earnings),
                "total_assets": str(report.total_assets),
                "total_liabilities": str(report.total_liabilities),
                "total_equity": str(report.total_equity),
                "balances": report.balances,
            }

        return _refusals(work)

    @server.tool(
        name="account_detail",
        description=(
            "Every posting against one account between two dates, in order, with a running "
            "balance and the balance the period opened with. Each entry names the transaction "
            "and the principal that wrote it, so a figure on a statement can be followed to "
            "what produced it."
        ),
    )
    def read_account_detail(
        entity_id: str,
        account_id: str,
        since: str,
        as_of: str | None = None,
        watermark: str | None = None,
    ) -> dict[str, Any]:
        def work() -> dict[str, Any]:
            when, taken = _at(as_of, watermark)
            start, _ = _at(since, None)
            report = present_account_detail(
                account_detail(
                    database,
                    entity_id=entity_id,
                    principal=acting(),
                    account_id=account_id,
                    since=start,
                    as_of=when,
                    watermark=taken,
                )
            )
            return {
                **_produced_on(report),
                "account_id": report.account_id,
                "code": report.code,
                "name": report.name,
                "account_type": report.account_type,
                "since": report.since.isoformat(),
                "opening_balance": str(report.opening_balance),
                "closing_balance": str(report.closing_balance),
                "entries": [
                    {
                        "transaction_id": entry.transaction_id,
                        "transaction_date": entry.transaction_date.isoformat(),
                        "description": entry.description,
                        "entry_kind": entry.entry_kind,
                        "reverses_id": entry.reverses_id,
                        "actor_principal_id": entry.actor_principal_id,
                        "actor_class": entry.actor_class,
                        "acting_for_principal_id": entry.acting_for_principal_id,
                        "amount": str(entry.amount),
                        "running_balance": str(entry.running_balance),
                    }
                    for entry in report.entries
                ],
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
