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
    [None] * 9,
    # A parent that takes postings of its own and has a sub-account, so the general ledger
    # below prints both a balance for it and a rollup over it.
    [None, "04/09/2026", "Expense", None, None, "Stamps", "Office", 12.00, None],
    [None, None, None, None, None, "Stamps", "Checking", None, 12.00],
    [None, None, None, None, None, None, None, 12.00, 12.00],  # totals row: skipped
    [None] * 9,
    [None, "04/10/2026", "Expense", None, None, "Toner", "Office:Printing", 30.00, None],
    [None, None, None, None, None, "Toner", "Checking", None, 30.00],
    [None, None, None, None, None, None, None, 30.00, 30.00],  # totals row: skipped
    [None] * 9,
    # A parent that takes none, so its bare total is a rollup rather than a balance.
    [None, "04/11/2026", "Expense", None, None, "Phone", "Utilities:Phone", 60.00, None],
    [None, None, None, None, None, "Phone", "Checking", None, 60.00],
    [None, None, None, None, None, None, None, 60.00, 60.00],  # totals row: skipped
]

# Only the rows the converter reads: the account sections themselves are detail it ignores,
# and the "Total for" rows are the source's own arithmetic over its own data.
GENERAL_LEDGER: Rows = [
    ["Synthetic Co", None, None, None, None, None, None, None, None, None],
    ["General Ledger", None, None, None, None, None, None, None, None, None],
    ["All Dates", None, None, None, None, None, None, None, None, None],
    [None] * 10,
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
        "Balance",
    ],
    ["Total for Checking", None, None, None, None, None, None, 1200.00, 552.25, None],
    ["Total for Rent", None, None, None, None, None, None, 450.25, None, None],
    ["Total for Services", None, None, None, None, None, None, None, 1200.00, None],
    ["Total for Office", None, None, None, None, None, None, 12.00, None, None],
    [
        "Total for Office with sub-accounts",
        *[None] * 6,
        42.00,
        None,
        None,
    ],
    ["Total for Office:Printing", *[None] * 6, 30.00, None, None],
    ["Total for Utilities", None, None, None, None, None, None, 60.00, None, None],
    ["Total for Utilities:Phone", *[None] * 6, 60.00, None, None],
    ["Saturday, Sep 05, 2026 07:30:59 AM GMT-7 - Accrual Basis", *[None] * 9],
]

TRIAL_BALANCE: Rows = [
    ["Synthetic Co", None, None],
    ["Trial Balance", None, None],
    ["All Dates", None, None],
    [None, None, None],
    [None, "Debit", "Credit"],
    ["Checking", 647.75, None],
    ["Rent", 450.25, None],
    ["Office", 12.00, None],
    ["Office:Printing", 30.00, None],
    ["Utilities:Phone", 60.00, None],
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
    ["Checking", 647.75],
    ["TOTAL ASSETS", 647.75],
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
    ["Office", 12.00],
    ["Printing", 30.00],
    ["Total Office with sub-accounts", 42.00],
    ["Utilities", 60.00],
    ["Total Expenses", 552.25],
    ["Saturday, Sep 05, 2026 07:30:59 AM GMT-7 - Accrual Basis", None],
]


def synthetic_export(trial_balance_rows: Rows | None = None) -> bytes:
    """A synthetic QuickBooks export: our figures, their layout."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("Journal.xlsx", workbook(JOURNAL))
        archive.writestr("General_ledger.xlsx", workbook(GENERAL_LEDGER))
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

    assert converted.transactions == 5
    assert len(converted.journal) == 10


def test_each_transaction_is_grouped_under_one_reference(export: bytes) -> None:
    """A transaction begins on the row carrying a date; its later lines carry none."""
    converted = convert(export)
    refs = [line["ref"] for line in converted.journal]

    assert refs == ["1", "1", "2", "2", "3", "3", "4", "4", "5", "5"]
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

    assert types["Checking"] == "asset"
    assert types["Rent"] == "expense"
    assert types["Services"] == "income"


def test_a_sub_account_takes_its_parents_type(export: bytes) -> None:
    """QuickBooks prints a sub-account under its bare leaf name, so the colon-separated path
    the journal uses matches no statement row. Reading the type off the parent is the source
    stating the hierarchy, not us guessing: QuickBooks requires the two to share a type."""
    types = {account["code"]: account["type"] for account in convert(export).accounts}

    # "Printing" and "Phone" appear on the profit and loss; "Office:Printing" and
    # "Utilities:Phone" never do.
    assert types["Office:Printing"] == "expense"
    assert types["Utilities:Phone"] == "expense"


def test_a_sub_account_points_at_its_parent_only_when_the_parent_posts(
    export: bytes,
) -> None:
    """A parent that takes no postings of its own is not an account here, so its child is
    top-level rather than pointing at something absent."""
    parents = {account["code"]: account["parent"] for account in convert(export).accounts}

    assert parents["Office:Printing"] == "Office"
    assert parents["Utilities:Phone"] == ""  # nothing posts to "Utilities"
    assert parents["Rent"] == ""


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


def test_the_ledgers_stated_totals_are_read_as_the_sources_own_balances(
    export: bytes,
) -> None:
    """The general ledger prints a total per account. That is the source computing a balance
    from its own data, which is what makes it usable as an oracle — our arithmetic against
    theirs over the same journal, rather than ours against itself."""
    totals = {
        row["account_code"]: Decimal(row["balance"]) for row in convert(export).ledger_totals
    }

    assert totals == {
        "Checking": Decimal("647.75"),
        "Rent": Decimal("450.25"),
        "Services": Decimal("-1200.00"),
        "Office": Decimal("12.00"),
        "Office:Printing": Decimal("30.00"),
        "Utilities:Phone": Decimal("60.00"),
    }


def test_a_subtotal_over_sub_accounts_is_not_read_as_an_account_balance(
    export: bytes,
) -> None:
    """Nothing posts to a subtotal, so comparing one against a chart account would report a
    divergence that is really a difference in what the two figures are.

    Both spellings are covered: "Office" takes postings of its own and so has a balance *and*
    a "with sub-accounts" rollup, while "Utilities" takes none and its bare total is a rollup.
    """
    converted = convert(export)
    rollups = {row["account_code"]: Decimal(row["balance"]) for row in converted.ledger_rollups}
    balances = {row["account_code"] for row in converted.ledger_totals}

    assert rollups == {"Office": Decimal("42.00"), "Utilities": Decimal("60.00")}
    assert "Utilities" not in balances
    assert "Office" in balances  # its own postings, apart from the rollup over its children


def test_a_ledger_total_is_absent_when_the_export_has_no_general_ledger() -> None:
    """Reported as absent rather than substituted for. An export with no general ledger states
    no balance of its own, and summing the journal ourselves would compare our arithmetic
    against itself."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("Journal.xlsx", workbook(JOURNAL))
        archive.writestr("Trial_balance.xlsx", workbook(TRIAL_BALANCE))

    converted = convert(buffer.getvalue())

    assert converted.ledger_totals == []
    assert converted.ledger_rollups == []
    assert converted.ledger_basis == "unknown"


def test_a_converted_export_reconciles_against_the_ledgers_own_totals(
    database: Database,
) -> None:
    """The reconciliation the real export gets, at a scale a test can hold.

    A different oracle from the trial balance above, and deliberately so: an export whose
    reports are run on a different accounting method from its journal has a trial balance that
    cannot sum to it, and the general ledger's own per-account totals still can.
    """
    converted = convert(synthetic_export())

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
            database, entity_id=entity_id, principal=PERSON, as_of=date(2026, 12, 31)
        ),
        [
            SourceBalance(account_code=row["account_code"], balance=Decimal(row["balance"]))
            for row in converted.ledger_totals
        ],
    )

    assert report.agrees, [
        (c.account_code, str(c.ours), str(c.theirs)) for c in report.disagreements
    ]


def test_the_general_ledgers_basis_is_read_from_its_own_footer(export: bytes) -> None:
    """A cash-basis oracle differs from accrual books on exactly the obligation accounts
    (ADR-0037), so a reader who does not know the basis cannot tell that from a defect."""
    assert convert(export).ledger_basis == "accrual"
