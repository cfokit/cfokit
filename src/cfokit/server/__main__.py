"""``python -m cfokit.server {rest|mcp}`` — run one of the deployable's surfaces.

One image, many entrypoints (ADR-0023). These replace `python -m cfokit.ledger.api` and
`python -m cfokit.ledger.mcp`, which served the ledger alone: a module's tools cannot be
reached through an entrypoint inside the ledger, because the ledger depends on no module
(ADR-0022, ADR-0040). Running the deployable means running it from above both.

Migrations are never applied here; they are a separate, explicitly invoked job (ADR-0004).
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import uvicorn

from cfokit.ledger.config import load_settings
from cfokit.ledger.errors import LedgerError
from cfokit.server import mcp_server, rest_app

USAGE = "usage: python -m cfokit.server {rest|mcp}"

# Where the image build puts the web client's static build (Dockerfile, ADR-0054). Absent in a
# source checkout, where the REST service then serves the API alone.
WEB_ROOT = Path("/app/web")


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


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1 or args[0] not in {"rest", "mcp"}:
        print(USAGE, file=sys.stderr)  # noqa: T201 - a usage line, before logging is up
        return 2

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)

    settings = load_settings()
    logging.getLogger("cfokit.server").info(
        f"starting {args[0]} service",
        extra={
            "fields": {
                "port": settings.port,
            }
        },
    )

    # Binding all interfaces is correct inside a container; the platform controls ingress.
    # TLS only when given a certificate: a local stack serves HTTPS itself, while a deployment
    # behind an ingress that terminates TLS leaves both unset, and uvicorn serves plain HTTP.
    if args[0] == "rest":
        uvicorn.run(
            rest_app(
                settings,
                web_root=WEB_ROOT if (WEB_ROOT / "index.html").is_file() else None,
            ),
            host="0.0.0.0",  # noqa: S104
            port=settings.port,
            log_level=settings.log_level,
            access_log=False,
            ssl_certfile=settings.tls_cert_file,
            ssl_keyfile=settings.tls_key_file,
        )
        return 0

    # The bind address also decides the SDK's DNS rebinding protection, which auto-enables only
    # for a localhost bind — so it is off here. That is the right posture and not an accident of
    # the address: the protection guards a server a browser can reach with ambient authority,
    # and this one has none. Every request must carry a bearer token, no cookie is issued, and
    # an attacker's page gets 401. Turning it on means an allowed-host list that must match what
    # clients send through the ingress, and a mismatch answers 421 to everything.
    #
    # Served by uvicorn directly rather than the SDK's run(), which takes no certificate; this
    # is the app run() would serve, with the same settings.
    uvicorn.run(
        mcp_server(settings).streamable_http_app(
            host="0.0.0.0",  # noqa: S104
            stateless_http=True,
            json_response=True,
        ),
        host="0.0.0.0",  # noqa: S104
        port=settings.port,
        log_level=settings.log_level,
        ssl_certfile=settings.tls_cert_file,
        ssl_keyfile=settings.tls_key_file,
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except LedgerError as exc:
        logging.getLogger(__name__).error(exc.message, extra={"fields": {"code": exc.code}})
        sys.exit(1)
