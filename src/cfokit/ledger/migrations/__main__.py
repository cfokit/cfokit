"""``uv run task migrate`` — apply pending migrations.

Runs only when invoked. Never on container startup, never on import (ADR-0004).

Each migration is applied in its own transaction and recorded in ``schema_migration``
within that same transaction, so a failure leaves the database at a known version rather
than partway through one. A session-level advisory lock serializes concurrent runs.
"""

from __future__ import annotations

import json
import logging
import sys

import psycopg

from cfokit.ledger.config import require_env
from cfokit.ledger.errors import LedgerError, MigrationError
from cfokit.ledger.migrations import (
    MIGRATION_LOCK_KEY,
    discover,
    ensure_ledger,
    pending,
)

log = logging.getLogger("cfokit.ledger.migrations")


class _JsonFormatter(logging.Formatter):
    """Structured JSON logs (CLAUDE.md, Observability)."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        extra = getattr(record, "fields", None)
        if isinstance(extra, dict):
            payload.update(extra)
        return json.dumps(payload)


def _configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)


def main() -> int:
    _configure_logging()

    database_url = require_env("DATABASE_URL")
    on_disk = discover()

    with psycopg.connect(database_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_lock(%s)", (MIGRATION_LOCK_KEY,))

        # The owner creates the ledger table if this database has never been migrated.
        # `applied_versions` deliberately does not, because the application role reads it on
        # every readiness check and cannot run DDL — which is what made every readiness check
        # answer "database unreachable: InsufficientPrivilege".
        ensure_ledger(conn)
        todo = pending(conn)
        if not todo:
            log.info(
                "no migrations to apply",
                extra={"fields": {"on_disk": len(on_disk), "applied": 0}},
            )
            return 0

        for migration in todo:
            try:
                with conn.transaction(), conn.cursor() as cur:
                    cur.execute(migration.sql)
                    cur.execute(
                        "INSERT INTO schema_migration (version, name) VALUES (%s, %s)",
                        (migration.version, migration.name),
                    )
            except psycopg.Error as exc:
                raise MigrationError(
                    f"migration {migration.version} failed: {exc.__class__.__name__}"
                ) from exc

            log.info(
                "applied migration",
                extra={"fields": {"version": migration.version, "name": migration.name}},
            )

    log.info("migrations complete", extra={"fields": {"applied": len(todo)}})
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except LedgerError as exc:
        logging.getLogger(__name__).error(exc.message, extra={"fields": {"code": exc.code}})
        sys.exit(1)
