"""``python -m cfokit.ledger.mcp`` — run the MCP service.

One of the entrypoints this image provides (ADR-0023). Migrations are never applied here;
they are a separate, explicitly invoked job (ADR-0004).

**Streamable HTTP, stateless, JSON responses.** ADR-0017 chose the cloud target partly on
streamable HTTP being reachable by standard MCP clients with no custom transport, and ADR-0012
makes stateful connections against a scale-to-zero container a binding non-goal — so sessions
are not held between requests, and `json_response` keeps replies plain JSON rather than an SSE
stream. Every request carries its own bearer token, which is what makes statelessness free
here: there is no session to attach an identity to.
"""

from __future__ import annotations

import json
import logging
import sys

from cfokit.ledger.config import load_settings
from cfokit.ledger.errors import LedgerError
from cfokit.ledger.mcp import create_server


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


def main() -> int:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)

    settings = load_settings()
    logging.getLogger("cfokit.ledger.mcp").info(
        "starting MCP service",
        extra={"fields": {"port": settings.port, "path": "/mcp"}},
    )

    # Binding all interfaces is correct inside a container; the platform controls ingress.
    create_server(settings).run(
        "streamable-http",
        host="0.0.0.0",  # noqa: S104
        port=settings.port,
        stateless_http=True,
        json_response=True,
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except LedgerError as exc:
        logging.getLogger(__name__).error(exc.message, extra={"fields": {"code": exc.code}})
        sys.exit(1)
