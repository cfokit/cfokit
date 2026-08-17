"""Configuration — environment variables only (ADR-0003).

No cloud metadata lookups. No provider SDK imports at module scope. Self-hosting is a
product promise, so the entire coupling between the application and its deployment is
the variables read here.

Adding a variable to this surface requires an ADR — ``infra/README.md`` is the
portability contract (ADR-0016).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from cfokit.ledger.errors import ConfigError


@dataclass(frozen=True, slots=True)
class Settings:
    """The complete configuration surface of the ledger service."""

    database_url: str
    """Postgres connection string. The only storage backend (ADR-0002)."""

    public_base_url: str
    """Authoritative for anything the service says about itself. Behind a proxy or
    tunnel, request headers lie — never derive external URLs from them (ADR-0003)."""

    auth_issuer_url: str
    """OAuth 2.1 issuer. The issuer is swappable; no issuer-specific code exists
    anywhere in the codebase (ADR-0019)."""

    auth_audience: str
    """Audience validation is mandatory on every request (ADR-0011, ADR-0019)."""

    port: int = 8080
    """Listen port. Optional; the platform usually supplies it."""

    log_level: str = "info"
    """Optional. Never raise this to a level that would log posting amounts, account
    numbers, or payee names (CLAUDE.md, Observability)."""


def require_env(name: str) -> str:
    """Read a required variable, or raise without disclosing its value."""
    value = os.environ.get(name)
    if not value:
        raise ConfigError(f"{name} is not set")
    return value


def optional_env(name: str, default: str) -> str:
    """Read an optional variable. This module is the only place the environment is read."""
    return os.environ.get(name) or default


def load_settings() -> Settings:
    """Load the full configuration surface, failing loudly on anything missing."""
    port_raw = optional_env("PORT", "8080")
    try:
        port = int(port_raw)
    except ValueError as exc:
        raise ConfigError("PORT is not an integer") from exc

    return Settings(
        database_url=require_env("DATABASE_URL"),
        public_base_url=require_env("PUBLIC_BASE_URL"),
        auth_issuer_url=require_env("AUTH_ISSUER_URL"),
        auth_audience=require_env("AUTH_AUDIENCE"),
        port=port,
        log_level=optional_env("LOG_LEVEL", "info"),
    )
