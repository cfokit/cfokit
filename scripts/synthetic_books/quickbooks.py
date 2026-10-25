"""The QuickBooks Online adapter: business events in, API payloads out. Nothing else.

Each payload is one call against the QuickBooks Online Accounting API (v3):

* `entity` — the API entity, as in `POST /v3/company/{realm}/{entity lowercased}`.
* `operation` — `create`, `update` (a sparse update), `void`, or `require`: settings the API
  accepts and ignores, which a person makes in QuickBooks and whoever posts checks before going
  on. An update or void needs the entity's current `SyncToken`, which whoever posts the payload
  reads first; none is written here.
* `defines` — the reference a created entity answers to from then on, such as `"invoice:inv-…"`.
* `body` — the request body, with two placeholders for identifiers QuickBooks assigns: an object
  carrying `"$ref": "kind:key"` becomes a reference, its `$ref` key replaced by `"value": <id>`
  and its other keys kept; a bare `{"$id": "kind:key"}` becomes the id itself, as a linked
  transaction's `TxnId` needs. `system:<AccountSubType>` names an account QuickBooks creates
  itself, found by its subtype; `default:<Name>` names one a new company starts with, found by
  its name.

The payload's `id` is sent as QuickBooks' `requestid`, so posting the same payload twice is a
replay rather than a second transaction.

Amounts are `Decimal` and are written as JSON numbers with their exact digits.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from decimal import Decimal

from synthetic_books.events import (
    HELD,
    PAYABLE,
    RECEIVABLE,
    RETAINED_EARNINGS,
    AccountType,
    AddCustomer,
    AddService,
    AddVendor,
    Applied,
    BankDeposit,
    CardRefund,
    CashSale,
    DeactivateAccount,
    Event,
    IssueCredit,
    IssueInvoice,
    IssueQuote,
    Journal,
    Json,
    Line,
    OpenAccount,
    OpenBalances,
    Pay,
    PayBills,
    PlaceOrder,
    ReceiveBill,
    ReceivePayment,
    RefundCustomer,
    RenameAccount,
    SaleLine,
    SetFiscalYear,
    Transfer,
    VendorCredit,
    Void,
)

ACCOUNT_TYPES: dict[AccountType, str] = {
    "bank": "Bank",
    "other_current_asset": "Other Current Asset",
    "credit_card": "Credit Card",
    "fixed_asset": "Fixed Asset",
    "other_current_liability": "Other Current Liability",
    "long_term_liability": "Long Term Liability",
    "equity": "Equity",
    "income": "Income",
    "other_income": "Other Income",
    "cost_of_sales": "Cost of Goods Sold",
    "expense": "Expense",
    "other_expense": "Other Expense",
}

# The detail type an account is given where QuickBooks' own choice will not do. It refuses a
# fixed asset without one; an equity account it would make the company's one Opening Balance
# Equity. For every other type it picks one itself, and no report prints it.
DETAIL_TYPES: dict[AccountType, str] = {
    "fixed_asset": "MachineryAndEquipment",
    "equity": "OwnersEquity",
}

MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)

# The chart a new company starts with, as a cleared US sandbox company holds it, less the two
# accounts found by subtype. An account the events open under one of these names is this one,
# numbered, because QuickBooks refuses a second account of the same name.
DEFAULT_CHART: dict[str, AccountType] = {
    "Prepaid Expenses": "other_current_asset",
    "Uncategorized Asset": "other_current_asset",
    "Billable Expense Income": "income",
    "Discounts": "income",
    "Gross Receipts": "income",
    "Refunds-Allowances": "income",
    "Sales": "income",
    "Services": "income",
    "Uncategorized Income": "income",
    "Advertising": "expense",
    "Bank Charges": "expense",
    "Commissions & fees": "expense",
    "Disposal Fees": "expense",
    "Dues & Subscriptions": "expense",
    "Insurance": "expense",
    "Insurance - Liability": "expense",
    "Legal & Professional Fees": "expense",
    "Meals and Entertainment": "expense",
    "Office Expenses": "expense",
    "Promotional": "expense",
    "Rent or Lease": "expense",
    "Repair & Maintenance": "expense",
    "Stationery & Printing": "expense",
    "Supplies": "expense",
    "Taxes & Licenses": "expense",
    "Tools": "expense",
    "Travel": "expense",
    "Travel Meals": "expense",
    "Uncategorized Expense": "expense",
    "Utilities": "expense",
    "Interest Earned": "other_income",
    "Other Portfolio Income": "other_income",
    "Miscellaneous": "other_expense",
    "Penalties & Settlements": "other_expense",
}

# Accounts QuickBooks creates for itself, found by subtype rather than created here.
UNDEPOSITED_FUNDS = "system:UndepositedFunds"
OPENING_BALANCE_EQUITY = "system:OpeningBalanceEquity"
SYSTEM = {
    HELD: UNDEPOSITED_FUNDS,
    RECEIVABLE: "system:AccountsReceivable",
    PAYABLE: "system:AccountsPayable",
    RETAINED_EARNINGS: "system:RetainedEarnings",
}

# The entity a voided document was created as, from its key's prefix.
VOIDABLE = {"inv": "Invoice", "pmt": "Payment"}


@dataclass(frozen=True, slots=True)
class Payload:
    id: str
    event: str
    entity: str
    operation: str
    body: dict[str, Json]
    defines: str | None = None

    def record(self) -> dict[str, Json]:
        return {
            "id": self.id,
            "event": self.event,
            "entity": self.entity,
            "operation": self.operation,
            "defines": self.defines,
            "body": self.body,
        }


def ref(target: str, **extra: Json) -> dict[str, Json]:
    return {"$ref": target, **extra}


def txn(target: str) -> dict[str, Json]:
    return {"$id": target}


def account(key: str) -> dict[str, Json]:
    if key in SYSTEM:
        return ref(SYSTEM[key])
    return ref(key if key.startswith("system:") else f"account:{key}")


def _sale_lines(lines: Sequence[SaleLine]) -> list[Json]:
    return [
        {
            "DetailType": "SalesItemLineDetail",
            "Amount": line.amount,
            "Description": line.memo,
            "SalesItemLineDetail": {
                "ItemRef": ref(f"item:{line.service}"),
                "Qty": 1,
                "UnitPrice": line.amount,
            },
        }
        for line in lines
    ]


def _expense_lines(lines: Sequence[Line]) -> list[Json]:
    return [
        {
            "DetailType": "AccountBasedExpenseLineDetail",
            "Amount": line.amount,
            "Description": line.memo,
            "AccountBasedExpenseLineDetail": {"AccountRef": account(line.account)},
        }
        for line in lines
    ]


def _journal_lines(lines: Sequence[Line]) -> list[Json]:
    out: list[Json] = []
    for line in lines:
        detail: dict[str, Json] = {
            "PostingType": "Debit" if line.amount > 0 else "Credit",
            "AccountRef": account(line.account),
        }
        if line.customer is not None:
            # A line on A/R must name whose receivable it is.
            detail["Entity"] = {
                "Type": "Customer",
                "EntityRef": ref(f"customer:{line.customer}"),
            }
        out.append(
            {
                "DetailType": "JournalEntryLineDetail",
                "Amount": abs(line.amount),
                "Description": line.memo,
                "JournalEntryLineDetail": detail,
            }
        )
    return out


def _linked(applied: Sequence[Applied], kind: str, txn_type: str) -> list[Json]:
    return [
        {
            "Amount": item.amount,
            "LinkedTxn": [{"TxnId": txn(f"{kind}:{item.target}"), "TxnType": txn_type}],
        }
        for item in applied
    ]


def _vendor(payee: str | None) -> dict[str, Json]:
    return {} if payee is None else {"EntityRef": ref(f"vendor:{payee}", type="Vendor")}


def _calls(event: Event) -> Iterator[tuple[str, str, dict[str, Json], str | None]]:
    """The calls one event becomes: (entity, operation, body, the reference it defines)."""
    day = event.on.isoformat()
    match event:
        case SetFiscalYear(start_month=month):
            # The company's settings. Beside the fiscal year the event names, QuickBooks is made
            # to keep what the events say and add nothing of its own: the numbers they give
            # accounts and documents, and no credit applied unless an event applies it. Whether
            # numbers print is a rendering's choice, made when a report is run. The API ignores
            # all of these but custom numbering, so the rest are required, not sent.
            yield (
                "Preferences",
                "require",
                {
                    "AccountingInfoPrefs": {
                        "FirstMonthOfFiscalYear": MONTHS[month - 1],
                        "UseAccountNumbers": True,
                    },
                    "SalesFormsPrefs": {"AutoApplyCredit": False},
                },
                None,
            )
            yield "Preferences", "update", {"SalesFormsPrefs": {"CustomTxnNumbers": True}}, None
        case OpenAccount(key=key, name=name, type=kind, number=number, parent=None) if (
            name in DEFAULT_CHART
        ):
            if DEFAULT_CHART[name] != kind:
                raise ValueError(f"{name} is a QuickBooks default of another type; escalate")
            body: dict[str, Json] = {"Id": txn(f"default:{name}"), "Name": name}
            if number:
                body["AcctNum"] = number
            yield "Account", "update", body, f"account:{key}"
        case OpenAccount(key=key, name=name, type=kind, number=number, parent=parent):
            body = {"Name": name, "AccountType": ACCOUNT_TYPES[kind]}
            if kind in DETAIL_TYPES:
                body["AccountSubType"] = DETAIL_TYPES[kind]
            if number:
                body["AcctNum"] = number
            if parent is not None:
                body |= {"SubAccount": True, "ParentRef": ref(f"account:{parent}")}
            yield "Account", "create", body, f"account:{key}"
        case RenameAccount(account=key, name=name):
            yield "Account", "update", {"Id": txn(f"account:{key}"), "Name": name}, None
        case DeactivateAccount(account=key):
            yield "Account", "update", {"Id": txn(f"account:{key}"), "Active": False}, None
        case AddCustomer(key=key, name=name, parent=parent):
            body = {"DisplayName": name}
            if parent is not None:
                body |= {"Job": True, "ParentRef": ref(f"customer:{parent}")}
            yield "Customer", "create", body, f"customer:{key}"
        case AddVendor(key=key, name=name):
            yield "Vendor", "create", {"DisplayName": name}, f"vendor:{key}"
        case AddService(key=key, name=name, income_account=income):
            yield (
                "Item",
                "create",
                {"Name": name, "Type": "Service", "IncomeAccountRef": account(income)},
                f"item:{key}",
            )
        case OpenBalances(lines=lines):
            equity = -sum((line.amount for line in lines), Decimal(0))
            balanced = (*lines, Line(OPENING_BALANCE_EQUITY, equity, "Opening balance"))
            # QuickBooks creates this account when an opening balance is first entered; a new
            # company has none, so it is created here, as QuickBooks would type it.
            yield (
                "Account",
                "create",
                {
                    "Name": "Opening Balance Equity",
                    "AccountType": "Equity",
                    "AccountSubType": "OpeningBalanceEquity",
                },
                OPENING_BALANCE_EQUITY,
            )
            yield (
                "JournalEntry",
                "create",
                {"TxnDate": day, "Line": _journal_lines(balanced)},
                None,
            )
        case IssueInvoice(key=key, customer=customer, due=due, lines=lines, number=number):
            yield (
                "Invoice",
                "create",
                {
                    "CustomerRef": ref(f"customer:{customer}"),
                    "TxnDate": day,
                    "DueDate": due.isoformat(),
                    "DocNumber": number,
                    "Line": _sale_lines(lines),
                },
                f"invoice:{key}",
            )
        case IssueQuote(key=key, customer=customer, lines=lines):
            yield (
                "Estimate",
                "create",
                {
                    "CustomerRef": ref(f"customer:{customer}"),
                    "TxnDate": day,
                    "Line": _sale_lines(lines),
                },
                f"estimate:{key}",
            )
        case PlaceOrder(key=key, vendor=vendor, lines=lines):
            yield (
                "PurchaseOrder",
                "create",
                {
                    "VendorRef": ref(f"vendor:{vendor}"),
                    "TxnDate": day,
                    "Line": _expense_lines(lines),
                },
                f"purchaseorder:{key}",
            )
        case Void(target=target):
            entity = VOIDABLE[target.split("-", 1)[0]]
            yield entity, "void", {"Id": txn(f"{entity.lower()}:{target}")}, None
        case ReceivePayment(
            key=key, customer=customer, amount=amount, applies=applies, into=into
        ):
            yield (
                "Payment",
                "create",
                {
                    "CustomerRef": ref(f"customer:{customer}"),
                    "TxnDate": day,
                    "TotalAmt": amount,
                    "DepositToAccountRef": account(into),
                    "Line": _linked(applies, "invoice", "Invoice"),
                },
                f"payment:{key}",
            )
        case BankDeposit(into=into, payments=payments, lines=lines):
            deposit_lines: list[Json] = [
                {
                    "Amount": item.amount,
                    "LinkedTxn": [
                        {
                            "TxnId": txn(f"payment:{item.target}"),
                            "TxnType": "Payment",
                            "TxnLineId": "0",
                        }
                    ],
                }
                for item in payments
            ]
            deposit_lines += [
                {
                    "DetailType": "DepositLineDetail",
                    "Amount": line.amount,
                    "Description": line.memo,
                    "DepositLineDetail": {"AccountRef": account(line.account)},
                }
                for line in lines
            ]
            yield (
                "Deposit",
                "create",
                {"TxnDate": day, "DepositToAccountRef": account(into), "Line": deposit_lines},
                None,
            )
        case CashSale(customer=customer, into=into, lines=lines):
            yield (
                "SalesReceipt",
                "create",
                {
                    **_customer(customer),
                    "TxnDate": day,
                    "DepositToAccountRef": account(into),
                    "Line": _sale_lines(lines),
                },
                None,
            )
        case IssueCredit(key=key, customer=customer, lines=lines, applies_to=invoice):
            yield (
                "CreditMemo",
                "create",
                {
                    "CustomerRef": ref(f"customer:{customer}"),
                    "TxnDate": day,
                    "Line": _sale_lines(lines),
                },
                f"creditmemo:{key}",
            )
            if invoice is not None:
                # QuickBooks applies a credit memo to an invoice through a payment of nothing.
                credited = sum((line.amount for line in lines), Decimal(0))
                yield (
                    "Payment",
                    "create",
                    {
                        "CustomerRef": ref(f"customer:{customer}"),
                        "TxnDate": day,
                        "TotalAmt": Decimal(0),
                        "Line": [
                            *_linked([Applied(invoice, credited)], "invoice", "Invoice"),
                            *_linked([Applied(key, credited)], "creditmemo", "CreditMemo"),
                        ],
                    },
                    None,
                )
        case RefundCustomer(customer=customer, out_of=out_of, lines=lines):
            yield (
                "RefundReceipt",
                "create",
                {
                    **_customer(customer),
                    "TxnDate": day,
                    "DepositToAccountRef": account(out_of),
                    "Line": _sale_lines(lines),
                },
                None,
            )
        case ReceiveBill(key=key, vendor=vendor, number=number, due=due, lines=lines):
            yield (
                "Bill",
                "create",
                {
                    "VendorRef": ref(f"vendor:{vendor}"),
                    "TxnDate": day,
                    "DueDate": due.isoformat(),
                    "DocNumber": number,
                    "Line": _expense_lines(lines),
                },
                f"bill:{key}",
            )
        case VendorCredit(key=key, vendor=vendor, lines=lines):
            yield (
                "VendorCredit",
                "create",
                {
                    "VendorRef": ref(f"vendor:{vendor}"),
                    "TxnDate": day,
                    "Line": _expense_lines(lines),
                },
                f"vendorcredit:{key}",
            )
        case PayBills(
            vendor=vendor, out_of=out_of, bills=bills, credits=credits, number=number
        ):
            total = sum((b.amount for b in bills), Decimal(0)) - sum(
                (c.amount for c in credits), Decimal(0)
            )
            yield (
                "BillPayment",
                "create",
                {
                    "VendorRef": ref(f"vendor:{vendor}"),
                    "TxnDate": day,
                    "DocNumber": number,
                    "PayType": "Check",
                    "TotalAmt": total,
                    "CheckPayment": {"BankAccountRef": account(out_of)},
                    "Line": [
                        *_linked(bills, "bill", "Bill"),
                        *_linked(credits, "vendorcredit", "VendorCredit"),
                    ],
                },
                None,
            )
        case Pay(by=by, out_of=out_of, payee=payee, lines=lines, number=number):
            body = {
                "PaymentType": {"check": "Check", "debit": "Cash", "card": "CreditCard"}[by],
                "AccountRef": account(out_of),
                **_vendor(payee),
                "TxnDate": day,
                "Line": _expense_lines(lines),
            }
            if number:
                body["DocNumber"] = number
            yield "Purchase", "create", body, None
        case CardRefund(card=card, payee=payee, lines=lines):
            yield (
                "Purchase",
                "create",
                {
                    "PaymentType": "CreditCard",
                    "Credit": True,
                    "AccountRef": account(card),
                    **_vendor(payee),
                    "TxnDate": day,
                    "Line": _expense_lines(lines),
                },
                None,
            )
        case Transfer(out_of=out_of, into=into, amount=amount, memo=memo):
            yield (
                "Transfer",
                "create",
                {
                    "FromAccountRef": account(out_of),
                    "ToAccountRef": account(into),
                    "Amount": amount,
                    "TxnDate": day,
                    "PrivateNote": memo,
                },
                None,
            )
        case Journal(memo=memo, lines=lines):
            yield (
                "JournalEntry",
                "create",
                {"TxnDate": day, "PrivateNote": memo, "Line": _journal_lines(lines)},
                None,
            )
        case _:
            raise TypeError(f"the QuickBooks adapter has no mapping for {event.KIND}")


def _customer(customer: str | None) -> dict[str, Json]:
    return {} if customer is None else {"CustomerRef": ref(f"customer:{customer}")}


def payloads(events: Sequence[tuple[str, Event]]) -> list[Payload]:
    """Every call the events become, in the order they must be made."""
    out: list[Payload] = []
    for event_id, event in events:
        for entity, operation, body, defines in _calls(event):
            out.append(
                Payload(
                    id=f"qbo-{len(out) + 1:05d}",
                    event=event_id,
                    entity=entity,
                    operation=operation,
                    body=body,
                    defines=defines,
                )
            )
    return out
