"""Grants, enforced server-side on every write (ADR-0011, `IAM-01`).

Until this existed, an authenticated caller could write to any entity. These are the tests
that say otherwise, and they run against a real database because the check is a query inside
the locked transaction — which is also what makes `IAM-15` true, since a revocation committed
a moment earlier is already in force.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import psycopg
import pytest

from cfokit.ledger.engine import Entry, Posting
from cfokit.ledger.errors import NotAuthorised
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.principal import ActorClass, Principal
from cfokit.ledger.service.read import read_transaction
from cfokit.ledger.service.write import WriteContext, record_transaction

pytestmark = pytest.mark.integration

TODAY = datetime.now(UTC).date()
STRANGER = Principal(id="user:stranger", actor_class=ActorClass.PERSON)


def grant(
    conn: psycopg.Connection[Any],
    entity_id: str,
    principal_id: str,
    role: str,
    *,
    lapses_at: datetime | None = None,
) -> str:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO entity_grant (entity_id, principal_id, role, granted_by, lapses_at)"
            " VALUES (%s, %s, %s, 'test', %s) RETURNING id",
            (entity_id, principal_id, role, lapses_at),
        )
        row = cur.fetchone()
    assert row is not None
    return str(row[0])


def context(entity_id: str, principal: Principal) -> WriteContext:
    return WriteContext(
        entity_id=entity_id,
        principal=principal,
        request_id=f"req-{uuid.uuid4().hex[:8]}",
        idempotency_key=uuid.uuid4().hex,
    )


def entry(cash: str, revenue: str) -> Entry:
    return Entry(
        transaction_date=TODAY,
        postings=(
            Posting(account_id=cash, amount=Decimal("100.00"), commodity="USD"),
            Posting(account_id=revenue, amount=Decimal("-100.00"), commodity="USD"),
        ),
    )


def test_a_principal_with_no_grant_cannot_write(
    database: Database, books: tuple[str, str, str]
) -> None:
    """`IAM-01`: "an identity holding no role for an entity can do nothing with it"."""
    entity_id, cash, revenue = books

    with pytest.raises(NotAuthorised) as caught:
        record_transaction(
            database, context(entity_id, STRANGER), entry=entry(cash, revenue), post=True
        )

    assert caught.value.code == "not_authorised"


def test_a_principal_with_no_grant_cannot_read(
    database: Database, books: tuple[str, str, str]
) -> None:
    entity_id, _, _ = books

    with pytest.raises(NotAuthorised):
        read_transaction(
            database,
            entity_id=entity_id,
            principal=STRANGER,
            transaction_id=str(uuid.uuid4()),
        )


def test_a_reader_cannot_record(
    database: Database, owner_conn: psycopg.Connection[Any], books: tuple[str, str, str]
) -> None:
    entity_id, cash, revenue = books
    reader = Principal(id="user:reader", actor_class=ActorClass.PERSON)
    grant(owner_conn, entity_id, reader.id, "reader")

    with pytest.raises(NotAuthorised, match="record"):
        record_transaction(
            database, context(entity_id, reader), entry=entry(cash, revenue), post=False
        )


def test_a_recorder_can_draft_but_not_post(
    database: Database, owner_conn: psycopg.Connection[Any], books: tuple[str, str, str]
) -> None:
    """`IAM-16` needs these separable: the person who drafts is not the person who posts."""
    entity_id, cash, revenue = books
    recorder = Principal(id="user:recorder", actor_class=ActorClass.PERSON)
    grant(owner_conn, entity_id, recorder.id, "recorder")

    drafted = record_transaction(
        database, context(entity_id, recorder), entry=entry(cash, revenue), post=False
    )
    assert drafted.status == "draft"

    with pytest.raises(NotAuthorised, match="post"):
        record_transaction(
            database, context(entity_id, recorder), entry=entry(cash, revenue), post=True
        )


def test_an_agents_authority_is_the_intersection(
    database: Database, owner_conn: psycopg.Connection[Any], books: tuple[str, str, str]
) -> None:
    """`IAM-11`, against a real grant table rather than in the abstract.

    The skill may post; the person it acts for may only read. The intersection is read, so the
    write is refused — the skill's own grant is not a way around the person's.
    """
    entity_id, cash, revenue = books
    grant(owner_conn, entity_id, "skill:limited", "poster")
    grant(owner_conn, entity_id, "user:onlyreads", "reader")
    agent = Principal(
        id="skill:limited", actor_class=ActorClass.AGENT, acting_for="user:onlyreads"
    )

    with pytest.raises(NotAuthorised):
        record_transaction(
            database, context(entity_id, agent), entry=entry(cash, revenue), post=False
        )


def test_revocation_takes_effect_immediately(
    database: Database, owner_conn: psycopg.Connection[Any], books: tuple[str, str, str]
) -> None:
    """`IAM-15`: "Revoking or reducing an identity's access takes effect immediately".

    No cache to invalidate, because the check is a query inside the transaction that does the
    work rather than something resolved at the edge.
    """
    entity_id, cash, revenue = books
    principal = Principal(id="user:temp", actor_class=ActorClass.PERSON)
    grant_id = grant(owner_conn, entity_id, principal.id, "poster")

    record_transaction(
        database, context(entity_id, principal), entry=entry(cash, revenue), post=True
    )

    with owner_conn.cursor() as cur:
        cur.execute(
            "UPDATE entity_grant SET revoked_at = now(), revoked_by = 'test' WHERE id = %s",
            (grant_id,),
        )

    with pytest.raises(NotAuthorised):
        record_transaction(
            database, context(entity_id, principal), entry=entry(cash, revenue), post=True
        )


def test_a_grant_lapses_without_anyone_acting(
    database: Database, owner_conn: psycopg.Connection[Any], books: tuple[str, str, str]
) -> None:
    """`IAM-09`: "A role can be granted for a stated period, after which it lapses without
    anyone acting. An advisor's access ending with the engagement does not depend on someone
    remembering." So lapsing is a stored boundary, not a job that has to run."""
    entity_id, cash, revenue = books
    advisor = Principal(id="user:advisor", actor_class=ActorClass.PERSON)
    grant(
        owner_conn,
        entity_id,
        advisor.id,
        "poster",
        lapses_at=datetime.now(UTC) - timedelta(seconds=1),
    )

    with pytest.raises(NotAuthorised):
        record_transaction(
            database, context(entity_id, advisor), entry=entry(cash, revenue), post=True
        )


def test_a_grant_that_has_not_lapsed_still_works(
    database: Database, owner_conn: psycopg.Connection[Any], books: tuple[str, str, str]
) -> None:
    """The positive control: without it, a bug making every grant appear lapsed would pass."""
    entity_id, cash, revenue = books
    advisor = Principal(id="user:future", actor_class=ActorClass.PERSON)
    grant(
        owner_conn,
        entity_id,
        advisor.id,
        "poster",
        lapses_at=datetime.now(UTC) + timedelta(days=30),
    )

    written = record_transaction(
        database, context(entity_id, advisor), entry=entry(cash, revenue), post=True
    )

    assert written.status == "posted"


def test_grants_are_isolated_between_entities(
    database: Database,
    owner_conn: psycopg.Connection[Any],
    books: tuple[str, str, str],
    two_entities: tuple[str, str],
) -> None:
    """`IAM-08`: one identity holds independent roles in each entity, and none in the rest."""
    _, cash, revenue = books
    other, _ = two_entities

    with pytest.raises(NotAuthorised):
        record_transaction(
            database,
            context(other, Principal(id="user:geoff", actor_class=ActorClass.PERSON)),
            entry=entry(cash, revenue),
            post=True,
        )


# --- The grant record itself (IAM-13, IAM-14) ---------------------------------------------


def test_a_grant_is_never_deleted(
    owner_conn: psycopg.Connection[Any], books: tuple[str, str, str]
) -> None:
    """`IAM-14` needs "for any date in the past, who held which role", and a deleted grant
    takes its history with it."""
    entity_id, _, _ = books
    grant_id = grant(owner_conn, entity_id, "user:doomed", "reader")

    with pytest.raises(psycopg.Error, match="append_only_violated"), owner_conn.cursor() as cur:
        cur.execute("DELETE FROM entity_grant WHERE id = %s", (grant_id,))


def test_only_revocation_may_change_a_grant(
    owner_conn: psycopg.Connection[Any], books: tuple[str, str, str]
) -> None:
    """Escalating a role in place would rewrite what was held in the past."""
    entity_id, _, _ = books
    grant_id = grant(owner_conn, entity_id, "user:climber", "reader")

    with pytest.raises(psycopg.Error, match="append_only_violated"), owner_conn.cursor() as cur:
        cur.execute("UPDATE entity_grant SET role = 'administrator' WHERE id = %s", (grant_id,))


def test_a_grant_cannot_be_revoked_twice(
    owner_conn: psycopg.Connection[Any], books: tuple[str, str, str]
) -> None:
    """Re-revoking would move the moment access ended, which `IAM-14` has to be able to
    report."""
    entity_id, _, _ = books
    grant_id = grant(owner_conn, entity_id, "user:twice", "reader")

    with owner_conn.cursor() as cur:
        cur.execute(
            "UPDATE entity_grant SET revoked_at = now(), revoked_by = 'a' WHERE id = %s",
            (grant_id,),
        )

    with pytest.raises(psycopg.Error, match="already revoked"), owner_conn.cursor() as cur:
        cur.execute(
            "UPDATE entity_grant SET revoked_at = now(), revoked_by = 'b' WHERE id = %s",
            (grant_id,),
        )
