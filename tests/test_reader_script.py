"""The QuickBooks reader that ships with the skill (ADR-0041).

**Driven as the skill drives it** — a subprocess, over the published JSON contract — because
that is the only relationship CFOKit has with it. `skills/` and the ledger are separate systems
sharing a contract (ADR-0014), so this imports nothing from the script and the script imports
nothing from `cfokit`. It is ADR-0036 layer 3 pointed at a client rather than an adapter.

Expected values come from the fixture's own inputs: the rows below are written here, so what the
reader should emit is known before it runs rather than read back from a first run (ADR-0036 §
5).

Needs no database, so it gates every commit.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
import zipfile
from decimal import Decimal
from pathlib import Path
from typing import Any

import openpyxl
import pytest

SCRIPT = (
    Path(__file__).resolve().parent.parent
    / "skills"
    / "bookkeeper"
    / "scripts"
    / "read_quickbooks.py"
)

Rows = list[list[Any]]

# Three title rows, a blank, a header row, then the body — the shape every QuickBooks report
# has, and the reason the reader skips exactly five rows.
JOURNAL: Rows = [
    ["Synthetic Co", None, None, None, None, None, None, None, None],
    ["Journal", None, None, None, None, None, None, None, None],
    ["All Dates", None, None, None, None, None, None, None, None],
    [None, None, None, None, None, None, None, None, None],
    [
        None,
        "Date",
        "Transaction Type",
        "Num",
        "Name",
        "Memo/Description",
        "Account",
        "Debit",
        "Credit",
    ],
    [
        None,
        "01/15/2026",
        "Invoice",
        "1001",
        "A Client",
        "Consulting",
        "Accounts Receivable",
        1200.00,
        None,
    ],
    [None, None, None, None, None, "Consulting", "Income:Consulting", None, 1200.00],
    [None, None, None, None, None, None, None, 1200.00, 1200.00],  # totals row: skipped
    [None, "02/02/2026", "Expense", None, None, "Coffee", "Meals:Client Meals", 12.50, None],
    [None, None, None, None, None, "Coffee", "Checking", None, 12.50],
    [None, None, None, None, None, None, None, 12.50, 12.50],
    # The grand total the journal prints for itself, above its footer. It carries no
    # accounting basis, because a journal is the record rather than a view of one (ADR-0050).
    ["TOTAL", None, None, None, None, None, None, 1212.50, 1212.50],
    [
        "Saturday, Sep 05, 2026 07:31:11 AM GMT-7",
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    ],
]

# Figures written as formulas with no cached value, which is how QuickBooks writes a statement.
PROFIT_AND_LOSS: Rows = [
    ["Synthetic Co", None],
    ["Profit and Loss", None],
    ["All Dates", None],
    [None, None],
    [None, "Total"],
    ["Income", None],
    ["   Consulting", "=1200.00"],
    ["Total Income", "=1200.00"],
    ["Expenses", None],
    ["   Meals", None],
    ["      Client Meals", "=12.50"],
    ["Saturday, Sep 05, 2026 07:30:59 AM GMT-7 - Accrual Basis", None],
]

BALANCE_SHEET: Rows = [
    ["Synthetic Co", None],
    ["Balance Sheet", None],
    ["All Dates", None],
    [None, None],
    [None, "Total"],
    ["ASSETS", None],
    ["   Checking", "=-12.50"],
    ["   Accounts Receivable", "=1200.00"],
    ["Saturday, Sep 05, 2026 07:30:59 AM GMT-7 - Accrual Basis", None],
]

GENERAL_LEDGER: Rows = [
    ["Synthetic Co", None, None, None, None, None, None, None, None],
    ["General Ledger", None, None, None, None, None, None, None, None],
    ["All Dates", None, None, None, None, None, None, None, None],
    [None, None, None, None, None, None, None, None, None],
    [
        None,
        "Date",
        "Transaction Type",
        "Num",
        "Name",
        "Memo/Description",
        "Account",
        "Debit",
        "Credit",
    ],
    ["Total for Accounts Receivable", None, None, None, None, None, None, 1200.00, None],
    ["Total for Income:Consulting", None, None, None, None, None, None, None, 1200.00],
    ["Total for Meals with sub-accounts", None, None, None, None, None, None, 12.50, None],
    ["Total for Checking", None, None, None, None, None, None, None, 12.50],
    [
        "Saturday, Sep 05, 2026 07:31:07 AM GMT-7 - Cash Basis",
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    ],
]


def workbook(rows: Rows) -> bytes:
    buffer = io.BytesIO()
    book = openpyxl.Workbook()
    sheet = book.active
    assert sheet is not None
    for row in rows:
        sheet.append(row)
    book.save(buffer)
    return buffer.getvalue()


def export(**replace: Rows) -> bytes:
    members = {
        "Journal.xlsx": JOURNAL,
        "General_ledger.xlsx": GENERAL_LEDGER,
        "Balance_sheet.xlsx": BALANCE_SHEET,
        "Profit_and_loss.xlsx": PROFIT_AND_LOSS,
    }
    members.update(replace)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, rows in members.items():
            archive.writestr(name, workbook(rows))
    return buffer.getvalue()


def run(archive: bytes, *flags: str, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    source = tmp_path / "export.zip"
    source.write_bytes(archive)
    return subprocess.run(  # noqa: S603 - our own script, at a path this file computes
        [sys.executable, str(SCRIPT), str(source), *flags],
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture
def books(tmp_path: Path) -> dict[str, Any]:
    done = run(export(), tmp_path=tmp_path)
    assert done.returncode == 0, done.stderr
    parsed: dict[str, Any] = json.loads(done.stdout)
    return parsed


# --- the shape ------------------------------------------------------------------------------


def test_it_emits_the_published_shape(books: dict[str, Any]) -> None:
    assert books["shape_version"] == "1"
    assert books["system"] == "QuickBooks Online"
    assert books["commodity"] == "USD"
    assert set(books) == {
        "shape_version",
        "system",
        "fingerprint",
        "basis",
        "balances_basis",
        "commodity",
        "accounts",
        "entries",
        "balances",
        "rollups",
        "statements",
        "journal_total",
    }


def test_the_journal_total_is_read_from_its_own_TOTAL_row(books: dict[str, Any]) -> None:
    """**The only figure in an export carrying no accounting basis** (ADR-0050).

    Read rather than summed: the value of this figure is that the source produced it, so a
    reader computing it would be checking its own arithmetic against itself. The fixture's two
    transactions are 1,200.00 and 12.50. Asserted as a value rather than a spelling: this
    fixture writes its cells through openpyxl, which stores 1212.50 as a float and loses the
    trailing zero, where a real export holds the text QuickBooks wrote.
    """
    total = books["journal_total"]

    assert Decimal(total["debits"]) == Decimal("1212.50")
    assert Decimal(total["credits"]) == Decimal("1212.50")


def test_an_export_whose_journal_prints_no_total_reports_none(tmp_path: Path) -> None:
    """Never fabricated. A source that states no total has the per-account half only."""
    without = [row for row in JOURNAL if str(row[0] or "").strip().upper() != "TOTAL"]
    done = run(export(**{"Journal.xlsx": without}), tmp_path=tmp_path)

    assert done.returncode == 0
    assert json.loads(done.stdout)["journal_total"] is None


def test_the_journal_states_no_basis_and_the_ledger_states_cash(books: dict[str, Any]) -> None:
    """Two different questions. The journal is the raw record and prints no method; the general
    ledger is a view and prints the one it was run on."""
    assert books["basis"] == "unknown"
    assert books["balances_basis"] == "cash"


def test_every_amount_crosses_as_a_string(books: dict[str, Any]) -> None:
    """A JSON number is a float in most parsers, and a float's binary expansion is not the
    figure
    the workbook shows (ADR-0005)."""
    for entry in books["entries"]:
        for line in entry["lines"]:
            assert isinstance(line["amount"], str)
    for balance in books["balances"] + books["rollups"]:
        assert isinstance(balance["balance"], str)


# --- the journal ----------------------------------------------------------------------------


def test_a_transaction_is_grouped_by_the_row_carrying_its_date(books: dict[str, Any]) -> None:
    assert [e["transaction_date"] for e in books["entries"]] == ["2026-01-15", "2026-02-02"]
    assert [len(e["lines"]) for e in books["entries"]] == [2, 2]


def test_the_totals_row_inside_each_transaction_is_skipped(books: dict[str, Any]) -> None:
    """It carries amounts and no account. Counted, every transaction would double."""
    assert sum(len(e["lines"]) for e in books["entries"]) == 4


def test_a_debit_is_positive_and_a_credit_negative(books: dict[str, Any]) -> None:
    lines = {
        line["account_code"]: Decimal(line["amount"]) for line in books["entries"][0]["lines"]
    }
    assert lines == {
        "Accounts Receivable": Decimal("1200.00"),
        "Income:Consulting": Decimal("-1200.00"),
    }


def test_every_transaction_balances(books: dict[str, Any]) -> None:
    for entry in books["entries"]:
        assert sum(Decimal(line["amount"]) for line in entry["lines"]) == 0


def test_a_blank_row_does_not_shift_the_body(books: dict[str, Any]) -> None:
    """**A regression.** A worksheet omits a row holding nothing, so row 4 — the blank between
    the titles and the header — may not exist in the XML at all. Read without filling the gap,
    every report shifts up by one and the first transaction disappears into the header."""
    assert books["entries"][0]["transaction_date"] == "2026-01-15"
    assert len(books["entries"]) == 2


# --- account types and paths ------------------------------------------------------------------


def test_types_come_from_the_sources_own_statement_sections(books: dict[str, Any]) -> None:
    typed = {a["code"]: a["account_type"] for a in books["accounts"]}
    assert typed["Accounts Receivable"] == "asset"
    assert typed["Checking"] == "asset"
    assert typed["Income:Consulting"] == "income"


def test_a_sub_account_takes_its_parents_type(books: dict[str, Any]) -> None:
    """A statement prints the leaf under its parent's header, so the journal's full path matches
    no row. Walking up is the source stating the hierarchy, not a guess about the account."""
    typed = {a["code"]: a["account_type"] for a in books["accounts"]}
    assert typed["Meals:Client Meals"] == "expense"


def test_a_parent_that_takes_no_postings_is_not_an_account(books: dict[str, Any]) -> None:
    codes = {a["code"] for a in books["accounts"]}
    assert "Meals" not in codes
    assert books["accounts"][0]["parent"] == ""


# --- the statements ---------------------------------------------------------------------------


def test_a_formula_stating_a_number_is_that_number(books: dict[str, Any]) -> None:
    """QuickBooks writes every statement figure as `=1200.00` with no cached result. A reader
    asking for cached values gets 0.0 for all of them — silently, and in the direction that
    looks
    like a balanced book."""
    profit = next(s for s in books["statements"] if s["report"] == "profit_and_loss")
    figures = {line["account_code"]: Decimal(line["balance"]) for line in profit["lines"]}
    assert figures["Income:Consulting"] == Decimal("1200.00")
    assert figures["Meals:Client Meals"] == Decimal("12.50")


def test_a_statement_path_comes_from_the_indentation(books: dict[str, Any]) -> None:
    """`Client Meals` indented under `Meals` is the account the journal calls
    `Meals:Client Meals`. The leaf alone would be ambiguous."""
    profit = next(s for s in books["statements"] if s["report"] == "profit_and_loss")
    assert "Meals:Client Meals" in {line["account_code"] for line in profit["lines"]}


def test_a_statement_keeps_the_sign_the_source_prints(books: dict[str, Any]) -> None:
    """Income prints positive on a statement and signs negative as a posting. The comparison is
    where the two conventions meet, so the reader does not translate."""
    profit = next(s for s in books["statements"] if s["report"] == "profit_and_loss")
    consulting = next(
        line for line in profit["lines"] if line["account_code"] == "Income:Consulting"
    )
    assert Decimal(consulting["balance"]) > 0


def test_a_subtotal_is_a_rollup_not_a_balance(books: dict[str, Any]) -> None:
    """ "Total for X with sub-accounts" covers a parent and its children. Compared against a
    chart
    account it would manufacture a divergence out of a category error."""
    assert {b["account_code"] for b in books["rollups"]} == {"Meals"}
    assert "Meals" not in {b["account_code"] for b in books["balances"]}


def test_the_ledgers_totals_are_read_as_the_sources_own_balances(books: dict[str, Any]) -> None:
    """This is what `IMP-08` reconciles against — the source's arithmetic over its own data."""
    stated = {b["account_code"]: Decimal(b["balance"]) for b in books["balances"]}
    assert stated == {
        "Accounts Receivable": Decimal("1200.00"),
        "Income:Consulting": Decimal("-1200.00"),
        "Checking": Decimal("-12.50"),
    }


# --- refusals ---------------------------------------------------------------------------------


def test_a_computed_cell_is_refused_rather_than_read_as_zero(tmp_path: Path) -> None:
    """A formula referencing other cells is a subtotal. Computing it would mean implementing a
    spreadsheet; returning zero would be worse than either, because a zero in a financial figure
    reads as a fact."""
    broken = [*PROFIT_AND_LOSS[:6], ["   Consulting", "=SUM(B7:B9)"], *PROFIT_AND_LOSS[7:]]
    done = run(export(**{"Profit_and_loss.xlsx": broken}), tmp_path=tmp_path)

    assert done.returncode == 1
    assert "unreadable_figure" in done.stderr


def test_an_export_with_no_journal_is_refused(tmp_path: Path) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("Balance_sheet.xlsx", workbook(BALANCE_SHEET))
    done = run(buffer.getvalue(), tmp_path=tmp_path)

    assert done.returncode == 1
    assert "import_refused" in done.stderr


def test_a_document_type_declaration_is_refused(tmp_path: Path) -> None:
    """Entity expansion — billion laughs, quadratic blowup — needs a DOCTYPE carrying ENTITY
    declarations, and a spreadsheet part never has one. Refusing it outright is a complete
    defence against that class and is why this script depends on nothing."""
    hostile = io.BytesIO()
    with zipfile.ZipFile(hostile, "w") as inner:
        inner.writestr(
            "xl/workbook.xml", '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><workbook/>'
        )
        inner.writestr("xl/worksheets/sheet1.xml", "<sheetData/>")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("Journal.xlsx", hostile.getvalue())
    done = run(buffer.getvalue(), tmp_path=tmp_path)

    assert done.returncode == 1
    assert "document type" in done.stderr


def test_an_archive_that_expands_past_the_ceiling_is_refused(tmp_path: Path) -> None:
    """A compressed size bounds an expanded size only if the ratio is sane. A real export runs
    at
    1.08x, because its members are `.xlsx` files and those are themselves zips."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("Journal.xlsx", b"\0" * (300 * 1024 * 1024 + 1))
    done = run(buffer.getvalue(), tmp_path=tmp_path)

    assert done.returncode == 1
    assert "import_too_large" in done.stderr


# --- what a person is shown -------------------------------------------------------------------


def test_the_summary_carries_no_amounts(tmp_path: Path) -> None:
    """The figures are the operator's revenue and their clients' names. The model relaying this
    does not need them and should not carry them (`IMP-05`, ADR-0040)."""
    done = run(export(), "--summary", tmp_path=tmp_path)

    assert done.returncode == 0
    assert "1200" not in done.stdout
    assert "12.50" not in done.stdout
    assert "2 transactions, 4 posting lines" in done.stdout


def test_the_summary_names_a_basis_mismatch(tmp_path: Path) -> None:
    """An accrual journal checked against cash-basis balances differs by exactly what is
    unsettled. ADR-0037 predicts it, so a person should read it as expected rather than
    broken."""
    done = run(export(), "--summary", tmp_path=tmp_path)

    assert "different basis" in done.stdout
