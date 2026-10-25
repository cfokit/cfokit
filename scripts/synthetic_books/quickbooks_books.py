"""What QuickBooks Online records for the events: its chart, and each transaction's lines.

The export writer renders reports from this, so this is where our belief about QuickBooks'
bookkeeping lives — which accounts an invoice touches, what a void leaves, how the cash basis
recognizes a part payment. **Every rule here is a belief until the sandbox agrees** (ADR-0075):
the validation run compares what these rules produce with what the Reports API returns for the
same postings, and a disagreement is fixed here.

Two views of the same transactions:

* **Accrual** is the journal as QuickBooks keeps it. Every report on the accrual basis is a sum
  of these lines, and the Journal report prints them whatever the basis.
* **Cash** recognizes an invoice or a bill only as it is paid, in proportion to the amount paid,
  dated with the payment. Everything that moves money directly is the same on both bases.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

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

OPENING_EQUITY = "opening-equity"
UNAPPLIED_INCOME = "unapplied-cash-payment-income"
CENT = Decimal("0.01")
ZERO = Decimal(0)

# Accounts QuickBooks keeps for itself: key -> (name, type).
SYSTEM_ACCOUNTS: dict[str, tuple[str, str]] = {
    RECEIVABLE: ("Accounts Receivable (A/R)", "receivable"),
    PAYABLE: ("Accounts Payable (A/P)", "payable"),
    HELD: ("Undeposited Funds", "other_current_asset"),
    OPENING_EQUITY: ("Opening Balance Equity", "equity"),
    RETAINED_EARNINGS: ("Retained Earnings", "equity"),
    # Only the cash basis posts here: it is where QuickBooks reports a payment no invoice took.
    UNAPPLIED_INCOME: ("Unapplied Cash Payment Income", "income"),
}


@dataclass(slots=True)
class Account:
    key: str
    name: str
    type: AccountType | str
    number: str = ""
    parent: str | None = None
    active: bool = True


@dataclass(frozen=True, slots=True)
class Posting:
    """One line of a transaction: signed, debit positive."""

    account: str
    amount: Decimal
    memo: str = ""
    name: str = ""
    # On the cash basis, the document a line recognizes part of, which the ledger shows it as.
    source: str | None = None


@dataclass(slots=True)
class Transaction:
    event: str
    on: date
    type: str  # as the Journal report labels it
    lines: list[Posting]
    number: str = ""
    name: str = ""
    voided: bool = False
    # What the cash basis needs: the document's own lines, and what it settles.
    document: str | None = None
    settles: tuple[Applied, ...] = ()
    unapplied: Decimal = ZERO
    deposit_account: str | None = None
    credits: tuple[Applied, ...] = ()


@dataclass(slots=True)
class Books:
    company: str
    fiscal_start_month: int
    accounts: dict[str, Account]
    transactions: list[Transaction] = field(default_factory=list)
    # Each invoice's, credit memo's, bill's and vendor credit's own lines, by document key, as
    # positive amounts of what the document is for. A discount line is negative.
    documents: dict[str, list[Posting]] = field(default_factory=dict)
    # The same documents as recorded, by key.
    sources: dict[str, Transaction] = field(default_factory=dict)

    def path(self, key: str, *, numbers: bool = False) -> str:
        """The account as every report names it: its full path, as it is called at the end."""
        account = self.accounts[key]
        own = f"{account.number} {account.name}" if numbers and account.number else account.name
        if not account.active:
            own += " (deleted)"
        return (
            own
            if account.parent is None
            else f"{self.path(account.parent, numbers=numbers)}:{own}"
        )


def allocate(amount: Decimal, lines: Sequence[Posting], total: Decimal) -> list[Posting]:
    """`amount` spread over `lines` in proportion to each line's share of `total`.

    Each share is rounded half up to the cent and the last line takes what remains, so the
    shares always sum to `amount` exactly.
    """
    out: list[Posting] = []
    remaining = amount
    for index, line in enumerate(lines):
        if index == len(lines) - 1:
            share = remaining
        else:
            share = (amount * line.amount / total).quantize(CENT, rounding=ROUND_HALF_UP)
            remaining -= share
        out.append(replace(line, amount=share))
    return out


class Recorder:
    """Turns events into QuickBooks' chart and transactions, in event order."""

    def __init__(self, company: str) -> None:
        self.books = Books(
            company=company,
            fiscal_start_month=1,
            accounts={k: Account(k, n, t) for k, (n, t) in SYSTEM_ACCOUNTS.items()},
        )
        self.customers: dict[str, str] = {}
        self.vendors: dict[str, str] = {}
        self.services: dict[str, str] = {}  # service -> income account
        self.by_key: dict[str, Transaction] = {}

    def name(self, customer: str | None) -> str:
        return "" if customer is None else self.customers[customer]

    def sale(self, lines: Sequence[SaleLine], sign: int, name: str) -> list[Posting]:
        return [
            Posting(self.services[line.service], sign * line.amount, line.memo, name)
            for line in lines
        ]

    def add(self, transaction: Transaction, key: str | None = None) -> None:
        self.books.transactions.append(transaction)
        if key is not None:
            self.by_key[key] = transaction
            if key in self.books.documents:
                self.books.sources[key] = transaction

    def record(self, event_id: str, event: Event) -> None:
        books, day = self.books, event.on
        match event:
            case SetFiscalYear(start_month=month):
                books.fiscal_start_month = month
            case OpenAccount(key=key, name=name, type=kind, number=number, parent=parent):
                books.accounts[key] = Account(key, name, kind, number, parent)
            case RenameAccount(account=key, name=name):
                books.accounts[key].name = name
            case DeactivateAccount(account=key):
                books.accounts[key].active = False
            case AddCustomer(key=key, name=name, parent=parent):
                self.customers[key] = (
                    name if parent is None else f"{self.customers[parent]}:{name}"
                )
            case AddVendor(key=key, name=name):
                self.vendors[key] = name
            case AddService(key=key, income_account=income):
                self.services[key] = income
            case OpenBalances(lines=lines):
                postings = [Posting(line.account, line.amount, line.memo) for line in lines]
                equity = -sum((line.amount for line in lines), ZERO)
                postings.append(Posting(OPENING_EQUITY, equity, "Opening balance"))
                self.add(Transaction(event_id, day, "Journal Entry", postings))
            case IssueInvoice(key=key, customer=customer, lines=lines, number=number):
                name = self.name(customer)
                detail = self.sale(lines, -1, name)
                total = -sum((p.amount for p in detail), ZERO)
                books.documents[key] = [replace(p, amount=-p.amount) for p in detail]
                receivable = Posting(RECEIVABLE, total, "", name)
                self.add(
                    Transaction(
                        event_id,
                        day,
                        "Invoice",
                        [receivable, *detail],
                        number,
                        name,
                        document=key,
                    ),
                    key,
                )
            case IssueCredit(key=key, customer=customer, lines=lines, applies_to=invoice):
                name = self.name(customer)
                detail = self.sale(lines, 1, name)
                total = sum((p.amount for p in detail), ZERO)
                books.documents[key] = detail
                receivable = Posting(RECEIVABLE, -total, "", name)
                self.add(
                    Transaction(event_id, day, "Credit Memo", [receivable, *detail], name=name),
                    key,
                )
                if invoice is not None:
                    # Applied through a payment of nothing: no lines, but on the cash basis it
                    # recognizes the invoice and the credit against each other.
                    self.add(
                        Transaction(
                            event_id,
                            day,
                            "Payment",
                            [],
                            name=name,
                            settles=(Applied(invoice, total),),
                            credits=(Applied(key, total),),
                        )
                    )
            case ReceivePayment(
                key=key, customer=customer, amount=amount, applies=applies, into=into
            ):
                name = self.name(customer)
                applied = sum((a.amount for a in applies), ZERO)
                self.add(
                    Transaction(
                        event_id,
                        day,
                        "Payment",
                        [
                            Posting(into, amount, "", name),
                            Posting(RECEIVABLE, -amount, "", name),
                        ],
                        name=name,
                        settles=applies,
                        unapplied=amount - applied,
                        deposit_account=into,
                    ),
                    key,
                )
            case Void(target=target):
                voided = self.by_key[target]
                voided.voided = True
                # Every line is kept at nothing; the first says it was voided.
                voided.lines = [
                    replace(p, amount=ZERO, memo="Voided" if i == 0 else p.memo)
                    for i, p in enumerate(voided.lines)
                ]
            case BankDeposit(into=into, payments=payments, lines=lines):
                # QuickBooks lists deposited payments by the day each was received, then in the
                # order they were made, whatever order the deposit names them in.
                payments = tuple(
                    sorted(
                        payments,
                        key=lambda p: (self.by_key[p.target].on, self.by_key[p.target].event),
                    )
                )
                postings = [Posting(HELD, -p.amount, "", "") for p in payments]
                postings += [Posting(line.account, -line.amount, line.memo) for line in lines]
                total = -sum((p.amount for p in postings), ZERO)
                # The bank line names whoever paid in, where that is one customer.
                payers = {self.by_key[p.target].name for p in payments}
                payer = payers.pop() if len(payers) == 1 and not lines else ""
                self.add(
                    Transaction(
                        event_id,
                        day,
                        "Deposit",
                        [Posting(into, total, "", payer), *postings],
                        name=payer,
                    )
                )
            case CashSale(customer=customer, into=into, lines=lines):
                name = self.name(customer)
                detail = self.sale(lines, -1, name)
                total = -sum((p.amount for p in detail), ZERO)
                self.add(
                    Transaction(
                        event_id,
                        day,
                        "Sales Receipt",
                        [Posting(into, total, "", name), *detail],
                        name=name,
                    )
                )
            case RefundCustomer(customer=customer, out_of=out_of, lines=lines):
                name = self.name(customer)
                detail = self.sale(lines, 1, name)
                total = sum((p.amount for p in detail), ZERO)
                self.add(
                    Transaction(
                        event_id,
                        day,
                        "Refund",
                        [Posting(out_of, -total, "", name), *detail],
                        name=name,
                    )
                )
            case ReceiveBill(key=key, vendor=vendor, number=number, lines=lines):
                name = self.vendors[vendor]
                detail = [Posting(line.account, line.amount, line.memo, name) for line in lines]
                total = sum((p.amount for p in detail), ZERO)
                books.documents[key] = detail
                self.add(
                    Transaction(
                        event_id,
                        day,
                        "Bill",
                        [Posting(PAYABLE, -total, "", name), *detail],
                        number,
                        name,
                        document=key,
                    ),
                    key,
                )
            case VendorCredit(key=key, vendor=vendor, lines=lines):
                name = self.vendors[vendor]
                detail = [
                    Posting(line.account, -line.amount, line.memo, name) for line in lines
                ]
                total = -sum((p.amount for p in detail), ZERO)
                books.documents[key] = [replace(p, amount=-p.amount) for p in detail]
                self.add(
                    Transaction(
                        event_id,
                        day,
                        "Vendor Credit",
                        [Posting(PAYABLE, total, "", name), *detail],
                        name=name,
                        document=key,
                    ),
                    key,
                )
            case PayBills(
                vendor=vendor, out_of=out_of, bills=bills, credits=credits, number=number
            ):
                name = self.vendors[vendor]
                total = sum((b.amount for b in bills), ZERO) - sum(
                    (c.amount for c in credits), ZERO
                )
                self.add(
                    Transaction(
                        event_id,
                        day,
                        "Bill Payment (Check)",
                        [Posting(out_of, -total, "", name), Posting(PAYABLE, total, "", name)],
                        number,
                        name,
                        settles=bills,
                        credits=credits,
                        deposit_account=out_of,
                    )
                )
            case Pay(by=by, out_of=out_of, payee=payee, lines=lines, number=number):
                name = "" if payee is None else self.vendors[payee]
                detail = [Posting(line.account, line.amount, line.memo, name) for line in lines]
                total = sum((p.amount for p in detail), ZERO)
                label = {"check": "Check", "debit": "Expense", "card": "Expense"}[by]
                self.add(
                    Transaction(
                        event_id,
                        day,
                        label,
                        [Posting(out_of, -total, "", name), *detail],
                        number,
                        name,
                    )
                )
            case CardRefund(card=card, payee=payee, lines=lines):
                name = "" if payee is None else self.vendors[payee]
                detail = [
                    Posting(line.account, -line.amount, line.memo, name) for line in lines
                ]
                total = -sum((p.amount for p in detail), ZERO)
                self.add(
                    Transaction(
                        event_id,
                        day,
                        "Credit Card Credit",
                        [Posting(card, total, "", name), *detail],
                        name=name,
                    )
                )
            case Transfer(out_of=out_of, into=into, amount=amount, memo=memo):
                self.add(
                    Transaction(
                        event_id,
                        day,
                        "Transfer",
                        [Posting(out_of, -amount, memo), Posting(into, amount, memo)],
                    )
                )
            case Journal(lines=lines):
                postings = [
                    Posting(line.account, line.amount, line.memo, self.name(line.customer))
                    for line in lines
                ]
                self.add(Transaction(event_id, day, "Journal Entry", postings))
            case IssueQuote() | PlaceOrder():
                pass  # an estimate or an order posts nothing
            case _:
                raise TypeError(f"no QuickBooks recording for {event.KIND}")


def record(company: str, events: Sequence[tuple[str, Event]]) -> Books:
    recorder = Recorder(company)
    for event_id, event in events:
        recorder.record(event_id, event)
    return recorder.books


def cash_lines(books: Books, transaction: Transaction) -> list[Posting]:
    """A transaction's lines on the cash basis.

    An invoice, credit memo, bill or vendor credit recognizes nothing when issued. A payment
    against one recognizes the document's own lines in proportion to the amount paid, against
    the account the money went to; whatever the payment leaves unapplied stays on A/R. A voided
    payment recognizes nothing. Everything else is the same on both bases.
    """
    if transaction.document is not None or transaction.voided:
        return []
    if transaction.type == "Payment":
        return _cash_receipt(books, transaction)
    if transaction.type == "Bill Payment (Check)":
        return _cash_disbursement(books, transaction)
    return list(transaction.lines)


def _recognized(books: Books, applied: Applied, sign: int) -> list[Posting]:
    """The applied amount of a document, spread over its own lines, signed as `sign` says."""
    lines = books.documents[applied.target]
    shares = allocate(applied.amount, lines, sum((p.amount for p in lines), ZERO))
    return [
        replace(share, amount=sign * share.amount, source=applied.target) for share in shares
    ]


def _cash_receipt(books: Books, payment: Transaction) -> list[Posting]:
    out: list[Posting] = []
    for applied in payment.settles:  # each invoice's income, recognized as a credit
        out += _recognized(books, applied, -1)
    for applied in payment.credits:  # each credit memo's lines, recognized as a debit
        out += _recognized(books, applied, 1)
    received = sum((a.amount for a in payment.settles), ZERO) - sum(
        (c.amount for c in payment.credits), ZERO
    )
    if payment.deposit_account is not None:
        out.append(
            Posting(payment.deposit_account, received + payment.unapplied, "", payment.name)
        )
    if payment.unapplied:
        out.append(Posting(UNAPPLIED_INCOME, -payment.unapplied, "", payment.name))
    return [replace(p, name=payment.name) for p in out]


def _cash_disbursement(books: Books, payment: Transaction) -> list[Posting]:
    out: list[Posting] = []
    for applied in payment.settles:  # each bill's expense, recognized as a debit
        out += _recognized(books, applied, 1)
    for applied in payment.credits:  # each vendor credit's lines, recognized as a credit
        out += _recognized(books, applied, -1)
    paid = sum((p.amount for p in out), ZERO)
    if payment.deposit_account is None:
        raise ValueError(f"{payment.event} pays bills out of no account")
    out.append(Posting(payment.deposit_account, -paid, "", payment.name))
    return [replace(p, name=payment.name) for p in out]
