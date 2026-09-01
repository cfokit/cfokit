"""Queries answering whether this instance can serve correctly.

Lives in `repository` rather than in `service` because it touches the database, and after
ADR-0028's boundary is enforced that is the only place allowed to.
"""

from __future__ import annotations

import psycopg

from cfokit.ledger.migrations import Migration, pending
from cfokit.ledger.repository.connection import DatabaseUnavailable, connect

__all__ = ["pending_migrations"]


def pending_migrations(dsn: str) -> list[Migration]:
    """Migrations on disk this database has not applied.

    Raises `DatabaseUnavailable` if it cannot be reached. An empty list means current, which
    is not the same answer as unreachable and must not be conflated with it — a rollout that
    treated "cannot tell" as "ready" would serve traffic against an unknown schema.
    """
    try:
        with connect(dsn) as conn:
            return pending(conn)
    except psycopg.Error as exc:
        raise DatabaseUnavailable(exc.__class__.__name__) from exc
