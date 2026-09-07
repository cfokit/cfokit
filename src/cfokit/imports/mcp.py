"""The import module's MCP tools.

Registered onto a server the module does not own. `cfokit.ledger.mcp` builds the server and may
not import this, because the ledger depends on no module (ADR-0022, ADR-0040); a composition
point above both puts the two together, which is what `cfokit.server` is for.

**The tools take a location, not a file.** A caller passes a path and the server reads it. For
an export of several thousand transactions that is an engineering constraint before it is
anything else: eleven thousand posting lines do not fit usefully in a context, a model asked to
carry them is a lossy pipe, and a truncated one corrupts books silently. What a model is *for*
here is reading the loaded books afterwards, which the reporting tools already serve.

**A path argument is a file-read primitive, and is treated as one.** The tools are registered
only when `IMPORT_ROOT` names a directory, and a path outside it is refused. Without that
variable a deployment exposes no import tool at all, which is the right default for a surface
that would otherwise let any holder of a token name any file on the host.

**A summary, and the disagreements in full.** Counts answer "did it reconcile"; the accounts
that did not answer "what do I do now", and only the second is worth a person's attention. So
the reply carries every divergence by name and amount, and the bulk — the whole chart, the
skipped rows, the accounts one side reports and the other does not — goes to a report file.

An earlier version returned counts alone, and it made the tool useless for its purpose: asked
which accounts diverged, the only honest answers left were to theorise from the count or to ask
the operator to supply figures the system already held. A reconciliation that cannot say what
disagreed has not reported a disagreement.

The line is bulk against answer, not figures against no figures. Eleven thousand postings
through a context is a lossy pipe; two account names is the result.

**A report goes where a deployment says, and nowhere by default.** The import directory is the
obvious place and the wrong one: an operator mounts their accounting exports read-only, which is
right, and a tool that wrote beside them would fail on a correctly configured deployment. So
`IMPORT_REPORTS` names a writable directory, and without it the tools write no file and say so.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from mcp.server import MCPServer

from cfokit.imports import Comparison, Plan, Result, apply, compare, plan, quickbooks
from cfokit.ledger.errors import LedgerError
from cfokit.ledger.mcp import refused
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.principal import Principal

__all__ = ["ImportPathRefused", "register"]


class ReportNotWritten(LedgerError):
    """`IMPORT_REPORTS` names a directory that cannot be written to.

    A refusal rather than a silent omission: an operator who configured a reports directory is
    expecting the detail to be there, and a tool that quietly skipped it would report agreement
    with nothing to check it against.
    """

    code = "report_not_written"
    status = 500


class ImportPathRefused(LedgerError):
    """A location outside the configured root, or one that is not a file.

    A `LedgerError` so it carries a stable `code` a caller can branch on, like every other
    refusal on this surface (ADR-0015).
    """

    code = "import_path_refused"
    status = 400


def resolve(root: Path, location: str) -> Path:
    """The file `location` names, if it is inside `root`.

    `resolve()` before comparing, so `..` and a symlink are both settled before the check
    rather than after it — a containment test against an unresolved path tests the string
    somebody supplied instead of the file it reaches.
    """
    candidate = (
        (root / location).resolve()
        if not Path(location).is_absolute()
        else Path(location).resolve()
    )
    if not candidate.is_relative_to(root.resolve()):
        raise ImportPathRefused(f"{location} is outside the configured import directory")
    if not candidate.is_file():
        raise ImportPathRefused(f"{location} is not a file")
    return candidate


def register(
    server: MCPServer,
    database: Database,
    *,
    root: Path,
    acting: Callable[[], Principal],
    reports: Path | None = None,
) -> None:
    """Add the import tools to `server`.

    `acting` derives the caller from the verified token on the request — supplied by the
    composition point rather than rebuilt here, so both surfaces derive a principal exactly one
    way (ADR-0033).

    `reports` is where detail is written. `None` means nowhere, and the tools say so rather
    than failing: the import directory is mounted read-only on any deployment that has thought
    about it, so writing beside the source is not a default that can be relied on.
    """

    def report(source: Path, payload: dict[str, Any]) -> str | None:
        if reports is None:
            return None
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        destination = reports / f"cfokit-{source.stem[:40]}-{stamp}.json"
        try:
            destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        except OSError as refused:
            raise ReportNotWritten(f"{destination}: {refused.strerror}") from refused
        return str(destination)

    def summarise(proposed: Plan) -> dict[str, Any]:
        return {
            "system": proposed.system,
            "entries_basis": proposed.basis,
            "stated_balances_basis": proposed.balances_basis,
            "commodity": proposed.commodity,
            "transactions": proposed.transactions,
            "postings": proposed.postings,
            "accounts_to_create": len(proposed.accounts_to_create),
            "accounts_already_present": len(proposed.accounts_already_present),
            "accounts_with_no_stated_type": len(proposed.untyped_accounts),
            "covering": {
                "earliest": proposed.earliest.isoformat() if proposed.earliest else None,
                "latest": proposed.latest.isoformat() if proposed.latest else None,
            },
            "rows_to_skip": len(proposed.refusals),
            "can_apply": proposed.can_apply,
            "blocked": proposed.blocked,
            # An accrual journal checked against cash-basis balances differs by exactly what is
            # unsettled (ADR-0037). Said here so a caller reads two divergences as predicted
            # rather than as broken.
            "expect_obligation_accounts_to_differ": proposed.oracle_differs_in_basis,
        }

    def detail(proposed: Plan, result: Result | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "plan": {
                **summarise(proposed),
                "accounts_to_create": list(proposed.accounts_to_create),
                "accounts_with_no_stated_type": list(proposed.untyped_accounts),
                "skipped": [
                    {
                        "reference": refusal.reference,
                        "date": refusal.when.isoformat() if refusal.when else None,
                        "code": refusal.code,
                        "detail": refusal.detail,
                    }
                    for refusal in proposed.refusals
                ],
            }
        }
        if result is not None:
            payload["result"] = {
                "import_id": result.import_id,
                "accounts_created": result.accounts_created,
                "transactions_posted": result.transactions_posted,
                "skipped": [
                    {
                        "reference": refusal.reference,
                        "date": refusal.when.isoformat() if refusal.when else None,
                        "code": refusal.code,
                        "detail": refusal.detail,
                    }
                    for refusal in result.refusals
                ],
                "reconciliation": {
                    "agreed": result.agreed,
                    "compared": result.compared,
                    "divergences": [
                        {"account": code, "ours": str(ours), "theirs": str(theirs)}
                        for code, ours, theirs in result.divergences
                    ],
                },
            }
        return payload

    @server.tool(
        name="plan_import",
        description=(
            "Read an accounting export on the server's filesystem and report what importing "
            "it would do — transactions, accounts to create, the period covered, and the rows "
            "it would skip and why. Posts nothing and writes nothing to the books. Pass the "
            "file's name within the configured import directory, never its contents: the "
            "server reads the file. Figures are written to a report file whose path is "
            "returned; the reply carries counts."
        ),
    )
    def plan_import(entity_id: str, location: str) -> dict[str, Any]:
        def work() -> dict[str, Any]:
            source = resolve(root, location)
            books = quickbooks.read(source.read_bytes())
            proposed = plan(database, entity_id=entity_id, principal=acting(), books=books)
            return {
                "ok": True,
                **summarise(proposed),
                "report": report(source, detail(proposed)),
            }

        return _refuse(work)

    @server.tool(
        name="compare_statements",
        description=(
            "Compare the profit and loss and balance sheet an accounting export printed "
            "against the ones CFOKit produces from the books, account by account, with no "
            "tolerance. Reads only and writes nothing. Run it after apply_import to check the "
            "import against the source's own statements rather than against a sum of the same "
            "journal. Every account that disagreed comes back named, with both figures, so a "
            "divergence never has to be inferred from a count. Where the two are on different "
            "accounting bases the obligation accounts differ by what is unsettled, which is "
            "expected and is flagged."
        ),
    )
    def compare_statements(entity_id: str, location: str) -> dict[str, Any]:
        def work() -> dict[str, Any]:
            source = resolve(root, location)
            books = quickbooks.read(source.read_bytes())
            comparisons = compare(
                database, entity_id=entity_id, principal=acting(), books=books
            )
            return {
                "ok": True,
                "statements": [_summarise_comparison(c) for c in comparisons],
                "exact": all(c.agrees for c in comparisons) and bool(comparisons),
                "report": report(
                    source,
                    {"statements": [_detail_comparison(c) for c in comparisons]},
                ),
            }

        return _refuse(work)

    @server.tool(
        name="apply_import",
        description=(
            "Import an accounting export into an entity's books: create the chart, post the "
            "journal, and reconcile the result against the balances the source states for "
            "itself. Re-plans first and refuses a blocked import. Every entry records the "
            "system it came from. Every account whose balance disagrees with the source comes "
            "back named, with both figures. Run plan_import first — this one writes. A "
            "person's act: a delegated agent session is refused with not_a_person, and should "
            "ask the person it acts for to apply the import."
        ),
    )
    def apply_import(entity_id: str, location: str) -> dict[str, Any]:
        def work() -> dict[str, Any]:
            source = resolve(root, location)
            books = quickbooks.read(source.read_bytes())
            principal = acting()
            proposed = plan(database, entity_id=entity_id, principal=principal, books=books)
            result = apply(
                database,
                entity_id=entity_id,
                principal=principal,
                request_id=f"mcp-import-{uuid.uuid4().hex[:8]}",
                books=books,
            )
            return {
                "ok": True,
                "import_id": result.import_id,
                "accounts_created": result.accounts_created,
                "transactions_posted": result.transactions_posted,
                "rows_skipped": len(result.refusals),
                "reconciliation": {
                    "agreed": result.agreed,
                    "compared": result.compared,
                    "divergences": len(result.divergences),
                    "diverging_accounts": _named(result.divergences),
                    "exact": result.reconciled,
                },
                "expect_obligation_accounts_to_differ": proposed.oracle_differs_in_basis,
                "report": report(source, detail(proposed, result)),
            }

        return _refuse(work)


def _refuse(work: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    """Return a refusal rather than raising it, as every tool on this surface does.

    ADR-0015 makes the `code` a published contract callers branch on, and the SDK renders a
    raised exception as a formatted string a caller would have to substring-parse.
    """
    try:
        return work()
    except LedgerError as exc:
        return refused(exc.code, exc.message)


# A ceiling on how much disagreement comes back inline. A healthy import has none or two; a
# reader facing hundreds needs the file, not a wall of them in a reply.
MAX_INLINE_DIVERGENCES = 25


def _summarise_comparison(comparison: Comparison) -> dict[str, Any]:
    """Counts, bases, and every account that disagreed.

    The disagreements are the answer. Reporting how many there were and not which ones leaves a
    caller to guess, and guessing about a figure is the one thing this surface must never make
    anybody do.
    """
    return {
        "report": comparison.report,
        "agreed": comparison.agreed,
        "compared": comparison.compared,
        "divergences": len(comparison.divergences),
        "diverging_accounts": _named(comparison.divergences),
        "their_basis": comparison.their_basis,
        "our_basis": comparison.our_basis,
        "expect_obligation_accounts_to_differ": comparison.their_basis
        not in {"unknown", comparison.our_basis},
        "accounts_only_they_report": len(comparison.only_theirs),
        "accounts_only_we_report": len(comparison.only_ours),
        "rows_that_are_not_accounts": len(comparison.unmatched),
    }


def _named(
    divergences: tuple[tuple[str, Decimal, Decimal], ...],
) -> list[dict[str, str]]:
    """Each disagreement, by account and by both figures.

    Both sides, never a difference alone: which is larger is the thing a person reads first, and
    a signed delta makes them reconstruct it.
    """
    return [
        {"account": code, "ours": str(ours), "theirs": str(theirs)}
        for code, ours, theirs in divergences[:MAX_INLINE_DIVERGENCES]
    ]


def _detail_comparison(comparison: Comparison) -> dict[str, Any]:
    return {
        **_summarise_comparison(comparison),
        "divergences": [
            {"account": code, "ours": str(ours), "theirs": str(theirs)}
            for code, ours, theirs in comparison.divergences
        ],
        "only_they_report": list(comparison.only_theirs),
        "only_we_report": list(comparison.only_ours),
        "not_accounts": list(comparison.unmatched),
    }
