"""Import from a QuickBooks export (`IMP-01` to `IMP-08`).

The export used here is **synthetic**: our own invented figures in the layout QuickBooks emits.
A file format is not copyrightable and nothing of Intuit's is reproduced; no real export enters
this repository, and a real one is read from a path outside it.

The reader is a translation layer, and ADR-0010 rejected one — a Beancount translator would be
"untested code sitting between the system and its own correctness evidence… a defect in it
produces false agreement as readily as false divergence". That objection does not reach here:
the reader transforms only the *inputs*, and the expected answer arrives through a different
report in the same export. A reader bug corrupts the journal and the reconciliation then fails
loudly. These tests hold that property by testing the reader directly as well.
"""

from __future__ import annotations

import io
import uuid
import zipfile
from datetime import date
from decimal import Decimal

import openpyxl
import pytest

from cfokit.imports import ImportRefused, apply, plan
from cfokit.imports.quickbooks import SYSTEM, read
from cfokit.ledger.engine import Entry, Posting
from cfokit.ledger.errors import NotAPerson
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.administration import create_entity, grant_role
from cfokit.ledger.service.principal import ActorClass, Principal
from cfokit.ledger.service.write import WriteContext, record_transaction

pytestmark = pytest.mark.integration

PERSON = Principal(id="user:geoff", actor_class=ActorClass.PERSON)

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
    ["Saturday, Sep 05, 2026 07:30:59 AM GMT-7 - Accrual Basis", *[None] * 8],
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


def entity(database: Database, basis: str = "accrual", currency: str = "USD") -> str:
    return create_entity(
        database,
        principal=PERSON,
        request_id="import",
        slug=f"import-{uuid.uuid4().hex[:8]}",
        name="Synthetic Co",
        accounting_basis=basis,
        fiscal_year_end_month=12,
        fiscal_year_end_day=31,
        functional_currency=currency,
        time_zone="UTC",
    ).entity_id


# --- the reader: what the source says, translated and nothing more -------------------------


def test_the_totals_row_inside_each_transaction_is_skipped(export: bytes) -> None:
    """Each journal group ends with a row carrying amounts and no account. Counted, every
    transaction would appear twice and the books would double."""
    books = read(export)

    assert len(books.entries) == 5
    assert sum(len(entry.lines) for entry in books.entries) == 10


def test_a_transaction_is_grouped_by_the_row_carrying_its_date(export: bytes) -> None:
    """A transaction begins on the row with a date; its remaining lines carry none."""
    books = read(export)

    assert [len(entry.lines) for entry in books.entries] == [2, 2, 2, 2, 2]
    assert books.entries[0].transaction_date == date(2026, 3, 14)


def test_every_transaction_balances(export: bytes) -> None:
    """The reader translates; it does not correct. A source whose journal does not balance
    produces entries that do not balance, and the plan refuses them by name."""
    books = read(export)

    for entry in books.entries:
        assert sum(line.amount for line in entry.lines) == 0


def test_a_debit_is_positive_and_a_credit_negative(export: bytes) -> None:
    """QuickBooks prints two columns; a posting has one signed amount. That translation is the
    reader's job and nothing below it should repeat it."""
    lines = {
        line.account_code: line.amount for entry in read(export).entries for line in entry.lines
    }

    assert lines["Rent"] == Decimal("450.25")
    assert lines["Services"] == Decimal("-1200.00")


def test_amounts_keep_the_scale_the_workbook_shows(export: bytes) -> None:
    """`Decimal(str(cell))`, never `Decimal(cell)`. A float's binary expansion is not the
    figure the workbook shows and `LED-04` allows no representation error (ADR-0005)."""
    rent = next(
        line
        for entry in read(export).entries
        for line in entry.lines
        if line.account_code == "Rent"
    )

    assert str(rent.amount) == "450.25"


def test_account_types_come_from_the_sources_own_statements(export: bytes) -> None:
    """An account under `ASSETS` is an asset; one under `Income` is income. Not guessed from
    the name — that would be our judgement entering data whose value is that it is not ours."""
    types = {account.code: account.account_type for account in read(export).accounts}

    assert types["Checking"] == "asset"
    assert types["Rent"] == "expense"
    assert types["Services"] == "income"


def test_a_sub_account_takes_its_parents_type(export: bytes) -> None:
    """QuickBooks prints a sub-account under its bare leaf name, so the colon-separated path
    the journal uses matches no statement row. Reading the type off the parent is the source
    stating the hierarchy, not us guessing: QuickBooks requires the two to share a type."""
    types = {account.code: account.account_type for account in read(export).accounts}

    assert types["Office:Printing"] == "expense"
    assert types["Utilities:Phone"] == "expense"


def test_a_sub_account_type_is_found_on_the_row_the_source_actually_prints(
    export: bytes,
) -> None:
    """A statement prints a sub-account under its bare leaf name, indented beneath a parent
    header that carries no amount when the parent takes no postings of its own.

    So neither the full path nor any prefix of it matches a row, while the leaf matches
    exactly. On a real export this was the difference between 12 accounts typed `unknown` and
    2 — and the two that remain are genuinely absent from every statement.
    """
    # How QuickBooks prints a parent that takes no postings of its own: a header with no
    # figure, and the amount on the leaf beneath it.
    indented: Rows = [
        ["Synthetic Co", None],
        ["Profit and Loss", None],
        ["All Dates", None],
        [None, None],
        [None, "Total"],
        ["Expenses", None],
        ["Utilities", None],
        ["Phone", 60.00],
        ["Total Utilities", 60.00],
        ["Total Expenses", 60.00],
        ["Saturday, Sep 05, 2026 07:30:59 AM GMT-7 - Accrual Basis", None],
    ]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("Journal.xlsx", workbook(JOURNAL))
        archive.writestr("Profit_and_loss.xlsx", workbook(indented))

    types = {account.code: account.account_type for account in read(buffer.getvalue()).accounts}

    # Neither "Utilities:Phone" nor "Utilities" appears as a row carrying a figure. "Phone"
    # does, and that is where the source states the type.
    assert types["Utilities:Phone"] == "expense"
    assert types["Checking"] == "unknown"  # on no statement here, and still reported as such


def test_a_sub_account_points_at_its_parent_only_when_the_parent_posts(export: bytes) -> None:
    """A parent that takes no postings of its own is not an account here, so its child is
    top-level rather than pointing at something absent."""
    parents = {account.code: account.parent for account in read(export).accounts}

    assert parents["Office:Printing"] == "Office"
    assert parents["Utilities:Phone"] == ""  # nothing posts to "Utilities"
    assert parents["Rent"] == ""


def test_an_account_on_no_statement_is_marked_unknown() -> None:
    """Recorded as a question rather than guessed: a wrong type is a silent misclassification,
    and a missing one is a question somebody can answer."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("Journal.xlsx", workbook(JOURNAL))

    types = {account.account_type for account in read(buffer.getvalue()).accounts}

    assert types == {"unknown"}


def test_the_ledgers_stated_totals_are_read_as_the_sources_own_balances(export: bytes) -> None:
    """The general ledger prints a total per account. That is the source computing a balance
    from its own data, which is what makes it usable as an oracle — our arithmetic against
    theirs over the same journal, rather than ours against itself."""
    balances = {balance.account_code: balance.balance for balance in read(export).balances}

    assert balances == {
        "Checking": Decimal("647.75"),
        "Rent": Decimal("450.25"),
        "Services": Decimal("-1200.00"),
        "Office": Decimal("12.00"),
        "Office:Printing": Decimal("30.00"),
        "Utilities:Phone": Decimal("60.00"),
    }


def test_a_subtotal_over_sub_accounts_is_not_read_as_an_account_balance(export: bytes) -> None:
    """Nothing posts to a subtotal, so comparing one against a chart account would report a
    divergence that is really a difference in what the two figures are.

    Both spellings are covered: "Office" takes postings of its own and so has a balance *and*
    a "with sub-accounts" rollup, while "Utilities" takes none and its bare total is a rollup.
    """
    books = read(export)
    rollups = {balance.account_code: balance.balance for balance in books.rollups}
    balances = {balance.account_code for balance in books.balances}

    assert rollups == {"Office": Decimal("42.00"), "Utilities": Decimal("60.00")}
    assert "Utilities" not in balances
    assert "Office" in balances  # its own postings, apart from the rollup over its children


def test_the_journals_basis_and_the_oracles_basis_are_read_separately(export: bytes) -> None:
    """Two questions, two files. The entries are the source's raw record; the stated balances
    are a view it computed, and a system can print cash-basis reports over an accrual journal.

    Conflating them would make `IMP-06` refuse a file whose data is fine because a report
    beside it was run differently.
    """
    books = read(export)

    assert books.basis == "accrual"
    assert books.balances_basis == "accrual"


def test_a_cash_basis_oracle_over_an_accrual_journal_is_not_a_conflict(
    database: Database,
) -> None:
    """The shape a real QuickBooks export actually has: reports run on a cash basis beside a
    journal that is the accrual record.

    `IMP-06` is about the entries, so this imports. The divergence it will produce on the
    obligation accounts is predicted rather than tolerated (ADR-0037), and the plan says so.
    """
    cash_ledger: Rows = [
        *GENERAL_LEDGER[:-1],
        ["Saturday, Sep 05, 2026 07:30:59 AM GMT-7 - Cash Basis", *[None] * 9],
    ]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("Journal.xlsx", workbook(JOURNAL))
        archive.writestr("General_ledger.xlsx", workbook(cash_ledger))
    books = read(buffer.getvalue())
    assert (books.basis, books.balances_basis) == ("accrual", "cash")

    proposed = plan(database, entity_id=entity(database), principal=PERSON, books=books)

    assert proposed.can_apply
    assert proposed.oracle_differs_in_basis


def test_a_journal_stating_no_basis_does_not_block(database: Database) -> None:
    """A source that prints no method on its raw record has not disagreed with anything.
    Refusing on `unknown` would refuse every export that does not label its journal."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("Journal.xlsx", workbook(JOURNAL[:-1]))  # footer removed
    books = read(buffer.getvalue())
    assert books.basis == "unknown"

    proposed = plan(database, entity_id=entity(database), principal=PERSON, books=books)

    assert proposed.can_apply


def test_an_export_with_no_general_ledger_states_no_balances() -> None:
    """Reported as absent rather than substituted for. Summing the journal ourselves and
    calling it an oracle would compare our arithmetic against itself."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("Journal.xlsx", workbook(JOURNAL))

    books = read(buffer.getvalue())

    assert books.balances == ()
    assert books.rollups == ()
    assert books.balances_basis == "unknown"


def test_the_reader_names_the_system_it_read(export: bytes) -> None:
    """`IMP-04`: every imported record "names the system it came from"."""
    assert read(export).system == SYSTEM


# --- IMP-05: validated before anything is posted -------------------------------------------


def test_a_plan_says_what_would_be_created_and_posts_nothing(database: Database) -> None:
    """`IMP-05`: "the operator sees what will be created, and what will not, and can abandon
    it". A plan that had to write to say so would not be a plan."""
    entity_id = entity(database)
    books = read(synthetic_export())

    proposed = plan(database, entity_id=entity_id, principal=PERSON, books=books)

    assert proposed.transactions == 5
    assert proposed.postings == 10
    assert len(proposed.accounts_to_create) == 6
    assert proposed.accounts_already_present == ()
    assert proposed.earliest == date(2026, 3, 14)
    assert proposed.latest == date(2026, 4, 11)
    assert proposed.can_apply

    with database.entity_write(entity_id) as write:
        assert write.chart() == []


def test_a_plan_names_the_rows_it_would_skip(database: Database) -> None:
    """An export with three malformed rows out of eleven thousand imports the rest and says
    so. A refusal is part of the plan, not an error that stops it."""
    unbalanced: Rows = [
        *JOURNAL[:-1],  # the footer goes last
        [None] * 9,
        [None, "05/01/2026", "Expense", None, None, "Wrong", "Rent", 10.00, None],
        [None, None, None, None, None, "Wrong", "Checking", None, 9.00],
        [None, None, None, None, None, None, None, 10.00, 9.00],  # totals row: skipped
        [None] * 9,
        # One line and nothing to balance against it. A zero-amount single line sums to zero,
        # so a balance check alone would pass it while it records no movement of value.
        [None, "05/02/2026", "Journal Entry", None, None, "Stub", "Rent", 0.00, None],
        JOURNAL[-1],
    ]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("Journal.xlsx", workbook(unbalanced))
    entity_id = entity(database)

    proposed = plan(
        database, entity_id=entity_id, principal=PERSON, books=read(buffer.getvalue())
    )

    assert sorted(refusal.code for refusal in proposed.refusals) == [
        "transaction_incomplete",
        "unbalanced",
    ]
    assert proposed.transactions == 5  # the good ones, still importable
    assert proposed.can_apply


def test_a_plan_names_the_accounts_the_source_states_no_type_for(database: Database) -> None:
    """They are created as assets, which is inert for a trial balance. Surfaced in the plan so
    the operator sees it rather than discovering it in a statement."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("Journal.xlsx", workbook(JOURNAL))
    entity_id = entity(database)

    proposed = plan(
        database, entity_id=entity_id, principal=PERSON, books=read(buffer.getvalue())
    )

    assert len(proposed.untyped_accounts) == len(proposed.accounts_to_create)


def test_an_import_is_blocked_when_the_basis_conflicts(database: Database) -> None:
    """`IMP-06`. Basis is a presentation property and no posting path branches on it
    (ADR-0037), so cash-basis figures landed in accrual books are figures the books cannot
    reproduce. Blocked outright rather than skipped row by row: it is the wrong file."""
    entity_id = entity(database, basis="cash")
    books = read(synthetic_export())
    assert books.basis == "accrual"

    proposed = plan(database, entity_id=entity_id, principal=PERSON, books=books)

    assert not proposed.can_apply
    assert proposed.blocked is not None
    assert "accrual" in proposed.blocked

    with pytest.raises(ImportRefused):
        apply(
            database,
            entity_id=entity_id,
            principal=PERSON,
            request_id="req",
            books=books,
        )


def test_an_import_is_blocked_when_the_currency_is_foreign(database: Database) -> None:
    """`IMP-07`, on the same terms as any other foreign amount."""
    entity_id = entity(database, currency="GBP")

    proposed = plan(
        database, entity_id=entity_id, principal=PERSON, books=read(synthetic_export())
    )

    assert not proposed.can_apply
    assert proposed.blocked is not None
    assert "USD" in proposed.blocked


# --- IMP-01, IMP-02, IMP-04, IMP-08: applying one ------------------------------------------


def test_an_import_lands_the_chart_and_the_journal(database: Database) -> None:
    """`IMP-01` and `IMP-02`: the chart the company already runs, and its history to the
    extent the export carries it."""
    entity_id = entity(database)

    result = apply(
        database,
        entity_id=entity_id,
        principal=PERSON,
        request_id="req",
        books=read(synthetic_export()),
    )

    assert result.accounts_created == 6
    assert result.transactions_posted == 5
    assert result.refusals == ()


def test_an_import_reconciles_against_the_sources_own_figures(database: Database) -> None:
    """**`IMP-08`, and the reason any of this is trustworthy.** Agreement is demonstrated
    against the balances the source states for itself, not against a sum we computed from the
    same journal we just loaded — that would be our arithmetic against itself.

    No tolerance. `NFR-01`: "a tolerance is a defect, not a target."
    """
    entity_id = entity(database)

    result = apply(
        database,
        entity_id=entity_id,
        principal=PERSON,
        request_id="req",
        books=read(synthetic_export()),
    )

    assert result.divergences == ()
    assert result.compared == 6
    assert result.reconciled


def test_a_reader_bug_shows_up_as_a_divergence(database: Database) -> None:
    """The property that answers ADR-0010's objection to a translator.

    The expected answer comes from a *different report in the same export*, so corrupting the
    journal cannot produce false agreement — it produces exactly the divergence it caused.
    """
    corrupted: Rows = [
        row if row[7] != 450.25 else [*row[:7], 460.25, *row[8:]] for row in JOURNAL
    ]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("Journal.xlsx", workbook(corrupted))
        archive.writestr("General_ledger.xlsx", workbook(GENERAL_LEDGER))
        archive.writestr("Balance_sheet.xlsx", workbook(BALANCE_SHEET))
        archive.writestr("Profit_and_loss.xlsx", workbook(PROFIT_AND_LOSS))
    entity_id = entity(database)

    result = apply(
        database,
        entity_id=entity_id,
        principal=PERSON,
        request_id="req",
        books=read(buffer.getvalue()),
    )

    assert not result.reconciled
    assert {code for code, _, _ in result.divergences} == {"Rent", "Checking"}


def test_every_imported_entry_names_where_it_came_from(database: Database) -> None:
    """`IMP-04`: "identifiable as imported and names the system it came from", and the lineage
    `SOC1-14` wants. Written at insert, because the entry is append-only and lineage that can
    be attached later is lineage that can be changed."""
    entity_id = entity(database)

    result = apply(
        database,
        entity_id=entity_id,
        principal=PERSON,
        request_id="req",
        books=read(synthetic_export()),
    )

    with database.entity_write(entity_id) as write:
        columns, rows = write.archived("ledger_transaction")
    lineage = [dict(zip(columns, row, strict=True))["derived_from"] for row in rows]

    assert len(lineage) == 5
    assert all(entry is not None for entry in lineage)
    assert {entry["system"] for entry in lineage} == {SYSTEM}
    assert {entry["import_id"] for entry in lineage} == {result.import_id}
    assert {entry["reference"] for entry in lineage} == {"1", "2", "3", "4", "5"}


def test_an_ordinary_write_carries_no_lineage(database: Database) -> None:
    """`derived_from` says what an entry came from *outside* the books. An entry a person typed
    came from nowhere outside them, and defaulting it to an empty object would make "imported"
    and "not imported" indistinguishable — which is exactly what `IMP-04` asks for."""
    entity_id = entity(database)
    apply(
        database,
        entity_id=entity_id,
        principal=PERSON,
        request_id="req",
        books=read(synthetic_export()),
    )
    with database.entity_write(entity_id) as write:
        accounts = {account.code: account.account_id for account in write.chart()}

    record_transaction(
        database,
        WriteContext(
            entity_id=entity_id,
            principal=PERSON,
            request_id="typed-by-hand",
            idempotency_key=uuid.uuid4().hex,
        ),
        entry=Entry(
            transaction_date=date(2026, 5, 1),
            postings=(
                Posting(
                    account_id=accounts["Checking"], amount=Decimal("5.00"), commodity="USD"
                ),
                Posting(
                    account_id=accounts["Services"], amount=Decimal("-5.00"), commodity="USD"
                ),
            ),
            description="Typed by hand",
        ),
        post=True,
    )

    with database.entity_write(entity_id) as write:
        columns, rows = write.archived("ledger_transaction")
    entries = [dict(zip(columns, row, strict=True)) for row in rows]
    by_hand = next(entry for entry in entries if entry["description"] == "Typed by hand")

    assert by_hand["derived_from"] is None
    assert all(entry["derived_from"] is not None for entry in entries if entry is not by_hand)


# --- applying is a person's act (ADR-0007, ADR-0030) ---------------------------------------


def staffed(database: Database) -> tuple[str, Principal]:
    """An entity, and an agent holding a role in it while acting for its owner.

    The grant matters: without one the agent is refused for holding nothing, which would make
    the tests below pass for the wrong reason.
    """
    entity_id = entity(database)
    agent = Principal(id="agent:bookkeeper", actor_class=ActorClass.AGENT, acting_for=PERSON.id)
    grant_role(
        database,
        entity_id=entity_id,
        principal=PERSON,
        request_id="req-grant",
        to_principal=agent.id,
        role="owner",
    )
    return entity_id, agent


def test_a_delegated_agent_may_plan_an_import(database: Database) -> None:
    """The proposing half. A skill reading an export and reporting what it would do is exactly
    what a skill is for, and it posts nothing."""
    entity_id, agent = staffed(database)

    proposed = plan(
        database, entity_id=entity_id, principal=agent, books=read(synthetic_export())
    )

    assert proposed.can_apply


def test_a_delegated_agent_may_not_apply_one(database: Database) -> None:
    """**The largest single act of posting the system offers**, in one call. ADR-0007: the
    agent proposes and a person's confirmation posts.

    A capability the agent does not hold, rather than an instruction it is asked to follow —
    the same division ADR-0030 drew around reopening a closed period, and for the same reason:
    an instruction can be argued past and a capability cannot.
    """
    entity_id, agent = staffed(database)

    with pytest.raises(NotAPerson):
        apply(
            database,
            entity_id=entity_id,
            principal=agent,
            request_id="req",
            books=read(synthetic_export()),
        )

    with database.entity_write(entity_id) as write:
        assert write.chart() == []  # refused before anything was created


def test_the_refusal_is_decided_on_the_token_shape_not_a_claim(database: Database) -> None:
    """`actor_class` comes from whether the token carries an RFC 8693 `act` claim (ADR-0033).
    A skill cannot describe itself as a person, which is what makes the control worth having.
    """
    entity_id, _ = staffed(database)
    rule = Principal(id="rule:importer", actor_class=ActorClass.RULE)

    with pytest.raises(NotAPerson):
        apply(
            database,
            entity_id=entity_id,
            principal=rule,
            request_id="req",
            books=read(synthetic_export()),
        )
