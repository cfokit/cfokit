"""REST adapter — one of two protocol adapters over one service layer (ADR-0009).

A published interface with stability obligations; the generated OpenAPI document is
committed and a diff means a contract change requiring review (ADR-0015).

**Handlers are synchronous `def`, never `async def`** (ADR-0025). FastAPI is used for its
OpenAPI generation and validation; the event loop lives in the server, not in this code.
`scripts/check_async.py` fails the build if that slips.

Adapters stay thin. Logic here is a defect, because it is then present in one protocol and
absent from the other (ADR-0008).
"""

from __future__ import annotations

from fastapi import FastAPI, Response, status

from cfokit.ledger.config import Settings
from cfokit.ledger.service.readiness import check_readiness

__all__ = ["create_app"]


def create_app(settings: Settings) -> FastAPI:
    """Build the REST application.

    Takes settings as an argument rather than reading the environment, so the app is
    constructible in a test without one (ADR-0003 keeps `config` the only reader).
    """
    app = FastAPI(
        title="CFOKit Ledger",
        version="0.0.0",
        summary="Multi-tenant double-entry accounting engine.",
    )

    @app.get("/healthz", tags=["operations"], summary="Liveness")
    def healthz() -> dict[str, str]:
        """Liveness only. Deliberately touches nothing.

        If this checked the database, a database blip would restart every healthy
        container — turning a recoverable outage into a rolling one.
        """
        return {"status": "ok"}

    @app.get("/readyz", tags=["operations"], summary="Readiness")
    def readyz(response: Response) -> dict[str, object]:
        """Database reachable, and migrations current.

        Returns 503 when not ready, so a rollout stops rather than serving traffic
        against a schema older than the code.
        """
        result = check_readiness(settings.database_url)
        if not result.ready:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "ready" if result.ready else "not_ready",
            "database_reachable": result.database_reachable,
            "migrations_current": result.migrations_current,
            "detail": result.detail,
        }

    return app
