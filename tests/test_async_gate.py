"""The gate confining async to the MCP module must actually catch a violation (ADR-0026).

A gate nobody has seen fail has not been verified.
"""

from __future__ import annotations

from pathlib import Path

from check_async import is_allowed, offending_nodes

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_synchronous_code_passes() -> None:
    source = "def total(a: int, b: int) -> int:\n    return a + b\n"
    assert offending_nodes(source) == []


def test_async_def_is_caught() -> None:
    assert offending_nodes("async def handler() -> None: ...")


def test_await_is_caught() -> None:
    source = "async def h():\n    await thing()\n"
    # Both the async def and the await are reported.
    assert len(offending_nodes(source)) == 2


def test_async_with_and_async_for_are_caught() -> None:
    assert offending_nodes("async def h():\n    async with x:\n        pass\n")
    assert offending_nodes("async def h():\n    async for i in x:\n        pass\n")


def test_asyncio_import_is_caught() -> None:
    assert offending_nodes("import asyncio\n")
    assert offending_nodes("from asyncio import sleep\n")


def test_anyio_and_trio_are_caught() -> None:
    """The SDK's runtime, not just the stdlib name."""
    assert offending_nodes("import anyio\n")
    assert offending_nodes("from trio import sleep\n")


def test_prose_mentioning_async_is_not_flagged() -> None:
    """Documentation of the rule must not trip the gate."""
    source = '"""Async is permitted only inside the MCP module. Never await here."""\n'
    assert offending_nodes(source) == []


def test_identifier_containing_await_is_not_flagged() -> None:
    assert offending_nodes("awaiting_review = True\nasyncio_note = 'x'\n") == []


def test_unrelated_import_is_not_flagged() -> None:
    assert offending_nodes("import asyncore_lookalike\nfrom decimal import Decimal\n") == []


def test_mcp_module_is_allowed() -> None:
    mcp = REPO_ROOT / "packages/ledger/src/cfokit/ledger/mcp/__init__.py"
    assert is_allowed(mcp)


def test_service_layer_is_not_allowed() -> None:
    service = REPO_ROOT / "packages/ledger/src/cfokit/ledger/service/__init__.py"
    assert not is_allowed(service)


def test_rest_adapter_is_not_allowed() -> None:
    """REST has no async requirement and is deliberately outside the allowlist (ADR-0026)."""
    api = REPO_ROOT / "packages/ledger/src/cfokit/ledger/api/__init__.py"
    assert not is_allowed(api)
