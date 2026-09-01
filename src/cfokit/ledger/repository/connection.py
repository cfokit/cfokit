"""Opening connections, and the one place the driver is named.

ADR-0028 confines SQL to this package by confining the driver to it. Everything above —
`service`, `api`, `mcp` — reaches the database through functions here and never imports
`psycopg`, which `import-linter` now enforces rather than merely asserting.

Nothing in this module logs a connection string. A DSN carries credentials, so failures are
reported by the driver's exception class name and nothing else.
"""

from __future__ import annotations

from typing import Any

import psycopg

__all__ = ["DatabaseUnavailable", "connect"]

# Long enough to cross a cold network path, short enough that a readiness probe answers
# rather than hanging and being killed.
CONNECT_TIMEOUT_SECONDS = 5


class DatabaseUnavailable(Exception):
    """The database could not be reached.

    Carries `reason`, which is the driver's exception class name — never the DSN, and never
    the driver's message, which can quote the host and user it failed to connect as.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def connect(dsn: str) -> psycopg.Connection[Any]:
    """Open a connection, or raise `DatabaseUnavailable` with nothing sensitive attached."""
    try:
        return psycopg.connect(dsn, connect_timeout=CONNECT_TIMEOUT_SECONDS)
    except psycopg.Error as exc:
        raise DatabaseUnavailable(exc.__class__.__name__) from exc
