"""Schema migrations, applied by an explicit command and never at startup (ADR-0003).

Migrations ship inside the package so the same files are available in the container, on
a laptop, and in CI. They are plain SQL, in keeping with the no-ORM decision (ADR-0008).

Naming: ``NNNN-short-description.sql``, applied in lexical order, never renumbered.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

SQL_DIR = Path(__file__).parent / "sql"


@dataclass(frozen=True, slots=True)
class Migration:
    """One migration file, identified by its numeric prefix."""

    version: str
    name: str
    path: Path

    @property
    def sql(self) -> str:
        return self.path.read_text(encoding="utf-8")


def discover(sql_dir: Path | None = None) -> list[Migration]:
    """Return every migration on disk, in the order it must be applied."""
    directory = SQL_DIR if sql_dir is None else sql_dir
    if not directory.is_dir():
        return []

    migrations: list[Migration] = []
    for path in sorted(directory.glob("*.sql")):
        version, _, name = path.stem.partition("-")
        migrations.append(Migration(version=version, name=name or path.stem, path=path))
    return migrations


# Created by the runner before anything else, so a fresh database can bootstrap itself.
# Migration 0001 also declares it with IF NOT EXISTS, which keeps the schema
# self-describing without the two definitions being able to disagree.
SCHEMA_MIGRATION_DDL = """
CREATE TABLE IF NOT EXISTS schema_migration (
    version     text        PRIMARY KEY,
    name        text        NOT NULL,
    applied_at  timestamptz NOT NULL DEFAULT now()
)
"""

# Serialises concurrent migration runs. Two instances starting at once is exactly the
# race that made migrations-at-startup unacceptable (ADR-0003); the explicit command
# does not get to have the same bug.
MIGRATION_LOCK_KEY = 8_474_021_100_001


def applied_versions(conn: object) -> set[str]:
    """Versions already recorded as applied."""
    with conn.cursor() as cur:  # type: ignore[attr-defined]
        cur.execute(SCHEMA_MIGRATION_DDL)
        cur.execute("SELECT version FROM schema_migration")
        return {row[0] for row in cur.fetchall()}


def pending(conn: object, sql_dir: Path | None = None) -> list[Migration]:
    """Migrations on disk that this database has not applied, in order."""
    done = applied_versions(conn)
    return [m for m in discover(sql_dir) if m.version not in done]
