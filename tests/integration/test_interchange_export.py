"""Interchange export (`EXP-01`), and its acceptance, which is a reconciliation.

> *Acceptance, EXP-01:* "The export is a single self-contained archive, and a trial balance
> derived from the archive alone agrees, line for line, with the trial balance CFOKit produces
> for the same date."

So the test is not "the file has the right shape". It is: derive the balances **from the
archive alone**, using nothing of ours but arithmetic, and reconcile them against the live
books. That is the reconciler built for `IMP-08`, pointed the other way.
"""

from __future__ import annotations

import csv
import io
import time
import uuid
import zipfile
from collections import defaultdict
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from cfokit.ledger.engine import Entry, Posting
from cfokit.ledger.errors import NotAuthorised
from cfokit.ledger.presentation import SourceBalance, present_reconciliation
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.administration import create_account, grant_role
from cfokit.ledger.service.interchange import export_interchange
from cfokit.ledger.service.principal import ActorClass, Principal
from cfokit.ledger.service.reports import trial_balance
from cfokit.ledger.service.write import WriteContext, record_transaction

pytestmark = pytest.mark.integration

MARCH = date(2026, 3, 14)
APRIL = date(2026, 4, 2)
AS_OF = date(2026, 12, 31)
PERSON = Principal(id="user:geoff", actor_class=ActorClass.PERSON)


def book(
    database: Database, entity_id: str, debit: str, credit: str, when: date, amount: str
) -> None:
    record_transaction(
        database,
        WriteContext(
            entity_id=entity_id,
            principal=PERSON,
            request_id=f"req-{uuid.uuid4().hex[:8]}",
            idempotency_key=uuid.uuid4().hex,
        ),
        entry=Entry(
            transaction_date=when,
            postings=(
                Posting(account_id=debit, amount=Decimal(amount), commodity="USD"),
                Posting(account_id=credit, amount=-Decimal(amount), commodity="USD"),
            ),
            description="Entry",
        ),
        post=True,
    )


def read(archive: bytes, name: str) -> list[dict[str, str]]:
    with zipfile.ZipFile(io.BytesIO(archive)) as opened:
        return list(csv.DictReader(io.StringIO(opened.read(name).decode("utf-8"))))


def derived_from_archive(archive: bytes) -> tuple[SourceBalance, ...]:
    """Sum the archive's journal into balances, using nothing of ours but addition.

    This is the "derived from the archive alone" half of `EXP-01`'s acceptance. It deliberately
    does not read `trial_balance.csv` — that file is the archive's own claim, and checking a
    claim against itself proves nothing.
    """
    totals: dict[str, Decimal] = defaultdict(Decimal)
    for line in read(archive, "journal.csv"):
        totals[line["account_code"]] += Decimal(line["amount"])
    return tuple(
        SourceBalance(account_code=code, balance=balance)
        for code, balance in sorted(totals.items())
        if balance != 0
    )


@pytest.fixture
def stocked(database: Database, owned_books: tuple[str, str, str]) -> tuple[str, str, str, str]:
    """The fixture entity with a third account, and three posted transactions."""
    entity_id, cash, revenue = owned_books
    expense = create_account(
        database,
        entity_id=entity_id,
        principal=PERSON,
        request_id="req",
        code=f"5000-{uuid.uuid4().hex[:6]}",
        name="Rent",
        account_type="expense",
    )
    book(database, entity_id, cash, revenue, MARCH, "100.00")
    book(database, entity_id, expense, cash, APRIL, "30.00")
    book(database, entity_id, cash, revenue, APRIL, "40.50")
    return entity_id, cash, revenue, expense


# --- EXP-01's acceptance ------------------------------------------------------------------


def test_balances_derived_from_the_archive_agree_line_for_line(
    database: Database, stocked: tuple[str, str, str, str]
) -> None:
    """**This is the acceptance.** Sum the archive's journal, reconcile against the live books,
    and every line must agree — not most, not to a tolerance."""
    entity_id, _, _, _ = stocked
    exported = export_interchange(database, entity_id=entity_id, principal=PERSON, as_of=AS_OF)

    report = present_reconciliation(
        trial_balance(database, entity_id=entity_id, principal=PERSON, as_of=AS_OF),
        derived_from_archive(exported.archive),
    )

    assert report.agrees, [
        (c.account_code, str(c.ours), str(c.theirs)) for c in report.disagreements
    ]


def test_the_archives_own_trial_balance_matches_what_it_carries(
    database: Database, stocked: tuple[str, str, str, str]
) -> None:
    """The archive is self-contained: its stated balances are the ones its journal produces.

    A reader who trusts `trial_balance.csv` and a reader who adds up `journal.csv` must reach
    the same figures, or the archive contradicts itself.
    """
    entity_id, _, _, _ = stocked
    archive = export_interchange(
        database, entity_id=entity_id, principal=PERSON, as_of=AS_OF
    ).archive

    stated = {
        row["account_code"]: Decimal(row["balance"])
        for row in read(archive, "trial_balance.csv")
    }
    derived = {b.account_code: b.balance for b in derived_from_archive(archive)}

    assert stated == derived


def test_the_archive_carries_all_three_files(
    database: Database, stocked: tuple[str, str, str, str]
) -> None:
    """`EXP-01`: "chart of accounts, transactions, and balances"."""
    entity_id, _, _, _ = stocked
    archive = export_interchange(
        database, entity_id=entity_id, principal=PERSON, as_of=AS_OF
    ).archive

    with zipfile.ZipFile(io.BytesIO(archive)) as opened:
        assert sorted(opened.namelist()) == [
            "accounts.csv",
            "journal.csv",
            "trial_balance.csv",
        ]


def test_the_chart_lists_every_account_including_ones_with_no_postings(
    database: Database, owned_books: tuple[str, str, str]
) -> None:
    """A chart of accounts is the chart, not the accounts that happen to have moved. A
    receiving system needs the empty ones to reproduce the books' shape."""
    entity_id, _, _ = owned_books
    create_account(
        database,
        entity_id=entity_id,
        principal=PERSON,
        request_id="req",
        code=f"9999-{uuid.uuid4().hex[:6]}",
        name="Never used",
        account_type="expense",
    )

    archive = export_interchange(
        database, entity_id=entity_id, principal=PERSON, as_of=AS_OF
    ).archive

    assert len(read(archive, "accounts.csv")) == 3


# --- Determinism and dating ---------------------------------------------------------------


def test_two_exports_of_unchanged_books_are_identical(
    database: Database, stocked: tuple[str, str, str, str]
) -> None:
    """Byte-identical, so a diff between two exports shows only what actually changed.

    That needs a total order on the journal — date, then when the transaction entered the
    books, then the posting id — because an order that can tie is one the database may return
    differently on a different day.
    """
    entity_id, _, _, _ = stocked

    first = export_interchange(database, entity_id=entity_id, principal=PERSON, as_of=AS_OF)
    second = export_interchange(database, entity_id=entity_id, principal=PERSON, as_of=AS_OF)

    assert first.archive == second.archive


def test_an_export_does_not_depend_on_the_clock(
    database: Database, stocked: tuple[str, str, str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same books exported a minute apart are still byte-identical.

    ZIP records a modification time per entry, to two-second resolution. An entry stamped
    with the wall clock makes the test above pass or fail depending on whether both exports
    land in the same two seconds. Moving the clock `zipfile` reads makes that deterministic.
    """
    entity_id, _, _, _ = stocked
    first = export_interchange(database, entity_id=entity_id, principal=PERSON, as_of=AS_OF)

    class Later:
        """`zipfile`'s view of the time module, a minute ahead."""

        localtime = staticmethod(time.localtime)

        @staticmethod
        def time() -> int:
            return int(time.time()) + 60

    monkeypatch.setattr("zipfile.time", Later)
    second = export_interchange(database, entity_id=entity_id, principal=PERSON, as_of=AS_OF)

    assert first.archive == second.archive


def test_an_earlier_watermark_exports_the_books_as_they_stood(
    database: Database, owned_books: tuple[str, str, str]
) -> None:
    """`RPT-11` reaches the export too: the archive given to a lender in March is reproducible
    in December, unchanged by what was posted between.

    Both entries are dated in March, so `as_of` cannot separate them. Only the watermark can.
    """
    entity_id, cash, revenue = owned_books
    book(database, entity_id, cash, revenue, MARCH, "100.00")
    taken = datetime.now(UTC)
    book(database, entity_id, cash, revenue, MARCH, "40.00")

    now = export_interchange(database, entity_id=entity_id, principal=PERSON, as_of=AS_OF)
    then = export_interchange(
        database, entity_id=entity_id, principal=PERSON, as_of=AS_OF, watermark=taken
    )

    assert now.postings == 4
    assert then.postings == 2
    assert derived_from_archive(then.archive)[0].balance == Decimal("100.0000000000")


def test_a_draft_is_not_exported(
    database: Database, stocked: tuple[str, str, str, str]
) -> None:
    """A draft is not in the books (`LED-07`), and an archive carrying one would not reconcile
    against a trial balance that excludes it."""
    entity_id, cash, revenue, _ = stocked
    before = export_interchange(
        database, entity_id=entity_id, principal=PERSON, as_of=AS_OF
    ).postings

    record_transaction(
        database,
        WriteContext(
            entity_id=entity_id,
            principal=PERSON,
            request_id="req",
            idempotency_key=uuid.uuid4().hex,
        ),
        entry=Entry(
            transaction_date=MARCH,
            postings=(
                Posting(account_id=cash, amount=Decimal("9.00"), commodity="USD"),
                Posting(account_id=revenue, amount=Decimal("-9.00"), commodity="USD"),
            ),
            description="Not yet",
        ),
        post=False,
    )

    after = export_interchange(
        database, entity_id=entity_id, principal=PERSON, as_of=AS_OF
    ).postings
    assert after == before


def test_exporting_requires_the_read_privilege(
    database: Database, stocked: tuple[str, str, str, str]
) -> None:
    entity_id, _, _, _ = stocked

    with pytest.raises(NotAuthorised):
        export_interchange(
            database,
            entity_id=entity_id,
            principal=Principal(id="user:stranger", actor_class=ActorClass.PERSON),
            as_of=AS_OF,
        )


def test_a_reader_can_export(database: Database, stocked: tuple[str, str, str, str]) -> None:
    """`EXP-03`: available "without asking anyone and without a support request". The positive
    control — a rule refusing everyone would pass the test above."""
    entity_id, _, _, _ = stocked
    grant_role(
        database,
        entity_id=entity_id,
        principal=PERSON,
        request_id="req",
        to_principal="user:reader",
        role="reader",
    )

    exported = export_interchange(
        database,
        entity_id=entity_id,
        principal=Principal(id="user:reader", actor_class=ActorClass.PERSON),
        as_of=AS_OF,
    )

    assert exported.postings == 6
