"""The deployable, composed: the ledger plus every module beside it.

ADR-0022 makes modules "siblings of the ledger, same deployable" and forbids the ledger from
depending on any of them. Both hold only if something *above* both puts them together — a
ledger adapter that mounted a module's routes would be the dependency the contract forbids, and
a module running its own server would not be the same deployable.

This is that point, and it is the only place that knows the module list. ADR-0023 keeps one
image with many entrypoints; these are the entrypoints, and `python -m cfokit.server` runs them.

**Not a capability.** No domain lives here — only wiring. A file in this package that decides
something about accounting has been put in the wrong place.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from mcp.server import MCPServer

from cfokit.activity import api as activity_api
from cfokit.activity import mcp as activity_mcp
from cfokit.assignment import api as assignment_api
from cfokit.assignment import mcp as assignment_mcp
from cfokit.imports import api as imports_api
from cfokit.imports import mcp as imports_mcp
from cfokit.ledger.api import create_app
from cfokit.ledger.config import Settings
from cfokit.ledger.mcp import acting, create_server
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.authentication import Authenticator
from cfokit.server.web import mount_web_client

__all__ = ["mcp_server", "rest_app"]


def mcp_server(settings: Settings, authenticator: Authenticator | None = None) -> MCPServer:
    """The MCP surface: the ledger's tools, plus each module's.

    Import contributes tools again, on different terms. They took a path to a file the
    server would read, which needed a directory mounted where the server could see it — no
    analogue on a hosted deployment, and not an onboarding step anybody completes. These take
    the parsed shape, because a sandboxed agent runtime cannot open a socket to CFOKit and the
    model is then the only bridge between the file and the books (ADR-0041 § 6).

    Registered unconditionally. The old ones existed only where `IMPORT_ROOT` named a
    directory, because a tool taking a path is a file-read primitive; these take a body, so
    there is nothing to withhold and the published contract no longer depends on how a
    deployment is configured.
    """
    server = create_server(settings, authenticator=authenticator)
    imports_mcp.register(server, Database(settings.database_url), acting=acting)
    assignment_mcp.register(server, Database(settings.database_url), acting=acting)
    activity_mcp.register(server, Database(settings.database_url), acting=acting)
    return server


def rest_app(
    settings: Settings,
    authenticator: Authenticator | None = None,
    web_root: Path | None = None,
) -> FastAPI:
    """The REST surface: the ledger's routes, plus each module's.

    Import contributes its own router rather than being mounted by the ledger's adapter, which
    would be the dependency ADR-0022's contract forbids. It is included unconditionally: the
    routes take a body, not a path, so unlike the MCP tools they are not a file-read primitive
    and there is nothing to withhold until a deployment asks for it (ADR-0041).

    `web_root` is the web client's static build, served at `/app/` when given (ADR-0049 § 5).
    The image always carries one; a test or a source checkout without a build passes none.
    """
    app = create_app(settings, authenticator=authenticator)
    app.include_router(imports_api.router)
    app.include_router(assignment_api.router)
    app.include_router(activity_api.router)
    if web_root is not None:
        mount_web_client(app, web_root, settings.auth_issuer_url)
    return app
