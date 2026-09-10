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

from fastapi import FastAPI
from mcp.server import MCPServer

from cfokit.imports import api as imports_api
from cfokit.ledger.api import create_app
from cfokit.ledger.config import Settings
from cfokit.ledger.mcp import create_server
from cfokit.ledger.service.authentication import Authenticator

__all__ = ["mcp_server", "rest_app"]


def mcp_server(settings: Settings, authenticator: Authenticator | None = None) -> MCPServer:
    """The MCP surface: the ledger's tools.

    No module contributes tools. Import's did, taking a path to a file the server would read —
    which needed a directory mounted where the server could see it, and that has no analogue on
    a hosted deployment and is not an onboarding step anybody completes. Its surface is now REST
    and its caller is a script in the agent's own runtime, so there is nothing here to register
    (ADR-0041).
    """
    return create_server(settings, authenticator=authenticator)


def rest_app(settings: Settings, authenticator: Authenticator | None = None) -> FastAPI:
    """The REST surface: the ledger's routes, plus each module's.

    Import contributes its own router rather than being mounted by the ledger's adapter, which
    would be the dependency ADR-0022's contract forbids. It is included unconditionally: the
    routes take a body, not a path, so unlike the MCP tools they are not a file-read primitive
    and there is nothing to withhold until a deployment asks for it (ADR-0041).
    """
    app = create_app(settings, authenticator=authenticator)
    app.include_router(imports_api.router)
    return app
