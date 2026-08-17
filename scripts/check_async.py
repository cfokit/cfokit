#!/usr/bin/env python3
"""Async is permitted only inside the MCP adapter module (ADR-0025).

The MCP Python SDK is async, and that is the sole reason async exists in this codebase. It is
therefore confined to one module rather than granted to the adapter layer generally: `engine`,
`repository`, `service`, and the REST `api` adapter all stay synchronous.

Why this needs a machine check rather than a rule: the failure is silent. An `await` added to a
service function still passes every test that calls it from async code, and a blocking call left
undispatched inside an async handler shows up as latency under load rather than as an error.
Neither is caught by a suite that runs one request at a time.

Parsed as an AST rather than matched textually, for the same reason `check_money.py` is:
a docstring explaining the rule is prose, not an `await`.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Only these module paths may contain async constructs. Adding an entry is an ADR-0025 change.
ALLOWED_PREFIXES = ("packages/ledger/src/cfokit/ledger/mcp/",)

ASYNC_MODULES = frozenset({"asyncio", "anyio", "trio"})


def is_allowed(path: Path) -> bool:
    """True if this file sits inside a module permitted to use async."""
    rel = path.relative_to(REPO_ROOT).as_posix()
    return rel.startswith(ALLOWED_PREFIXES)


def offending_nodes(source: str) -> list[tuple[int, str]]:
    """Return (line number, what was found) for each async construct in the source."""
    tree = ast.parse(source)
    hits: list[tuple[int, str]] = []

    for node in ast.walk(tree):
        # Inlined rather than a tuple alias so mypy narrows to a union that has `lineno`.
        if isinstance(node, ast.AsyncFunctionDef | ast.Await | ast.AsyncFor | ast.AsyncWith):
            hits.append((node.lineno, type(node).__name__))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in ASYNC_MODULES:
                    hits.append((node.lineno, f"import {alias.name}"))
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root in ASYNC_MODULES:
                hits.append((node.lineno, f"from {node.module} import ..."))

    return sorted(set(hits))


def main() -> int:
    py_files = sorted(
        path for path in REPO_ROOT.glob("packages/**/*.py") if "__pycache__" not in path.parts
    )

    checked = 0
    failures = 0
    for path in py_files:
        if is_allowed(path):
            continue
        checked += 1
        source = path.read_text(encoding="utf-8")
        lines = source.splitlines()
        for number, what in offending_nodes(source):
            text = lines[number - 1].strip() if number <= len(lines) else ""
            rel = path.relative_to(REPO_ROOT)
            print(f"{rel}:{number}: {what} outside the MCP module (ADR-0025)")
            print(f"    {text}")
            failures += 1

    if failures:
        print(f"\nAsync boundary violated: {failures} occurrence(s).")
        print("Async is confined to cfokit.ledger.mcp. Widening it is an ADR-0025 change.")
        return 1

    print(f"Async boundary holds: {checked} file(s) outside the MCP module, none async.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
