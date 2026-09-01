"""Readiness: is this instance able to serve correctly?

Lives in the service layer rather than the adapter so the REST and MCP surfaces answer
the same question the same way, and so no adapter reaches past `service` into the
database (ADR-0008).

`/healthz` deliberately does not call any of this. Liveness must not depend on the
database, or a database blip restarts healthy containers.
"""

from __future__ import annotations

from dataclasses import dataclass

from cfokit.ledger.repository.connection import DatabaseUnavailable
from cfokit.ledger.repository.health import pending_migrations


@dataclass(frozen=True, slots=True)
class Readiness:
    """Why an instance is or is not ready. Reported, not just tallied."""

    database_reachable: bool
    migrations_current: bool
    pending_migrations: int
    detail: str

    @property
    def ready(self) -> bool:
        return self.database_reachable and self.migrations_current


def check_readiness(database_url: str) -> Readiness:
    """Check database reachability and that migrations are current.

    Migrations are checked because an instance running against a schema older than its
    code is not ready — it is wrong, and it would fail on the first request that used a
    column the migration adds. Reporting it as unready is what stops a rollout from
    proceeding past a missed migration (ADR-0004).
    """
    try:
        outstanding = pending_migrations(database_url)
    except DatabaseUnavailable as exc:
        return Readiness(
            database_reachable=False,
            migrations_current=False,
            pending_migrations=-1,
            # The driver's exception class, never the connection string: it carries
            # credentials, and the repository has already stripped everything else.
            detail=f"database unreachable: {exc.reason}",
        )

    if outstanding:
        return Readiness(
            database_reachable=True,
            migrations_current=False,
            pending_migrations=len(outstanding),
            detail=f"{len(outstanding)} migration(s) pending; run the migrate job",
        )

    return Readiness(
        database_reachable=True,
        migrations_current=True,
        pending_migrations=0,
        detail="ready",
    )
