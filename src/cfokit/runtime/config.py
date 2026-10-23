"""The runtime's configuration, from environment variables only (ADR-0004).

A component reads the three every component reads (ADR-0032, `infra/README.md`), the issuer the
API already names, and its own. Nothing here reads cloud metadata, and nothing names a provider
SDK at module scope.

No audience: the exchanged token's audience is the one the issuer binds every token in the
realm to, so the runtime asks for none (RFC 8693 § 2.1 makes it optional) and the API validates
what comes back as it validates any token.
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
    client_id: str
    client_secret: str
    model: str
    skill_path: Path
    # The inference credential. Absent, the runtime is off and says so, and nothing else changes
    # (ADR-0075 § 2).
    anthropic_api_key: str | None
    # The web client's origin, the one browser origin allowed to call the runtime (CORS). The
    # runtime has its own address, as the MCP service does, so the chat window's request is
    # cross-origin on a stack with no load balancer in front (ADR-0075 § 1).
    web_origin: str
    port: int
    # HTTPS from these, as the other services serve it; both or neither.
    tls_cert_file: str | None
    tls_key_file: str | None

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> RuntimeSettings:
        source = os.environ if env is None else env

        def required(name: str) -> str:
            value = source.get(name, "").strip()
            if not value:
                raise ConfigError(f"{name} is required")
            return value

        tls_cert_file = source.get("TLS_CERT_FILE", "").strip() or None
        tls_key_file = source.get("TLS_KEY_FILE", "").strip() or None
        if (tls_cert_file is None) != (tls_key_file is None):
            raise ConfigError("TLS_CERT_FILE and TLS_KEY_FILE are set together, or not at all")

        return cls(
            api_url=required("CFOKIT_API_URL").rstrip("/"),
            mcp_url=required("CFOKIT_MCP_URL"),
            issuer_url=required("AUTH_ISSUER_URL").rstrip("/"),
            client_id=required("AUTH_CLIENT_ID"),
            client_secret=required("AUTH_CLIENT_SECRET"),
            model=source.get("CFOKIT_RUNTIME_MODEL", "").strip() or DEFAULT_MODEL,
            skill_path=Path(source.get("CFOKIT_RUNTIME_SKILL", "").strip() or DEFAULT_SKILL),
            anthropic_api_key=source.get("ANTHROPIC_API_KEY", "").strip() or None,
            web_origin=required("WEB_PUBLIC_BASE_URL").rstrip("/"),
            port=int(source.get("PORT", "").strip() or "8082"),
            tls_cert_file=tls_cert_file,
            tls_key_file=tls_key_file,
        )
