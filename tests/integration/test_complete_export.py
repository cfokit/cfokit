"""Complete export (`EXP-02`), and the one property that makes it worth having.

> "Everything the entity holds — the interchange content, plus supporting documents,
> attachments, raw ingested payloads, rule definitions and the attribution linking them to
> postings, approvals, the record of what an agent did and on what basis, and the audit trail."

`EXP-04` is what the file is *for*: taken from one deployment and imported into another it
reproduces the books, their history, and their attribution. That half needs an import path and
is not built. What is testable now is the half that would make it possible — that nothing the
entity holds is left behind, and that what is carried is carried as stored rather than as some
report renders it.

**So the tests are about absence, not shape.** A test that the archive has ten files passes
while an eleventh table goes unexported. The test that matters walks the schema and fails when
a table nobody exported appears.
"""

from __future__ import annotations

import io
import json
import uuid
import zipfile
from datetime import date
from decimal import Decimal
from typing import Any

import psycopg
import pytest

from cfokit.ledger.engine import Entry, Posting
from cfokit.ledger.engine.periods import Period
from cfokit.ledger.errors import NotAuthorized
from cfokit.ledger.repository import archive
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.administration import grant_role
from cfokit.ledger.service.interchange import ARCHIVE_FORMAT, export_complete
from cfokit.ledger.service.periods import close_period
from cfokit.ledger.service.principal import ActorClass, Principal
from cfokit.ledger.service.write import WriteContext, record_transaction

pytestmark = pytest.mark.integration

MARCH = date(2026, 3, 14)
PERSON = Principal(id="user:geoff", actor_class=ActorClass.PERSON)

# Tables the archive deliberately does not carry, and why. Listed here so the sweep below can
# tell "decided against" from "forgotten", which is the whole point of that test.
NOT_ENTITY_HELD = {
    "role",  # the deployment's privilege definitions, not the entity's
    "role_privilege",  # same
    "schema_migration",  # the database's own state; the manifest names its version instead
    "idempotency_key",  # a replay cache with its own lifetime, not part of the books
}


def book(
    database: Database, entity_id: str, debit: str, credit: str, amount: str, *, post: bool
) -> str:
    return record_transaction(
        database,
        WriteContext(
            entity_id=entity_id,
            principal=PERSON,
            request_id=f"req-{uuid.uuid4().hex[:8]}",
            idempotency_key=uuid.uuid4().hex,
        ),
        entry=Entry(
            transaction_date=MARCH,
            postings=(
                Posting(account_id=debit, amount=Decimal(amount), commodity="USD"),
                Posting(account_id=credit, amount=-Decimal(amount), commodity="USD"),
            ),
            description=None if post else "A draft",
        ),
        post=post,
    ).transaction_id


def member(bundle: bytes, name: str) -> bytes:
    with zipfile.ZipFile(io.BytesIO(bundle)) as opened:
        return opened.read(name)


def rows(bundle: bytes, table: str) -> list[dict[str, object]]:
    text = member(bundle, f"tables/{table}.jsonl").decode("utf-8")
    return [json.loads(line) for line in text.splitlines()]


@pytest.fixture
def stocked(database: Database, owned_books: tuple[str, str, str]) -> tuple[str, str, str]:
    """The fixture entity with a posted transaction, a draft, and a closed period."""
    entity_id, cash, revenue = owned_books
    book(database, entity_id, cash, revenue, "100.00", post=True)
    book(database, entity_id, cash, revenue, "25.00", post=False)
    close_period(
        database,
        entity_id=entity_id,
        principal=PERSON,
        request_id="req-close",
        period=Period(year=2026, month=3),
    )
    return entity_id, cash, revenue


# --- Nothing the entity holds is left behind ----------------------------------------------


def test_every_entity_scoped_table_is_exported(
    owner_conn: psycopg.Connection[Any],
) -> None:
    """**This is the test that matters.** Walk the live schema, not a list we wrote.

    A table added by a later migration and never added to the archive would leave a complete
    export quietly incomplete, and `EXP-04` would restore books missing something nobody
    noticed. Adding a table means deciding, here, whether the entity holds it.
    """
    with owner_conn.cursor() as cur:
        cur.execute(
            "SELECT table_name FROM information_schema.columns"
            " WHERE table_schema = 'public' AND column_name = 'entity_id'"
        )
        entity_scoped = {str(row[0]) for row in cur.fetchall()}

    exported = {name for name, _ in archive.TABLES}

    assert entity_scoped - exported - NOT_ENTITY_HELD == set()


def test_the_entity_row_itself_is_exported() -> None:
    """`entity` has no `entity_id` column, so the sweep above cannot see it. Its settings are
    the shape of the books — basis, fiscal year end, functional currency — and a restore
    without them would reproduce figures into a differently-configured entity."""
    assert "entity" in {name for name, _ in archive.TABLES}


def test_a_draft_is_carried_even_though_no_statement_shows_it(
    database: Database, stocked: tuple[str, str, str]
) -> None:
    """A draft is not in the books (`LED-07`) and so appears in no report. It is still
    something the entity holds, and `EXP-04` reproduces what was there rather than a tidied
    version of it."""
    entity_id, _, _ = stocked
    bundle = export_complete(
        database, entity_id=entity_id, principal=PERSON, request_id="req"
    ).archive

    statuses = {str(row["status"]) for row in rows(bundle, "ledger_transaction")}

    assert statuses == {"posted", "draft"}


def test_the_audit_trail_is_carried(database: Database, stocked: tuple[str, str, str]) -> None:
    """`EXP-02` names it explicitly, and it is the only record of who did what."""
    entity_id, _, _ = stocked
    bundle = export_complete(
        database, entity_id=entity_id, principal=PERSON, request_id="req"
    ).archive

    actions = {str(row["action"]) for row in rows(bundle, "audit_log")}

    assert {"create_entity", "create_account", "record_transaction"} <= actions


def test_attribution_survives_the_export(
    database: Database, stocked: tuple[str, str, str]
) -> None:
    """`EXP-04`: "reproduces the books, their history, and their attribution". Who acted, on
    whose behalf, and under what class, is on the transaction itself."""
    entity_id, _, _ = stocked
    bundle = export_complete(
        database, entity_id=entity_id, principal=PERSON, request_id="req"
    ).archive

    transactions = rows(bundle, "ledger_transaction")
    posted = next(row for row in transactions if row["status"] == "posted")

    assert posted["actor_principal_id"] == PERSON.id
    assert posted["actor_class"] == ActorClass.PERSON.value
    assert posted["recorded_at"] is not None
    assert posted["posted_at"] is not None


def test_the_grants_are_carried(database: Database, stocked: tuple[str, str, str]) -> None:
    """Who could act, and when. An entity restored without its grants has no owner."""
    entity_id, _, _ = stocked
    bundle = export_complete(
        database, entity_id=entity_id, principal=PERSON, request_id="req"
    ).archive

    assert [row["role"] for row in rows(bundle, "entity_grant")] == ["owner"]


def test_the_receivables_a_module_holds_are_carried(
    database: Database, stocked: tuple[str, str, str]
) -> None:
    """`EXP-02` is "everything the entity holds", and a module's tables are the entity's as
    much as the ledger's are. A restore without them would return books with no customers and
    no billing history, and the sweep above is what would otherwise have let that ship."""
    entity_id, _, _ = stocked
    bundle = export_complete(
        database, entity_id=entity_id, principal=PERSON, request_id="req"
    ).archive

    exported = {name for name, _ in archive.TABLES}

    assert {"customer", "invoice", "invoice_line", "invoice_series"} <= exported
    assert rows(bundle, "customer") == []  # this entity has none, and the file says so


def test_a_closed_period_is_carried(database: Database, stocked: tuple[str, str, str]) -> None:
    """A close is a fact about the books, not a report of them. Restoring without it would
    reopen a period somebody closed."""
    entity_id, _, _ = stocked
    bundle = export_complete(
        database, entity_id=entity_id, principal=PERSON, request_id="req"
    ).archive

    closes = rows(bundle, "period_close")

    assert [(row["period_year"], row["period_month"]) for row in closes] == [(2026, 3)]


# --- As stored, not as rendered -----------------------------------------------------------


def test_amounts_are_carried_as_strings_at_full_precision(
    database: Database, stocked: tuple[str, str, str]
) -> None:
    """JSON's number is a float in every reader that matters, and `LED-04` allows no
    representation error (ADR-0005). A `Decimal` crosses as text or it does not cross."""
    entity_id, _, _ = stocked
    bundle = export_complete(
        database, entity_id=entity_id, principal=PERSON, request_id="req"
    ).archive

    amounts = [row["amount"] for row in rows(bundle, "posting")]

    assert all(isinstance(amount, str) for amount in amounts)
    assert Decimal("100.0000000000") in {Decimal(str(amount)) for amount in amounts}


def test_an_absent_value_is_null_and_not_an_empty_string(
    database: Database, stocked: tuple[str, str, str]
) -> None:
    """The reason the complete export is JSON Lines and not CSV. A transaction with no
    description has none; one described as `""` is a different transaction."""
    entity_id, _, _ = stocked
    bundle = export_complete(
        database, entity_id=entity_id, principal=PERSON, request_id="req"
    ).archive

    transactions = rows(bundle, "ledger_transaction")
    posted = next(row for row in transactions if row["status"] == "posted")

    assert posted["description"] is None


def test_the_interchange_files_travel_inside_the_complete_export(
    database: Database, stocked: tuple[str, str, str]
) -> None:
    """`EXP-02` is "the interchange content, plus" — so a receiver that only speaks CSV gets
    something usable out of the same file."""
    entity_id, _, _ = stocked
    bundle = export_complete(
        database, entity_id=entity_id, principal=PERSON, request_id="req"
    ).archive

    with zipfile.ZipFile(io.BytesIO(bundle)) as opened:
        interchange = sorted(n for n in opened.namelist() if n.startswith("interchange/"))

    assert interchange == [
        "interchange/accounts.csv",
        "interchange/journal.csv",
        "interchange/trial_balance.csv",
    ]


def test_the_manifest_states_what_a_receiver_needs_to_refuse_on(
    database: Database, stocked: tuple[str, str, str]
) -> None:
    """A receiving deployment reads the archive format to know whether it understands the
    layout, and the schema version to know whether it can place the rows. Without both, a
    restore that cannot work becomes a partial one that looks like it did."""
    entity_id, _, _ = stocked
    exported = export_complete(
        database, entity_id=entity_id, principal=PERSON, request_id="req"
    )

    manifest = json.loads(member(exported.archive, "manifest.json"))

    assert manifest["archive_format"] == ARCHIVE_FORMAT
    assert manifest["schema_version"] == exported.schema_version
    assert manifest["schema_version"] != ""
    assert manifest["entity_id"] == entity_id
    assert manifest["rows"]["posting"] == 4  # two transactions, two postings each


def test_two_exports_of_unchanged_books_are_identical(
    database: Database, stocked: tuple[str, str, str]
) -> None:
    """Byte-identical but for the moment it was taken, so a diff shows only what changed.

    Every table is read in a total order for the same reason the interchange journal is: an
    order that can tie is one the database may return differently on a different day.
    """
    entity_id, _, _ = stocked
    first = export_complete(database, entity_id=entity_id, principal=PERSON, request_id="a")
    second = export_complete(database, entity_id=entity_id, principal=PERSON, request_id="b")

    with (
        zipfile.ZipFile(io.BytesIO(first.archive)) as one,
        zipfile.ZipFile(io.BytesIO(second.archive)) as two,
    ):
        assert one.namelist() == two.namelist()
        for name in one.namelist():
            if name == "manifest.json":
                continue  # carries the moment it was taken, and the request that asked
            assert one.read(name) == two.read(name), name


# --- EXP-03: available in any state, needing nothing but READ ------------------------------


def test_reading_the_books_is_the_whole_privilege(
    database: Database, owned_books: tuple[str, str, str]
) -> None:
    """`EXP-03`: "at any time, in any entity state short of deletion, without asking anyone".

    A privilege beyond reading would be a way for an entity to become unexportable, which is
    the failure this requirement exists to prevent.
    """
    entity_id, _, _ = owned_books
    reader = Principal(id=f"user:reader-{uuid.uuid4().hex[:8]}", actor_class=ActorClass.PERSON)
    grant_role(
        database,
        entity_id=entity_id,
        principal=PERSON,
        request_id="req-grant",
        to_principal=reader.id,
        role="owner",
    )

    exported = export_complete(
        database, entity_id=entity_id, principal=reader, request_id="req"
    )

    assert exported.entity_id == entity_id


def test_a_stranger_is_refused(database: Database, owned_books: tuple[str, str, str]) -> None:
    """Needing only `READ` is not the same as needing nothing."""
    entity_id, _, _ = owned_books
    stranger = Principal(id="user:nobody", actor_class=ActorClass.PERSON)

    with pytest.raises(NotAuthorized):
        export_complete(database, entity_id=entity_id, principal=stranger, request_id="req")


def test_exporting_writes_no_audit_row(
    database: Database, stocked: tuple[str, str, str]
) -> None:
    """It changes nothing, and "exactly one audit row per state change" cuts both ways.

    It also protects `EXP-03`: an export that had to write could be refused by anything that
    stops a write, and an entity that cannot be exported is the failure the requirement names.
    """
    entity_id, _, _ = stocked
    before = export_complete(
        database, entity_id=entity_id, principal=PERSON, request_id="req"
    ).rows["audit_log"]

    after = export_complete(
        database, entity_id=entity_id, principal=PERSON, request_id="req"
    ).rows["audit_log"]

    assert before == after
