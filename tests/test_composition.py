"""The deployable, composed: what the ledger's own adapters cannot reach (ADR-0022, ADR-0040).

No database. These are about which tools exist and which paths a tool will read, both of which
are decided before a connection is opened.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from cfokit.imports.mcp import ImportPathRefused, resolve
from cfokit.imports.quickbooks import MAX_ARCHIVE_BYTES, ImportTooLarge
from cfokit.ledger.config import Settings
from cfokit.server import mcp_server

REPO_ROOT = Path(__file__).resolve().parent.parent


def settings(import_root: Path | None = None) -> Settings:
    """A configuration that is never connected to. Which tools exist is decided before a
    connection is opened, which is what lets these run without a database."""
    return Settings(
        database_url="postgresql://unreachable.invalid/none",
        public_base_url="http://localhost:8081",
        auth_issuer_url="http://localhost:8180/realms/cfokit",
        auth_audience="cfokit-ledger",
        import_root=import_root,
    )


def tools(config: Settings) -> set[str]:
    return {tool.name for tool in asyncio.run(mcp_server(config).list_tools())}


# --- the module's tools exist only when a deployment asked for them ------------------------


def test_the_import_tools_are_absent_without_a_configured_root() -> None:
    """**The default, and the one that matters.** A tool taking a path is a file-read
    primitive. Absent rather than present-and-refusing: a surface any holder of a token can
    reach should not exist unless a deployment asked for it."""
    named = tools(settings())

    assert "plan_import" not in named
    assert "apply_import" not in named
    assert "trial_balance" in named  # the ledger's own surface is unaffected


def test_the_import_tools_appear_when_a_root_is_configured(tmp_path: Path) -> None:
    named = tools(settings(tmp_path))

    assert {"plan_import", "apply_import"} <= named


def test_the_ledger_alone_has_no_import_tools(tmp_path: Path) -> None:
    """The contract `import-linter` holds, seen from the outside: the ledger's server knows
    nothing about a module even when one is configured, because it cannot import one."""
    from cfokit.ledger.mcp import create_server

    named = {tool.name for tool in asyncio.run(create_server(settings(tmp_path)).list_tools())}

    assert "plan_import" not in named


# --- a path argument is treated as a file-read primitive -----------------------------------


def test_a_path_inside_the_root_resolves(tmp_path: Path) -> None:
    (tmp_path / "books.zip").write_bytes(b"not really a zip")

    assert resolve(tmp_path, "books.zip") == (tmp_path / "books.zip").resolve()


def test_a_path_escaping_the_root_is_refused(tmp_path: Path) -> None:
    """`..` is settled by resolving before comparing. A containment test against the string
    somebody supplied tests the string, not the file it reaches."""
    outside = tmp_path.parent / "elsewhere.zip"
    outside.write_bytes(b"not really a zip")
    root = tmp_path / "root"
    root.mkdir()

    with pytest.raises(ImportPathRefused):
        resolve(root, "../elsewhere.zip")


def test_an_archive_over_the_ceiling_is_refused(tmp_path: Path) -> None:
    """Refused before 100 MB is read into memory to be handed to the reader.

    The reader holds the real ceiling — `tests/test_archive_bounds.py` — because every path
    onto the books goes through it and this one is an adapter. This check is the fast
    refusal in front of it, on the same constant so the two cannot drift.
    """
    oversized = tmp_path / "books.zip"
    oversized.write_bytes(b"\0" * (MAX_ARCHIVE_BYTES + 1))

    with pytest.raises(ImportTooLarge):
        resolve(tmp_path, "books.zip")


def test_an_archive_at_the_ceiling_is_read(tmp_path: Path) -> None:
    """The limit is a ceiling, not a threshold: the boundary case is allowed, or the message
    telling an operator the maximum names a size they cannot actually use."""
    (tmp_path / "books.zip").write_bytes(b"\0" * MAX_ARCHIVE_BYTES)

    assert resolve(tmp_path, "books.zip") == (tmp_path / "books.zip").resolve()


def test_an_absolute_path_outside_the_root_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()

    with pytest.raises(ImportPathRefused):
        resolve(root, "/etc/passwd")


def test_a_symlink_out_of_the_root_is_refused(tmp_path: Path) -> None:
    """Resolved before the check, so a link is followed to where it actually goes. A
    containment test that ran first would pass a link whose target is anywhere."""
    outside = tmp_path / "elsewhere.zip"
    outside.write_bytes(b"not really a zip")
    root = tmp_path / "root"
    root.mkdir()
    (root / "books.zip").symlink_to(outside)

    with pytest.raises(ImportPathRefused):
        resolve(root, "books.zip")


def test_a_directory_is_not_a_file(tmp_path: Path) -> None:
    (tmp_path / "nested").mkdir()

    with pytest.raises(ImportPathRefused):
        resolve(tmp_path, "nested")


def test_a_missing_file_is_refused_rather_than_read(tmp_path: Path) -> None:
    with pytest.raises(ImportPathRefused):
        resolve(tmp_path, "absent.zip")


def test_the_surface_a_deployment_serves_matches_the_published_contract(tmp_path: Path) -> None:
    """**The comparison a stale container fails.**

    Gate 5 diffs the contract this code generates against the one committed, and both live in
    the repository — so they agree with each other while a running container serves whatever
    surface it was built with. A tool merged and never rolled out is invisible to every check
    that reads the repository, and shows up only as a client reporting that it does not exist.

    `/readyz` reports the served names and a digest of them, so the same comparison can be made
    against a deployment with a single unauthenticated request. This fixes the shape of it: the
    composed surface, which is what a deployment serves, against the published list.
    """
    published = json.loads(
        (REPO_ROOT / "docs" / "contracts" / "mcp-tools.json").read_text(encoding="utf-8")
    )
    served = sorted(
        tool.name for tool in asyncio.run(mcp_server(settings(tmp_path)).list_tools())
    )

    assert served == sorted(tool["name"] for tool in published)
