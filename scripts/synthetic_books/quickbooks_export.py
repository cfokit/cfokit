"""The QuickBooks Online export, written from what QuickBooks records (`quickbooks_books`).

One archive per rendering: the same books, run on a basis, with or without account numbers, over
all dates or one fiscal year, under a fiscal year starting in July or January. Each archive
holds what Export Data writes — Journal, General Ledger, Profit and Loss, Balance Sheet and
Trial Balance, and the Customer, Vendor and Employee contact lists — and beside it, the trial
balance at every month end, which the round trip compares against.

**What a report prints** is as the Reports API showed it for every posting of the synthetic
company, asked as Export Data asks (ADR-0078):

* Export Data runs every report over all dates. Nothing is then closed into Retained Earnings,
  which holds only what was posted to it, and the balance sheet's Net Income is every year's.
  From a start, a balance is presented at the end, earlier fiscal years closed.
* An account with any line in a report's span is printed, at zero if it nets to nothing. The
  balance sheet always prints Retained Earnings, blank when it has no figure.
* A trial balance at a month end states income and expense from its fiscal year's start.
* The general ledger names each line by its transaction, keeps the balance on the account's
  natural side, prints a beginning balance only where there is one (Retained Earnings' with
  every earlier year's profit), and says "with sub-accounts" only of a parent with entries of
  its own. On the cash basis, what a payment recognizes is shown as the invoice or bill it is
  part of. The API's ledger also has a Split column, which the export does not print.
* The ledger's order within a day is QuickBooks' own and not stable: the same day comes back
  differently for different date ranges, in the API and in the export alike. Ours is the order
  the events were made in.

**The layout is an Export Data download's**, compared with it cell by cell (ADR-0078):

* Three title rows — the company, the report, its period — a blank row and a header row before
  the body, and three blank rows before a statement's footer, two before the journal's and the
  ledger's. The footer names the basis, except on the journal and the contact lists.
* A blank row after each of the journal's transactions. A document number that is all digits
  is a number cell. A zero amount is a debit of 0, except on a payment's A/R line for several
  documents that net to nothing, which shows none.
* Every figure of a statement and a trial balance is a formula, cached as zero: an account's,
  its figure to the cent; a total's, the sum of the rows above it, nested as
  `((B11)+(B14))+(B18)`.
* Sub-accounts are indented three spaces a level, on a statement and in the general ledger's
  headings and totals, and named by full path in the journal, the trial balance and each
  ledger entry's Account column. A parent's own entries are totalled a level in. An indented
  total's empty amount holds its indentation as text.

Only an accrual download over all dates has been compared. How a cash download, a numbered one
or one over a fiscal year prints is still our belief; the Reports API never prints account
numbers, so only a download can show them.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

from synthetic_books.business import END, MONTH_NAMES, month_end, months
from synthetic_books.events import RECEIVABLE, RETAINED_EARNINGS
from synthetic_books.quickbooks_books import (
    NOT_SPECIFIED,
    ZERO,
    Books,
    Posting,
    Transaction,
    cash_lines,
)
from synthetic_books.xlsx import Cell, Formula, Number, Row, archive, workbook

COMPANY = "Brightwater Design Studio"
RUN_AT = "Wednesday, Jul 01, 2026 09:00:00 AM GMT-7"
JOURNAL_HEADER: Row = [
    None,
    "Date",
    "Transaction Type",
    "Num",
    "Name",
    "Memo/Description",
    "Account",
    "Debit",
    "Credit",
]
LEDGER_HEADER: Row = [*JOURNAL_HEADER, "Balance"]
CUSTOMER_HEADER: Row = [
    None,
    "Customer",
    "Phone Numbers",
    "Email",
    "Full Name",
    "Billing Address",
    "Shipping Address",
]
VENDOR_HEADER: Row = [
    None,
    "Vendor",
    "Phone Numbers",
    "Email",
    "Full Name",
    "Address",
    "Account #",
]
EMPLOYEE_HEADER: Row = [None, "Employee", "Phone Numbers", "Email", "Address"]

# The order QuickBooks lists account types in, and which side of the books each sits on.
TYPE_ORDER = (
    "bank",
    "receivable",
    "other_current_asset",
    "fixed_asset",
    "payable",
    "credit_card",
    "other_current_liability",
    "long_term_liability",
    "equity",
    "income",
    "cost_of_sales",
    "expense",
    "other_income",
    "other_expense",
    "not_specified",
)
PROFIT_AND_LOSS_TYPES = {"income", "cost_of_sales", "expense", "other_income", "other_expense"}
CREDIT_NATURE = {
    "payable",
    "credit_card",
    "other_current_liability",
    "long_term_liability",
    "equity",
    "income",
    "other_income",
}


@dataclass(frozen=True, slots=True)
class Rendering:
    name: str
    basis: Literal["accrual", "cash"] = "accrual"
    numbers: bool = False
    start: date | None = None  # None is "All Dates"
    fiscal_start_month: int | None = None  # None is the company's own


RENDERINGS = (
    Rendering("accrual"),
    Rendering("cash", basis="cash"),
    Rendering("account-numbers", numbers=True),
    Rendering("partial-range", start=date(2025, 7, 1)),
    Rendering("calendar-year", fiscal_start_month=1),
)

# Renderings whose month-end trial balances differ from the accrual one's.
OWN_TRIAL_BALANCES = ("accrual", "cash", "calendar-year")


def long_date(day: date) -> str:
    return f"{MONTH_NAMES[day.month - 1]} {day.day}, {day.year}"


def short_date(day: date) -> str:
    return f"{day.month:02d}/{day.day:02d}/{day.year}"


class Report:
    """The books as one rendering presents them."""

    def __init__(self, books: Books, rendering: Rendering) -> None:
        self.books = books
        self.rendering = rendering
        self.fiscal_start = rendering.fiscal_start_month or books.fiscal_start_month
        self.start = rendering.start
        self.end = END
        self.postings: list[tuple[Transaction, list[Posting]]] = [
            (t, cash_lines(books, t) if rendering.basis == "cash" else list(t.lines))
            for t in books.transactions
        ]

    # --- names and order ---------------------------------------------------------------------

    def path(self, key: str) -> str:
        return self.books.path(key, numbers=self.rendering.numbers)

    def leaf(self, key: str) -> str:
        return self.path(key).rsplit(":", 1)[-1]

    def depth(self, key: str) -> int:
        parent, level = self.books.accounts[key].parent, 0
        while parent is not None:
            parent, level = self.books.accounts[parent].parent, level + 1
        return level

    def type_of(self, key: str) -> str:
        return str(self.books.accounts[key].type)

    def ordered(self, keys: Iterable[str]) -> list[str]:
        """By type, then down the tree: a parent before its children, siblings by name."""
        return sorted(
            keys,
            key=lambda k: (TYPE_ORDER.index(self.type_of(k)), tuple(self.path(k).split(":"))),
        )

    def children(self, key: str) -> list[str]:
        return [k for k, a in self.books.accounts.items() if a.parent == key]

    # --- figures -----------------------------------------------------------------------------

    def fiscal_year_start(self, day: date) -> date:
        year = day.year if day.month >= self.fiscal_start else day.year - 1
        return date(year, self.fiscal_start, 1)

    def balances(self, since: date | None, until: date) -> dict[str, Decimal]:
        """Each account's net movement (debit positive) over [since, until]."""
        out: dict[str, Decimal] = defaultdict(Decimal)
        for transaction, lines in self.postings:
            for line in lines:
                on = line.on or transaction.on
                if on <= until and (since is None or on >= since):
                    out[line.account] += line.amount
        return out

    def as_presented(self, until: date) -> dict[str, Decimal]:
        """Debit-positive balances as QuickBooks presents them at `until`: balance-sheet
        accounts all time; income and expense from the fiscal year's start; and earlier years'
        profit carried into Retained Earnings. An account with any line in its span is kept at
        zero, because QuickBooks prints it; Retained Earnings, only when it has a figure.
        """
        year_start = self.fiscal_year_start(until)
        out = {
            k: v
            for k, v in self.balances(None, until).items()
            if self.type_of(k) not in PROFIT_AND_LOSS_TYPES | {"not_specified"}
        }
        prior = self.balances(None, year_start - timedelta(days=1))
        earlier = sum(
            (v for k, v in prior.items() if self.type_of(k) in PROFIT_AND_LOSS_TYPES), ZERO
        )
        out[RETAINED_EARNINGS] = out.get(RETAINED_EARNINGS, ZERO) + earlier
        for k, v in self.balances(year_start, until).items():
            if self.type_of(k) in PROFIT_AND_LOSS_TYPES:
                out[k] = v
        if not out[RETAINED_EARNINGS]:
            del out[RETAINED_EARNINGS]
        return out

    def all_dates(self, until: date) -> dict[str, Decimal]:
        """Debit-positive balances over all dates, as Export Data reports them: every account
        all time, and no year closed into Retained Earnings, which holds only what was posted
        to it."""
        out = {
            k: v
            for k, v in self.balances(None, until).items()
            if self.type_of(k) != "not_specified"
        }
        if not out.get(RETAINED_EARNINGS, 1):
            del out[RETAINED_EARNINGS]
        return out

    def trial_balance(
        self, until: date, *, closing: bool = True
    ) -> list[tuple[str, Decimal, Decimal]]:
        presented = self.as_presented(until) if closing else self.all_dates(until)
        return [
            (
                self.path(k),
                presented[k] if presented[k] > 0 else ZERO,
                -presented[k] if presented[k] < 0 else ZERO,
            )
            for k in self.ordered(presented)
        ]

    # --- the reports -------------------------------------------------------------------------

    def title(self, name: str, period: str) -> list[Row]:
        return [[COMPANY], [name], [period], []]

    def period(self) -> str:
        if self.start is None:
            return "All Dates"
        return f"{long_date(self.start)} - {long_date(self.end)}"

    def as_of(self) -> str:
        """A balance's period: all dates when the report has no start, as Export Data runs it.
        With a start, how QuickBooks names the period is not yet seen in a download."""
        return "All Dates" if self.start is None else f"As of {long_date(self.end)}"

    def footer(self) -> Row:
        return [f"{RUN_AT} - {self.rendering.basis.title()} Basis"]

    def in_range(self, transaction: Transaction) -> bool:
        return self.start is None or transaction.on >= self.start

    @staticmethod
    def number(text: str) -> Cell:
        """A document's number: a number cell where it is all digits, as QuickBooks has it."""
        if not text:
            return None
        return Number(Decimal(text)) if text.isdigit() else text

    def journal(self) -> list[Row]:
        """Every transaction with lines, as recorded: the journal has no basis. A blank row
        follows each transaction's totals."""
        rows: list[Row] = [*self.title("Journal", self.period()), JOURNAL_HEADER]
        debit_total = credit_total = ZERO
        for transaction in self.books.transactions:
            if not transaction.lines or not self.in_range(transaction):
                continue
            debit = credit = ZERO
            for index, line in enumerate(transaction.lines):
                first = index == 0
                rows.append(
                    [
                        None,
                        short_date(transaction.on) if first else None,
                        transaction.type if first else None,
                        self.number(transaction.number) if first else None,
                        (transaction.name or None) if first else None,
                        line.memo or None,
                        self.path(line.account) if line.account != NOT_SPECIFIED else None,
                        *self.amounts(transaction, line),
                    ]
                )
                debit += max(line.amount, ZERO)
                credit += max(-line.amount, ZERO)
            totals = [Number(debit), Number(credit)] if debit or credit else self.sides(ZERO)
            rows += [[*[None] * 7, *totals], []]
            debit_total += debit
            credit_total += credit
        rows.append(["TOTAL", *[None] * 6, Number(debit_total), Number(credit_total)])
        rows += [[], [], [RUN_AT]]
        return rows

    @staticmethod
    def sides(amount: Decimal) -> list[Cell]:
        """An amount on its debit or credit side; nothing, as a debit of zero."""
        if amount < 0:
            return [None, Number(-amount)]
        return [Number(amount), None]

    def amounts(self, transaction: Transaction, line: Posting) -> list[Cell]:
        """A line's amount cells. A payment's A/R line for several documents that net to
        nothing, as applying a credit memo is, shows no amount at all."""
        several = len(transaction.settles) + len(transaction.credits) > 1
        if line.account == RECEIVABLE and several and not line.amount:
            return [None, None]
        return self.sides(line.amount)

    def general_ledger(self) -> list[Row]:
        rows: list[Row] = [*self.title("General Ledger", self.period()), LEDGER_HEADER]
        by_account: dict[str, list[tuple[Transaction, Posting]]] = defaultdict(list)
        for transaction, lines in self.postings:
            for line in lines:
                if self.start is None or (line.on or transaction.on) >= self.start:
                    by_account[line.account].append((transaction, line))
        for entries in by_account.values():  # by day, as QuickBooks sorts a ledger
            entries.sort(key=lambda entry: entry[1].on or entry[0].on)
        opening: dict[str, Decimal] = {}
        if self.start is not None:
            # Balance-sheet accounts open with everything before the range; income and expense,
            # with what their fiscal year had booked before it; and Retained Earnings with every
            # earlier year's profit besides, as it is presented.
            year_start = self.fiscal_year_start(self.start)
            before = self.start - timedelta(days=1)
            year = self.balances(year_start, before)
            opening = {
                k: year.get(k, ZERO) if self.type_of(k) in PROFIT_AND_LOSS_TYPES else v
                for k, v in self.balances(None, before).items()
            }
            closed = sum(
                (
                    v
                    for k, v in self.balances(None, year_start - timedelta(days=1)).items()
                    if self.type_of(k) in PROFIT_AND_LOSS_TYPES
                ),
                ZERO,
            )
            opening[RETAINED_EARNINGS] = opening.get(RETAINED_EARNINGS, ZERO) + closed
        roots = [
            k
            for k in self.ordered(self.books.accounts)
            if self.books.accounts[k].parent is None
        ]
        for root in roots:
            rows += self.ledger_block(root, 0, by_account, opening)
        rows += [[], [], self.footer()]
        return rows

    def subtree(self, key: str) -> list[str]:
        return [key] + [
            k for child in self.ordered(self.children(key)) for k in self.subtree(child)
        ]

    def shown(self, transaction: Transaction, line: Posting) -> Transaction:
        """The transaction a ledger line is shown as: on the cash basis, a line recognized
        from an invoice or a bill is shown as that document."""
        return transaction if line.source is None else self.books.sources[line.source]

    @staticmethod
    def ledger_total(label: str, level: int, debit: Decimal, credit: Decimal) -> Row:
        """A ledger's total, indented to its level. An indented total's empty amount carries
        the indentation as text, as QuickBooks writes it; a total of nothing shows a zero
        debit."""
        pad = "   " * level

        def side(amount: Decimal) -> Cell:
            return Number(amount) if amount else (pad or None)

        amounts = (
            [Number(ZERO), pad or None]
            if not debit and not credit
            else [
                side(debit),
                side(credit),
            ]
        )
        return [pad + label, *[None] * 6, *amounts]

    def ledger_block(
        self,
        key: str,
        level: int,
        by_account: dict[str, list[tuple[Transaction, Posting]]],
        opening: dict[str, Decimal],
    ) -> list[Row]:
        """One account's entries and its children's, as the ledger lists them.

        The account is named by its leaf, indented three spaces a level, and each entry names
        it by its full path. Amounts sit on their debit or credit side; the running balance is
        on the account's natural side. A beginning balance is printed only where there is one.
        A parent's own entries are totalled one level in, apart from its children's, only when
        it has any.
        """
        if not any(by_account.get(k) or opening.get(k) for k in self.subtree(key)):
            return []
        rows: list[Row] = [["   " * level + self.leaf(key)]]
        balance = self.natural(key, opening.get(key, ZERO))
        if balance:
            rows.append([None, "Beginning Balance", *[None] * 7, Number(balance)])
        debit = credit = ZERO
        for transaction, line in by_account.get(key, []):
            shown = self.shown(transaction, line)
            balance += self.natural(key, line.amount)
            debit += max(line.amount, ZERO)
            credit += max(-line.amount, ZERO)
            rows.append(
                [
                    None,
                    short_date(line.on or transaction.on),
                    shown.type,
                    self.number(shown.number),
                    shown.name or None,  # the transaction's name, never a line's own
                    line.memo or None,
                    self.path(key) if key != NOT_SPECIFIED else None,
                    *self.amounts(transaction, line),
                    Number(balance),
                ]
            )
        children = self.ordered(self.children(key))
        own = bool(by_account.get(key) or opening.get(key))
        if own or not children:
            leaf = self.leaf(key)
            rows.append(
                self.ledger_total(f"Total for {leaf}", level + bool(children), debit, credit)
            )
        if children:
            for child in children:
                rows += self.ledger_block(child, level + 1, by_account, opening)
            sub_debit = sub_credit = ZERO
            for k in self.subtree(key):
                for _, line in by_account.get(k, []):
                    sub_debit += max(line.amount, ZERO)
                    sub_credit += max(-line.amount, ZERO)
            label = f"Total for {self.leaf(key)}" + (" with sub-accounts" if own else "")
            rows.append(self.ledger_total(label, level, sub_debit, sub_credit))
        return rows

    @staticmethod
    def sum_of(refs: list[int], column: str = "B") -> Formula:
        """A sum of the figures in these rows, nested as QuickBooks writes it:
        `((B11)+(B14))+(B18)`."""
        text = f"{column}{refs[0]}"
        for ref in refs[1:]:
            text = f"({text})+({column}{ref})"
        return Formula(text)

    def statement_rows(
        self, rows: list[Row], kinds: tuple[str, ...], figures: dict[str, Decimal], indent: int
    ) -> list[int]:
        """The accounts of these types, appended to `rows` as a statement lists them; returns
        the rows that hold each top-level account's figure, for the total above to sum.

        A parent's own figure is on its row, its children indented beneath, and its total after
        them, which sums its row and theirs. An account with nothing in its subtree is left out.
        Figures are on the account's natural side, each written as a formula.
        """

        def block(key: str, depth: int) -> int | None:
            if not any(k in figures for k in self.subtree(key)):
                return None
            pad = "   " * depth
            own = figures.get(key)
            children = self.ordered(self.children(key))
            if not children:
                rows.append([pad + self.leaf(key), Formula.of(ZERO if own is None else own)])
                return len(rows)
            rows.append([pad + self.leaf(key), Formula.of(own) if own else None])
            refs = [len(rows)]
            for child in children:
                ref = block(child, depth + 1)
                if ref is not None:
                    refs.append(ref)
            rows.append([f"{pad}Total {self.leaf(key)}", self.sum_of(refs)])
            return len(rows)

        roots = self.ordered(
            k
            for k, a in self.books.accounts.items()
            if a.parent is None and self.type_of(k) in kinds
        )
        return [ref for root in roots if (ref := block(root, indent)) is not None]

    def natural(self, key: str, debit_positive: Decimal) -> Decimal:
        return -debit_positive if self.type_of(key) in CREDIT_NATURE else debit_positive

    def profit_and_loss(self) -> list[Row]:
        figures = {
            k: self.natural(k, v)
            for k, v in self.balances(self.start, self.end).items()
            if self.type_of(k) in PROFIT_AND_LOSS_TYPES
        }
        rows: list[Row] = [*self.title("Profit and Loss", self.period()), [None, "Total"]]
        totals: dict[str, int] = {}
        for label, kind in (
            ("Income", "income"),
            ("Cost of Goods Sold", "cost_of_sales"),
            ("Expenses", "expense"),
            ("Other Income", "other_income"),
            ("Other Expenses", "other_expense"),
        ):
            rows.append([label, None])
            refs = self.statement_rows(rows, (kind,), figures, 1)
            if not refs:
                raise ValueError(f"no {label}: a statement without it is not yet seen")
            rows.append([f"Total {label}", self.sum_of(refs)])
            totals[kind] = len(rows)
            if kind == "cost_of_sales":
                rows.append(
                    ["Gross Profit", Formula(f"(B{totals['income']})-(B{totals[kind]})")]
                )
                totals["gross"] = len(rows)
            if kind == "expense":
                rows.append(
                    ["Net Operating Income", Formula(f"(B{totals['gross']})-(B{totals[kind]})")]
                )
                totals["operating"] = len(rows)
        other = f"(B{totals['other_income']})-(B{totals['other_expense']})"
        rows.append(["Net Other Income", Formula(other)])
        rows.append(["Net Income", Formula(f"(B{totals['operating']})+(B{len(rows)})")])
        rows += [[], [], [], self.footer()]
        return rows

    def balance_sheet(self) -> list[Row]:
        """The balance sheet over the report's span: over all dates, as Export Data runs it,
        no year is closed, so Net Income is every year's and Retained Earnings holds only what
        was posted to it; from a start, the fiscal year's income, earlier years closed."""
        if self.start is None:
            presented = self.all_dates(self.end)
            year_start: date | None = None
        else:
            presented = self.as_presented(self.end)
            year_start = self.fiscal_year_start(self.end)
        net_income = -sum(
            (
                v
                for k, v in self.balances(year_start, self.end).items()
                if self.type_of(k) in PROFIT_AND_LOSS_TYPES
            ),
            ZERO,
        )
        figures = {
            k: self.natural(k, v)
            for k, v in presented.items()
            if self.type_of(k) not in PROFIT_AND_LOSS_TYPES
        }
        rows: list[Row] = [*self.title("Balance Sheet", self.as_of()), [None, "Total"]]

        def group(label: str, kinds: tuple[str, ...], indent: int) -> int | None:
            at = len(rows)
            pad = "   " * indent
            rows.append([pad + label, None])
            refs = self.statement_rows(rows, kinds, figures, indent + 1)
            if not refs:
                del rows[at:]
                return None
            rows.append([f"{pad}Total {label}", self.sum_of(refs)])
            return len(rows)

        def total(label: str, refs: list[int | None]) -> int:
            rows.append([label, self.sum_of([r for r in refs if r is not None])])
            return len(rows)

        rows += [["ASSETS", None], ["   Current Assets", None]]
        current = [
            group("Bank Accounts", ("bank",), 2),
            group("Accounts Receivable", ("receivable",), 2),
            group("Other Current Assets", ("other_current_asset",), 2),
        ]
        current_assets = total("   Total Current Assets", current)
        fixed = group("Fixed Assets", ("fixed_asset",), 1)
        total("TOTAL ASSETS", [current_assets, fixed])

        rows += [["LIABILITIES AND EQUITY", None], ["   Liabilities", None]]
        rows.append(["      Current Liabilities", None])
        current = [
            group("Accounts Payable", ("payable",), 3),
            group("Credit Cards", ("credit_card",), 3),
            group("Other Current Liabilities", ("other_current_liability",), 3),
        ]
        current_liabilities = total("      Total Current Liabilities", current)
        long_term = group("Long-Term Liabilities", ("long_term_liability",), 2)
        liabilities = total("   Total Liabilities", [current_liabilities, long_term])

        # Retained Earnings is always printed, and printed blank when it has no figure.
        figures.setdefault(RETAINED_EARNINGS, ZERO)
        rows.append(["   Equity", None])
        equity = self.statement_rows(rows, ("equity",), figures, 2)
        for ref in equity:
            if rows[ref - 1] == ["      Retained Earnings", Formula.of(ZERO)]:
                rows[ref - 1] = ["      Retained Earnings", None]
        rows.append(["      Net Income", Formula.of(net_income)])
        equity_total = total("   Total Equity", [*equity, len(rows)])
        total("TOTAL LIABILITIES AND EQUITY", [liabilities, equity_total])
        rows += [[], [], [], self.footer()]
        return rows

    def trial_balance_report(self) -> list[Row]:
        """The trial balance over the report's span, each figure a formula and the totals sums
        of every row above: over all dates, as Export Data runs it, nothing is closed; from a
        start, as it stands at the end."""
        rows: list[Row] = [
            *self.title("Trial Balance", self.as_of()),
            [None, "Debit", "Credit"],
        ]
        first = len(rows) + 1
        for name, debit, credit in self.trial_balance(self.end, closing=self.start is not None):
            rows.append(
                [
                    name,
                    Formula.of(debit) if debit or not credit else None,
                    Formula.of(credit) if credit else None,
                ]
            )
        refs = list(range(first, len(rows) + 1))
        rows.append(["TOTAL", self.sum_of(refs, "B"), self.sum_of(refs, "C")])
        rows += [[], [], [], self.footer()]
        return rows

    def contact_list(self, title: str, header: Row, names: Iterable[str]) -> list[Row]:
        """A contact list as Export Data writes one: each name, and nothing else the company
        never entered."""
        rows: list[Row] = [[COMPANY], [title], [""], [], header]
        listed: list[Row] = [[None, name] for name in sorted(names)]
        rows += listed or [[], ["This report contains no data."]]
        rows += [[], [], [RUN_AT]] if listed else [[], [RUN_AT]]
        return rows

    def customers(self) -> list[Row]:
        return self.contact_list(
            "Customer Contact List", CUSTOMER_HEADER, self.books.customers.values()
        )

    def vendors(self) -> list[Row]:
        return self.contact_list(
            "Vendor Contact List", VENDOR_HEADER, self.books.vendors.values()
        )

    def employees(self) -> list[Row]:
        return self.contact_list("Employee Contact List", EMPLOYEE_HEADER, ())


# In the order Export Data writes them.
REPORTS = (
    ("Balance_sheet.xlsx", Report.balance_sheet),
    ("Customers.xlsx", Report.customers),
    ("Employees.xlsx", Report.employees),
    ("General_ledger.xlsx", Report.general_ledger),
    ("Journal.xlsx", Report.journal),
    ("Profit_and_loss.xlsx", Report.profit_and_loss),
    ("Vendors.xlsx", Report.vendors),
    ("Trial_balance.xlsx", Report.trial_balance_report),
)


def sheets(books: Books, rendering: Rendering) -> dict[str, list[Row]]:
    report = Report(books, rendering)
    return {member: write(report) for member, write in REPORTS}


def export(books: Books, rendering: Rendering) -> bytes:
    """One rendering of the books, as the archive Export Data writes."""
    return archive(
        {member: workbook(rows) for member, rows in sheets(books, rendering).items()}
    )


def month_ends() -> Iterator[date]:
    for first in months():
        yield month_end(first)


def trial_balances(books: Books, rendering: Rendering) -> str:
    """The trial balance at every month end, as JSON: what the round trip compares against."""
    report = Report(books, rendering)
    out: dict[str, list[dict[str, str]]] = {}
    for day in month_ends():
        out[day.isoformat()] = [
            {"account": name, "debit": format(debit, "f"), "credit": format(credit, "f")}
            for name, debit, credit in report.trial_balance(day)
        ]
    return json.dumps(out, ensure_ascii=False, indent=1) + "\n"
