#!/usr/bin/env python3
"""The ledger stays synchronous; async is permitted outside it (ADR-0024).

The boundary is the ledger, not the codebase. What the rule protects is code holding a
transaction and an advisory lock, where an `await` can yield mid-transaction: `engine`,
`repository`, `service`, and the REST `api` adapter all stay synchronous. `cfokit.ledger.mcp`
is exempt because the MCP SDK is async.

Modules and components are deliberately not checked. Ingestion, invoice delivery and
notifications are I/O-bound against third parties, and a component is a separate runtime
reaching the ledger over HTTP (ADR-0022, ADR-0023), so its execution model cannot reach the
write path. They ship in the same distribution as sibling packages under `src/cfokit/`,
which the prefix below excludes without needing to name them.

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

# The gate covers the ledger only. Modules and components choose their own execution model,
# and a sibling capability under src/cfokit/ is outside this prefix by construction.
CHECKED_PREFIX = "src/cfokit/ledger/"

# Paths inside the checked tree that may still contain async. Adding one is an ADR-0024 change.
ALLOWED_PREFIXES = ("src/cfokit/ledger/mcp/",)

ASYNC_MODULES = frozenset({"asyncio", "anyio", "trio"})


def is_checked(path: Path) -> bool:
    """True if this file is inside the ledger, which is where the rule applies."""
    return path.relative_to(REPO_ROOT).as_posix().startswith(CHECKED_PREFIX)


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
        path for path in REPO_ROOT.glob("src/**/*.py") if "__pycache__" not in path.parts
    )

    checked = 0
    failures = 0
    for path in py_files:
        if not is_checked(path) or is_allowed(path):
            continue
        checked += 1
        source = path.read_text(encoding="utf-8")
        lines = source.splitlines()
        for number, what in offending_nodes(source):
            text = lines[number - 1].strip() if number <= len(lines) else ""
            rel = path.relative_to(REPO_ROOT)
            print(f"{rel}:{number}: {what} inside the ledger (ADR-0024)")
            print(f"    {text}")
            failures += 1

    if failures:
        print(f"\nAsync boundary violated: {failures} occurrence(s).")
        print("The ledger stays synchronous. Widening this is an ADR-0024 change.")
        return 1

    print(f"Async boundary holds: {checked} ledger file(s) outside mcp/, none async.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
