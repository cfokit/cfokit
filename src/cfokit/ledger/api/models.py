"""The REST wire format. A published interface with stability obligations (ADR-0015).

**Amounts are strings, and JSON numbers are refused.** A JSON number cannot carry scale:
`100.00` parses to `Decimal("100")`, losing the two decimal places the caller stated. The
idempotency digest is taken over the parameters as sent, so two spellings of the same value
would otherwise be two different requests — refusing the number is the only way to know what
was sent.

Storage does not preserve that scale, and is not meant to: every amount column is
`NUMERIC(28,10)`, so `100.00` is stored and read back as `100.0000000000`. That is `LED-06`
working rather than a loss — recorded amounts carry more precision than they are shown at,
and the display scale is applied where a figure is presented (ADR-0025).

Nothing here is a `float`, at any point, including in transit (ADR-0005).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, Field, WithJsonSchema

from cfokit.ledger.service.reports import Comparative

__all__ = [
    "CreateEntityRequest",
    "EntityCreatedResponse",
    "GrantResponse",
    "GrantRoleRequest",
    "Money",
    "PostingModel",
    "RecordTransactionRequest",
    "TransactionResponse",
]


def _decimal_string(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if not isinstance(value, str):
        raise ValueError(
            "amount must be a decimal string, not a JSON number: a number cannot carry the "
            "scale the amount was written at"
        )
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"not a decimal amount: {value!r}") from exc


Money = Annotated[
    Decimal,
    BeforeValidator(_decimal_string),
    WithJsonSchema({"type": "string", "examples": ["100.00", "-1250.5000000000"]}),
]


class PostingModel(BaseModel):
    """One side of a transaction. Positive is a debit, negative a credit."""

    account_id: str = Field(description="The account this posting hits.")
    amount: Money = Field(description="Signed decimal string. Positive debits the account.")
    commodity: str = Field(description="The unit the amount is denominated in, e.g. USD.")


class RecordTransactionRequest(BaseModel):
    """Record a transaction, as a draft or posted straight through."""

    transaction_date: date = Field(
        description="When the event economically occurred. Not when it was recorded — that is "
        "server-assigned and cannot be supplied."
    )
    postings: list[PostingModel] = Field(
        description="Every side of the transaction. Must sum to zero per commodity to post."
    )
    description: str | None = None
    raises_obligation: Money | None = Field(
        default=None,
        description="Record this transaction as raising an obligation of this amount (LED-17) "
        "— an invoice, or anything else owed. Requires post: a draft is not in the books.",
    )
    settles: list[AppliedModel] = Field(
        default_factory=list,
        description="Obligations this transaction settles, and by how much (AR-12). Partial "
        "payment and overpayment are both representable. Requires post.",
    )
    post: bool = Field(
        default=False,
        description="Post immediately. A draft is freely editable; posting is the point of no "
        "return.",
    )


class TransactionResponse(BaseModel):
    """A transaction as the books hold it."""

    id: str
    status: str
    transaction_date: date
    description: str | None
    reverses_id: str | None
    entry_kind: str
    actor_principal_id: str
    actor_class: str
    acting_for_principal_id: str | None
    postings: list[PostingModel]


class WriteResponse(BaseModel):
    """What a write produced."""

    transaction_id: str
    status: str
    replayed: bool = Field(
        description="True when this request replayed an earlier one with the same idempotency "
        "key. Nothing was booked a second time."
    )


class ErrorResponse(BaseModel):
    """Every error, on both adapters, in this shape.

    `code` is the contract; `message` is not and may be reworded at will (ADR-0015).
    """

    code: str
    message: str


class ConnectionResponse(BaseModel):
    mcp_url: str | None = Field(
        description="Where an agent connects to this deployment's MCP surface, or null when "
        "the REST service is not told (MCP_PUBLIC_BASE_URL)."
    )


class CreateEntityRequest(BaseModel):
    """Everything an entity declares at creation, all of it required.

    `LED-14` and `LED-15` say the basis, the fiscal year end and the functional currency have
    no undeclared state, and `PLT-08` says the same for the time zone. There are no defaults
    here for that reason: a default would be an undeclared state wearing a value.
    """

    slug: str = Field(description="Stable identifier, unique in this deployment.")
    name: str
    accounting_basis: Literal["cash", "accrual"] = Field(
        description="Fixes what every report defaults to. A property of the entity, not a "
        "per-report option, and never a posting rule (ADR-0037)."
    )
    fiscal_year_end_month: int = Field(ge=1, le=12)
    fiscal_year_end_day: int = Field(ge=1, le=31)
    functional_currency: str = Field(
        description="Amounts in any other commodity are refused until LED-16 activates."
    )
    time_zone: str = Field(description="Period boundaries are determined in it (PLT-08).")
    owner: str | None = Field(
        default=None,
        description="The entity's first owner. Defaults to the creating principal; an "
        "entity never exists without one (IAM-05).",
    )


class EntityCreatedResponse(BaseModel):
    entity_id: str
    owner_grant_id: str


class CreateAccountRequest(BaseModel):
    """Add an account to the entity's chart (LED-01, LED-02)."""

    code: str = Field(min_length=1)
    name: str = Field(min_length=1)
    account_type: Literal["asset", "liability", "equity", "income", "expense"] = Field(
        description="Fixed at creation and never changed (LED-02)."
    )
    parent_id: str | None = Field(default=None, description="Charts are hierarchical (LED-01).")
    opening_balance: bool = Field(
        default=False,
        description="Name this account as the one carried-in balances balance against "
        "(LED-10). Equity accounts only, and deliberately separate from retained earnings.",
    )
    retained_earnings: bool = Field(
        default=False,
        description="Name this account as the one a fiscal year closes to (LED-12). "
        "Equity accounts only.",
    )


class AccountCreatedResponse(BaseModel):
    account_id: str


class CloseYearRequest(BaseModel):
    """Close the fiscal year containing this date (LED-12).

    A date rather than a year, because a fiscal year is named by the calendar year its end
    falls in and the entity decides where that boundary sits.
    """

    day_in_year: date


class YearClosedResponse(BaseModel):
    fiscal_year: str
    transaction_id: str
    reversed_transaction_ids: list[str] = Field(
        description="Stale closing entries reversed by this run (ADR-0027). Empty for a first "
        "close."
    )


class TrialBalanceLineModel(BaseModel):
    """One line of a trial balance. Exactly one of debit or credit carries a figure."""

    account_id: str
    code: str
    name: str
    account_type: str
    debit: str | None = Field(
        default=None, description="Rounded to the commodity's display scale (RPT-12)."
    )
    credit: str | None = None


class TrialBalanceResponse(BaseModel):
    """A trial balance as of a date (RPT-01).

    Amounts are strings for the same reason they are on the way in: a JSON number cannot
    carry the scale the figure is presented at, and `100.00` would arrive as `100`.
    """

    as_of: date
    watermark: datetime | None = Field(
        default=None,
        description="The moment the books were reproduced as at, if one was asked for "
        "(RPT-11).",
    )
    accounting_basis: str = Field(
        description="Stated on the face of every report (RPT-10). Read from the entity, "
        "never from the caller."
    )
    commodity: str
    lines: list[TrialBalanceLineModel]
    total_debit: str
    total_credit: str
    balances: bool = Field(
        description="Whether the two columns agree. False means a posting is unbalanced, "
        "which the schema should have made impossible (ADR-0006)."
    )


class AccountEntryModel(BaseModel):
    """One movement against an account, with what it left the balance at (RPT-05).

    Carries the transaction and the principal that wrote it, which is where RPT-08's chain
    goes next and what LED-20 records.
    """

    transaction_id: str
    transaction_date: date
    description: str | None = None
    entry_kind: str
    reverses_id: str | None = None
    actor_principal_id: str
    actor_class: str
    acting_for_principal_id: str | None = None
    amount: str
    running_balance: str


class AccountDetailResponse(BaseModel):
    """One account's movements over a period, in order (RPT-05)."""

    account_id: str
    code: str
    name: str
    account_type: str
    since: date
    as_of: date
    watermark: datetime | None = None
    accounting_basis: str = Field(description="Stated on the face of every report (RPT-10).")
    commodity: str
    opening_balance: str = Field(
        description="What the account stood at before the period. Without it the running "
        "balance would show the right movements against the wrong figures."
    )
    closing_balance: str
    entries: list[AccountEntryModel]


class ComparativeLineModel(BaseModel):
    """One account across two periods, and what changed (RPT-07)."""

    account_id: str
    code: str
    name: str
    account_type: str
    current: str
    comparison: str
    variance: str = Field(
        description="Current less comparison, computed from the unrounded figures rather than "
        "by subtracting the two printed ones (RPT-12). Absolute: a percentage divides by the "
        "comparison, which is zero for every line that is new."
    )


class ComparativeProfitAndLossResponse(BaseModel):
    """A profit and loss beside the preceding period or the same period a year earlier."""

    comparative: Comparative
    since: date
    as_of: date
    comparison_since: date
    comparison_as_of: date
    watermark: datetime | None = None
    accounting_basis: str
    commodity: str
    income: list[ComparativeLineModel]
    expenses: list[ComparativeLineModel]
    total_income: ComparativeLineModel
    total_expenses: ComparativeLineModel
    net_income: ComparativeLineModel


class SourceBalanceModel(BaseModel):
    """One account's balance as the source system states it."""

    account_code: str
    balance: Money = Field(
        description="Signed the way a posting is: positive is a debit. Converting a foreign "
        "export's sign convention is the caller's job."
    )


class ReconcileRequest(BaseModel):
    """Compare our books against a source system's own figures (IMP-08)."""

    as_of: date
    balances: list[SourceBalanceModel] = Field(min_length=1)
    source_is_rounded: bool = Field(
        default=False,
        description="Round both sides once before comparing. Most exports carry rounded "
        "figures; comparing them against exact recorded values would disagree by design.",
    )
    watermark: datetime | None = None


class AccountComparisonModel(BaseModel):
    account_code: str
    ours: str | None = None
    theirs: str | None = None
    difference: str
    agrees: bool


class ReconciliationResponse(BaseModel):
    """Two figures per account and a difference — nothing about what a difference means.

    A comparison detects difference; it cannot say which side is wrong.
    """

    as_of: date
    watermark: datetime | None = None
    accounting_basis: str
    commodity: str
    source_is_rounded: bool
    agrees: bool
    comparisons: list[AccountComparisonModel]


class StatementLineModel(BaseModel):
    """One line of a statement, signed so positive means more of what the account is."""

    account_id: str
    code: str
    name: str
    account_type: str
    amount: str


class ProfitAndLossResponse(BaseModel):
    """Income and expense over a period (RPT-02)."""

    since: date
    as_of: date
    watermark: datetime | None = None
    accounting_basis: str = Field(description="Stated on the face of every report (RPT-10).")
    commodity: str
    income: list[StatementLineModel]
    expenses: list[StatementLineModel]
    total_income: str
    total_expenses: str
    net_income: str = Field(
        description="Computed from the unrounded totals, so it cannot drift a unit from the "
        "difference a reader takes by hand (RPT-12)."
    )


class BalanceSheetResponse(BaseModel):
    """Assets, liabilities and equity as of a date (RPT-03)."""

    as_of: date
    watermark: datetime | None = None
    accounting_basis: str = Field(description="Stated on the face of every report (RPT-10).")
    commodity: str
    assets: list[StatementLineModel]
    liabilities: list[StatementLineModel]
    equity: list[StatementLineModel]
    unclosed_earnings: str = Field(
        description="Income and expense not yet closed to retained earnings. LED-12 moves them "
        "only at a fiscal year end, so mid-year they are equity that has not been moved. "
        "Included in total_equity."
    )
    total_assets: str
    total_liabilities: str
    total_equity: str
    balances: bool = Field(
        description="Whether assets equal liabilities plus equity, which is what the statement "
        "asserts."
    )


class IssueStatementRequest(BaseModel):
    """Mark a statement issued, fixing what was reported, to whom, and when (RPT-17)."""

    report: Literal["trial_balance", "profit_and_loss", "balance_sheet"]
    as_of: date
    since: date | None = Field(
        default=None, description="The start of the window. Null for an as-of report."
    )
    issued_to: str = Field(
        min_length=1,
        description="A lender, a board, an accountant. Free text: the recipient is usually not "
        "a principal of this deployment, and inventing one for them would be wrong.",
    )
    figures: dict[str, Any] = Field(
        description="The rendered statement as the recipient received it. Stored rather than "
        "re-derived, because re-deriving assumes the presentation never changes and it will."
    )


class IssuedStatementModel(BaseModel):
    """A statement that was given to somebody, and whether it still holds."""

    issuance_id: str
    report: str
    since: date | None = None
    as_of: date
    watermark: datetime = Field(
        description="What the books stood at when it was produced. Re-running the report at "
        "this moment reproduces what was reported (RPT-11)."
    )
    issued_by: str
    issued_at: datetime
    issued_to: str
    superseded: bool = Field(
        description="Whether a posting entered this statement's window after it was issued, "
        "changing its figures (SOC1-20). Detected, never stored."
    )
    superseded_by: int = Field(description="How many such postings.")
    figures: dict[str, Any]


class IssuedStatementsResponse(BaseModel):
    statements: list[IssuedStatementModel]


class AppliedModel(BaseModel):
    """How much of a settlement goes against one obligation (AR-12)."""

    obligation_id: str
    amount: Money = Field(description="Signed decimal string, in the entity's currency.")


class ObligationModel(BaseModel):
    """A commitment to receive or pay, with what has been applied to it (LED-17)."""

    obligation_id: str
    transaction_id: str
    transaction_date: date
    amount: str
    settled: str
    outstanding: str = Field(
        description="Derived, never stored: the amount less what has been applied."
    )
    commodity: str


class SettlementModel(BaseModel):
    settlement_id: str
    transaction_id: str
    transaction_date: date
    amount: str
    commodity: str


class ObligationDetailResponse(BaseModel):
    """One obligation read as both events (LED-17)."""

    obligation: ObligationModel
    settlements: list[SettlementModel]


class OutstandingResponse(BaseModel):
    as_of: date | None = None
    obligations: list[ObligationModel]


class CarriedBalanceModel(BaseModel):
    """One account's balance as it stood in the system CFOKit is taking over from."""

    account_id: str
    amount: Money = Field(description="Signed decimal string. Positive debits the account.")
    commodity: str


class OpenBalancesRequest(BaseModel):
    """Carry balances in from before CFOKit held the books (LED-10).

    The equity side is not supplied: the ledger computes the counterweight, so an entry that
    does not balance is impossible rather than refused.
    """

    as_of: date = Field(
        description="The day the balances stood at — conventionally the day before the first "
        "period CFOKit keeps, so they sit outside every period it reports on."
    )
    balances: list[CarriedBalanceModel] = Field(min_length=1)


class OpenedBooksResponse(BaseModel):
    transaction_id: str
    as_of: date
    equity_amount: str = Field(
        description="What was posted to the opening balance account to make the entry balance."
    )


class ClosePeriodRequest(BaseModel):
    """Mark a period reviewed (LED-11)."""

    year: int = Field(ge=1, le=9999)
    month: int = Field(ge=1, le=12)


class ReopenPeriodRequest(ClosePeriodRequest):
    """Reopen a closed period (LED-11, ADR-0030).

    A person's act, never a skill's. `reason` is required: SOC1-17 asks the reopen to capture
    one, and a reopen without a reason is indistinguishable from a mistake afterwards.
    """

    reason: str = Field(min_length=1)


class PeriodCloseResponse(BaseModel):
    close_id: str


class GrantRoleRequest(BaseModel):
    """Grant a role in this entity. Administrative only (IAM-03)."""

    principal_id: str
    role: str = Field(
        description="A role name from this deployment's catalog. Roles are rows rather than "
        "a fixed enumeration, so the set is not enumerable here; an unknown name is refused "
        "with `unknown_role` (ADR-0039).",
    )
    lapses_at: datetime | None = Field(
        default=None,
        description="When the role lapses without anyone acting (IAM-09). Null is open-ended.",
    )


class GrantResponse(BaseModel):
    grant_id: str


class NotificationModel(BaseModel):
    """An open notification: identifiers and where it is answered, never a figure (ADR-0052)."""

    notification_id: str
    entity_id: str
    notification_class: str = Field(
        description="What kind of question it is, such as `unresolved_transaction`."
    )
    subject_ref: str = Field(description="What it is about, in the raising module's terms.")
    link: str = Field(
        description="Where it is answered: a path under this deployment's address."
    )
    raised_at: datetime


class NotificationsResponse(BaseModel):
    """The caller's open notifications. Closed ones stay in the entity's records and export."""

    notifications: list[NotificationModel]


class DismissalResponse(BaseModel):
    notification_id: str
    replayed: bool = False
