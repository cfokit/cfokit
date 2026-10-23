"""The runtime's configuration, from environment variables only (ADR-0004).

A component reads the three every component reads (ADR-0032, `infra/README.md`), the issuer the
API already names, and three of its own. Nothing here reads cloud metadata, and nothing names a
provider SDK at module scope.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

__all__ = ["DEFAULT_MODEL", "RuntimeSettings"]

# The model a deployment uses unless it names another. Pinned here and recorded with every
# response, so a change of model is a change to this value, visible in the history (`SOC1-35`).
DEFAULT_MODEL = "claude-opus-5-5"

# Where the image carries the skill (ADR-0075 § 2).
DEFAULT_SKILL = Path("/opt/cfokit/skills/cfokit/bookkeeper/SKILL.md")


class ConfigError(RuntimeError):
    """A required variable is missing. Raised at start, so the runtime fails at once rather than
    on its first turn (`infra/README.md`)."""

    code = "config_error"


@dataclass(frozen=True, slots=True)
class RuntimeSettings:
    api_url: str
    mcp_url: str
    issuer_url: str
    audience: str
    client_id: str
    client_secret: str
    model: str
    skill_path: Path
    # The inference credential. Absent, the runtime is off and says so, and nothing else changes
    # (ADR-0075 § 2).
    anthropic_api_key: str | None

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> RuntimeSettings:
        source = os.environ if env is None else env

        def required(name: str) -> str:
            value = source.get(name, "").strip()
            if not value:
                raise ConfigError(f"{name} is required")
            return value

        return cls(
            api_url=required("CFOKIT_API_URL").rstrip("/"),
            mcp_url=required("CFOKIT_MCP_URL"),
            issuer_url=required("AUTH_ISSUER_URL").rstrip("/"),
            audience=required("AUTH_AUDIENCE"),
            client_id=required("AUTH_CLIENT_ID"),
            client_secret=required("AUTH_CLIENT_SECRET"),
            model=source.get("CFOKIT_RUNTIME_MODEL", "").strip() or DEFAULT_MODEL,
            skill_path=Path(source.get("CFOKIT_RUNTIME_SKILL", "").strip() or DEFAULT_SKILL),
            anthropic_api_key=source.get("ANTHROPIC_API_KEY", "").strip() or None,
        )
