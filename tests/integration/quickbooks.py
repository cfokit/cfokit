"""Converting a QuickBooks export into the interchange format (`IMP-08` case 3).

A QuickBooks Online export is a zip of `.xlsx` reports. This reads three of them and produces
the same three CSVs a conformance case uses, so the reconciler and the loader never learn what
QuickBooks is and a second source needs a converter rather than a second pipeline.

**The converter transforms inputs only.** ADR-0010 rejected a Beancount translator because it
would be "untested code sitting between the system and its own correctness evidence… a defect in
it produces false agreement as readily as false divergence". That objection does not reach here:
the expected answer arrives through a *different report in the same export*, so a converter bug
corrupts the journal and the reconciliation then fails loudly rather than agreeing falsely.

**Account types come from the source's own statements**, not from us. An account under `ASSETS`
on the balance sheet is an asset; one under `Income` on the profit and loss is income. Guessing
a type from an account's name would put our judgement into data whose whole value is that it is
not ours.

**Accounts are identified by name.** QuickBooks has no account codes, so the name — the full
colon-separated path — is what the two systems agree on, and it is what the interchange format's
`code` column carries here.

**Basis matters, and the export's reports are not all usable.** Every report in a QuickBooks
export carries its accounting method in its footer. `Journal.xlsx` is the accrual record; a
report run on a cash basis does not sum to it and must not be used as its oracle.
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

import openpyxl

__all__ = ["Converted", "convert", "read_basis"]

Row = tuple[object, ...]

# Column positions in the Journal report, from its header row.
_DATE, _ACCOUNT, _DEBIT, _CREDIT, _MEMO = 1, 6, 7, 8, 5
_HEADER_ROWS = 5

_BALANCE_SHEET_SECTIONS = {
    "ASSETS": "asset",
    "LIABILITIES AND EQUITY": None,  # split further by its own subsections
    "Liabilities": "liability",
    "Equity": "equity",
}
_INCOME_STATEMENT_SECTIONS = {"Income": "income", "Expenses": "expense"}


@dataclass(frozen=True, slots=True)
class Converted:
    """One export, in the interchange format."""

    accounts: list[dict[str, str]] = field(default_factory=list)
    journal: list[dict[str, str]] = field(default_factory=list)
    trial_balance: list[dict[str, str]] = field(default_factory=list)
    trial_balance_basis: str = "unknown"
    # The general ledger prints its own total per account. That is the source computing a
    # balance from its own data, which is what makes it usable as an oracle: our arithmetic
    # against theirs over the same journal. The trial balance is not usable that way when it
    # is run on a different accounting method from the journal beside it.
    ledger_totals: list[dict[str, str]] = field(default_factory=list)
    # Subtotals the same report prints over a parent and everything beneath it. Held apart
    # from `ledger_totals` because a subtotal is not an account's balance: nothing posts to
    # it, and comparing it against a chart account would report a divergence that is really a
    # difference in what the two figures are. Reconciled by summing the children instead.
    ledger_rollups: list[dict[str, str]] = field(default_factory=list)
    # The accounting method the general ledger was run on, from its own footer. Load-bearing
    # rather than informational: CFOKit's books are intrinsically accrual (ADR-0037), so a
    # cash-basis oracle will differ on exactly the obligation accounts, and a reader who does
    # not know the basis cannot tell that apart from a defect.
    ledger_basis: str = "unknown"
    transactions: int = 0


def read_basis(rows: Sequence[Row]) -> str:
    """The accounting method a report was run on, from its footer.

    QuickBooks prints it on the last labelled row — "… - Cash Basis" or "… - Accrual Basis".
    A report whose basis cannot be read is `unknown`, which callers must treat as unusable
    rather than assume.
    """
    for row in reversed(rows):
        label = row[0]
        if label is None:
            continue
        text = str(label)
        if "Cash Basis" in text:
            return "cash"
        if "Accrual Basis" in text:
            return "accrual"
        break
    return "unknown"


def convert(archive: bytes) -> Converted:
    """Read a QuickBooks export and produce the interchange format."""
    with zipfile.ZipFile(io.BytesIO(archive)) as export:
        types = _account_types(export)
        journal, transactions = _journal(export)
        trial_balance, basis = _trial_balance(export)
        ledger_totals, ledger_rollups, ledger_basis = _ledger_totals(export, journal)

    used = {line["account_code"] for line in journal} | {
        row["account_code"] for row in trial_balance
    }
    return Converted(
        accounts=[
            {
                "code": name,
                "name": name,
                "type": _typed(name, types),
                "parent": _parent(name, used),
            }
            for name in sorted(used)
        ],
        journal=journal,
        trial_balance=trial_balance,
        trial_balance_basis=basis,
        ledger_totals=ledger_totals,
        ledger_rollups=ledger_rollups,
        ledger_basis=ledger_basis,
        transactions=transactions,
    )


def _typed(name: str, types: dict[str, str]) -> str:
    """An account's type, from the statement it appears on or from its parent's.

    QuickBooks prints a sub-account under its bare leaf name on the balance sheet and the profit
    and loss, so the full colon-separated path the journal uses never matches one of those rows.
    Walking up the path is not a guess about the account: QuickBooks requires a sub-account to
    share its parent's type, and the path is the source stating the hierarchy.

    Unknown means the account appears in the journal and beneath no statement section at all —
    recorded as such rather than guessed, because a wrong type is a silent misclassification and
    a missing one is a question somebody can answer.
    """
    parts = name.split(":")
    for cut in range(len(parts), 0, -1):
        stated = types.get(":".join(parts[:cut]))
        if stated is not None:
            return stated
    return "unknown"


def _parent(name: str, accounts: set[str]) -> str:
    """The account this one sits under, where the export has one.

    A parent that takes no postings of its own is not in the journal and so is not an account
    here; the child is then reported as top-level rather than pointing at something absent.
    """
    parts = name.split(":")
    for cut in range(len(parts) - 1, 0, -1):
        candidate = ":".join(parts[:cut])
        if candidate in accounts:
            return candidate
    return ""


def _account_types(export: zipfile.ZipFile) -> dict[str, str]:
    """Map each account to a type, using the source's own statement sections."""
    types: dict[str, str] = {}
    for member, sections in (
        ("Balance_sheet.xlsx", _BALANCE_SHEET_SECTIONS),
        ("Profit_and_loss.xlsx", _INCOME_STATEMENT_SECTIONS),
    ):
        if member not in export.namelist():
            continue
        rows = _rows(export, member)
        current: str | None = None
        for row in rows[_HEADER_ROWS:]:
            label = row[0]
            if label is None:
                continue
            text = str(label).strip()
            if text in sections:
                current = sections[text]
                continue
            # "Total X" and "TOTAL X" are subtotals, not accounts.
            if text.upper().startswith("TOTAL") or text.startswith("Gross "):
                continue
            if current is not None and any(cell is not None for cell in row[1:]):
                types.setdefault(text, current)
    return types


def _journal(export: zipfile.ZipFile) -> tuple[list[dict[str, str]], int]:
    """Every posting line, grouped into transactions.

    A transaction begins on the row carrying a date; its remaining lines carry none. Each group
    ends with a totals row that has amounts and no account — skipped, or every transaction would
    count twice.
    """
    rows = _rows(export, "Journal.xlsx")
    lines: list[dict[str, str]] = []
    reference = 0
    when: date | None = None

    for row in rows[_HEADER_ROWS:]:
        if row[_DATE] is not None:
            reference += 1
            when = _as_date(row[_DATE])
        account = row[_ACCOUNT]
        if account is None or when is None:
            continue
        lines.append(
            {
                "ref": str(reference),
                "date": when.isoformat(),
                "description": str(row[_MEMO] or ""),
                "account_code": str(account),
                "amount": str(_amount(row[_DEBIT]) - _amount(row[_CREDIT])),
                "commodity": "USD",
            }
        )
    return lines, reference


def _trial_balance(export: zipfile.ZipFile) -> tuple[list[dict[str, str]], str]:
    rows = _rows(export, "Trial_balance.xlsx")
    basis = read_basis(rows)
    balances: list[dict[str, str]] = []
    for row in rows[_HEADER_ROWS:]:
        label = row[0]
        if label is None:
            continue
        text = str(label).strip()
        if text.upper().startswith("TOTAL") or "Basis" in text:
            continue
        balance = _amount(row[1]) - _amount(row[2])
        balances.append({"account_code": text, "balance": str(balance)})
    return balances, basis


def _ledger_totals(
    export: zipfile.ZipFile, journal: Sequence[dict[str, str]]
) -> tuple[list[dict[str, str]], list[dict[str, str]], str]:
    """The general ledger's own stated totals, split into account balances and rollups, and
    the accounting method it was run on.

    QuickBooks closes each account's section with a "Total for <account>" row. Those are the
    source's own balances — the figure to reconcile against — and they cover only accounts with
    activity, which is why an account may be in the journal and absent here.

    Some of those rows are **subtotals over a parent and its children**, printed as
    "Total for X with sub-accounts" where the parent also takes postings of its own, and as a
    bare "Total for X" where it does not. Both are recognised, and the bare case is decided
    against the export's own data rather than its wording: a bare total is a rollup only when
    the journal posts beneath that parent and never to the parent itself. A parent that takes
    direct postings therefore keeps its own balance in `ledger_totals` and contributes its
    "with sub-accounts" row to `ledger_rollups`, which is what those two rows mean.

    The two are returned apart because they answer different questions, and comparing a subtotal
    against a chart account would manufacture a divergence out of a category error.
    """
    if "General_ledger.xlsx" not in export.namelist():
        return [], [], "unknown"
    rows = _rows(export, "General_ledger.xlsx")
    posted_to = {line["account_code"] for line in journal}
    totals: list[dict[str, str]] = []
    rollups: list[dict[str, str]] = []
    for row in rows[_HEADER_ROWS:]:
        label = row[0]
        if label is None or not str(label).startswith("Total for "):
            continue
        account = str(label)[len("Total for ") :].strip()
        parent = account.removesuffix(" with sub-accounts")
        stated = {
            "account_code": parent,
            "balance": str(_amount(row[_DEBIT]) - _amount(row[_CREDIT])),
        }
        has_children = any(code.startswith(parent + ":") for code in posted_to)
        if account != parent or (has_children and parent not in posted_to):
            rollups.append(stated)
        else:
            totals.append(stated)
    return totals, rollups, read_basis(rows)


def _rows(export: zipfile.ZipFile, member: str) -> list[Row]:
    """One report's cells.

    Rows rather than a worksheet, so nothing downstream needs openpyxl's types — and the two
    shapes `load_workbook` returns for read-only and normal mode stop mattering.
    """
    workbook = openpyxl.load_workbook(
        io.BytesIO(export.read(member)), read_only=True, data_only=True
    )
    try:
        return list(workbook.worksheets[0].iter_rows(values_only=True))
    finally:
        workbook.close()


def _amount(value: object) -> Decimal:
    """A cell as an exact decimal.

    `Decimal(str(value))` rather than `Decimal(value)`: a float's binary expansion is not the
    figure the workbook shows, and `LED-04` allows no representation error.
    """
    if value is None:
        return Decimal(0)
    return Decimal(str(value))


def _as_date(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value), "%m/%d/%Y").date()  # noqa: DTZ007
