"""The web client's static build, served at ``/app/`` on the API's origin (ADR-0049 § 5).

Wiring, not a capability: the files are built from ``web/`` in the image build (ADR-0054) and
this only hands them out. On GCP a CDN serves the same files at the same path and the load
balancer never routes ``/app/`` here (ADR-0055); everywhere else, this is how the client is
reached.

Nothing here is a route of the client's own. Every path under ``/app/`` answers with a file of
the build, or with ``index.html`` so that the client's router can take a deep link, or with 404.
None of it appears in the OpenAPI document, because none of it is API (ADR-0015).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, RedirectResponse, Response

__all__ = ["SECURITY_HEADERS", "mount_web_client"]

PREFIX = "/app"

# The client's security headers, in one place: the REST service sends these for /app/, and the
# CDN on GCP is configured with the same values (ADR-0049 § 6, ADR-0055 § 2). Everything the
# client loads is bundled, so its own origin is the only source it needs.
SECURITY_HEADERS: dict[str, str] = {
    "Content-Security-Policy": (
        "default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; "
        "form-action 'self'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
}

# Vite names every file under assets/ by its content hash, so a name never changes meaning and
# can be cached for a year. Everything else — index.html, and later the service worker and the
# manifest — is revalidated, so a deploy reaches an open tab at its next navigation.
IMMUTABLE = "public, max-age=31536000, immutable"
REVALIDATE = "no-cache"


def mount_web_client(app: FastAPI, root: Path) -> None:
    """Serve the build in ``root`` at ``/app/``, and send ``/`` there."""
    root = root.resolve()
    index = root / "index.html"

    def respond(path: Path) -> Response:
        cache = IMMUTABLE if path.parent == root / "assets" else REVALIDATE
        return FileResponse(path, headers={**SECURITY_HEADERS, "Cache-Control": cache})

    @app.get("/", include_in_schema=False)
    def to_client() -> RedirectResponse:
        return RedirectResponse(f"{PREFIX}/", status_code=308)

    @app.get(PREFIX, include_in_schema=False)
    def to_client_root() -> RedirectResponse:
        return RedirectResponse(f"{PREFIX}/", status_code=308)

    @app.get(PREFIX + "/{path:path}", include_in_schema=False)
    def client(path: str) -> Response:
        candidate = (root / path).resolve()
        if not candidate.is_relative_to(root):
            raise HTTPException(status_code=404)
        if candidate.is_file():
            return respond(candidate)
        # A path naming a file that is not in the build is a missing file, not a page: answering
        # it with index.html would hand HTML to a script tag. Anything else is the client's own
        # route, which its router resolves.
        if "." in Path(path).name:
            raise HTTPException(status_code=404)
        return respond(index)
