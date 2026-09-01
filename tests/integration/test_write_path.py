"""The write path's four obligations, proved against a real database.

Each is "a bug if missed" rather than a nice-to-have, and none of them is visible from a unit
test: the lock, the idempotency check and the audit row are all properties of what happens in
one database transaction.

- **The entity lock** serialises writes (ADR-0011). ADR-0011 is explicit that this must be
  proved "by actually running concurrent writes, not by inspection", which is what
  `test_writes_to_one_entity_serialise` does.
- **The idempotency key** is mandatory, and a replay returns the original result without
  repeating the work (ADR-0029).
- **Exactly one audit row** per state change — and none for a replay, because a replayed
  request is not a state change.
- **Attribution** comes from the authenticated principal, never from a parameter (ADR-0033).
"""

from __future__ import annotations

import threading
import uuid
from datetime import date
from decimal import Decimal
from typing import Any

import psycopg
import pytest

from cfokit.ledger.engine import Entry, Posting
from cfokit.ledger.errors import (
    IdempotencyKeyRequired,
    IdempotencyKeyReused,
    TransactionAlreadyPosted,
    UnbalancedTransaction,
)
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.principal import ActorClass, Principal
from cfokit.ledger.service.write import (
    WriteContext,
    post_transaction,
    record_transaction,
    reverse_transaction,
)

pytestmark = pytest.mark.integration

TODAY = date(2026, 9, 1)
PERSON = Principal(id="user:geoff", actor_class=ActorClass.PERSON)
AGENT = Principal(id="skill:bookkeeper", actor_class=ActorClass.AGENT, acting_for="user:geoff")


def context(entity_id: str, principal: Principal = PERSON) -> WriteContext:
    return WriteContext(
        entity_id=entity_id,
        principal=principal,
        request_id=f"req-{uuid.uuid4().hex[:8]}",
        idempotency_key=uuid.uuid4().hex,
    )


def balanced(cash: str, revenue: str, amount: str = "100.00") -> Entry:
    return Entry(
        transaction_date=TODAY,
        postings=(
            Posting(account_id=cash, amount=Decimal(amount), commodity="USD"),
            Posting(account_id=revenue, amount=-Decimal(amount), commodity="USD"),
        ),
        description="Invoice 1001",
    )


def audit_rows(conn: psycopg.Connection[Any], entity_id: str) -> list[tuple[Any, ...]]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT action, actor, subject_id, request_id FROM audit_log"
            " WHERE entity_id = %s ORDER BY occurred_at",
            (entity_id,),
        )
        return list(cur.fetchall())


def transaction_count(conn: psycopg.Connection[Any], entity_id: str) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM ledger_transaction WHERE entity_id = %s", (entity_id,)
        )
        row = cur.fetchone()
        assert row is not None
        return int(row[0])


# --- Recording and posting ----------------------------------------------------------------


def test_a_draft_is_recorded_with_attribution_from_the_principal(
    database: Database, owner_conn: psycopg.Connection[Any], books: tuple[str, str, str]
) -> None:
    """`LED-20`: the transaction itself records what wrote it, and on whose behalf."""
    entity_id, cash, revenue = books

    written = record_transaction(
        database,
        context(entity_id, AGENT),
        entry=balanced(cash, revenue),
        functional_currency="USD",
        post=False,
    )

    assert written.status == "draft"
    with owner_conn.cursor() as cur:
        cur.execute(
            "SELECT actor_principal_id, actor_class, acting_for_principal_id, entry_kind"
            " FROM ledger_transaction WHERE id = %s",
            (written.transaction_id,),
        )
        row = cur.fetchone()
    assert row == ("skill:bookkeeper", "agent", "user:geoff", "ordinary")


def test_a_balanced_entry_can_be_posted_straight_through(
    database: Database, owner_conn: psycopg.Connection[Any], books: tuple[str, str, str]
) -> None:
    entity_id, cash, revenue = books

    written = record_transaction(
        database,
        context(entity_id),
        entry=balanced(cash, revenue),
        functional_currency="USD",
        post=True,
    )

    assert written.status == "posted"
    with owner_conn.cursor() as cur:
        cur.execute(
            "SELECT status, posted_at IS NOT NULL FROM ledger_transaction WHERE id = %s",
            (written.transaction_id,),
        )
        assert cur.fetchone() == ("posted", True)


def test_an_unbalanced_entry_is_refused_before_it_reaches_the_database(
    database: Database, owner_conn: psycopg.Connection[Any], books: tuple[str, str, str]
) -> None:
    """ADR-0006: the application check exists so the caller gets a stable code first.

    And nothing is written — the transaction rolls back, so a refused write leaves no draft
    behind for someone to find later and wonder about.
    """
    entity_id, cash, revenue = books
    entry = Entry(
        transaction_date=TODAY,
        postings=(
            Posting(account_id=cash, amount=Decimal("100.00"), commodity="USD"),
            Posting(account_id=revenue, amount=Decimal("-99.00"), commodity="USD"),
        ),
    )

    with pytest.raises(UnbalancedTransaction) as caught:
        record_transaction(
            database, context(entity_id), entry=entry, functional_currency="USD", post=True
        )

    assert caught.value.code == "unbalanced_transaction"
    assert transaction_count(owner_conn, entity_id) == 0


def test_a_draft_can_be_posted_later(database: Database, books: tuple[str, str, str]) -> None:
    entity_id, cash, revenue = books
    draft = record_transaction(
        database,
        context(entity_id),
        entry=balanced(cash, revenue),
        functional_currency="USD",
        post=False,
    )

    posted = post_transaction(
        database,
        context(entity_id),
        transaction_id=draft.transaction_id,
        functional_currency="USD",
    )

    assert posted.transaction_id == draft.transaction_id
    assert posted.status == "posted"


def test_posting_twice_is_refused(database: Database, books: tuple[str, str, str]) -> None:
    """`LED-07`: posting is the point of no return, and a distinct code says which one."""
    entity_id, cash, revenue = books
    written = record_transaction(
        database,
        context(entity_id),
        entry=balanced(cash, revenue),
        functional_currency="USD",
        post=True,
    )

    with pytest.raises(TransactionAlreadyPosted) as caught:
        post_transaction(
            database,
            context(entity_id),
            transaction_id=written.transaction_id,
            functional_currency="USD",
        )

    assert caught.value.code == "transaction_already_posted"


# --- Idempotency (ADR-0029) ---------------------------------------------------------------


def test_a_write_without_a_key_is_rejected(
    database: Database, books: tuple[str, str, str]
) -> None:
    """Mandatory, because "the write that omits a key is the write that double-books"."""
    entity_id, cash, revenue = books
    ctx = WriteContext(
        entity_id=entity_id, principal=PERSON, request_id="req-1", idempotency_key=""
    )

    with pytest.raises(IdempotencyKeyRequired) as caught:
        record_transaction(
            database, ctx, entry=balanced(cash, revenue), functional_currency="USD", post=True
        )

    assert caught.value.code == "idempotency_key_required"


def test_a_replay_returns_the_original_and_books_nothing_further(
    database: Database, owner_conn: psycopg.Connection[Any], books: tuple[str, str, str]
) -> None:
    """`NFR-03` allows zero duplicates under retry. This is the test that says so."""
    entity_id, cash, revenue = books
    ctx = context(entity_id)
    entry = balanced(cash, revenue)

    first = record_transaction(database, ctx, entry=entry, functional_currency="USD", post=True)
    second = record_transaction(
        database, ctx, entry=entry, functional_currency="USD", post=True
    )

    assert second.transaction_id == first.transaction_id
    assert second.replayed is True
    assert first.replayed is False
    assert transaction_count(owner_conn, entity_id) == 1


def test_a_replay_writes_no_second_audit_row(
    database: Database, owner_conn: psycopg.Connection[Any], books: tuple[str, str, str]
) -> None:
    """ADR-0029: "a replayed idempotent request is not a new state change and must not write
    a second row"."""
    entity_id, cash, revenue = books
    ctx = context(entity_id)
    entry = balanced(cash, revenue)

    record_transaction(database, ctx, entry=entry, functional_currency="USD", post=True)
    record_transaction(database, ctx, entry=entry, functional_currency="USD", post=True)

    assert len(audit_rows(owner_conn, entity_id)) == 1


def test_a_key_reused_with_different_parameters_is_refused(
    database: Database, books: tuple[str, str, str]
) -> None:
    """A client error, not a replay. Silently succeeding with the wrong amount is the failure
    this prevents."""
    entity_id, cash, revenue = books
    ctx = context(entity_id)

    record_transaction(
        database,
        ctx,
        entry=balanced(cash, revenue, "100.00"),
        functional_currency="USD",
        post=True,
    )

    with pytest.raises(IdempotencyKeyReused) as caught:
        record_transaction(
            database,
            ctx,
            entry=balanced(cash, revenue, "250.00"),
            functional_currency="USD",
            post=True,
        )

    assert caught.value.code == "idempotency_key_reused"


def test_two_identical_transactions_under_different_keys_both_book(
    database: Database, owner_conn: psycopg.Connection[Any], books: tuple[str, str, str]
) -> None:
    """ADR-0029 rejects content hashing for exactly this: "two five-dollar coffees on the same
    day stay two transactions"."""
    entity_id, cash, revenue = books
    entry = balanced(cash, revenue, "5.00")

    record_transaction(
        database, context(entity_id), entry=entry, functional_currency="USD", post=True
    )
    record_transaction(
        database, context(entity_id), entry=entry, functional_currency="USD", post=True
    )

    assert transaction_count(owner_conn, entity_id) == 2


# --- The audit trail (ADR-0011) -----------------------------------------------------------


def test_exactly_one_audit_row_per_state_change(
    database: Database, owner_conn: psycopg.Connection[Any], books: tuple[str, str, str]
) -> None:
    entity_id, cash, revenue = books

    draft = record_transaction(
        database,
        context(entity_id),
        entry=balanced(cash, revenue),
        functional_currency="USD",
        post=False,
    )
    post_transaction(
        database,
        context(entity_id),
        transaction_id=draft.transaction_id,
        functional_currency="USD",
    )

    rows = audit_rows(owner_conn, entity_id)
    assert [r[0] for r in rows] == ["record_transaction", "post_transaction"]


def test_the_audit_row_names_the_principal_and_the_request(
    database: Database, owner_conn: psycopg.Connection[Any], books: tuple[str, str, str]
) -> None:
    """One request id per inbound call, propagated into the trail (CLAUDE.md)."""
    entity_id, cash, revenue = books
    ctx = context(entity_id, AGENT)

    record_transaction(
        database, ctx, entry=balanced(cash, revenue), functional_currency="USD", post=True
    )

    (row,) = audit_rows(owner_conn, entity_id)
    assert row[1] == "skill:bookkeeper for user:geoff"
    assert row[3] == ctx.request_id


def test_the_audit_detail_carries_no_amounts(
    database: Database, owner_conn: psycopg.Connection[Any], books: tuple[str, str, str]
) -> None:
    """Identifiers and counts only (CLAUDE.md, Observability). `detail` is jsonb and it is
    easy to put the whole request in it; this is what stops that."""
    entity_id, cash, revenue = books

    record_transaction(
        database,
        context(entity_id),
        entry=balanced(cash, revenue, "1234.56"),
        functional_currency="USD",
        post=True,
    )

    with owner_conn.cursor() as cur:
        cur.execute("SELECT detail::text FROM audit_log WHERE entity_id = %s", (entity_id,))
        row = cur.fetchone()
    assert row is not None
    assert "1234.56" not in row[0]
    assert cash not in row[0]


def test_a_failed_write_leaves_no_audit_row(
    database: Database, owner_conn: psycopg.Connection[Any], books: tuple[str, str, str]
) -> None:
    """The row and the change it describes cannot be separated by a failure."""
    entity_id, cash, revenue = books
    entry = Entry(
        transaction_date=TODAY,
        postings=(
            Posting(account_id=cash, amount=Decimal("100.00"), commodity="USD"),
            Posting(account_id=revenue, amount=Decimal("-99.00"), commodity="USD"),
        ),
    )

    with pytest.raises(UnbalancedTransaction):
        record_transaction(
            database, context(entity_id), entry=entry, functional_currency="USD", post=True
        )

    assert audit_rows(owner_conn, entity_id) == []


# --- Reversal (ADR-0007, LED-08) ----------------------------------------------------------


def test_a_reversal_is_posted_linked_and_nets_to_zero(
    database: Database, owner_conn: psycopg.Connection[Any], books: tuple[str, str, str]
) -> None:
    entity_id, cash, revenue = books
    original = record_transaction(
        database,
        context(entity_id),
        entry=balanced(cash, revenue),
        functional_currency="USD",
        post=True,
    )

    reversal = reverse_transaction(
        database,
        context(entity_id),
        transaction_id=original.transaction_id,
        functional_currency="USD",
        original_period_closed=False,
        current_period_date=TODAY,
    )

    assert reversal.status == "posted"
    with owner_conn.cursor() as cur:
        cur.execute(
            "SELECT reverses_id FROM ledger_transaction WHERE id = %s",
            (reversal.transaction_id,),
        )
        row = cur.fetchone()
        assert row is not None
        assert str(row[0]) == original.transaction_id

        cur.execute(
            "SELECT commodity, sum(amount) FROM posting"
            " WHERE entity_id = %s GROUP BY commodity",
            (entity_id,),
        )
        assert cur.fetchall() == [("USD", Decimal("0.0000000000"))]


def test_both_entries_remain_visible_after_a_correction(
    database: Database, owner_conn: psycopg.Connection[Any], books: tuple[str, str, str]
) -> None:
    """`LED-08`'s acceptance: "both the original entry and its reversal are retrievable, and
    no field of the original has changed"."""
    entity_id, cash, revenue = books
    original = record_transaction(
        database,
        context(entity_id),
        entry=balanced(cash, revenue),
        functional_currency="USD",
        post=True,
    )
    before = None
    with owner_conn.cursor() as cur:
        cur.execute(
            "SELECT to_jsonb(t) FROM ledger_transaction t WHERE id = %s",
            (original.transaction_id,),
        )
        row = cur.fetchone()
        assert row is not None
        before = row[0]

    reverse_transaction(
        database,
        context(entity_id),
        transaction_id=original.transaction_id,
        functional_currency="USD",
        original_period_closed=False,
        current_period_date=TODAY,
    )

    with owner_conn.cursor() as cur:
        cur.execute(
            "SELECT to_jsonb(t) FROM ledger_transaction t WHERE id = %s",
            (original.transaction_id,),
        )
        row = cur.fetchone()
        assert row is not None
        assert row[0] == before
    assert transaction_count(owner_conn, entity_id) == 2


# --- Serialisation (ADR-0011) -------------------------------------------------------------


def test_writes_to_one_entity_serialise(
    database: Database,
    owner_conn: psycopg.Connection[Any],
    owner_dsn: str,
    books: tuple[str, str, str],
) -> None:
    """ADR-0011: "Tests must prove serialisation by actually running concurrent writes, not by
    inspection."

    Holds the entity's advisory lock on one connection and starts a service write on another.
    The write must block — if it did not take the same lock it would sail through — and must
    complete once the lock is released.

    The lock key is `entity.lock_key`, an identity column, never a hash of `entity.id`: the
    advisory namespace is a global bigint, and a hash collision would not fail, it would
    silently serialise two unrelated entities against each other.
    """
    entity_id, cash, revenue = books
    finished = threading.Event()

    with owner_conn.cursor() as cur:
        cur.execute("SELECT lock_key FROM entity WHERE id = %s", (entity_id,))
        row = cur.fetchone()
        assert row is not None
        lock_key = row[0]

    blocker = psycopg.connect(owner_dsn, autocommit=False)
    try:
        with blocker.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(%s)", (lock_key,))

        def write() -> None:
            record_transaction(
                database,
                context(entity_id),
                entry=balanced(cash, revenue),
                functional_currency="USD",
                post=True,
            )
            finished.set()

        worker = threading.Thread(target=write, daemon=True)
        worker.start()

        assert not finished.wait(timeout=1.0), "the write did not take the entity lock"

        blocker.rollback()  # releases the transaction-scoped advisory lock

        assert finished.wait(timeout=10.0), "the write did not proceed once the lock was free"
        worker.join(timeout=5)
    finally:
        blocker.close()

    assert transaction_count(owner_conn, entity_id) == 1
