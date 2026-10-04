"""The import module's MCP surface: reading what an import was reconciled to.

**Read only.** Books are imported on the getting-started pages, never through a model, so the
import itself has no tool here (ADR-0058). What the agent needs afterwards is the answer to the
first question a person asks — do the books match the system they came from, and if not, why —
and that is the recorded reconciliation.

**A second transport, not a second design.** The tool calls the same service function the REST
route does; the rendering is duplicated rather than imported from `api`, for the reason the
ledger's two adapters do not import each other.

**A refusal is returned, not raised**, so the published `code` survives the SDK (ADR-0015).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from decimal import Decimal
from typing import Any

from mcp.server import MCPServer

from cfokit.imports.reconciliation import Reconciled, reconciliations
from cfokit.ledger.errors import LedgerError
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.principal import Principal

__all__ = ["register"]


def _divergences(found: Iterable[tuple[str, Decimal, Decimal]]) -> list[dict[str, str]]:
    return [
        {"account_code": code, "ours": str(ours), "theirs": str(theirs)}
        for code, ours, theirs in found
    ]


def _rendered(reconciled: Reconciled) -> dict[str, Any]:
    total = reconciled.total
    return {
        "reconciliation_id": reconciled.id,
        "import_id": reconciled.import_id,
        "recorded_at": reconciled.recorded_at.isoformat(),
        "since": None if reconciled.since is None else reconciled.since.isoformat(),
        "as_of": None if reconciled.as_of is None else reconciled.as_of.isoformat(),
        "journal_total": (
            None
            if total is None
            else {
                "stated_debits": str(total.stated_debits),
                "stated_credits": str(total.stated_credits),
                "our_debits": str(total.our_debits),
                "our_credits": str(total.our_credits),
                "agrees": total.agrees,
                "difference": str(total.difference),
            }
        ),
        "balances": {
            "agreed": reconciled.balances.agreed,
            "compared": reconciled.balances.compared,
            "divergences_net_to_zero": reconciled.divergences_net_to_zero,
            "divergences": _divergences(reconciled.balances.divergences),
        },
        "statements": [
            {
                "report": comparison.report,
                "their_basis": comparison.their_basis,
                "our_basis": comparison.our_basis,
                "agreed": comparison.agreed,
                "divergences": _divergences(comparison.divergences),
                "only_ours": list(comparison.only_ours),
                "only_theirs": list(comparison.only_theirs),
                "unmatched": list(comparison.unmatched),
            }
            for comparison in reconciled.statements
        ],
    }


def register(server: MCPServer, database: Database, *, acting: Callable[[], Principal]) -> None:
    """Register the import tools. `acting` is the ledger's derivation of the caller from the
    bearer token, passed in so there is exactly one place that does it (ADR-0033)."""

    @server.tool(
        name="import_reconciliations",
        description=(
            "What each import into this entity was reconciled to when it finished, newest "
            "first; the first for an import is its current answer. Use it to answer whether "
            "the books match the system they were imported from. journal_total compares the "
            "source's own journal total with ours and is basis-free. balances compares the "
            "source's stated balances with ours in posting signs (positive is a debit); "
            "divergences that net to zero are consistent with the source's reports being on "
            "a different accounting basis, and ones that do not are a defect. statements "
            "compares each statement the source printed, signed as printed, and lists "
            "accounts on one side only and rows the reader could not match. Writes nothing."
        ),
    )
    def reconciliations_tool(entity_id: str) -> dict[str, Any]:
        try:
            found = reconciliations(database, entity_id=entity_id, principal=acting())
        except LedgerError as exc:
            return {"ok": False, "code": exc.code, "message": exc.message}
        return {"ok": True, "reconciliations": [_rendered(each) for each in found]}
