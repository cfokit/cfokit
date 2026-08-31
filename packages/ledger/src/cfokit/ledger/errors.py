"""Errors carry a stable, machine-readable ``code``. Callers depend on it (ADR-0015).

Adding a code is a contract change. Renaming one is a breaking change.
"""

from __future__ import annotations


class LedgerError(Exception):
    """Base for every error the ledger raises across a published interface."""

    code: str = "internal_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ConfigError(LedgerError):
    """Configuration is missing or unusable. Never carries the offending value."""

    code = "config_invalid"


class MigrationError(LedgerError):
    """A migration could not be applied."""

    code = "migration_failed"
