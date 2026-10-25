"""The events a business is written as: the seam between the generator and any adapter.

Business terms only. An amount is a `Decimal` and, written out, a decimal string; a reference is
a key the generator chose (`"harbor-dental"`, `"inv-harbor-dental-2023-07"`), never an
identifier a platform assigned. A line amount in a journal is signed, debit positive.

The set of kinds is closed. A case the kinds cannot express gets a new kind, reviewed, not a
free-form field on an existing one.
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import ClassVar, Literal

AccountType = Literal[
    "bank",
    "other_current_asset",
    "credit_card",
    "fixed_asset",
    "other_current_liability",
    "long_term_liability",
    "equity",
    "income",
    "other_income",
    "cost_of_sales",
    "expense",
    "other_expense",
]

# A payment from a customer goes into a bank account, or is held to be banked later with others.
HELD = "held"

# Accounts every set of books has without opening them, named by what they are for.
RECEIVABLE = "receivable"
PAYABLE = "payable"
RETAINED_EARNINGS = "retained-earnings"

type Json = bool | int | str | Decimal | list[Json] | dict[str, Json] | None


@dataclass(frozen=True, slots=True)
class Line:
    """An amount against an account, what it was for, and whose it is where that matters."""

    account: str
    amount: Decimal
    memo: str = ""
    customer: str | None = None


@dataclass(frozen=True, slots=True)
class SaleLine:
    """An amount charged for a service."""

    service: str
    amount: Decimal
    memo: str = ""


@dataclass(frozen=True, slots=True)
class Applied:
    """An amount of one settlement applied to one document: an invoice, a bill, a credit."""

    target: str
    amount: Decimal


@dataclass(frozen=True, slots=True, kw_only=True)
class Event:
    on: date
    cases: tuple[str, ...] = ()

    KIND: ClassVar[str]


# --- The company ----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True, kw_only=True)
class SetFiscalYear(Event):
    KIND = "set_fiscal_year"
    start_month: int


@dataclass(frozen=True, slots=True, kw_only=True)
class OpenAccount(Event):
    KIND = "open_account"
    key: str
    name: str
    type: AccountType
    number: str = ""
    parent: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class RenameAccount(Event):
    KIND = "rename_account"
    account: str
    name: str


@dataclass(frozen=True, slots=True, kw_only=True)
class DeactivateAccount(Event):
    KIND = "deactivate_account"
    account: str


@dataclass(frozen=True, slots=True, kw_only=True)
class AddCustomer(Event):
    KIND = "add_customer"
    key: str
    name: str
    parent: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class AddVendor(Event):
    KIND = "add_vendor"
    key: str
    name: str


@dataclass(frozen=True, slots=True, kw_only=True)
class AddService(Event):
    KIND = "add_service"
    key: str
    name: str
    income_account: str


@dataclass(frozen=True, slots=True, kw_only=True)
class OpenBalances(Event):
    """What the company held on its first day. Whatever balances them is the owners' equity."""

    KIND = "open_balances"
    lines: tuple[Line, ...]


# --- Selling --------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True, kw_only=True)
class IssueInvoice(Event):
    KIND = "issue_invoice"
    key: str
    customer: str
    due: date
    lines: tuple[SaleLine, ...]
    number: str = ""


@dataclass(frozen=True, slots=True, kw_only=True)
class IssueQuote(Event):
    """An estimate offered to a customer. Nothing is owed, so nothing is booked."""

    KIND = "issue_quote"
    key: str
    customer: str
    lines: tuple[SaleLine, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class Void(Event):
    """An invoice or payment canceled in place: it stays on record, worth nothing."""

    KIND = "void"
    target: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ReceivePayment(Event):
    """Money from a customer. What `amount` exceeds the applied total is left as credit."""

    KIND = "receive_payment"
    key: str
    customer: str
    amount: Decimal
    applies: tuple[Applied, ...]
    into: str


@dataclass(frozen=True, slots=True, kw_only=True)
class BankDeposit(Event):
    """Held payments banked together, and any other money paid in with them."""

    KIND = "bank_deposit"
    key: str
    into: str
    payments: tuple[Applied, ...] = ()
    lines: tuple[Line, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class CashSale(Event):
    KIND = "cash_sale"
    key: str
    customer: str | None
    into: str
    lines: tuple[SaleLine, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class IssueCredit(Event):
    """A credit to a customer, applied against one of their open invoices where one is named."""

    KIND = "issue_credit"
    key: str
    customer: str
    lines: tuple[SaleLine, ...]
    applies_to: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class RefundCustomer(Event):
    KIND = "refund_customer"
    key: str
    customer: str | None
    out_of: str
    lines: tuple[SaleLine, ...]


# --- Buying ---------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True, kw_only=True)
class ReceiveBill(Event):
    KIND = "receive_bill"
    key: str
    vendor: str
    number: str
    due: date
    lines: tuple[Line, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class PlaceOrder(Event):
    """A purchase order to a supplier. Nothing is owed until the bill, so nothing is booked."""

    KIND = "place_order"
    key: str
    vendor: str
    lines: tuple[Line, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class VendorCredit(Event):
    KIND = "vendor_credit"
    key: str
    vendor: str
    lines: tuple[Line, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class PayBills(Event):
    """One check settling bills from one vendor, less any of their credits taken against it."""

    KIND = "pay_bills"
    key: str
    vendor: str
    out_of: str
    bills: tuple[Applied, ...]
    credits: tuple[Applied, ...] = ()
    number: str = ""


@dataclass(frozen=True, slots=True, kw_only=True)
class Pay(Event):
    """Money spent at the time it was spent: by check, by debit card, or on a credit card."""

    KIND = "pay"
    key: str
    by: Literal["check", "debit", "card"]
    out_of: str
    payee: str | None
    lines: tuple[Line, ...]
    number: str = ""


@dataclass(frozen=True, slots=True, kw_only=True)
class CardRefund(Event):
    """A merchant's refund back onto a credit card."""

    KIND = "card_refund"
    key: str
    card: str
    payee: str | None
    lines: tuple[Line, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class Transfer(Event):
    KIND = "transfer"
    key: str
    out_of: str
    into: str
    amount: Decimal
    memo: str = ""


@dataclass(frozen=True, slots=True, kw_only=True)
class Journal(Event):
    """An entry made directly, such as a payroll provider's run. Signed, debit positive."""

    KIND = "journal"
    key: str
    memo: str
    lines: tuple[Line, ...]


def record(event_id: str, event: Event) -> dict[str, Json]:
    """One event as written out: its id, date and kind, then its own fields, then its cases."""
    out: dict[str, Json] = {"id": event_id, "date": event.on.isoformat(), "kind": event.KIND}
    for field in dataclasses.fields(event):
        if field.name not in ("on", "cases"):
            out[field.name] = _plain(getattr(event, field.name))
    out["cases"] = list(event.cases)
    return out


def _plain(value: object) -> Json:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: _plain(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if value is None or isinstance(value, bool | int | str):
        return value
    raise TypeError(f"no written form for {type(value).__name__}")


def dumps(value: Json) -> str:
    """JSON with a `Decimal` written as its exact digits: no amount passes through a float."""
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, dict):
        return "{" + ",".join(f"{dumps(k)}:{dumps(v)}" for k, v in value.items()) + "}"
    if isinstance(value, list):
        return "[" + ",".join(dumps(item) for item in value) + "]"
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    return json.dumps(value, ensure_ascii=False)
