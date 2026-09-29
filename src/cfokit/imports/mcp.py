"""The import module's MCP surface, for a runtime that cannot reach CFOKit (ADR-0041 § 6).

**A second transport, not a second design.** The REST surface takes the neutral shape over
HTTP and is what an agent running as an ordinary process uses. A Claude Desktop chat cannot: its
skill
code runs in a sandbox whose egress is a proxy with a domain allowlist, so no port on the
operator's machine is reachable and a tunnel's hostname is not on the list either. The model is
then the only bridge between the sandbox holding the file and the MCP server able to write, and
these tools are that bridge.

**The encoding is the design.** One line per transaction, and the chart sent as an index rather
than a path repeated on every posting: 62 accounts named 11,580 times are 270 KB of a 509 KB
payload, so indexing halves it. About 74,000 tokens against 404,000 as JSON, measured on a real
export.

**The archive still never passes through a model** (ADR-0040). What crosses is the parsed shape,
and the sandbox does the parsing — this surface never sees a zip.

**Every figure here was retyped by something that can retype it wrong**, and that is why
`IMP-08` runs at the end against balances the source states for itself. A mistyped amount makes
the books
disagree with a figure nobody in this path produced, and `NFR-01` forbids carrying that.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from mcp.server import MCPServer

from cfokit.imports import Refusal, check_total, compare, nets_to_zero, open_books, post_entries
from cfokit.imports import _import_id as import_id_for
from cfokit.imports import _reconcile as reconcile_balances
from cfokit.imports.source import (
    SourceAccount,
    SourceBooks,
    SourceEntry,
    SourceLine,
    StatedBalance,
    StatedStatement,
    StatedTotal,
)
from cfokit.ledger.errors import LedgerError
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.principal import Principal
from cfokit.ledger.service.reports import trial_balance

__all__ = ["register"]

# Entries per call. Small enough that a refused batch loses little and the model's output stays
# reviewable; large enough that a real export is a dozen calls rather than hundreds. At the
# measured encoding this is about 6,000 tokens of arguments.
BATCH = 500

# Divergences and skipped rows returned inline. Beyond this the reply names the count, because a
# tool result a person cannot read is not a report.
MAX_INLINE = 25


class ImportToolError(Exception):
    """A refusal raised inside a tool, before it is turned into a result."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(json.dumps({"code": code, "message": message}))
        self.code = code
        self.detail = message


def _refused(code: str, message: str) -> dict[str, Any]:
    return {"ok": False, "code": code, "message": message}


def _refusals(work: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    try:
        return work()
    except ImportToolError as exc:
        return _refused(exc.code, exc.detail)
    except LedgerError as exc:
        return _refused(exc.code, exc.message)


def _accounts(chart: list[str]) -> tuple[SourceAccount, ...]:
    """The chart, from `code|type|parent` lines.

    Ordered, because a posting names an account by its position here. Position rather than name
    is the whole economy of this surface, and it is also the one thing a caller can get wrong
    invisibly — so `_lines` refuses an index outside the chart rather than reaching for a
    neighbor.
    """
    out: list[SourceAccount] = []
    for at, row in enumerate(chart):
        parts = row.split("|")
        if len(parts) != 3:
            raise ImportToolError(
                "invalid_argument",
                f"chart line {at} is {row!r}; each line is 'code|type|parent'",
            )
        code, kind, parent = (p.strip() for p in parts)
        if not code:
            raise ImportToolError("invalid_argument", f"chart line {at} states no code")
        out.append(
            SourceAccount(code=code, name=code, account_type=kind or "unknown", parent=parent)
        )
    return tuple(out)


def _amount(text: str, where: str) -> Decimal:
    """A signed decimal, from the text the caller sent.

    Never a float, at any point (ADR-0005) — and never coerced from something unparseable,
    because a figure that arrives as zero is indistinguishable from a real zero.
    """
    try:
        return Decimal(text)
    except InvalidOperation as broken:
        raise ImportToolError(
            "invalid_argument", f"{where}: {text!r} is not a decimal amount"
        ) from broken


def _lines(
    entries: list[str], chart: tuple[SourceAccount, ...], commodity: str
) -> tuple[SourceEntry, ...]:
    """Transactions, from `ref|date|description|index~amount|index~amount` lines."""
    out: list[SourceEntry] = []
    for row in entries:
        parts = row.split("|")
        minimum = 4  # reference, date, description, and at least one posting
        if len(parts) < minimum:
            raise ImportToolError(
                "invalid_argument",
                f"{row[:60]!r}: each line is 'ref|date|description' then one 'index~amount'"
                " per posting",
            )
        reference, when, description, *postings = parts
        try:
            transaction_date = date.fromisoformat(when.strip())
        except ValueError as broken:
            raise ImportToolError(
                "invalid_argument", f"{reference}: {when!r} is not an ISO date"
            ) from broken

        lines: list[SourceLine] = []
        for posting in postings:
            index, _, amount = posting.partition("~")
            if not index.strip().isdigit() or int(index) >= len(chart):
                raise ImportToolError(
                    "invalid_argument",
                    f"{reference}: {index!r} is not an account in the chart sent at open",
                )
            lines.append(
                SourceLine(
                    account_code=chart[int(index)].code,
                    amount=_amount(amount, f"{reference}"),
                    commodity=commodity,
                )
            )
        out.append(
            SourceEntry(
                reference=reference.strip(),
                transaction_date=transaction_date,
                description=description.strip(),
                lines=tuple(lines),
            )
        )
    return tuple(out)


def _stated(balances: list[str], where: str) -> tuple[StatedBalance, ...]:
    """Figures the source states for itself, from `code|amount` lines."""
    out: list[StatedBalance] = []
    for row in balances:
        code, _, amount = row.partition("|")
        if not code.strip() or not amount:
            raise ImportToolError(
                "invalid_argument", f"{where}: {row[:60]!r} is not 'account|amount'"
            )
        out.append(StatedBalance(account_code=code.strip(), balance=_amount(amount, where)))
    return tuple(out)


def _refusal_rows(refusals: tuple[Refusal, ...]) -> list[dict[str, Any]]:
    return [
        {
            "reference": r.reference,
            "date": r.when.isoformat() if r.when else None,
            "code": r.code,
            "detail": r.detail,
        }
        for r in refusals[:MAX_INLINE]
    ]


def _divergences(found: Any) -> list[dict[str, str]]:
    return [
        {"account": code, "ours": str(ours), "theirs": str(theirs)}
        for code, ours, theirs in list(found)[:MAX_INLINE]
    ]


def register(server: MCPServer, database: Database, *, acting: Callable[[], Principal]) -> None:
    """Add the import tools to an MCP server.

    `acting` is the ledger's own derivation of the caller from the bearer token, passed in
    rather
    than reimplemented: a principal is read from the credential and never from an argument
    (ADR-0033), and there must be exactly one place that does it.
    """

    @server.tool(
        name="open_import",
        description=(
            "Open an import of a company's books and create the chart it needs. Run the reader "
            "in this session first — it parses the export locally and prints the chart and the "
            "transactions in the compact form these tools take; the export file itself never "
            "reaches CFOKit. Send the chart here, then the transactions in batches with "
            "import_entries, then reconcile_import. A person's act: a delegated agent "
            "session is "
            "refused with not_a_person, and should ask the person it acts for. Refused "
            "outright "
            "if the source's accounting basis conflicts with this entity's, or its currency is "
            "not the one this entity keeps books in."
        ),
    )
    def open_import(
        entity_id: str,
        system: str,
        fingerprint: str,
        basis: str,
        balances_basis: str,
        commodity: str,
        chart: list[str],
    ) -> dict[str, Any]:
        """`IMP-01`. The chart is ordered, and a posting names an account by its position.

        `fingerprint` is a digest of the file the reader read. It names this import and is half
        of
        every entry's idempotency key, so re-running the whole flow over the same file replays
        rather than duplicating (ADR-0029) — which is what makes a run that died halfway safe to
        repeat.
        """

        def work() -> dict[str, Any]:
            opened = open_books(
                database,
                entity_id=entity_id,
                principal=acting(),
                request_id=f"mcp-{uuid.uuid4().hex}",
                books=SourceBooks(
                    system=system,
                    fingerprint=fingerprint,
                    basis=basis,
                    balances_basis=balances_basis,
                    commodity=commodity,
                    accounts=_accounts(chart),
                ),
            )
            reply: dict[str, Any] = {
                "ok": True,
                "import_id": opened.import_id,
                "accounts_created": opened.accounts_created,
                "accounts_already_present": opened.accounts_already_present,
            }
            if balances_basis not in {"unknown", basis}:
                reply["expect_obligation_accounts_to_differ"] = True
            return reply

        return _refusals(work)

    @server.tool(
        name="import_entries",
        description=(
            "Post one batch of a company's transactions. Each line is "
            "'reference|YYYY-MM-DD|description' followed by one 'index~amount' per posting, "
            "where index is the account's position in the chart sent to open_import. "
            f"Send about {BATCH} lines per call. Positive amounts debit, negative credit, "
            "and every "
            "transaction must sum to zero. Safe to repeat: a batch sent twice is reported as "
            "replayed rather than posted a second time, so a run that stopped part way is "
            "resumed by sending the same batches again. Report skipped rows; do not repair "
            "them."
        ),
    )
    def import_entries(
        entity_id: str,
        import_id: str,
        fingerprint: str,
        system: str,
        chart: list[str],
        entries: list[str],
    ) -> dict[str, Any]:
        """`IMP-02`, `IMP-04`.

        The chart comes with every batch rather than being remembered between calls. Nothing
        about
        an import is stored — the import id is derived from the fingerprint, not looked up — so
        a
        batch is self-contained and can be retried, reordered, or sent after a disconnection
        without the server needing to know what came before. It costs about 450 tokens a call,
        which is the price of having no state to get out of step.
        """

        def work() -> dict[str, Any]:
            if import_id != import_id_for(fingerprint):
                raise ImportToolError(
                    "import_refused",
                    "this import id does not belong to that fingerprint; open the import first",
                )
            accounts = _accounts(chart)
            done = post_entries(
                database,
                entity_id=entity_id,
                principal=acting(),
                request_id=f"mcp-{uuid.uuid4().hex}",
                system=system,
                fingerprint=fingerprint,
                entries=_lines(entries, accounts, _commodity(database, entity_id, acting())),
            )
            return {
                "ok": True,
                "posted": done.posted,
                # Never added to `posted`. "Nothing happened, it was already done" and
                # "the books changed" are different answers, and a person about to say what
                # changed needs to tell them apart.
                "replayed": done.replayed,
                "skipped": len(done.refusals),
                "skipped_detail": _refusal_rows(done.refusals),
            }

        return _refusals(work)

    @server.tool(
        name="reconcile_import",
        description=(
            "Check the imported books against the figures the source states for itself, and "
            "compare the statements it printed. Balances are 'account|amount' lines from the "
            "source's own general ledger totals; statements are what its profit and loss and "
            "balance sheet printed. journal_total is 'debits|credits' from the journal's own "
            "TOTAL row — the one figure in an export carrying no accounting basis, so it holds "
            "however the reports beside it were run. This is the answer an import is for: "
            "anything short of "
            "agreement is a finding to report, never a rounding to explain away. Where the "
            "source's reports were run on a different accounting basis from its journal, the "
            "receivable and the income behind it differ by exactly what is unsettled — that "
            "is "
            "arithmetic, not a defect."
        ),
    )
    def reconcile_import(
        entity_id: str,
        balances: list[str],
        profit_and_loss: list[str] | None = None,
        balance_sheet: list[str] | None = None,
        their_basis: str = "unknown",
        journal_total: str | None = None,
    ) -> dict[str, Any]:
        """`IMP-08`, and the reason any of this is trustworthy.

        Against figures the source states, never a sum computed from the journal that was just
        loaded — that would be our arithmetic against itself (`NFR-01`). It is also what catches
        a
        figure this surface's caller retyped wrongly, which is the cost of the model being the
        bridge.

        A read, so it may be repeated and needs no reservation: anyone who may read these books
        may check them.
        """

        def work() -> dict[str, Any]:
            statements: list[StatedStatement] = []
            for report, lines in (
                ("profit_and_loss", profit_and_loss),
                ("balance_sheet", balance_sheet),
            ):
                if lines:
                    statements.append(
                        StatedStatement(
                            report=report,
                            basis=their_basis,
                            lines=_stated(lines, report),
                        )
                    )
            stated_total = None
            if journal_total:
                stated_debits, _, stated_credits = journal_total.partition("|")
                if not stated_credits:
                    raise ImportToolError(
                        "invalid_argument",
                        "journal_total is 'debits|credits' from the journal's own TOTAL row",
                    )
                stated_total = StatedTotal(
                    debits=_amount(stated_debits, "journal_total"),
                    credits=_amount(stated_credits, "journal_total"),
                )
            books = SourceBooks(
                system="",
                fingerprint="",
                basis="unknown",
                balances_basis=their_basis,
                commodity="",
                journal_total=stated_total,
                balances=_stated(balances, "balances"),
                statements=tuple(statements),
            )
            principal = acting()
            agreed, compared, divergences = reconcile_balances(
                database, entity_id=entity_id, principal=principal, books=books
            )
            total = check_total(database, entity_id=entity_id, principal=principal, books=books)
            reply: dict[str, Any] = {
                "ok": True,
                "agreed": agreed,
                "compared": compared,
                "divergences": _divergences(divergences),
                "reconciled": compared > 0 and agreed == compared,
                # Cash basis excludes whole transactions, so a basis difference sums to zero in
                # posting signs. False means the difference is not the basis, and is a defect.
                "divergences_net_to_zero": nets_to_zero(divergences),
            }
            if total is not None:
                reply["journal_total"] = {
                    "stated_debits": str(total.stated_debits),
                    "our_debits": str(total.our_debits),
                    "stated_credits": str(total.stated_credits),
                    "our_credits": str(total.our_credits),
                    "agrees": total.agrees,
                    "difference": str(total.difference),
                }
            reply["statements"] = [
                {
                    "report": c.report,
                    "agreed": c.agreed,
                    "compared": c.compared,
                    "their_basis": c.their_basis,
                    "our_basis": c.our_basis,
                    "divergences": _divergences(c.divergences),
                    "accounts_only_they_report": len(c.only_theirs),
                    "accounts_only_we_report": len(c.only_ours),
                }
                for c in compare(
                    database, entity_id=entity_id, principal=principal, books=books
                )
            ]
            return reply

        return _refusals(work)


def _commodity(database: Database, entity_id: str, principal: Principal) -> str:
    """The unit this entity keeps books in, read from the entity rather than sent.

    A caller who could state the commodity per posting could state its way past `IMP-07`, and
    the
    saving would be one repeated field. `open_import` has already refused a source whose
    declared
    commodity is not this one.
    """
    return trial_balance(
        database, entity_id=entity_id, principal=principal, as_of=date.max
    ).functional_currency
