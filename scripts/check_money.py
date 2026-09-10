#!/usr/bin/env python3
"""CI gate 4: no floats touch money — in the schema or in the code (ADR-0005).

Two checks, because ADR-0005 covers both and CLAUDE.md restates it as "use `decimal.Decimal`
everywhere; never `float`, including in tests and fixtures":

1. **Schema.** No `REAL`, `DOUBLE PRECISION`, `FLOAT`, or `MONEY` column types. A float
   column silently loses cents, and for a system whose value proposition is that the books
   are correct that is disqualifying.
2. **Python source.** No `float` annotations or casts under `src/` or `tests/`. A `float`
   in a fixture teaches the next contributor the wrong thing and eventually reaches
   production code, so the test tree is in scope as deliberately as the source tree.

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


def offending_python_lines(source: str, *, literals: bool = False) -> list[tuple[int, str]]:
    """Return (line number, text) for each real use of `float` in Python code.

    Parsed as an AST rather than matched line by line. A docstring explaining that money is
    never a float is prose, not a float, and a regex cannot tell the difference — the first
    version of this gate flagged its own rule documentation.

    `literals` additionally rejects a float *constant*. That is a separate check because it
    catches a separate bug: `Decimal(0.1)` names no `float` at all, so the walk below cannot
    see it, and it is the one CLAUDE.md forbids by name — it carries the binary expansion into
    the type chosen to avoid it, and `Decimal(0.1)` is
    `0.1000000000000000055511151231257827`. Construct from a string.
    """
    tree = ast.parse(source)
    lines = source.splitlines()

    def offends(node: ast.Name | ast.Constant) -> bool:
        # `x: float`, `-> float`, `float(x)` and `list[float]` all resolve to a Name load.
        if isinstance(node, ast.Name):
            return node.id == "float"
        # A float literal. `bool` subclasses `int` and never `float`, so `True` is not a hit.
        return literals and isinstance(node.value, float)

    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        # Narrowed before `offends` so `lineno` is reachable: `ast.AST` does not declare it,
        # but every expression node does.
        if not isinstance(node, ast.Name | ast.Constant) or not offends(node):
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

    sql_files = sorted(REPO_ROOT.glob("src/cfokit/*/migrations/sql/*.sql"))
    for path in sql_files:
        for number, text in offending_lines(path.read_text(encoding="utf-8")):
            _report(path, number, text, "float storage type — use NUMERIC(28,10) (ADR-0005)")
            failures += 1

    # Both trees. ADR-0005 puts fixtures explicitly in scope, so dropping tests/ here
    # would quietly narrow the gate to less than the rule it enforces.
    py_files = sorted(
        path
        for tree in ("src", "tests")
        for path in REPO_ROOT.glob(f"{tree}/**/*.py")
        if "__pycache__" not in path.parts
    )
    for path in py_files:
        # Float *literals* are rejected under src/ only. A fixture building a synthetic .xlsx
        # legitimately holds one: a spreadsheet cell is an IEEE double and openpyxl writes
        # exactly that, so a fixture stating the cell as a Decimal would build a file no
        # source system emits. Under src/ there is no such excuse, and there is deliberately
        # no way to mark an exception: if a float literal ever belongs there, that is a
        # decision to make in this file, in a diff someone reviews.
        in_src = path.relative_to(REPO_ROOT).parts[0] == "src"
        source = path.read_text(encoding="utf-8")
        for number, text in offending_python_lines(source, literals=in_src):
            _report(path, number, text, "float in package code — use Decimal (ADR-0005)")
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
