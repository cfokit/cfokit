"""The deployable, composed: what the ledger's own adapters cannot reach (ADR-0022, ADR-0041).

No database. These are about which surface a deployment serves, which is decided before a
connection is opened.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from cfokit.ledger.api import create_app
from cfokit.ledger.config import Settings
from cfokit.server import mcp_server, rest_app

REPO_ROOT = Path(__file__).resolve().parent.parent


def settings() -> Settings:
    return Settings(
        database_url="postgresql://composition.invalid/none",
        public_base_url="http://localhost:8080",
        auth_issuer_url="http://localhost:8180/realms/cfokit",
        auth_audience="cfokit-ledger",
    )


def routes(app: object) -> set[str]:
    """Every path the app serves, from its own OpenAPI document.

    Not `app.routes`: an included router appears there as one opaque entry rather than as its
    routes, so a check over that list would report a module's routes as absent while a client
    reached them perfectly well. The generated document is what the app actually serves and what
    gate 5 publishes, so it is the honest thing to assert over.
    """
    return set(app.openapi()["paths"])  # type: ignore[attr-defined]


# --- a module contributes routes, and the ledger does not know it ---------------------------


def test_the_composed_app_serves_the_import_routes() -> None:
    """Import's surface is REST because its caller is the getting-started pages, which read the
    export in the person's browser and post the neutral shape with their token (ADR-0058)."""
    served = routes(rest_app(settings()))

    assert "/entities/{entity_id}/imports" in served
    assert "/entities/{entity_id}/imports/{import_id}/entries" in served
    assert "/entities/{entity_id}/imports/{import_id}/reconciliation" in served


def test_the_composed_deployable_serves_account_statements() -> None:
    """Activity is a module, so its surface is reachable only from above the ledger: a
    statement read in a Claude Desktop chat arrives over MCP, and one read by a script over
    REST (ADR-0046)."""
    served = routes(rest_app(settings()))
    tools = {tool.name for tool in asyncio.run(mcp_server(settings()).list_tools())}

    assert "/entities/{entity_id}/account-statements" in served
    assert {"record_account_statement", "account_statement_agreement"} <= tools
    assert not [path for path in routes(create_app(settings())) if "account-statements" in path]


def test_the_ledger_alone_serves_none_of_them() -> None:
    """**The contract, as a test.** "The ledger depends on no module" is enforced by
    `import-linter` over import paths; this is the same rule observed at the surface, where a
    ledger adapter that had quietly mounted a module's router would show up."""
    served = routes(create_app(settings()))

    assert not [path for path in served if "imports" in path]


def test_the_import_routes_need_no_configuration() -> None:
    """The published contract must not depend on how a deployment is configured, so a caller can
    bind to it."""
    assert routes(rest_app(settings())) == routes(rest_app(settings()))


def test_import_contributes_no_tools() -> None:
    """Books are imported on the getting-started pages, never through a model: a tool taking the
    parsed shape would make the model retype every figure (ADR-0058 § 3)."""
    served = {tool.name for tool in asyncio.run(mcp_server(settings()).list_tools())}

    assert not {"open_import", "import_entries", "reconcile_import"} & served


# --- what a deployment serves, against what is published ------------------------------------


def test_the_tool_surface_matches_the_published_contract() -> None:
    """**The comparison a stale container fails.**

    Gate 5 diffs the contract this code generates against the one committed, and both live in
    the repository — so they agree with each other while a running container serves whatever
    surface it was built with. A tool merged and never rolled out is invisible to every check
    that reads the repository, and shows up only as a client reporting it does not exist.

    `/readyz` reports the served names and a digest of them, so the same comparison can be made
    against a deployment with one unauthenticated request. This fixes the shape of it.
    """
    published = json.loads(
        (REPO_ROOT / "docs" / "contracts" / "mcp-tools.json").read_text(encoding="utf-8")
    )
    served = sorted(tool.name for tool in asyncio.run(mcp_server(settings()).list_tools()))

    assert served == sorted(tool["name"] for tool in published)


def test_the_rest_surface_matches_the_published_contract() -> None:
    """The same comparison for REST, which now has a module's routes in it — so a contract taken
    from the ledger's app alone would publish less than a deployment serves."""
    published = json.loads(
        (REPO_ROOT / "docs" / "contracts" / "openapi.json").read_text(encoding="utf-8")
    )

    assert sorted(published["paths"]) == sorted(rest_app(settings()).openapi()["paths"])


# --- The assignment module (ADR-0045) -----------------------------------------------------


def test_the_composed_app_serves_the_assignment_routes() -> None:
    served = routes(rest_app(settings()))

    assert {
        "/entities/{entity_id}/assignment-rules",
        "/entities/{entity_id}/assignment-rules/proposals",
        "/entities/{entity_id}/assignment-runs",
        "/entities/{entity_id}/assignment-replay",
    } <= served


def test_the_ledger_alone_serves_no_assignment_route() -> None:
    """**The contract, as a test.** ADR-0022 forbids the ledger depending on a module, and a
    ledger adapter that had quietly mounted this module's router would show up here even
    though `import-linter` would also catch it. Two layers, because the surface is what a
    deployment actually serves."""
    assert [path for path in routes(create_app(settings())) if "assignment" in path] == []


def test_the_assignment_tools_are_served_and_need_no_configuration() -> None:
    first = {tool.name for tool in asyncio.run(mcp_server(settings()).list_tools())}
    second = {tool.name for tool in asyncio.run(mcp_server(settings()).list_tools())}

    assert {
        "propose_assignment_rule",
        "approve_assignment_rule",
        "run_assignment",
        "replay_assignments",
    } <= first
    assert first == second
