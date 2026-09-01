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
        cur.execute("DELETE FROM account WHERE entity_id IN (%s, %s)", (first, second))
        cur.execute("DELETE FROM entity WHERE id IN (%s, %s)", (first, second))
