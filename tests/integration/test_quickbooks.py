"""Converting a QuickBooks export into the interchange format (`IMP-08` case 3).

The export used here is **synthetic**: our own invented figures in the layout QuickBooks emits.
A file format is not copyrightable and nothing of Intuit's is reproduced; no real export enters
this repository, and a real one is read from a path outside it.

The converter is a translation layer, and ADR-0010 rejected one — a Beancount translator would
be "untested code sitting between the system and its own correctness evidence… a defect in it
produces false agreement as readily as false divergence". That objection does not reach here:
the converter transforms only the *inputs*, and the expected answer arrives through a different
report in the same export. A converter bug corrupts the journal and the reconciliation then
fails loudly. These tests hold that property by testing the converter directly as well.
"""

from __future__ import annotations

import io
import uuid
import zipfile
from datetime import date
from decimal import Decimal

import openpyxl
import pytest
from quickbooks import Converted, convert

from cfokit.ledger.engine import Entry, Posting
from cfokit.ledger.presentation import SourceBalance, present_reconciliation
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.administration import create_account, create_entity
from cfokit.ledger.service.principal import ActorClass, Principal
from cfokit.ledger.service.reports import trial_balance
from cfokit.ledger.service.write import WriteContext, record_transaction

pytestmark = pytest.mark.integration

PERSON = Principal(id="user:geoff", actor_class=ActorClass.PERSON)

# A report as a grid of cells, which is what openpyxl writes and reads.
Rows = list[list[object]]

# One report's shape: three title rows, a blank, a header row, then the body — which is what
# `_HEADER_ROWS` in the converter skips.
JOURNAL: Rows = [
    ["Synthetic Co", None, None, None, None, None, None, None, None],
    ["Journal", None, None, None, None, None, None, None, None],
    ["All Dates", None, None, None, None, None, None, None, None],
    [None] * 9,
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
    [None, "03/14/2026", "Deposit", None, None, "Consulting fee", "Checking", 1200.00, None],
    [None, None, None, None, None, "Consulting fee", "Services", None, 1200.00],
    [None, None, None, None, None, None, None, 1200.00, 1200.00],  # totals row: skipped
    [None] * 9,
    [None, "04/02/2026", "Expense", None, "Landlord", "April rent", "Rent", 450.25, None],
    [None, None, None, None, None, "April rent", "Checking", None, 450.25],
    [None, None, None, None, None, None, None, 450.25, 450.25],  # totals row: skipped
]

TRIAL_BALANCE: Rows = [
    ["Synthetic Co", None, None],
    ["Trial Balance", None, None],
    ["All Dates", None, None],
    [None, None, None],
    [None, "Debit", "Credit"],
    ["Checking", 749.75, None],
    ["Rent", 450.25, None],
    ["Services", None, 1200.00],
    ["TOTAL", 1200.00, 1200.00],
    ["Saturday, Sep 05, 2026 07:30:59 AM GMT-7 - Accrual Basis", None, None],
]

BALANCE_SHEET: Rows = [
    ["Synthetic Co", None],
    ["Balance Sheet", None],
    ["All Dates", None],
    [None, None],
    [None, "Total"],
    ["ASSETS", None],
    ["Checking", 749.75],
    ["TOTAL ASSETS", 749.75],
    ["Saturday, Sep 05, 2026 07:30:59 AM GMT-7 - Accrual Basis", None],
]

PROFIT_AND_LOSS: Rows = [
    ["Synthetic Co", None],
    ["Profit and Loss", None],
    ["All Dates", None],
    [None, None],
    [None, "Total"],
    ["Income", None],
    ["Services", 1200.00],
    ["Total Income", 1200.00],
    ["Expenses", None],
    ["Rent", 450.25],
    ["Total Expenses", 450.25],
    ["Saturday, Sep 05, 2026 07:30:59 AM GMT-7 - Accrual Basis", None],
]


def synthetic_export(trial_balance_rows: Rows | None = None) -> bytes:
    """A synthetic QuickBooks export: our figures, their layout."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("Journal.xlsx", workbook(JOURNAL))
        archive.writestr("Trial_balance.xlsx", workbook(trial_balance_rows or TRIAL_BALANCE))
        archive.writestr("Balance_sheet.xlsx", workbook(BALANCE_SHEET))
        archive.writestr("Profit_and_loss.xlsx", workbook(PROFIT_AND_LOSS))
    return buffer.getvalue()


def post_converted(database: Database, entity_id: str, converted: Converted) -> None:
    """Create the chart and post the journal, through the service layer.

    The same path a customer's writes take. A loader that reached past it would verify a route
    nobody uses.
    """
    accounts = {
        account["code"]: create_account(
            database,
            entity_id=entity_id,
            principal=PERSON,
            request_id="quickbooks",
            code=account["code"],
            name=account["name"],
            account_type=account["type"],
        )
        for account in converted.accounts
    }

    grouped: dict[str, list[dict[str, str]]] = {}
    for line in converted.journal:
        grouped.setdefault(line["ref"], []).append(line)

    for ref, lines in grouped.items():
        record_transaction(
            database,
            WriteContext(
                entity_id=entity_id,
                principal=PERSON,
                request_id=f"quickbooks-{ref}",
                idempotency_key=uuid.uuid4().hex,
            ),
            entry=Entry(
                transaction_date=date.fromisoformat(lines[0]["date"]),
                postings=tuple(
                    Posting(
                        account_id=accounts[line["account_code"]],
                        amount=Decimal(line["amount"]),
                        commodity=line["commodity"],
                    )
                    for line in lines
                ),
                description=lines[0]["description"],
            ),
            post=True,
        )


def workbook(rows: Rows) -> bytes:
    book = openpyxl.Workbook()
    sheet = book.active
    assert sheet is not None
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


@pytest.fixture
def export() -> bytes:
    return synthetic_export()


# --- The conversion -----------------------------------------------------------------------


def test_the_totals_row_inside_each_transaction_is_skipped(export: bytes) -> None:
    """**The error that would double every figure.** QuickBooks closes each transaction with a
    row carrying amounts and no account; counting it books everything twice."""
    converted = convert(export)

    assert converted.transactions == 2
    assert len(converted.journal) == 4


def test_each_transaction_is_grouped_under_one_reference(export: bytes) -> None:
    """A transaction begins on the row carrying a date; its later lines carry none."""
    converted = convert(export)
    refs = [line["ref"] for line in converted.journal]

    assert refs == ["1", "1", "2", "2"]
    assert {line["date"] for line in converted.journal if line["ref"] == "1"} == {"2026-03-14"}


def test_the_converted_journal_sums_to_zero(export: bytes) -> None:
    """Every transaction balances (`LED-03`), so the whole journal does — and a converter that
    dropped or duplicated a line would show up here before anything reached the books."""
    assert sum(Decimal(line["amount"]) for line in convert(export).journal) == 0


def test_a_debit_is_positive_and_a_credit_negative(export: bytes) -> None:
    """The sign convention the interchange format uses, which is ours, not QuickBooks'."""
    converted = convert(export)
    amounts = {
        (line["account_code"], line["ref"]): Decimal(line["amount"])
        for line in converted.journal
    }

    assert amounts[("Checking", "1")] == Decimal("1200.00")
    assert amounts[("Services", "1")] == Decimal("-1200.00")


def test_account_types_come_from_the_sources_own_statements(export: bytes) -> None:
    """An account under `ASSETS` is an asset; one under `Income` is income. Not guessed from
    the name — that would be our judgement entering data whose value is that it is not ours."""
    types = {account["code"]: account["type"] for account in convert(export).accounts}

    assert types == {"Checking": "asset", "Rent": "expense", "Services": "income"}


def test_an_account_on_no_statement_is_marked_unknown() -> None:
    """Recorded as a question rather than guessed: a wrong type is a silent
    misclassification, and a missing one is a question somebody can answer."""
    # No Balance_sheet.xlsx and no Profit_and_loss.xlsx, so nothing states a type.
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("Journal.xlsx", workbook(JOURNAL))
        archive.writestr("Trial_balance.xlsx", workbook(TRIAL_BALANCE))

    types = {
        account["code"]: account["type"] for account in convert(buffer.getvalue()).accounts
    }

    assert set(types.values()) == {"unknown"}


def test_the_accounting_basis_is_read_from_the_report_footer(export: bytes) -> None:
    """**Load-bearing.** A QuickBooks export's reports each carry their accounting method in a
    footer, and a cash-basis report does not sum to the accrual journal beside it. Reading the
    basis is what stops one being used as the other's oracle.
    """
    assert convert(export).trial_balance_basis == "accrual"


def test_a_cash_basis_report_is_reported_as_such() -> None:
    cash: Rows = [*TRIAL_BALANCE[:-1], ["Sat, Sep 05, 2026 - Cash Basis", None, None]]

    assert convert(synthetic_export(cash)).trial_balance_basis == "cash"


def test_amounts_keep_the_scale_the_workbook_shows(export: bytes) -> None:
    """`LED-04` allows no representation error. A cell arrives as a float, and
    `Decimal(str(value))` keeps the figure shown rather than a binary expansion of it."""
    rent = next(line for line in convert(export).journal if line["account_code"] == "Rent")

    assert Decimal(rent["amount"]) == Decimal("450.25")


# --- End to end: convert, load, reconcile -------------------------------------------------


def test_a_converted_export_reconciles_against_its_own_trial_balance(
    database: Database,
) -> None:
    """The whole point of case 3, at small scale.

    Convert the export, post its journal through the service layer, and reconcile our trial
    balance against the export's own — which came out of a different report in the same file.
    A converter bug corrupts the journal and this fails; it cannot agree falsely.
    """
    converted = convert(synthetic_export())
    assert converted.trial_balance_basis == "accrual"

    entity_id = create_entity(
        database,
        principal=PERSON,
        request_id="quickbooks",
        slug=f"qb-{uuid.uuid4().hex[:8]}",
        name="Synthetic Co",
        accounting_basis="accrual",
        fiscal_year_end_month=12,
        fiscal_year_end_day=31,
        functional_currency="USD",
        time_zone="UTC",
    ).entity_id
    post_converted(database, entity_id, converted)

    report = present_reconciliation(
        trial_balance(
            database,
            entity_id=entity_id,
            principal=PERSON,
            as_of=date(2026, 12, 31),
        ),
        [
            SourceBalance(account_code=row["account_code"], balance=Decimal(row["balance"]))
            for row in converted.trial_balance
        ],
    )

    assert report.agrees, [
        (c.account_code, str(c.ours), str(c.theirs)) for c in report.disagreements
    ]
