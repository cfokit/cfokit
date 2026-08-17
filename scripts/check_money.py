#!/usr/bin/env python3
"""CI gate 4: no floats touch money — in the schema or in the code (ADR-0004).

Two checks, because ADR-0004 covers both and CLAUDE.md restates it as "use `decimal.Decimal`
everywhere; never `float`, including in tests and fixtures":

1. **Schema.** No `REAL`, `DOUBLE PRECISION`, `FLOAT`, or `MONEY` column types. A float
   column silently loses cents, and for a system whose value proposition is that the books
   are correct that is disqualifying.
2. **Python source.** No `float` annotations or casts under `packages/`. A `float` in a
   fixture teaches the next contributor the wrong thing and eventually reaches production
   code.

Escape hatch for the genuinely non-monetary case (a timeout, a ratio): put `not-money` in a
comment on the same line. Use it rarely and say why.

Exits non-zero listing every offence, so CI fails loudly.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Word-boundary matched so a column named `floating_holiday` does not trip the gate.
FORBIDDEN_SQL = re.compile(
    r"\b(real|float4|float8|float|double\s+precision|money)\b",
    re.IGNORECASE,
)

SQL_COMMENT = re.compile(r"^\s*--")
ALLOW_MARKER = "not-money"


def offending_lines(sql: str) -> list[tuple[int, str]]:
    """Return (line number, text) for each schema line declaring a float storage type."""
    hits: list[tuple[int, str]] = []
    for number, line in enumerate(sql.splitlines(), start=1):
        if SQL_COMMENT.match(line) or ALLOW_MARKER in line:
            continue
        if FORBIDDEN_SQL.search(line):
            hits.append((number, line.strip()))
    return hits


def offending_python_lines(source: str) -> list[tuple[int, str]]:
    """Return (line number, text) for each real use of `float` in Python code.

    Parsed as an AST rather than matched line by line. A docstring explaining that money is
    never a float is prose, not a float, and a regex cannot tell the difference — the first
    version of this gate flagged its own rule documentation.
    """
    tree = ast.parse(source)
    lines = source.splitlines()

    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        # `x: float`, `-> float`, `float(x)`, and `list[float]` all resolve to a Name load.
        if not (isinstance(node, ast.Name) and node.id == "float"):
            continue
        number = node.lineno
        text = lines[number - 1] if number <= len(lines) else ""
        if ALLOW_MARKER in text:
            continue
        hits.append((number, text.strip()))

    return sorted(set(hits))


def _report(path: Path, number: int, text: str, message: str) -> None:
    print(f"{path.relative_to(REPO_ROOT)}:{number}: {message}")
    print(f"    {text}")


def main() -> int:
    failures = 0

    sql_files = sorted(REPO_ROOT.glob("packages/*/src/cfokit/*/migrations/sql/*.sql"))
    for path in sql_files:
        for number, text in offending_lines(path.read_text(encoding="utf-8")):
            _report(path, number, text, "float storage type — use NUMERIC(28,10) (ADR-0004)")
            failures += 1

    py_files = sorted(
        path for path in REPO_ROOT.glob("packages/**/*.py") if "__pycache__" not in path.parts
    )
    for path in py_files:
        for number, text in offending_python_lines(path.read_text(encoding="utf-8")):
            _report(path, number, text, "float in package code — use Decimal (ADR-0004)")
            failures += 1

    if failures:
        print(f"\nCI gate 4 failed: {failures} float offence(s).")
        print("If a value is genuinely not money, add a 'not-money' comment on that line.")
        return 1

    print(
        f"CI gate 4 passed: {len(sql_files)} migration file(s) and "
        f"{len(py_files)} source file(s), no floats touching money."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
