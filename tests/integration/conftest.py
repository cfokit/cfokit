"""Fixtures for tests that need a real database.

These run inside the compose network, where Postgres is reachable by service name —
`compose.yaml` deliberately publishes no database port, and CI gate 2 runs it without the dev
overlay (ADR-0018). On a developer's host without the stack up, they skip.

Two connections, because the difference between them is the thing under test:

- `app_conn` connects as `cfokit_app`, a non-superuser that does not own the tables, so the
  row-level security policies from migration 0001 apply to it exactly as they do in
  production.
- `owner_conn` connects as the schema owner, which bypasses RLS. Fixtures use it to arrange
  rows across entities — something the application deliberately cannot do.

**Both are autocommit, and that is load-bearing rather than convenient.** A test that expects
a write to be refused, run against a database where it is *not* refused, leaves an open
transaction holding a row lock; the cleanup below then blocks on it and the suite hangs
instead of failing. That is exactly what happened the first time these were run against a
superuser connection. Autocommit means no statement holds a lock past its own execution, so a
wrong result fails the assertion rather than wedging the run.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from typing import Any

import psycopg
import pytest

from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.administration import create_account, create_entity
from cfokit.ledger.service.principal import ActorClass, Principal

APP_URL = os.environ.get("DATABASE_URL", "")
OWNER_URL = os.environ.get("DATABASE_OWNER_URL", "")

# A second safety net for the failure above. If anything ever does hold a conflicting lock,
# cleanup raises within seconds and names the problem instead of hanging until CI times out.
LOCK_TIMEOUT = "5s"


@pytest.fixture(autouse=True)
def _requires_database() -> None:
    """Skip everything in this directory unless a database is configured.

    Autouse rather than an importable marker, because `tests` is not a package and making it
    one to share a constant would be a lot of ceremony for a skip.
    """
    if not (APP_URL and OWNER_URL):
        pytest.skip("needs the compose stack: docker compose --profile test run --rm test")


def _connect(dsn: str) -> psycopg.Connection[Any]:
    conn = psycopg.connect(dsn, connect_timeout=5, autocommit=True)
    with conn.cursor() as cur:
        cur.execute(f"SET lock_timeout = '{LOCK_TIMEOUT}'")
    return conn


# What a deployment adds when it has somebody to hold it (ADR-0039). Only `owner` ships, so
# these are defined the way a real deployment would define them — by inserting catalogue rows —
# which is also the only test that the mechanism works. Session-scoped and never removed:
# `entity_grant.role` references `role.name`, so a role a test has granted cannot be deleted.
DELEGATED_ROLES: dict[str, frozenset[str]] = {
    "reader": frozenset({"read"}),
    "recorder": frozenset({"read", "record"}),
    "poster": frozenset({"read", "record", "post"}),
    "administrator": frozenset({"grant"}),
    # Every class of work and none of the reservation — the component ADR-0042 is about, and the
    # shape the old `actor_class` check let through.
    "month-end": frozenset({"read", "record", "post", "close"}),
    "everything-else": frozenset({"read", "record", "post", "grant", "close", "own"}),
    # A component an operator has deliberately trusted with a person's act.
    "importer": frozenset({"read", "record", "post", "grant", "act_as_principal"}),
}


@pytest.fixture(scope="session", autouse=True)
def delegated_roles() -> dict[str, frozenset[str]]:
    """Define the delegated roles this suite exercises, once for the run.

    Returned as well as seeded, because `tests` is not a package and a test that needs the
    names has no import path to them.
    """
    if not OWNER_URL:
        return DELEGATED_ROLES
    with _connect(OWNER_URL) as conn, conn.cursor() as cur:
        for name, privileges in DELEGATED_ROLES.items():
            cur.execute(
                "INSERT INTO role (name, description) VALUES (%s, %s)"
                " ON CONFLICT (name) DO NOTHING",
                (name, f"Defined by the integration suite: {', '.join(sorted(privileges))}."),
            )
            for privilege in sorted(privileges):
                cur.execute(
                    "INSERT INTO role_privilege (role_name, privilege) VALUES (%s, %s)"
                    " ON CONFLICT DO NOTHING",
                    (name, privilege),
                )
    return DELEGATED_ROLES


@pytest.fixture
def owner_conn() -> Iterator[psycopg.Connection[Any]]:
    """A connection as the schema owner. Bypasses RLS; use only to arrange fixtures."""
    with _connect(OWNER_URL) as conn:
        yield conn


@pytest.fixture
def app_conn() -> Iterator[psycopg.Connection[Any]]:
    """A connection as the application role, subject to row-level security."""
    with _connect(APP_URL) as conn:
        yield conn


@pytest.fixture
def owner_dsn() -> str:
    """The owner connection string, for a test that must open its own connection.

    `Connection.info.dsn` deliberately omits the password, so it cannot be used to reconnect.
    """
    return OWNER_URL


@pytest.fixture
def app_dsn() -> str:
    """The application role's connection string, as the service layer is configured with."""
    return APP_URL


@pytest.fixture
def database() -> Database:
    """The database as the service layer sees it, connecting as the application role."""
    return Database(APP_URL)


@pytest.fixture
def owned_books(database: Database) -> tuple[str, str, str]:
    """One entity with two accounts, created the way a customer creates them.

    Everything here goes through the service layer: `create_entity` makes the caller the
    entity's owner (`IAM-05`), and `create_account` builds the chart (`LED-01`). Distinct from
    `books`, which arranges the same shape with owner-role SQL so schema invariants can be
    tested independently of the privilege layer.

    Use this wherever the test is about a capability, because the fixture holding `owner` is
    what makes the privilege checks reachable at all.
    """
    suffix = uuid.uuid4().hex[:12]
    person = Principal(id="user:geoff", actor_class=ActorClass.PERSON)
    entity_id = create_entity(
        database,
        principal=person,
        request_id="fixture",
        slug=f"owned-{suffix}",
        name="Books",
        accounting_basis="accrual",
        fiscal_year_end_month=12,
        fiscal_year_end_day=31,
        functional_currency="USD",
        time_zone="UTC",
    ).entity_id

    accounts = [
        create_account(
            database,
            entity_id=entity_id,
            principal=person,
            request_id="fixture",
            code=code,
            name=name,
            account_type=account_type,
        )
        for code, name, account_type in (
            ("1000", "Cash", "asset"),
            ("4000", "Revenue", "income"),
        )
    ]
    return entity_id, accounts[0], accounts[1]


@pytest.fixture
def books(owner_conn: psycopg.Connection[Any]) -> Iterator[tuple[str, str, str]]:
    """One entity with two accounts. Returns (entity_id, cash_id, revenue_id).

    Arranged with the owner connection so the schema invariants can be tested independently
    of the privilege layer: as the application role a refused DELETE raises
    InsufficientPrivilege before any trigger runs, which would test the grant rather than the
    trigger it is meant to back up.
    """
    suffix = uuid.uuid4().hex[:12]
    with owner_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO entity
                (slug, name, accounting_basis, fiscal_year_end_month, fiscal_year_end_day,
                 functional_currency, time_zone)
            VALUES (%s, 'Books', 'accrual', 12, 31, 'USD', 'UTC')
            RETURNING id
            """,
            (f"books-{suffix}",),
        )
        row = cur.fetchone()
        assert row is not None
        entity_id = row[0]

        account_ids = []
        for code, name, account_type in (
            ("1000", "Cash", "asset"),
            ("4000", "Revenue", "income"),
        ):
            cur.execute(
                "INSERT INTO account (entity_id, code, name, type)"
                " VALUES (%s, %s, %s, %s) RETURNING id",
                (entity_id, code, name, account_type),
            )
            account_row = cur.fetchone()
            assert account_row is not None
            account_ids.append(account_row[0])

        # Writes are authorised now (`IAM-01`), so the fixture grants what the tests use.
        # `poster` rather than `administrator`: a test should hold the least that lets it
        # work, or it stops being able to notice a capability check that is missing.
        for principal_id in ("user:geoff", "skill:bookkeeper"):
            cur.execute(
                "INSERT INTO entity_grant (entity_id, principal_id, role, granted_by)"
                " VALUES (%s, %s, 'poster', 'test-fixture')",
                (entity_id, principal_id),
            )

    yield str(entity_id), str(account_ids[0]), str(account_ids[1])

    # The append-only triggers refuse to delete a transaction or a posted transaction's
    # postings — which is the guarantee under test, working. An append-only ledger cannot
    # have its rows removed, so cleaning up after a test that proves that requires the one
    # hatch Postgres provides.
    #
    # `session_replication_role = replica` suppresses user triggers for this session only.
    # It needs superuser, which is exactly why the application role can never do this: the
    # application connects as `cfokit_app`, which is NOSUPERUSER, so this escape is
    # unavailable to it by construction rather than by policy.
    #
    # This is the only place in the repository that bypasses an append-only trigger, and it
    # runs against a disposable test database.
    with owner_conn.cursor() as cur:
        cur.execute("SET session_replication_role = replica")
        cur.execute("DELETE FROM entity_grant WHERE entity_id = %s", (entity_id,))
        cur.execute("DELETE FROM posting WHERE entity_id = %s", (entity_id,))
        cur.execute("DELETE FROM ledger_transaction WHERE entity_id = %s", (entity_id,))
        cur.execute("DELETE FROM audit_log WHERE entity_id = %s", (entity_id,))
        cur.execute("DELETE FROM account WHERE entity_id = %s", (entity_id,))
        cur.execute("DELETE FROM entity WHERE id = %s", (entity_id,))
        cur.execute("SET session_replication_role = origin")


@pytest.fixture
def two_entities(owner_conn: psycopg.Connection[Any]) -> Iterator[tuple[str, str]]:
    """Two entities with one account each, created outside RLS. Returns their ids.

    Removed afterwards, so the suite leaves nothing behind and can be re-run against the same
    database. Slugs carry a random suffix because slug is unique per deployment and a rerun
    must not collide with a row a crashed run failed to clean up — the process id, which this
    first used, is not unique across container runs, where pytest is always the same pid.
    """
    suffix = uuid.uuid4().hex[:12]
    with owner_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO entity
                (slug, name, accounting_basis, fiscal_year_end_month, fiscal_year_end_day,
                 functional_currency, time_zone)
            VALUES (%s, 'First',  'accrual', 12, 31, 'USD', 'UTC'),
                   (%s, 'Second', 'cash',    12, 31, 'USD', 'UTC')
            RETURNING id
            """,
            (f"first-{suffix}", f"second-{suffix}"),
        )
        first, second = (row[0] for row in cur.fetchall())

        for entity_id in (first, second):
            cur.execute(
                "INSERT INTO account (entity_id, code, name, type)"
                " VALUES (%s, '1000', 'Cash', 'asset')",
                (entity_id,),
            )

    yield str(first), str(second)

    with owner_conn.cursor() as cur:
        cur.execute("SET session_replication_role = replica")
        cur.execute("DELETE FROM entity_grant WHERE entity_id IN (%s, %s)", (first, second))
        cur.execute("DELETE FROM account WHERE entity_id IN (%s, %s)", (first, second))
        cur.execute("DELETE FROM entity WHERE id IN (%s, %s)", (first, second))
        cur.execute("SET session_replication_role = origin")
