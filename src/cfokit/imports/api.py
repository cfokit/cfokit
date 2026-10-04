"""The import module's REST surface: the neutral interchange shape (ADR-0041).

**A router the module owns**, included by `cfokit.server`. The ledger's adapter cannot
mount it — "the ledger depends on no module" is an `import-linter` contract, and a
ledger adapter importing this would be exactly that dependency (ADR-0022).

**Three calls rather than one.** A company's whole journal is about 1.35 MB and about a
minute of posting: too much for one request, and nothing like enough to need a job. The
client holds the loop counter, so each request is short and progress is inherent.

**The archive never arrives.** It is parsed in the person's browser by the web client's
reader, so this process parses no foreign binary format and a hostile spreadsheet reaches
the machine whose owner opened it and nothing else (`NFR-04`, ADR-0058).

**This shape is the published contract**, not a QuickBooks export. A reader for a
system CFOKit has never heard of targets these models and needs nothing else
(`NFR-12`).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field

from cfokit.imports import (
    ImportRefused,
    Refusal,
    open_books,
    post_entries,
)
from cfokit.imports import _import_id as import_id_for
from cfokit.imports.reconciliation import Reconciled, reconciliations, record_reconciliation
from cfokit.imports.source import (
    SourceAccount,
    SourceBooks,
    SourceEntry,
    SourceLine,
    StatedBalance,
    StatedStatement,
    StatedTotal,
)
from cfokit.ledger.api import ERRORS, get_database, get_principal
from cfokit.ledger.api.models import Money
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.principal import Principal

__all__ = ["router"]

Basis = Literal["accrual", "cash", "unknown"]


class SourceAccountModel(BaseModel):
    """One account in the source's chart.

    `code` is whatever the source system agrees with itself on. QuickBooks has no account codes,
    so it is the full colon-separated name; another source may have real ones.
    """

    code: str = Field(min_length=1)
    name: str
    account_type: Literal["asset", "liability", "equity", "income", "expense", "unknown"] = (
        Field(
            description="`unknown` where the source states none. Recorded as a question"
            " rather than guessed: a wrong type is a silent misclassification, and a missing"
            " one is something an operator can answer."
        )
    )
    parent: str = Field(default="", description="The `code` this sits under, or empty.")


class SourceLineModel(BaseModel):
    """One posting line. Positive is a debit, as everywhere else."""

    account_code: str = Field(min_length=1)
    amount: Money
    commodity: str = Field(min_length=1)


class SourceEntryModel(BaseModel):
    """One transaction, as the source grouped it."""

    reference: str = Field(
        min_length=1,
        description="The source's own identifier for this transaction, or a positional one."
        " Half of the idempotency key, so it must be stable across a retry of the same file and"
        " unique within it (ADR-0029).",
    )
    transaction_date: date
    description: str = ""
    lines: list[SourceLineModel]


class StatedBalanceModel(BaseModel):
    """A balance the source states for one account — its arithmetic, not ours.

    This is what makes an import checkable (`IMP-08`). Summing the journal ourselves and
    comparing that against our own books would be comparing our arithmetic against itself.
    """

    account_code: str = Field(min_length=1)
    balance: Money


class StatedStatementModel(BaseModel):
    """A statement the source printed, by account, signed as the source prints it."""

    report: Literal["profit_and_loss", "balance_sheet"]
    basis: Basis
    lines: list[StatedBalanceModel] = Field(default_factory=list)
    unmatched: list[str] = Field(
        default_factory=list,
        description="Rows whose account the reader could not resolve. Reported rather than"
        " dropped: a line silently missing from a comparison is a difference that reads as"
        " agreement.",
    )


class OpenImportRequest(BaseModel):
    """Open an import: create the chart, and name the import.

    Carries no entries. Those arrive in batches, because a company's whole journal in one
    request is the shape this design exists to avoid.
    """

    shape_version: Literal["1"]
    system: str = Field(min_length=1, description="Where the books came from (`IMP-04`).")
    fingerprint: str = Field(
        min_length=16,
        description="A digest of the file the shape was read from. The import's identity and"
        " half of every entry's idempotency key, so re-reading the same file names the same"
        " import and re-sending its entries replays rather than duplicates (ADR-0029).",
    )
    basis: Basis = Field(
        description="The accounting method of the *entries*. `IMP-06` refuses a conflict with"
        " the entity's declared basis; `unknown` conflicts with nothing."
    )
    balances_basis: Basis = Field(
        description="The method the stated balances were computed on. Not a gate — an"
        " explanation. An accrual journal reconciled against cash-basis balances differs by"
        " exactly what is unsettled, which ADR-0037 predicts."
    )
    commodity: str = Field(min_length=1)
    accounts: list[SourceAccountModel]


class OpenImportResponse(BaseModel):
    import_id: str
    accounts_created: int
    accounts_already_present: int


class PostEntriesRequest(BaseModel):
    """One batch of entries."""

    system: str = Field(min_length=1)
    fingerprint: str = Field(min_length=16)
    entries: list[SourceEntryModel]


class RefusalModel(BaseModel):
    """One thing the import would not do, and why (`IMP-05`)."""

    reference: str
    date: date | None
    code: str
    detail: str


class PostEntriesResponse(BaseModel):
    """Never sum `posted` and `replayed`: they answer different questions.

    An operator re-running an import wants to see `replayed` rise and `posted` stay at zero.
    That is the retry working, not the file half-importing.
    """

    posted: int
    replayed: int
    refusals: list[RefusalModel] = Field(default_factory=list)


class StatedTotalModel(BaseModel):
    """What the source's raw journal says it sums to.

    The only figure in an accounting export that carries no basis, because a journal is the
    record rather than a view of one — so this comparison holds whatever basis the reports
    beside it were run on (ADR-0050).
    """

    debits: Money
    credits: Money


class ReconcileImportRequest(BaseModel):
    """The figures the source states for itself, for `IMP-08`'s comparison."""

    balances: list[StatedBalanceModel] = Field(default_factory=list)
    journal_total: StatedTotalModel | None = Field(
        default=None,
        description="The total the source prints on its own raw journal. Omitted where it"
        " prints none — never computed, because summing the rows and comparing that against"
        " the books they were loaded into is our arithmetic against itself.",
    )
    statements: list[StatedStatementModel] = Field(default_factory=list)
    since: date | None = Field(
        default=None,
        description="Start of the period the statements cover. Omitted means all dates, which"
        " is what a source's own reports are usually run over — and the period must match, or"
        " the figures differ for a reason that says nothing about correctness.",
    )
    as_of: date | None = Field(
        default=None, description="End of that period. Omitted means all dates."
    )


class DivergenceModel(BaseModel):
    account_code: str
    ours: Money
    theirs: Money


class StatementComparisonModel(BaseModel):
    report: str
    their_basis: str
    our_basis: str
    agreed: int
    divergences: list[DivergenceModel] = Field(default_factory=list)
    only_ours: list[str] = Field(default_factory=list)
    only_theirs: list[str] = Field(default_factory=list)
    unmatched: list[str] = Field(default_factory=list)


class TotalAgreementModel(BaseModel):
    """`IMP-08`'s "totals" half. Basis-free, and blind to which account a row landed in."""

    stated_debits: Money
    stated_credits: Money
    our_debits: Money
    our_credits: Money
    agrees: bool
    difference: Money


class ReconcileImportResponse(BaseModel):
    """One recorded reconciliation. No tolerance: `NFR-01`, "a tolerance is a defect, not a
    target"."""

    reconciliation_id: str
    import_id: str
    recorded_at: datetime
    since: date | None = Field(description="Start of the period compared. Null is all dates.")
    as_of: date | None = Field(description="End of the period compared. Null is all dates.")
    agreed: int
    compared: int
    journal_total: TotalAgreementModel | None = Field(
        default=None,
        description="Our totals against the one the source states for its raw journal. Null"
        " where the source printed none.",
    )
    divergences_net_to_zero: bool = Field(
        default=True,
        description="Whether the divergences are consistent with an accounting-basis"
        " difference. Cash basis excludes whole transactions, so the difference between an"
        " accrual journal and a cash-basis report sums to zero in posting signs. False means"
        " the difference is not the basis and is a defect.",
    )
    divergences: list[DivergenceModel] = Field(default_factory=list)
    statements: list[StatementComparisonModel] = Field(default_factory=list)


class ImportReconciliationsResponse(BaseModel):
    reconciliations: list[ReconcileImportResponse] = Field(
        description="Newest first. The first for an import is its current answer."
    )


router = APIRouter(tags=["import"])


@router.post(
    "/entities/{entity_id}/imports",
    summary="Open an import and create the chart it needs",
    status_code=201,
    responses=ERRORS,
)
def open_import(
    entity_id: str,
    body: OpenImportRequest,
    acting: Annotated[Principal, Depends(get_principal)],
    database: Annotated[Database, Depends(get_database)],
    request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> OpenImportResponse:
    """Create every account the source uses that this entity lacks (`IMP-01`).

    A person's act, never a delegated agent's (ADR-0007): an agent session is refused with
    `not_a_person` and should ask the person it acts for.

    Refused outright where the source's basis conflicts with the entity's declared one
    (`IMP-06`) or its commodity is not the entity's (`IMP-07`). Both are read from the entity
    rather than taken from the body — a caller who could state them could state its way past the
    refusal.

    Safe to repeat: an account already present is skipped, so a client retrying this step
    creates nothing twice.
    """
    opened = open_books(
        database,
        entity_id=entity_id,
        principal=acting,
        request_id=request_id or f"req-{uuid.uuid4().hex}",
        books=_shape(body),
    )
    return OpenImportResponse(
        import_id=opened.import_id,
        accounts_created=opened.accounts_created,
        accounts_already_present=opened.accounts_already_present,
    )


@router.post(
    "/entities/{entity_id}/imports/{import_id}/entries",
    summary="Post one batch of a source's transactions",
    responses=ERRORS,
)
def post_import_entries(
    entity_id: str,
    import_id: str,
    body: PostEntriesRequest,
    acting: Annotated[Principal, Depends(get_principal)],
    database: Annotated[Database, Depends(get_database)],
    request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> PostEntriesResponse:
    """Each entry is a write through the ledger's ordinary path (`IMP-02`, `IMP-04`).

    **Safe to retry.** Every entry's idempotency key is derived from the file's fingerprint and
    the source's own reference, so a batch sent twice is a replay rather than a second set of
    books (ADR-0029) — which is what lets a client that dies mid-import resume by sending the
    same batches again. `replayed` counts what a previous attempt had already done, and is never
    summed with `posted`.

    `import_id` must be the one this fingerprint yields. It is derived rather than stored, so
    this is a check that the caller is continuing the import it opened rather than a lookup.

    A row this cannot post is reported and the rest of the batch proceeds: `IMP-05` asks for an
    import that skips a malformed row rather than abandoning eleven thousand good ones.
    """
    if import_id != import_id_for(body.fingerprint):
        raise ImportRefused(
            "this import id does not belong to that fingerprint; open the import first"
        )
    done = post_entries(
        database,
        entity_id=entity_id,
        principal=acting,
        request_id=request_id or f"req-{uuid.uuid4().hex}",
        system=body.system,
        fingerprint=body.fingerprint,
        entries=[
            SourceEntry(
                reference=entry.reference,
                transaction_date=entry.transaction_date,
                description=entry.description,
                lines=tuple(
                    SourceLine(
                        account_code=line.account_code,
                        amount=line.amount,
                        commodity=line.commodity,
                    )
                    for line in entry.lines
                ),
            )
            for entry in body.entries
        ],
    )
    return PostEntriesResponse(
        posted=done.posted,
        replayed=done.replayed,
        refusals=[_refusal(refusal) for refusal in done.refusals],
    )


@router.post(
    "/entities/{entity_id}/imports/{import_id}/reconciliation",
    summary="Compare the imported books against the figures the source states, and record it",
    status_code=201,
    responses=ERRORS,
)
def reconcile_import(
    entity_id: str,
    import_id: str,
    body: ReconcileImportRequest,
    acting: Annotated[Principal, Depends(get_principal)],
    database: Annotated[Database, Depends(get_database)],
    request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> ReconcileImportResponse:
    """`IMP-08`, and the reason any of this is trustworthy.

    Agreement is demonstrated against the balances the source states **for itself**, not against
    a sum computed from the same journal that was just loaded — that would be our arithmetic
    against itself (`NFR-01`).

    **Recorded with the import**, so a later conversation explains what the person was shown
    rather than a comparison rerun against books that have moved on. A person's act, like the
    import it finishes; an agent reads it from `GET …/imports/reconciliations`. Run again, it
    records again beside the first.

    No tolerance. Where the source's statements were run on a different basis from its
    journal, the obligation accounts differ by exactly what is unsettled — ADR-0037
    predicts it, and it is reported as a divergence rather than absorbed.
    """
    reports = [statement.report for statement in body.statements]
    if len(set(reports)) != len(reports):
        raise ImportRefused(
            "a reconciliation takes one statement of each report; send each report once"
        )
    books = SourceBooks(
        system="",
        fingerprint="",
        basis="unknown",
        balances_basis="unknown",
        commodity="",
        balances=tuple(
            StatedBalance(account_code=line.account_code, balance=line.balance)
            for line in body.balances
        ),
        journal_total=(
            None
            if body.journal_total is None
            else StatedTotal(
                debits=body.journal_total.debits, credits=body.journal_total.credits
            )
        ),
        statements=tuple(
            StatedStatement(
                report=statement.report,
                basis=statement.basis,
                lines=tuple(
                    StatedBalance(account_code=line.account_code, balance=line.balance)
                    for line in statement.lines
                ),
                unmatched=tuple(statement.unmatched),
            )
            for statement in body.statements
        ),
    )
    return _rendered(
        record_reconciliation(
            database,
            entity_id=entity_id,
            principal=acting,
            request_id=request_id or f"req-{uuid.uuid4().hex}",
            import_id=import_id,
            books=books,
            since=body.since,
            as_of=body.as_of,
        )
    )


@router.get(
    "/entities/{entity_id}/imports/reconciliations",
    summary="The reconciliations recorded for this entity's imports",
    responses=ERRORS,
)
def import_reconciliations(
    entity_id: str,
    acting: Annotated[Principal, Depends(get_principal)],
    database: Annotated[Database, Depends(get_database)],
) -> ImportReconciliationsResponse:
    """What each import was reconciled to when it finished: whether the books match the
    source, and where they do not. A read."""
    return ImportReconciliationsResponse(
        reconciliations=[
            _rendered(found)
            for found in reconciliations(database, entity_id=entity_id, principal=acting)
        ]
    )


def _rendered(reconciled: Reconciled) -> ReconcileImportResponse:
    total = reconciled.total
    return ReconcileImportResponse(
        reconciliation_id=reconciled.id,
        import_id=reconciled.import_id,
        recorded_at=reconciled.recorded_at,
        since=reconciled.since,
        as_of=reconciled.as_of,
        agreed=reconciled.balances.agreed,
        compared=reconciled.balances.compared,
        journal_total=(
            None
            if total is None
            else TotalAgreementModel(
                stated_debits=total.stated_debits,
                stated_credits=total.stated_credits,
                our_debits=total.our_debits,
                our_credits=total.our_credits,
                agrees=total.agrees,
                difference=total.difference,
            )
        ),
        divergences_net_to_zero=reconciled.divergences_net_to_zero,
        divergences=_divergences(reconciled.balances.divergences),
        statements=[
            StatementComparisonModel(
                report=comparison.report,
                their_basis=comparison.their_basis,
                our_basis=comparison.our_basis,
                agreed=comparison.agreed,
                divergences=_divergences(comparison.divergences),
                only_ours=list(comparison.only_ours),
                only_theirs=list(comparison.only_theirs),
                unmatched=list(comparison.unmatched),
            )
            for comparison in reconciled.statements
        ],
    )


def _shape(body: OpenImportRequest) -> SourceBooks:
    """The opening call's body as the neutral shape, with no entries.

    `rollups` and `statements` are absent on purpose: a rollup is a subtotal nothing posts to,
    and a statement is compared at reconciliation rather than at opening.
    """
    return SourceBooks(
        system=body.system,
        fingerprint=body.fingerprint,
        basis=body.basis,
        balances_basis=body.balances_basis,
        commodity=body.commodity,
        accounts=tuple(
            SourceAccount(
                code=account.code,
                name=account.name,
                account_type=account.account_type,
                parent=account.parent,
            )
            for account in body.accounts
        ),
    )


def _refusal(refusal: Refusal) -> RefusalModel:
    return RefusalModel(
        reference=refusal.reference,
        date=refusal.when,
        code=refusal.code,
        detail=refusal.detail,
    )


def _divergences(found: Iterable[tuple[str, Decimal, Decimal]]) -> list[DivergenceModel]:
    return [
        DivergenceModel(account_code=code, ours=ours, theirs=theirs)
        for code, ours, theirs in found
    ]
