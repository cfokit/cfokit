"""The QuickBooks Online export, written from what QuickBooks records (`quickbooks_books`).

One archive per rendering: the same books, run on a basis, with or without account numbers, over
all dates or one fiscal year, under a fiscal year starting in July or January. Each archive
holds the five reports Export Data writes — Journal, General Ledger, Profit and Loss, Balance
Sheet and Trial Balance — and beside it, the trial balance at every month end, which the round
trip compares against.

**The layout is our belief about QuickBooks**, taken from the reader and the export it was built
against: three title rows, a blank row and a header row before the body; sub-accounts indented
three spaces a level on a statement and named by full path elsewhere; statement figures as
formulas holding a number; each report's basis in its footer, and none on the journal. ADR-0075
checks it against one real export, cell by cell, and the content against the Reports API.
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
from synthetic_books.events import RETAINED_EARNINGS
from synthetic_books.quickbooks_books import ZERO, Books, Posting, Transaction, cash_lines
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
LEDGER_HEADER: Row = [*JOURNAL_HEADER[:6], "Split", "Debit", "Credit", "Balance"]

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
            if transaction.on > until or (since is not None and transaction.on < since):
                continue
            for line in lines:
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
            if self.type_of(k) not in PROFIT_AND_LOSS_TYPES
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

    def trial_balance(self, until: date) -> list[tuple[str, Decimal, Decimal]]:
        presented = self.as_presented(until)
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

    def footer(self) -> Row:
        return [f"{RUN_AT} - {self.rendering.basis.title()} Basis"]

    def in_range(self, transaction: Transaction) -> bool:
        return self.start is None or transaction.on >= self.start

    def journal(self) -> list[Row]:
        """Every transaction with lines, as recorded: the journal has no basis."""
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
                        (transaction.number or None) if first else None,
                        (transaction.name or None) if first else None,
                        line.memo or None,
                        self.path(line.account),
                        *self.sides(line.amount),
                    ]
                )
                debit += max(line.amount, ZERO)
                credit += max(-line.amount, ZERO)
            rows.append([*[None] * 7, Number(debit), Number(credit)])
            debit_total += debit
            credit_total += credit
        rows.append(["TOTAL", *[None] * 6, Number(debit_total), Number(credit_total)])
        rows += [[], [RUN_AT]]
        return rows

    @staticmethod
    def sides(amount: Decimal) -> list[Cell]:
        if amount > 0:
            return [Number(amount), None]
        if amount < 0:
            return [None, Number(-amount)]
        return [None, None]

    def general_ledger(self) -> list[Row]:
        rows: list[Row] = [*self.title("General Ledger", self.period()), LEDGER_HEADER]
        by_account: dict[str, list[tuple[Transaction, Posting]]] = defaultdict(list)
        for transaction, lines in self.postings:
            if self.in_range(transaction):
                for line in lines:
                    by_account[line.account].append((transaction, line))
        opening: dict[str, Decimal] = {}
        if self.start is not None:
            # Balance-sheet accounts open with everything before the range; income and expense,
            # with what their fiscal year had booked before it.
            before = self.start - timedelta(days=1)
            year = self.balances(self.fiscal_year_start(self.start), before)
            opening = {
                k: year.get(k, ZERO) if self.type_of(k) in PROFIT_AND_LOSS_TYPES else v
                for k, v in self.balances(None, before).items()
            }
        roots = [
            k
            for k in self.ordered(self.books.accounts)
            if self.books.accounts[k].parent is None
        ]
        for root in roots:
            rows += self.ledger_block(root, by_account, opening)
        rows += [[], self.footer()]
        return rows

    def subtree(self, key: str) -> list[str]:
        return [key] + [
            k for child in self.ordered(self.children(key)) for k in self.subtree(child)
        ]

    def shown(self, transaction: Transaction, line: Posting) -> tuple[Transaction, str]:
        """The transaction a ledger line is shown as, and its Split: the other side of the line
        as it was recorded, whatever the basis.

        A line the cash basis recognizes from an invoice or a bill is shown as that document,
        split against its first line. Every line of a journal entry is "-Split-". A document's
        first line is split against the rest, which is "-Split-" when the rest is more than one
        line; any other line, against the first.
        """
        if line.source is not None:
            document = self.books.sources[line.source]
            return document, self.path(document.lines[0].account)
        if transaction.type == "Journal Entry":
            return transaction, "-Split-"
        first, *rest = transaction.lines
        if line.account != first.account:
            return transaction, self.path(first.account)
        return transaction, self.path(rest[0].account) if len(rest) == 1 else "-Split-"

    def ledger_block(
        self,
        key: str,
        by_account: dict[str, list[tuple[Transaction, Posting]]],
        opening: dict[str, Decimal],
    ) -> list[Row]:
        """One account's entries and its children's, as the ledger lists them.

        Amounts sit on their debit or credit side; the running balance is on the account's
        natural side, as QuickBooks keeps it. A beginning balance is printed only where there is
        one. A parent's own entries are totalled apart from its children's only when it has any.
        """
        if not any(by_account.get(k) or opening.get(k) for k in self.subtree(key)):
            return []
        rows: list[Row] = [[self.path(key)]]
        balance = self.natural(key, opening.get(key, ZERO))
        if balance:
            rows.append([None, "Beginning Balance", *[None] * 7, Number(balance)])
        debit = credit = ZERO
        for transaction, line in by_account.get(key, []):
            shown, split = self.shown(transaction, line)
            balance += self.natural(key, line.amount)
            debit += max(line.amount, ZERO)
            credit += max(-line.amount, ZERO)
            rows.append(
                [
                    None,
                    short_date(transaction.on),
                    shown.type,
                    shown.number or None,
                    line.name or shown.name or None,
                    line.memo or None,
                    split,
                    *self.sides(line.amount),
                    Number(balance),
                ]
            )
        children = self.ordered(self.children(key))
        own = bool(by_account.get(key) or opening.get(key))
        if own or not children:
            rows.append(
                [f"Total for {self.path(key)}", *[None] * 6, Number(debit), Number(credit)]
            )
        if children:
            for child in children:
                rows += self.ledger_block(child, by_account, opening)
            sub_debit = sub_credit = ZERO
            for k in self.subtree(key):
                for _, line in by_account.get(k, []):
                    sub_debit += max(line.amount, ZERO)
                    sub_credit += max(-line.amount, ZERO)
            label = f"Total for {self.path(key)}" + (" with sub-accounts" if own else "")
            rows.append([label, *[None] * 6, Number(sub_debit), Number(sub_credit)])
        return rows

    def statement_rows(
        self, kinds: tuple[str, ...], figures: dict[str, Decimal], indent: int
    ) -> tuple[list[Row], Decimal]:
        """The accounts of these types as a statement lists them, and their total.

        A parent's own figure is on its row, its children indented beneath, and its total after
        them. An account with nothing in its subtree is left out. Figures are on the account's
        natural side.
        """

        def block(key: str, depth: int) -> list[Row]:
            if not any(k in figures for k in self.subtree(key)):
                return []
            pad = "   " * depth
            own = figures.get(key, ZERO)
            children = self.ordered(self.children(key))
            if not children:
                return [[pad + self.leaf(key), Formula(own)]]
            total = sum((figures.get(k, ZERO) for k in self.subtree(key)), ZERO)
            rows: list[Row] = [[pad + self.leaf(key), Formula(own) if own else None]]
            for child in children:
                rows += block(child, depth + 1)
            return [*rows, [f"{pad}Total {self.leaf(key)}", Formula(total)]]

        roots = self.ordered(
            k
            for k, a in self.books.accounts.items()
            if a.parent is None and self.type_of(k) in kinds
        )
        rows = [row for root in roots for row in block(root, indent)]
        total = sum((v for k, v in figures.items() if self.type_of(k) in kinds), ZERO)
        return rows, total

    def natural(self, key: str, debit_positive: Decimal) -> Decimal:
        return -debit_positive if self.type_of(key) in CREDIT_NATURE else debit_positive

    def profit_and_loss(self) -> list[Row]:
        figures = {
            k: self.natural(k, v)
            for k, v in self.balances(self.start, self.end).items()
            if self.type_of(k) in PROFIT_AND_LOSS_TYPES
        }
        rows: list[Row] = [*self.title("Profit and Loss", self.period()), [None, "Total"]]
        totals: dict[str, Decimal] = {}
        for label, kind in (
            ("Income", "income"),
            ("Cost of Goods Sold", "cost_of_sales"),
            ("Expenses", "expense"),
            ("Other Income", "other_income"),
            ("Other Expenses", "other_expense"),
        ):
            body, totals[kind] = self.statement_rows((kind,), figures, 1)
            if body:
                rows += [[label, None], *body, [f"Total {label}", Formula(totals[kind])]]
            if kind == "cost_of_sales":
                rows.append(["Gross Profit", Formula(totals["income"] - totals[kind])])
            if kind == "expense":
                operating = totals["income"] - totals["cost_of_sales"] - totals[kind]
                rows.append(["Net Operating Income", Formula(operating)])
        other = totals["other_income"] - totals["other_expense"]
        net = totals["income"] - totals["cost_of_sales"] - totals["expense"] + other
        rows += [["Net Other Income", Formula(other)], ["Net Income", Formula(net)]]
        rows += [[], self.footer()]
        return rows

    def balance_sheet(self) -> list[Row]:
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
        rows: list[Row] = [
            *self.title("Balance Sheet", f"As of {long_date(self.end)}"),
            [None, "Total"],
        ]

        def group(label: str, kinds: tuple[str, ...], indent: int) -> tuple[list[Row], Decimal]:
            body, total = self.statement_rows(kinds, figures, indent + 1)
            if not body:
                return [], total
            pad = "   " * indent
            return [[pad + label, None], *body, [f"{pad}Total {label}", Formula(total)]], total

        bank, bank_total = group("Bank Accounts", ("bank",), 2)
        receivable, receivable_total = group("Accounts Receivable", ("receivable",), 2)
        other_current, other_total = group("Other Current Assets", ("other_current_asset",), 2)
        current = bank_total + receivable_total + other_total
        fixed, fixed_total = group("Fixed Assets", ("fixed_asset",), 1)
        rows += [
            ["ASSETS", None],
            ["   Current Assets", None],
            *bank,
            *receivable,
            *other_current,
        ]
        rows += [["   Total Current Assets", Formula(current)], *fixed]
        rows += [["TOTAL ASSETS", Formula(current + fixed_total)]]

        payable, payable_total = group("Accounts Payable", ("payable",), 3)
        cards, cards_total = group("Credit Cards", ("credit_card",), 3)
        other_liabilities, other_liabilities_total = group(
            "Other Current Liabilities", ("other_current_liability",), 3
        )
        current_liabilities = payable_total + cards_total + other_liabilities_total
        long_term, long_term_total = group("Long-Term Liabilities", ("long_term_liability",), 2)
        liabilities = current_liabilities + long_term_total
        rows += [["LIABILITIES AND EQUITY", None], ["   Liabilities", None]]
        rows += [["      Current Liabilities", None], *payable, *cards, *other_liabilities]
        rows += [["      Total Current Liabilities", Formula(current_liabilities)], *long_term]
        rows += [["   Total Liabilities", Formula(liabilities)]]

        # Retained Earnings is always printed, and printed blank when it has no figure.
        figures.setdefault(RETAINED_EARNINGS, ZERO)
        equity_rows, equity = self.statement_rows(("equity",), figures, 2)
        equity_rows = [
            [row[0], None]
            if row[1] == Formula(ZERO) and row[0] == "      Retained Earnings"
            else row
            for row in equity_rows
        ]
        rows += [["   Equity", None], *equity_rows, ["      Net Income", Formula(net_income)]]
        rows += [["   Total Equity", Formula(equity + net_income)]]
        rows += [["TOTAL LIABILITIES AND EQUITY", Formula(liabilities + equity + net_income)]]
        rows += [[], self.footer()]
        return rows

    def trial_balance_report(self) -> list[Row]:
        rows: list[Row] = [
            *self.title("Trial Balance", f"As of {long_date(self.end)}"),
            [None, "Debit", "Credit"],
        ]
        debit_total = credit_total = ZERO
        for name, debit, credit in self.trial_balance(self.end):
            rows.append(
                [
                    name,
                    Number(debit) if debit or not credit else None,
                    Number(credit) if credit else None,
                ]
            )
            debit_total += debit
            credit_total += credit
        rows += [["TOTAL", Number(debit_total), Number(credit_total)], [], self.footer()]
        return rows


REPORTS = (
    ("Journal.xlsx", Report.journal),
    ("General_ledger.xlsx", Report.general_ledger),
    ("Profit_and_loss.xlsx", Report.profit_and_loss),
    ("Balance_sheet.xlsx", Report.balance_sheet),
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
