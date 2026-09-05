#!/usr/bin/env python3
"""CI gate 5: regenerate the published interfaces and diff them (ADR-0015).

Three interfaces are published, and two of them are generated artifacts:

1. **The REST API**, as an OpenAPI document.
2. **The MCP tool surface**, as tool names, descriptions and input schemas.
3. **The error codes**, which are enumerated in `errors.py` and written out here too, because
   ADR-0015 makes them a contract in their own right: "adding a code is a contract change;
   renaming or removing one is breaking".

The artifacts are committed. CI regenerates them and fails on any diff, so a contract change
cannot happen without appearing in a pull request as a change to a contract.

**The output must be deterministic**, or the diff is noise rather than signal — ADR-0015 says
so explicitly. Hence sorted keys and a fixed indent.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACTS = REPO_ROOT / "docs" / "contracts"

sys.path.insert(0, str(REPO_ROOT / "src"))

from cfokit.ledger import errors as errors_module  # noqa: E402
from cfokit.ledger.config import Settings  # noqa: E402
from cfokit.server import mcp_server, rest_app  # noqa: E402

# A DSN that is never connected to. Generating a contract must not need a database, or the
# gate would need one too (ADR-0004).
#
# `import_root` is set, so the published surface is everything the deployable *can* expose. A
# deployment that leaves `IMPORT_ROOT` unset exposes fewer tools than the contract lists, which
# is a deployment choice rather than a contract change — the opposite arrangement would make
# the published contract depend on configuration, and a caller could not bind to it.
SETTINGS = Settings(
    database_url="postgresql://contract.invalid/none",
    public_base_url="http://localhost:8080",
    auth_issuer_url="http://localhost:4444",
    auth_audience="cfokit-ledger",
    import_root=Path("/imports"),
)


def openapi_document() -> dict[str, Any]:
    return rest_app(SETTINGS).openapi()


def mcp_tools() -> list[dict[str, Any]]:
    """Tool name, description and input schema — what a client actually binds to.

    `list_tools` is a coroutine, so this drives one. That is fine here and nowhere else: this
    is a CI script under `scripts/`, outside the tree `check_async.py` guards, and the async
    boundary ADR-0024 draws is around the ledger package rather than the repository.
    """
    tools = asyncio.run(mcp_server(SETTINGS).list_tools())
    return sorted(
        (
            {
                "name": tool.name,
                "description": tool.description,
                "inputSchema": tool.input_schema,
            }
            for tool in tools
        ),
        key=lambda entry: str(entry["name"]),
    )


def error_codes() -> list[dict[str, str]]:
    """Every stable `code` an error can carry, with the class that raises it."""
    found: list[dict[str, str]] = []
    for name, member in vars(errors_module).items():
        if (
            inspect.isclass(member)
            and issubclass(member, errors_module.LedgerError)
            and member is not errors_module.LedgerError
        ):
            found.append({"code": member.code, "error": name})
    return sorted(found, key=lambda entry: entry["code"])


def write(path: Path, payload: object) -> bool:
    """Write `payload` as deterministic JSON. True if it changed."""
    rendered = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    path.write_text(rendered, encoding="utf-8")
    return rendered != existing


def main() -> int:
    CONTRACTS.mkdir(parents=True, exist_ok=True)
    changed = [
        name
        for name, payload in (
            ("openapi.json", openapi_document()),
            ("mcp-tools.json", mcp_tools()),
            ("error-codes.json", error_codes()),
        )
        if write(CONTRACTS / name, payload)
    ]

    if changed:
        print(f"Contracts regenerated, {len(changed)} changed: {', '.join(changed)}")
        print("If this is intentional, commit the diff — it is a contract change (ADR-0015).")
    else:
        print("Contracts unchanged.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
