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
    administrator: str | None = Field(
        default=None,
        description="The entity's first administrator. Defaults to the creating principal; an "
        "entity never exists without one (IAM-05).",
    )


class EntityCreatedResponse(BaseModel):
    entity_id: str
    administrator_grant_id: str


class GrantRoleRequest(BaseModel):
    """Grant a role in this entity. Administrative only (IAM-03)."""

    principal_id: str
    role: Literal["reader", "recorder", "poster", "administrator"]
    lapses_at: datetime | None = Field(
        default=None,
        description="When the role lapses without anyone acting (IAM-09). Null is open-ended.",
    )


class GrantResponse(BaseModel):
    grant_id: str
