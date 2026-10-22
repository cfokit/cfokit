"""Brightwater Design Studio: three fiscal years of a small services business, as events.

A six-to-eight person design studio, fiscal year starting July 1, from 2023-07-01 to 2026-06-30.
About a dozen clients on monthly retainers, two of whom pay late; a project spike every October
to December; workshops sold in the spring; semimonthly payroll from an outside provider; rent by
check; software subscriptions and travel on a card; quarterly insurance and accounting bills; a
contractor billing through the busy season.

**Every catalog case is placed deliberately**, in a plausible spot, and tagged with its id. The
everyday flow around them is drawn from a seeded generator, so the same seed writes the same
business byte for byte. Amounts are whole cents throughout and become `Decimal` only at the
edge; nothing here is a float.
"""

from __future__ import annotations

import dataclasses
import random
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

from synthetic_books.events import (
    HELD,
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
    Journal,
    Line,
    OpenAccount,
    OpenBalances,
    Pay,
    PayBills,
    ReceiveBill,
    ReceivePayment,
    RefundCustomer,
    RenameAccount,
    SaleLine,
    SetFiscalYear,
    SetReportBasis,
    Transfer,
    VendorCredit,
    Void,
)

SEED = 20230701
START = date(2023, 7, 1)
END = date(2026, 6, 30)
FIRST_INVOICE = 1001
FIRST_CHECK = 5001


def money(cents: int) -> Decimal:
    """Whole cents as an exact two-place decimal."""
    return Decimal(cents).scaleb(-2)


def month_end(day: date) -> date:
    following = date(day.year + day.month // 12, day.month % 12 + 1, 1)
    return following - timedelta(days=1)


def months() -> list[date]:
    out, at = [], START
    while at <= END:
        out.append(at)
        at = date(at.year + at.month // 12, at.month % 12 + 1, 1)
    return out


def fiscal_year(day: date) -> int:
    """1 for July 2023 to June 2024, and so on."""
    return day.year - START.year + (1 if day.month >= 7 else 0)


# --- The chart ------------------------------------------------------------------------------

ACCOUNTS: tuple[tuple[str, str, AccountType, str | None, tuple[str, ...]], ...] = (
    # key, name, type, parent key, cases
    ("checking", "Operating Checking", "bank", None, ()),
    ("savings", "Reserve Savings", "bank", None, ()),
    ("card", "Business Card", "credit_card", None, ()),
    ("equipment", "Computer Equipment", "fixed_asset", None, ()),
    ("payroll-liabilities", "Payroll Liabilities", "other_current_liability", None, ()),
    ("loan", "Equipment Loan", "long_term_liability", None, ()),
    ("design", "Design Services", "income", None, ()),
    ("workshops", "Workshops", "income", None, ()),
    ("interest-earned", "Interest Earned", "other_income", None, ("d-deposit-other-income",)),
    ("cost-of-services", "Cost of Services", "cost_of_sales", None, ("d-same-leaf",)),
    ("contractors", "Contractors", "cost_of_sales", "cost-of-services", ()),
    ("render-software", "Software", "cost_of_sales", "cost-of-services", ("d-same-leaf",)),
    ("stock", "Stock Photography", "cost_of_sales", "cost-of-services", ("d-renamed-account",)),
    ("rent", "Rent", "expense", None, ()),
    ("payroll", "Payroll Expenses", "expense", None, ()),
    ("wages", "Wages", "expense", "payroll", ()),
    ("employer-taxes", "Employer Taxes", "expense", "payroll", ()),
    ("office", "Office Expenses", "expense", None, ("d-same-leaf",)),
    ("office-software", "Software", "expense", "office", ("d-same-leaf",)),
    ("supplies", "Office Supplies", "expense", None, ()),
    ("meals", "Meals & Entertainment", "expense", None, ("d-punctuation-names",)),
    ("repairs", "Repairs/Maintenance", "expense", None, ("d-punctuation-names",)),
    ("professional", "Professional Fees", "expense", None, ("d-punctuation-names",)),
    ("legal", "Legal & Accounting", "expense", "professional", ("d-punctuation-names",)),
    ("travel", "Travel", "expense", None, ("d-parent-with-postings",)),
    ("airfare", "Airfare", "expense", "travel", ("d-parent-with-postings",)),
    ("telephone", "Telephone", "expense", None, ("d-inactive-account",)),
    ("insurance", "Insurance", "expense", None, ()),
    ("bank-fees", "Bank Fees", "expense", None, ()),
    ("interest-expense", "Interest Expense", "other_expense", None, ()),
)

# Opened when it replaces Telephone, at the start of the third fiscal year.
INTERNET: tuple[str, str, AccountType, str | None, tuple[str, ...]] = (
    "internet",
    "Internet & Phone",
    "expense",
    None,
    ("d-inactive-account",),
)


# --- Clients and suppliers ------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Client:
    key: str
    name: str
    retainer: int  # cents a month in the first fiscal year
    pays: Literal["ach", "check"]
    lag: tuple[int, int]  # days from invoice to payment
    joins: date = START
    leaves: date = date.max


CLIENTS = (
    Client("harbor-dental", "Harbor Dental Group", 450000, "ach", (8, 20)),
    Client("juniper", "Juniper Analytics", 620000, "ach", (10, 25)),
    Client("cafe-nandu", "Café Ñandú, LLC", 280000, "check", (12, 26), joins=date(2023, 9, 1)),
    Client("northwind", "Northwind Studio", 150000, "ach", (10, 20), joins=date(2024, 1, 1)),
    Client("tidewater", "Tidewater Credit Union", 900000, "ach", (45, 75)),
    Client("oakline", "Oakline Builders", 380000, "check", (15, 25)),
    Client(
        "pinecrest", "Pinecrest Veterinary", 220000, "check", (10, 18), leaves=date(2025, 3, 31)
    ),
    Client("meridian", "Meridian Bike Co.", 310000, "ach", (50, 80), joins=date(2024, 2, 1)),
    Client("lantern", "Lantern Theatre Company", 180000, "check", (14, 24)),
    Client("sable-finch", "Sable & Finch Law", 540000, "ach", (5, 15)),
    Client("glacier", "Glacier Outfitters", 260000, "ach", (10, 20), joins=date(2025, 1, 1)),
    Client("copperleaf", "Copperleaf Foods", 470000, "ach", (12, 25), leaves=date(2026, 2, 28)),
)

VENDORS = (
    ("elm-street", "Elm Street Properties"),
    ("payflow", "PayFlow Payroll"),
    ("tax-agency", "Payroll Tax Agency"),
    ("keystone", "Keystone Mutual Insurance"),
    ("ledger-lane", "Ledger & Lane CPAs"),
    # The same studio is a client; QuickBooks will not give a vendor a customer's name.
    ("northwind-v", "Northwind Studio (V)"),
    ("metro-fiber", "Metro Fiber"),
    ("vectorly", "Vectorly"),
    ("renderfarm", "RenderFarm Cloud"),
    ("stockhouse", "Stockhouse Images"),
    ("paper-co", "Paper & Pixel Supply"),
    ("first-harbor-bank", "First Harbor Bank"),
    ("skyway", "Skyway Air"),
    ("hotel-row", "Hotel Row"),
    ("fixit", "FixIt Building Services"),
)

SERVICES = (
    ("retainer", "Design Retainer", "design"),
    ("project", "Project Work", "design"),
    ("workshop-seat", "Workshop Seat", "workshops"),
)

MONTH_NAMES = (
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

# Retainer payments forced into the last days of May 2024, so three are held over the month end
# and banked together on Monday 3 June (d-undeposited-funds).
HELD_OVER_MONTH_END = {
    ("cafe-nandu", date(2024, 5, 1)): date(2024, 5, 28),
    ("oakline", date(2024, 5, 1)): date(2024, 5, 29),
    ("lantern", date(2024, 5, 1)): date(2024, 5, 30),
}


class Business:
    """Accumulates events in the order they are written, and orders them by date at the end."""

    def __init__(self, seed: int = SEED) -> None:
        self.rng = random.Random(seed)  # noqa: S311 — a reproducible simulation, not a secret
        self._events: list[Event] = []
        self._held: list[
            tuple[date, str, str, int]
        ] = []  # received, payment key, customer, cents
        self._card: dict[date, int] = defaultdict(int)  # month -> net charges, cents
        self._withheld: dict[date, int] = defaultdict(
            int
        )  # month -> payroll liabilities, cents
        self._northwind_bills: list[tuple[date, str, int]] = []
        self._sequence = 0

    def add(self, event: Event) -> Event:
        self._events.append(event)
        return event

    def key(self, prefix: str) -> str:
        self._sequence += 1
        return f"{prefix}-{self._sequence:04d}"

    def cents(self, low: int, high: int) -> int:
        """Cents in [low, high], rounded to the dollar so it reads like a price."""
        return self.rng.randint(low, high) // 100 * 100

    # --- writing it --------------------------------------------------------------------------

    def write(self) -> list[tuple[str, Event]]:
        self._setup()
        for month in months():
            self._month(month)
        self._cases()
        self._deposits()
        self._card_payments()
        self._remittances()
        self._northwind_payments()
        return self._ordered()

    def _ordered(self) -> list[tuple[str, Event]]:
        """By date; on one day, the company's setup comes before anything posted against it."""
        setup = (
            SetFiscalYear,
            SetReportBasis,
            OpenAccount,
            RenameAccount,
            DeactivateAccount,
            AddCustomer,
            AddVendor,
            AddService,
        )
        indexed = sorted(
            enumerate(self._events),
            key=lambda item: (item[1].on, 0 if isinstance(item[1], setup) else 1, item[0]),
        )
        invoice, check = FIRST_INVOICE, FIRST_CHECK
        out: list[tuple[str, Event]] = []
        for position, (_, event) in enumerate(indexed, 1):
            if isinstance(event, IssueInvoice):
                event = dataclasses.replace(event, number=str(invoice))
                invoice += 1
            elif isinstance(event, PayBills) or (
                isinstance(event, Pay) and event.by == "check"
            ):
                event = dataclasses.replace(event, number=str(check))
                check += 1
            out.append((f"ev-{position:05d}", event))
        return out

    # --- the company -------------------------------------------------------------------------

    def _setup(self) -> None:
        self.add(SetFiscalYear(on=START, start_month=7, cases=("d-fiscal-year-july",)))
        self.add(SetReportBasis(on=START, basis="cash", cases=("d-cash-basis-reports",)))
        for key, name, kind, parent, tags in ACCOUNTS:
            self.add(
                OpenAccount(on=START, key=key, name=name, type=kind, parent=parent, cases=tags)
            )
        for key, name, service_account in SERVICES:
            self.add(AddService(on=START, key=key, name=name, income_account=service_account))
        for client in CLIENTS:
            cases: tuple[str, ...] = ()
            if client.key == "cafe-nandu":
                cases = ("d-unicode-commas",)
            elif client.key == "northwind":
                cases = ("d-name-both-sides",)
            self.add(
                AddCustomer(on=client.joins, key=client.key, name=client.name, cases=cases)
            )
        for key, name in VENDORS:
            cases = ("d-name-both-sides",) if key == "northwind-v" else ()
            self.add(AddVendor(on=START, key=key, name=name, cases=cases))
        self.add(
            OpenBalances(
                on=START,
                lines=(
                    Line("checking", money(4200000), "Opening balance"),
                    Line("savings", money(2500000), "Opening balance"),
                    Line("equipment", money(1800000), "Opening balance"),
                    Line("loan", money(-2400000), "Opening balance"),
                ),
                cases=("d-opening-balance-equity",),
            )
        )
        # Stock Photography becomes Stock Media halfway through the second fiscal year.
        self.add(
            RenameAccount(
                on=date(2025, 1, 1),
                account="stock",
                name="Stock Media",
                cases=("d-renamed-account",),
            )
        )
        # Telephone is replaced by Internet & Phone, and retired, when the third year opens.
        key, name, kind, parent, cases = INTERNET
        third_year = date(2025, 7, 1)
        self.add(OpenAccount(on=third_year, key=key, name=name, type="expense", cases=cases))
        self.add(DeactivateAccount(on=third_year, account="telephone", cases=cases))

    # --- an ordinary month -------------------------------------------------------------------

    def _month(self, first: date) -> None:
        last = month_end(first)
        year = fiscal_year(first)
        for client in CLIENTS:
            if client.joins <= first <= client.leaves:
                self._retainer(client, first, year)
        if first.month in (10, 11, 12):
            for client in self.rng.sample(self._active(first), 3):
                self._invoice(
                    client,
                    first + timedelta(days=self.rng.randint(4, 20)),
                    "project",
                    self.cents(300000, 1200000),
                    f"Holiday campaign — {MONTH_NAMES[first.month - 1]} deliverables",
                )
        if first.month in (3, 4, 5):
            for _ in range(self.rng.randint(2, 4)):
                self._workshop(first + timedelta(days=self.rng.randint(2, 26)))

        self._rent(first, year)
        for day in (first.replace(day=15), last):
            self._payroll(day, year)
        self._subscriptions(first)
        self._phone(first)
        self._loan(first)
        self._everyday(first)
        self._bills(first)

        interest = self.cents(1800, 3200)
        self.add(
            BankDeposit(
                on=last,
                key=self.key("dep"),
                into="savings",
                lines=(Line("interest-earned", money(interest), "Interest"),),
                cases=("d-deposit-other-income",) if first == START else (),
            )
        )
        self.add(
            Pay(
                on=last,
                key=self.key("pay"),
                by="debit",
                out_of="checking",
                payee="first-harbor-bank",
                lines=(Line("bank-fees", money(2500), "Monthly service fee"),),
            )
        )

    def _active(self, first: date) -> list[Client]:
        return [c for c in CLIENTS if c.joins <= first <= c.leaves]

    def _retainer(self, client: Client, first: date, year: int) -> None:
        amount = client.retainer
        for _ in range(year - 1):  # four percent a year, to the nearest hundred dollars
            amount = (amount * 104 + 500000) // 1000000 * 10000
        memo = f"{MONTH_NAMES[first.month - 1]} {first.year} retainer"
        cases: tuple[str, ...] = ()
        if client.key == "cafe-nandu" and first == date(2024, 3, 1):
            memo = "Q3 retainer — 東京 office, phase 2"
            cases = ("d-unicode-commas",)
        if client.key == "tidewater" and first == START:
            cases = ("d-invoice",)  # a late payer: still open on July 31
        if client.key == "harbor-dental" and first == date(2024, 2, 1):
            self._overpaid(client, first, amount, memo)
            return
        if client.key == "juniper" and first == date(2024, 11, 1):
            self._credited(client, first, amount, memo)
            return
        paid = HELD_OVER_MONTH_END.get((client.key, first))
        self._invoice(client, first, "retainer", amount, memo, cases=cases, paid_on=paid)

    def _invoice(
        self,
        client: Client,
        on: date,
        service: str,
        cents: int,
        memo: str,
        *,
        cases: tuple[str, ...] = (),
        paid_on: date | None = None,
    ) -> str:
        key = f"inv-{client.key}-{on.isoformat()}-{service}"
        self.add(
            IssueInvoice(
                on=on,
                key=key,
                customer=client.key,
                due=on + timedelta(days=30),
                lines=(SaleLine(service, money(cents), memo),),
                cases=cases,
            )
        )
        received = paid_on or on + timedelta(days=self.rng.randint(*client.lag))
        payment_cases = ("d-undeposited-funds",) if paid_on is not None else ()
        self._payment(client, received, ((key, cents),), cents, cases=payment_cases)
        return key

    def _payment(
        self,
        client: Client,
        on: date,
        applies: tuple[tuple[str, int], ...],
        cents: int,
        *,
        cases: tuple[str, ...] = (),
    ) -> None:
        if on > END:
            return  # still owed when the books end
        key = self.key("pmt")
        into = HELD if client.pays == "check" else "checking"
        self.add(
            ReceivePayment(
                on=on,
                key=key,
                customer=client.key,
                amount=money(cents),
                applies=tuple(Applied(invoice, money(part)) for invoice, part in applies),
                into=into,
                cases=cases,
            )
        )
        if into == HELD:
            self._held.append((on, key, client.key, cents))

    def _workshop(self, on: date, cases: tuple[str, ...] = ()) -> None:
        seats = self.rng.randint(4, 12)
        self.add(
            CashSale(
                on=on,
                key=self.key("sale"),
                customer=None,
                into="checking",
                lines=(
                    SaleLine("workshop-seat", money(seats * 45000), f"{seats} workshop seats"),
                ),
                cases=cases,
            )
        )

    def _rent(self, first: date, year: int) -> None:
        cents = 650000 if year < 3 else 680000
        self.add(
            Pay(
                on=first,
                key=self.key("rent"),
                by="check",
                out_of="checking",
                payee="elm-street",
                lines=(Line("rent", money(cents), f"{MONTH_NAMES[first.month - 1]} rent"),),
                cases=("d-check",) if first == START else (),
            )
        )

    def _payroll(self, day: date, year: int) -> None:
        gross = (1900000, 2050000, 2200000)[year - 1]
        employer_tax = gross * 765 // 10000
        withheld = gross * 22 // 100
        self.add(
            Journal(
                on=day,
                key=self.key("payroll"),
                memo=f"PayFlow payroll, period ending {day.isoformat()}",
                lines=(
                    Line("wages", money(gross)),
                    Line("employer-taxes", money(employer_tax)),
                    Line("checking", money(-(gross - withheld))),
                    Line("payroll-liabilities", money(-(withheld + employer_tax))),
                ),
                cases=("d-journal-entry",) if day == date(2023, 7, 15) else (),
            )
        )
        self._withheld[day.replace(day=1)] += withheld + employer_tax

    def _card_charge(
        self,
        on: date,
        payee: str,
        account: str,
        cents: int,
        memo: str,
        cases: tuple[str, ...] = (),
    ) -> None:
        self.add(
            Pay(
                on=on,
                key=self.key("card"),
                by="card",
                out_of="card",
                payee=payee,
                lines=(Line(account, money(cents), memo),),
                cases=cases,
            )
        )
        self._card[on.replace(day=1)] += cents

    def _subscriptions(self, first: date) -> None:
        # The first month posts to both accounts named Software; the months either side of the
        # rename give Stock Photography history under each of its names.
        same_leaf = ("d-same-leaf",) if first == START else ()
        renamed = (
            ("d-renamed-account",) if first in (date(2024, 12, 1), date(2025, 1, 1)) else ()
        )
        self._card_charge(
            first.replace(day=3), "vectorly", "office-software", 5400, "Vectorly", same_leaf
        )
        self._card_charge(
            first.replace(day=7),
            "renderfarm",
            "render-software",
            self.cents(18900, 32000),
            "Render hours",
            same_leaf,
        )
        self._card_charge(
            first.replace(day=11), "stockhouse", "stock", 4900, "Image licenses", renamed
        )

    def _phone(self, first: date) -> None:
        account = "telephone" if first < date(2025, 7, 1) else "internet"
        self.add(
            Pay(
                on=first.replace(day=18),
                key=self.key("pay"),
                by="debit",
                out_of="checking",
                payee="metro-fiber",
                lines=(Line(account, money(18500), "Phones and fiber"),),
            )
        )

    def _loan(self, first: date) -> None:
        paid = (fiscal_year(first) - 1) * 12 + (first.month - 7) % 12
        remaining = 2400000 - paid * 60000
        interest = remaining * 65 // 12000
        self.add(
            Pay(
                on=first.replace(day=10),
                key=self.key("loan"),
                by="debit",
                out_of="checking",
                payee="first-harbor-bank",
                lines=(
                    Line("loan", money(60000), "Principal"),
                    Line("interest-expense", money(interest), "Interest"),
                ),
            )
        )

    def _everyday(self, first: date) -> None:
        day = first + timedelta(days=self.rng.randint(5, 25))
        supplies = self.cents(3000, 15000)
        self.add(
            Pay(
                on=day,
                key=self.key("pay"),
                by="debit",
                out_of="checking",
                payee="paper-co",
                lines=(Line("supplies", money(supplies), "Paper, ink, mounting board"),),
                cases=("d-expense",) if first == START else (),
            )
        )
        for _ in range(self.rng.randint(1, 2)):
            self._card_charge(
                first + timedelta(days=self.rng.randint(1, 27)),
                "hotel-row" if self.rng.randint(1, 5) == 1 else "paper-co",
                "meals",
                self.cents(4000, 22000),
                "Client lunch",
            )
        if first.month in (1, 4, 7, 10):
            self.add(
                Pay(
                    on=first + timedelta(days=self.rng.randint(5, 20)),
                    key=self.key("pay"),
                    by="debit",
                    out_of="checking",
                    payee="fixit",
                    lines=(Line("repairs", money(self.cents(15000, 60000)), "HVAC service"),),
                )
            )
        if first.month in (2, 5, 8, 11):
            trip = first + timedelta(days=self.rng.randint(3, 20))
            cases = ("d-parent-with-postings",) if first == date(2023, 8, 1) else ()
            self._card_charge(
                trip, "skyway", "airfare", self.cents(40000, 90000), "Client site visit", cases
            )
            self._card_charge(
                trip + timedelta(days=2),
                "hotel-row",
                "travel",
                self.cents(20000, 50000),
                "Hotel and taxis",
                cases,
            )

    def _bills(self, first: date) -> None:
        if first.month in (7, 10, 1, 4):
            key = f"bill-keystone-{first.isoformat()}"
            cases = ("d-bill",) if first == START else ()
            self.add(
                ReceiveBill(
                    on=first,
                    key=key,
                    vendor="keystone",
                    number=f"KM-{first:%Y%m}",
                    due=first + timedelta(days=30),
                    lines=(Line("insurance", money(210000), "Quarterly premium"),),
                    cases=cases,
                )
            )
            self._pay_bills(
                "keystone", first + timedelta(days=self.rng.randint(32, 40)), key, 210000, cases
            )
        if first.month in (8, 11, 2, 5):
            on = first.replace(day=15)
            cents = self.cents(120000, 180000)
            key = f"bill-ledger-lane-{on.isoformat()}"
            self.add(
                ReceiveBill(
                    on=on,
                    key=key,
                    vendor="ledger-lane",
                    number=f"LL-{on:%y%m}",
                    due=on + timedelta(days=30),
                    lines=(Line("legal", money(cents), "Quarterly bookkeeping review"),),
                )
            )
            self._pay_bills(
                "ledger-lane", on + timedelta(days=self.rng.randint(15, 25)), key, cents
            )
        if first >= date(2023, 9, 1):
            days = (3, 12, 24) if first.month in (10, 11, 12) else (12,)
            for day in days:
                on = first.replace(day=day)
                cents = self.cents(80000, 240000)
                key = f"bill-northwind-{on.isoformat()}"
                cases = ("d-name-both-sides",) if on == date(2024, 1, 12) else ()
                if first == date(2023, 10, 1):
                    cases = ("d-bill-payment-multi",)
                self.add(
                    ReceiveBill(
                        on=on,
                        key=key,
                        vendor="northwind-v",
                        number=f"NW-{on:%y%m%d}",
                        due=on + timedelta(days=30),
                        lines=(Line("contractors", money(cents), "Freelance illustration"),),
                        cases=cases,
                    )
                )
                self._northwind_bills.append((on, key, cents))

    def _pay_bills(
        self, vendor: str, on: date, bill: str, cents: int, cases: tuple[str, ...] = ()
    ) -> None:
        if on > END:
            return
        self.add(
            PayBills(
                on=on,
                key=self.key("billpmt"),
                vendor=vendor,
                out_of="checking",
                bills=(Applied(bill, money(cents)),),
                cases=cases,
            )
        )

    # --- the cases that need more than one event placed together -----------------------------

    def _overpaid(self, client: Client, first: date, cents: int, memo: str) -> None:
        """The client pays $400 over the invoice; the excess stays on their account."""
        key = f"inv-{client.key}-{first.isoformat()}-retainer"
        self.add(
            IssueInvoice(
                on=first,
                key=key,
                customer=client.key,
                due=first + timedelta(days=30),
                lines=(SaleLine("retainer", money(cents), memo),),
                cases=("d-overpayment",),
            )
        )
        self._payment(
            client,
            first + timedelta(days=14),
            ((key, cents),),
            cents + 40000,
            cases=("d-overpayment",),
        )

    def _credited(self, client: Client, first: date, cents: int, memo: str) -> None:
        """A credit for a missed deadline, applied to the month's invoice; the rest is paid."""
        key = f"inv-{client.key}-{first.isoformat()}-retainer"
        credit = 50000
        self.add(
            IssueInvoice(
                on=first,
                key=key,
                customer=client.key,
                due=first + timedelta(days=30),
                lines=(SaleLine("retainer", money(cents), memo),),
                cases=("d-credit-memo",),
            )
        )
        self.add(
            IssueCredit(
                on=date(2024, 11, 12),
                key=self.key("credit"),
                customer=client.key,
                lines=(SaleLine("retainer", money(credit), "Credit — missed launch deadline"),),
                applies_to=key,
                cases=("d-credit-memo",),
            )
        )
        self._payment(
            client,
            date(2024, 11, 26),
            ((key, cents - credit),),
            cents - credit,
            cases=("d-credit-memo",),
        )

    def _cases(self) -> None:
        juniper = next(c for c in CLIENTS if c.key == "juniper")
        oakline = next(c for c in CLIENTS if c.key == "oakline")

        # A project invoice paid in two parts, one each side of December 31.
        project = f"inv-juniper-{date(2023, 12, 1).isoformat()}-milestone"
        self.add(
            IssueInvoice(
                on=date(2023, 12, 1),
                key=project,
                customer="juniper",
                due=date(2023, 12, 31),
                lines=(SaleLine("project", money(1000000), "Brand system — milestone 2"),),
                cases=("d-partial-payment",),
            )
        )
        for on, part in ((date(2023, 12, 20), 400000), (date(2024, 1, 15), 600000)):
            self._payment(juniper, on, ((project, part),), part, cases=("d-partial-payment",))

        # An invoice raised twice by mistake; the duplicate is voided two days later.
        duplicate = "inv-oakline-2024-04-01-duplicate"
        self.add(
            IssueInvoice(
                on=date(2024, 4, 1),
                key=duplicate,
                customer=oakline.key,
                due=date(2024, 5, 1),
                lines=(SaleLine("retainer", money(380000), "Duplicate — raised in error"),),
                cases=("d-void-invoice",),
            )
        )
        self.add(Void(on=date(2024, 4, 3), target=duplicate, cases=("d-void-invoice",)))

        # The first workshop of the year is the sales receipt the catalog points at.
        self._workshop(date(2024, 3, 2), cases=("d-sales-receipt",))

        # One seat refunded out of checking after a spring workshop.
        self.add(
            RefundCustomer(
                on=date(2025, 4, 22),
                key=self.key("refund"),
                customer=None,
                out_of="checking",
                lines=(SaleLine("workshop-seat", money(45000), "Refund — cancelled seat"),),
                cases=("d-refund-receipt",),
            )
        )

        # A chair bought on the card and returned two weeks later.
        self._card_charge(
            date(2024, 9, 6),
            "paper-co",
            "supplies",
            64900,
            "Drafting chair",
            ("d-card-credit",),
        )
        self.add(
            CardRefund(
                on=date(2024, 9, 19),
                key=self.key("cardrefund"),
                card="card",
                payee="paper-co",
                lines=(Line("supplies", money(64900), "Drafting chair returned"),),
                cases=("d-card-credit",),
            )
        )
        self._card[date(2024, 9, 1)] -= 64900

        # Reserve savings covers a thin January.
        self.add(
            Transfer(
                on=date(2024, 1, 8),
                key=self.key("transfer"),
                out_of="savings",
                into="checking",
                amount=money(1500000),
                memo="Cover January payroll",
                cases=("d-transfer",),
            )
        )

        # Northwind credits a reshoot; the credit rides the next bill payment.
        self.add(
            VendorCredit(
                on=date(2025, 2, 18),
                key="vcredit-northwind-2025-02-18",
                vendor="northwind-v",
                lines=(
                    Line("contractors", money(45000), "Reshoot credit — misprinted proofs"),
                ),
                cases=("d-vendor-credit",),
            )
        )

    # --- what follows from the month's activity ----------------------------------------------

    def _deposits(self) -> None:
        """Held payments are banked on the Monday after they arrive."""
        batches: dict[date, list[tuple[str, int]]] = defaultdict(list)
        for received, key, _, cents in self._held:
            monday = received + timedelta(days=7 - received.weekday())
            if monday <= END:
                batches[monday].append((key, cents))
        for monday in sorted(batches):
            payments = batches[monday]
            self.add(
                BankDeposit(
                    on=monday,
                    key=self.key("dep"),
                    into="checking",
                    payments=tuple(Applied(key, money(cents)) for key, cents in payments),
                    cases=("d-undeposited-funds",) if monday == date(2024, 6, 3) else (),
                )
            )

    def _card_payments(self) -> None:
        """The card's balance for a month is paid in full on the 20th of the next."""
        for month, cents in sorted(self._card.items()):
            on = month_end(month) + timedelta(days=20)
            if on <= END and cents > 0:
                self.add(
                    Transfer(
                        on=on,
                        key=self.key("cardpmt"),
                        out_of="checking",
                        into="card",
                        amount=money(cents),
                        memo=f"Card statement, {MONTH_NAMES[month.month - 1]} {month.year}",
                    )
                )

    def _remittances(self) -> None:
        """A month's withholding and employer tax are remitted on the 5th of the next."""
        for month, cents in sorted(self._withheld.items()):
            on = month_end(month) + timedelta(days=5)
            if on <= END:
                self.add(
                    Pay(
                        on=on,
                        key=self.key("pay"),
                        by="debit",
                        out_of="checking",
                        payee="tax-agency",
                        lines=(
                            Line("payroll-liabilities", money(cents), "Payroll tax deposit"),
                        ),
                    )
                )

    def _northwind_payments(self) -> None:
        """Northwind is paid on the 10th for every bill open at the end of the month before."""
        credit_taken = False
        for first in months()[1:]:
            on = first.replace(day=10)
            due = [(k, c) for d, k, c in self._northwind_bills if d < first]
            self._northwind_bills = [b for b in self._northwind_bills if b[0] >= first]
            if not due:
                continue
            taken: tuple[Applied, ...] = ()
            cases: tuple[str, ...] = ()
            if not credit_taken and first == date(2025, 3, 1):
                taken = (Applied("vcredit-northwind-2025-02-18", money(45000)),)
                cases = ("d-vendor-credit",)
                credit_taken = True
            if first == date(2023, 11, 1):
                cases = ("d-bill-payment-multi",)
            self.add(
                PayBills(
                    on=on,
                    key=self.key("billpmt"),
                    vendor="northwind-v",
                    out_of="checking",
                    bills=tuple(Applied(k, money(c)) for k, c in due),
                    credits=taken,
                    cases=cases,
                )
            )


def write(seed: int = SEED) -> list[tuple[str, Event]]:
    """The whole business, as numbered events in date order."""
    return Business(seed).write()
