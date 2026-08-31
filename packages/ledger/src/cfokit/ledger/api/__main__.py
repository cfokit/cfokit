"""``python -m cfokit.ledger.api`` — run the REST service.

One of the entrypoints this image provides (ADR-0023). Migrations are never applied here;
they are a separate, explicitly invoked job (ADR-0004).
"""

from __future__ import annotations

import json
import logging
import sys

import uvicorn

from cfokit.ledger.api import create_app
from cfokit.ledger.config import load_settings
from cfokit.ledger.errors import LedgerError


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
    logging.getLogger("cfokit.ledger.api").info(
        "starting REST service",
        extra={"fields": {"port": settings.port}},
    )

    # Binding all interfaces is correct inside a container; the platform controls ingress.
    uvicorn.run(
        create_app(settings),
        host="0.0.0.0",  # noqa: S104
        port=settings.port,
        log_level=settings.log_level,
        access_log=False,
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except LedgerError as exc:
        logging.getLogger(__name__).error(exc.message, extra={"fields": {"code": exc.code}})
        sys.exit(1)
