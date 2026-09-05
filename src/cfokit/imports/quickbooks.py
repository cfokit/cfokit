"""Reading a QuickBooks Online export (`IMP-01`, `IMP-02`).

A QuickBooks Online export is a zip of `.xlsx` reports. This reads four of them and produces
`SourceBooks`, so nothing below it learns what QuickBooks is and a second source is a reader
rather than a second pipeline.

**The reader transforms inputs only.** ADR-0010 rejected a Beancount translator because it
would be "untested code sitting between the system and its own correctness evidence… a defect in
it produces false agreement as readily as false divergence". That objection does not reach here:
the expected answer arrives through a *different report in the same export*, so a reader bug
corrupts the journal and the reconciliation then fails loudly rather than agreeing falsely.

**Account types come from the source's own statements**, not from us. An account under `ASSETS`
on the balance sheet is an asset; one under `Income` on the profit and loss is income. Guessing
a type from an account's name would put our judgement into data whose whole value is that it is
not ours.

**Accounts are identified by name.** QuickBooks has no account codes, so the name — the full
colon-separated path — is what the two systems agree on, and it is what the `code` carries here.

**Basis matters, and the export's reports are not all usable.** Every report in a QuickBooks
export carries its accounting method in its footer. `Journal.xlsx` is the accrual record; a
report run on a cash basis does not sum to it and must not be used as its oracle.
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal

import openpyxl

from cfokit.imports.source import (
    SourceAccount,
    SourceBooks,
    SourceEntry,
    SourceLine,
    StatedBalance,
)

__all__ = ["SYSTEM", "read", "read_basis"]

# What `IMP-04` requires an imported record to name.
SYSTEM = "QuickBooks Online"

# QuickBooks Online exports one currency per company file, and states it nowhere in these
# reports. Declared here rather than guessed from a cell: `IMP-07` refuses a foreign amount, and
# that refusal is worth nothing if the commodity was inferred.
_COMMODITY = "USD"

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


def read(archive: bytes) -> SourceBooks:
    """One QuickBooks export, as `SourceBooks`.

    The general ledger's own per-account totals are the oracle, not the trial balance. Every
    *report* in an export carries its accounting method in its footer; `Journal.xlsx` carries
    none, because it is the raw record rather than a view of it.

    So the two bases come from different files and mean different things. `basis` is the
    journal's — `unknown` for QuickBooks, which is honest: it prints none. `balances_basis` is
    the general ledger's, and it is routinely `cash` on the same export whose journal is
    accrual. Reconciling one against the other then diverges on exactly the obligation
    accounts, which ADR-0037 predicts and `IMP-08` reports rather than tolerates.
    """
    with zipfile.ZipFile(io.BytesIO(archive)) as export:
        types = _account_types(export)
        entries = _entries(export)
        basis = read_basis(_rows(export, "Journal.xlsx"))
        balances, rollups, balances_basis = _ledger_totals(export, entries)
        commodity = _COMMODITY

    used = sorted({line.account_code for entry in entries for line in entry.lines})
    return SourceBooks(
        system=SYSTEM,
        basis=basis,
        balances_basis=balances_basis,
        commodity=commodity,
        accounts=tuple(
            SourceAccount(
                code=name,
                name=name,
                account_type=_typed(name, types),
                parent=_parent(name, set(used)),
            )
            for name in used
        ),
        entries=entries,
        balances=balances,
        rollups=rollups,
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
    # Last resort: the bare leaf. A statement prints "Accounting Services" indented under its
    # parent's header, and the header itself carries no amount when the parent takes no
    # postings of its own — so neither the full path nor any prefix of it matches a row, while
    # the leaf matches exactly. Tried after every prefix, because a leaf name can repeat under
    # two parents and the more specific answer should win where there is one.
    return types.get(parts[-1], "unknown")


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


def _entries(export: zipfile.ZipFile) -> tuple[SourceEntry, ...]:
    """Every transaction in the journal, with its lines.

    A transaction begins on the row carrying a date; its remaining lines carry none. Each group
    ends with a totals row that has amounts and no account — skipped, or every transaction would
    count twice.

    The reference is positional because QuickBooks' journal prints no stable identifier for a
    transaction. Positional is honest about what it is: it identifies the row in *this* export,
    which is what a person tracing a posting back to the file needs.
    """
    rows = _rows(export, "Journal.xlsx")
    entries: list[SourceEntry] = []
    lines: list[SourceLine] = []
    reference = 0
    when: date | None = None
    description = ""

    def flush() -> None:
        if when is not None:
            entries.append(
                SourceEntry(
                    reference=str(reference),
                    transaction_date=when,
                    description=description,
                    lines=tuple(lines),
                )
            )

    for row in rows[_HEADER_ROWS:]:
        if row[_DATE] is not None:
            flush()
            lines = []
            reference += 1
            when = _as_date(row[_DATE])
            description = str(row[_MEMO] or "")
        account = row[_ACCOUNT]
        if account is None or when is None:
            continue
        lines.append(
            SourceLine(
                account_code=str(account),
                amount=_amount(row[_DEBIT]) - _amount(row[_CREDIT]),
                commodity=_COMMODITY,
            )
        )
    flush()
    return tuple(entries)


def _ledger_totals(
    export: zipfile.ZipFile, entries: Sequence[SourceEntry]
) -> tuple[tuple[StatedBalance, ...], tuple[StatedBalance, ...], str]:
    """The general ledger's own stated totals, split into balances and rollups, and its basis.

    QuickBooks closes each account's section with a "Total for <account>" row. Those are the
    source's own balances — the figure `IMP-08` reconciles against — and they cover only
    accounts with activity, which is why an account may be in the journal and absent here.

    Some of those rows are **subtotals over a parent and its children**, printed as
    "Total for X with sub-accounts" where the parent also takes postings of its own, and as a
    bare "Total for X" where it does not. Both are recognised, and the bare case is decided
    against the export's own data rather than its wording: a bare total is a rollup only when
    the journal posts beneath that parent and never to the parent itself. A parent that takes
    direct postings therefore keeps its own balance and contributes its "with sub-accounts" row
    to the rollups, which is what those two rows mean.

    They are held apart because comparing a subtotal against a chart account would manufacture
    a divergence out of a category error.
    """
    if "General_ledger.xlsx" not in export.namelist():
        return (), (), "unknown"
    rows = _rows(export, "General_ledger.xlsx")
    posted_to = {line.account_code for entry in entries for line in entry.lines}
    balances: list[StatedBalance] = []
    rollups: list[StatedBalance] = []
    for row in rows[_HEADER_ROWS:]:
        label = row[0]
        if label is None or not str(label).startswith("Total for "):
            continue
        account = str(label)[len("Total for ") :].strip()
        parent = account.removesuffix(" with sub-accounts")
        stated = StatedBalance(
            account_code=parent, balance=_amount(row[_DEBIT]) - _amount(row[_CREDIT])
        )
        has_children = any(code.startswith(parent + ":") for code in posted_to)
        if account != parent or (has_children and parent not in posted_to):
            rollups.append(stated)
        else:
            balances.append(stated)
    return tuple(balances), tuple(rollups), read_basis(rows)


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
