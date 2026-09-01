"""Entity isolation is two layers, and this proves the database one is live.

ADR-0003 requires "row-level security keyed on `entity_id`, **plus** explicit service-layer
filtering. Two layers, because RLS misconfiguration is silent." Silent is the operative word:
the policies shipped in migration 0001 from the first commit, and were inert the whole time,
because the application connected as a superuser. Nothing failed. Nothing could fail — a
missing policy and a bypassed one look identical from the application's side.

So these tests assert the property from the outside, as the application role, against a real
database. They are the reason the `test` compose profile exists.
"""

from __future__ import annotations

from typing import Any

import psycopg
import pytest

pytestmark = pytest.mark.integration


def scoped(conn: psycopg.Connection[Any], entity_id: str) -> None:
    """Scope the session the way the application will: one entity, per transaction."""
    with conn.cursor() as cur:
        cur.execute("SELECT set_config('cfokit.entity_id', %s, false)", (entity_id,))


def count_accounts(conn: psycopg.Connection[Any]) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM account")
        row = cur.fetchone()
        assert row is not None
        return int(row[0])


def test_the_application_role_is_not_a_superuser(app_conn: psycopg.Connection[Any]) -> None:
    """A superuser bypasses row-level security entirely, whatever the policies say.

    This is the assertion that would have caught the original defect on day one.
    """
    with app_conn.cursor() as cur:
        cur.execute("SELECT usesuper FROM pg_user WHERE usename = current_user")
        row = cur.fetchone()
        assert row is not None
        assert row[0] is False, "the application must not connect as a superuser"


def test_the_application_role_does_not_own_the_tables(
    app_conn: psycopg.Connection[Any],
) -> None:
    """An owner also bypasses RLS, unless the table is FORCE'd. Ours are not.

    Compares the owner against `current_user` rather than against a hardcoded role name. The
    first version asserted `!= "cfokit_app"`, which is trivially true whenever the connection
    is anyone else — including the superuser this test exists to reject.
    """
    with app_conn.cursor() as cur:
        cur.execute(
            "SELECT tableowner = current_user FROM pg_tables"
            " WHERE schemaname = 'public' AND tablename = %s",
            ("account",),
        )
        row = cur.fetchone()
        assert row is not None
        assert row[0] is False, "the application must not own the tables it writes"


def test_nothing_is_visible_without_an_entity_scope(
    app_conn: psycopg.Connection[Any], two_entities: tuple[str, str]
) -> None:
    """An unscoped session sees no rows at all, rather than every row.

    This is the direction that matters: a forgotten scope must fail closed. Failing open
    would make a missing `SET` a cross-entity data leak rather than an empty result.
    """
    assert count_accounts(app_conn) == 0


def test_scoping_to_an_entity_shows_only_that_entity(
    app_conn: psycopg.Connection[Any], two_entities: tuple[str, str]
) -> None:
    first, second = two_entities

    scoped(app_conn, first)
    assert count_accounts(app_conn) == 1

    scoped(app_conn, second)
    assert count_accounts(app_conn) == 1


def test_a_write_for_another_entity_is_refused(
    app_conn: psycopg.Connection[Any], two_entities: tuple[str, str]
) -> None:
    """`NFR-04` allows zero cross-entity writes, not merely zero cross-entity reads.

    The policies carry no explicit `WITH CHECK`, so Postgres uses `USING` for both. That is
    the behaviour relied on here, asserted rather than assumed.
    """
    first, second = two_entities
    scoped(app_conn, first)

    with pytest.raises(psycopg.errors.InsufficientPrivilege), app_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO account (entity_id, code, name, type)"
            " VALUES (%s, '9999', 'Smuggled', 'asset')",
            (second,),
        )


def test_the_application_role_cannot_delete_a_transaction(
    app_conn: psycopg.Connection[Any], two_entities: tuple[str, str]
) -> None:
    """ADR-0007 says a posted transaction is never removed. The trigger refuses it; the role
    does not hold the privilege either, so a defect in one is not the only thing standing
    between a bug and a deleted ledger."""
    first, _ = two_entities
    scoped(app_conn, first)

    with pytest.raises(psycopg.errors.InsufficientPrivilege), app_conn.cursor() as cur:
        cur.execute("DELETE FROM ledger_transaction WHERE entity_id = %s", (first,))


def test_the_application_role_cannot_rewrite_the_audit_log(
    app_conn: psycopg.Connection[Any], two_entities: tuple[str, str]
) -> None:
    """Insert-only, or it is not a trail."""
    first, _ = two_entities
    scoped(app_conn, first)

    with pytest.raises(psycopg.errors.InsufficientPrivilege), app_conn.cursor() as cur:
        cur.execute(
            "UPDATE audit_log SET actor = 'someone else' WHERE entity_id = %s", (first,)
        )


def test_the_application_role_cannot_apply_migrations(
    app_conn: psycopg.Connection[Any],
) -> None:
    """Applying a migration is the migrate job's business, and it runs as the owner."""
    with pytest.raises(psycopg.errors.InsufficientPrivilege), app_conn.cursor() as cur:
        cur.execute("INSERT INTO schema_migration (version, name) VALUES ('9999', 'forged')")
