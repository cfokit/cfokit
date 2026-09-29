#!/usr/bin/env python3
"""Read a QuickBooks Online export into CFOKit's neutral interchange shape (ADR-0041).

**Runs where the file is**, in the agent's own runtime, and emits JSON on stdout. The archive
never reaches CFOKit: the server accepts the shape below and parses no foreign binary format,
so a zip bomb or a hostile spreadsheet reaches the machine whose owner opened it and nothing
else (`NFR-04`).

**Standard library only.** An `.xlsx` is a zip of XML, so `zipfile` and `ElementTree` are the
whole requirement. Nothing here may be installed, and nothing here imports CFOKit: this is a
separate system sharing a published contract (ADR-0014), and the contract is the JSON below.

**Amounts are strings, never JSON numbers.** A JSON number is a float in most parsers, and a
float's binary expansion is not the figure the workbook shows (ADR-0005). Every amount crosses
this boundary as the text the cell holds.

    python3 read_quickbooks.py <zip>                     # the shape, on stdout
    python3 read_quickbooks.py <zip> --summary           # counts only, for a person to read
    python3 read_quickbooks.py <zip> --post <url> --entity <id>   # sign in and import
    python3 read_quickbooks.py <zip> --mcp               # the form the MCP import tools take

**`--mcp` is for a runtime that cannot reach CFOKit.** A Claude Desktop chat runs this in a
sandbox whose egress is a proxy with a domain allowlist, so no port on the operator's machine is
reachable and `--post` cannot work. It prints the chart and the transactions in the compact form
the `open_import` and `import_entries` tools take, and the model relays them. The archive still
never passes through a model — what crosses is the parsed shape (ADR-0040, ADR-0041 § 6).

**`--post` signs a person in.** It cannot borrow the agent session's credential: importing
is a person's act and the ledger refuses a delegated one (ADR-0007), so a token carrying an
RFC 8693 `act` claim would be rejected on arrival. RFC 8628 device authorization, because
this may run in a container with no browser and no port it can bind, and the person
approving may be at another machine. Nothing is cached — one sign-in per run, for an
operation a company performs about once.

Exit status is 0 on success and 1 on a refusal, with the reason on stderr.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime
from decimal import Decimal
from typing import Any

SYSTEM = "QuickBooks Online"
SHAPE_VERSION = "1"

# Declared in the realm this deployment ships (ADR-0041). A public client, so it holds no
# secret and there is nothing here to keep out of a repository.
CLIENT_ID = "cfokit-importer"

# Entries per request. Small enough that a request is short and a failure loses little;
# large enough that 5,556 transactions is a dozen requests rather than a thousand. At the
# measured 10.2 ms per transaction this is about five seconds of posting.
BATCH = 500

# A person opening a browser, reading a code and approving. Generous: the failure this
# guards is a script waiting for an approval that is never coming, not a slow reader.
SIGN_IN_TIMEOUT_SECONDS = 600

# QuickBooks Online exports one currency per company file and states it in none of these
# reports. Declared rather than inferred: `IMP-07` refuses a foreign amount, and that refusal
# is worth nothing if the commodity was guessed from a cell.
COMMODITY = "USD"

# Measured against a real export: eight members, 979,403 bytes expanded from 904,749, a ratio
# of 1.08. That ratio is structural rather than lucky — the members are `.xlsx` files, which
# are themselves zips — so a genuine export is very nearly incompressible and a high ratio is
# evidence the file is not one. These leave room for an export a hundred times larger.
MAX_ARCHIVE_BYTES = 100 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 300 * 1024 * 1024
MAX_MEMBERS = 64

# A formula whose whole body is the number it states, which is how QuickBooks writes a figure.
_LITERAL = re.compile(r"-?\d+(\.\d+)?")

# Column positions in the Journal report, from its header row.
_DATE, _MEMO, _ACCOUNT, _DEBIT, _CREDIT = 1, 5, 6, 7, 8
_HEADER_ROWS = 5

_BALANCE_SHEET_SECTIONS = {
    "ASSETS": "asset",
    "LIABILITIES AND EQUITY": None,
    "Liabilities": "liability",
    "Equity": "equity",
}
# A profit and loss has four sections, not two. "Other Income" and "Other Expenses" carry
# things outside the trading result — interest earned, a gain on disposal — and an account
# under one of them is still income or expense.
_INCOME_STATEMENT_SECTIONS = {
    "Income": "income",
    "Other Income": "income",
    "Expenses": "expense",
    "Other Expenses": "expense",
}


class Refused(Exception):
    """The export will not be read, and why. Carries the code the server would use."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code


# --- the spreadsheet, without a spreadsheet library ----------------------------------------


def _local(tag: str) -> str:
    """An element's name without its namespace."""
    return tag.rsplit("}", 1)[-1]


def _parse(payload: bytes) -> ET.Element:
    """XML, refusing a document type declaration.

    Entity-expansion attacks — billion laughs, quadratic blowup — need a `DOCTYPE` carrying
    `ENTITY` declarations, and a spreadsheet part never has one. Refusing the declaration
    outright is a complete defense against that class here and needs no third-party parser,
    which is why this script depends on nothing.
    """
    head = payload[:4096].lstrip()
    if b"<!DOCTYPE" in head.upper() or b"<!ENTITY" in payload[:4096].upper():
        raise Refused("unreadable_figure", "a spreadsheet part declares a document type")
    return ET.fromstring(payload)  # noqa: S314 - DOCTYPE refused above; no entities possible


def _column(reference: str) -> int:
    """`C` from `C7`, as a zero-based index."""
    index = 0
    for char in reference:
        if not char.isalpha():
            break
        index = index * 26 + (ord(char.upper()) - ord("A") + 1)
    return index - 1


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    """The workbook's string table.

    Each `<si>` may hold one `<t>` or several inside `<r>` runs; the value is all of them
    joined. Leading whitespace is load-bearing — a statement's indentation is how a
    sub-account's path is recovered — so `xml:space="preserve"` text is kept exactly.
    """
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = _parse(_member(archive, "xl/sharedStrings.xml"))
    return [
        "".join(node.text or "" for node in item.iter() if _local(node.tag) == "t")
        for item in root
        if _local(item.tag) == "si"
    ]


def _first_sheet(archive: zipfile.ZipFile) -> str:
    """The path of the workbook's first worksheet, resolved through its relationships."""
    workbook = _parse(_member(archive, "xl/workbook.xml"))
    sheets = [node for node in workbook.iter() if _local(node.tag) == "sheet"]
    if not sheets:
        raise Refused("unreadable_figure", "the workbook declares no worksheet")
    relationship = next(
        (value for key, value in sheets[0].attrib.items() if _local(key) == "id"), None
    )
    if relationship is not None and "xl/_rels/workbook.xml.rels" in archive.namelist():
        rels = _parse(_member(archive, "xl/_rels/workbook.xml.rels"))
        for node in rels:
            if node.get("Id") == relationship:
                target = node.get("Target", "")
                return "xl/" + target.lstrip("/").removeprefix("xl/")
    return "xl/worksheets/sheet1.xml"


def _cells(archive: zipfile.ZipFile, member: str) -> list[tuple[Any, ...]]:
    """One worksheet as rows of cell values, the shape the parsing below expects.

    `None` for an empty cell, the text for a string, `"=…"` for a formula, and the *raw digits*
    for a number — never a float. QuickBooks writes every figure in the statement reports as a
    formula with no cached result, so a reader that asked for cached values would get a zero for
    each of them; and a number that went through a float on the way here would no longer be the
    figure the workbook shows.
    """
    strings = _shared_strings(archive)
    sheet = _parse(_member(archive, _first_sheet(archive)))

    rows: list[tuple[Any, ...]] = []
    for element in sheet.iter():
        if _local(element.tag) != "row":
            continue
        # A worksheet omits a row that holds nothing, and its `r` attribute is the real row
        # number. The gap has to be filled: every report here is read by position — five header
        # rows, then the body — so a missing blank row shifts the whole file up by one and the
        # first transaction disappears into the header.
        declared = element.get("r")
        if declared is not None:
            while len(rows) < int(declared) - 1:
                rows.append(())
        values: dict[int, Any] = {}
        for cell in element:
            if _local(cell.tag) != "c":
                continue
            at = _column(cell.get("r", "A"))
            kind = cell.get("t")
            formula = next((c for c in cell if _local(c.tag) == "f"), None)
            if formula is not None:
                values[at] = "=" + (formula.text or "")
                continue
            if kind == "inlineStr":
                values[at] = "".join(
                    node.text or "" for node in cell.iter() if _local(node.tag) == "t"
                )
                continue
            raw = next((c.text for c in cell if _local(c.tag) == "v"), None)
            if raw is None:
                continue
            if kind == "s":
                index = int(raw)
                values[at] = strings[index] if index < len(strings) else ""
            else:
                values[at] = raw
        width = max(values) + 1 if values else 0
        rows.append(tuple(values.get(at) for at in range(width)))
    return rows


# --- bounds, because the archive is somebody else's file ------------------------------------


def _member(archive: zipfile.ZipFile, name: str) -> bytes:
    """One member's bytes, refusing to read past the ceiling.

    Streamed with an explicit stop rather than `ZipFile.read`, because a member's declared size
    comes from the central directory and whoever built the archive wrote that. A member
    declaring a kilobyte and delivering a terabyte is stopped here.
    """
    with archive.open(name) as stream:
        payload = stream.read(MAX_UNCOMPRESSED_BYTES + 1)
    if len(payload) > MAX_UNCOMPRESSED_BYTES:
        raise Refused(
            "import_too_large",
            f"{name} expands past {MAX_UNCOMPRESSED_BYTES} bytes;"
            " the archive's own directory understated it",
        )
    return payload


def _bounded(archive: zipfile.ZipFile) -> None:
    """Refuse an archive that would expand past what this reads.

    Checked against the central directory, which is metadata rather than decompression, so the
    ordinary case is refused before a byte is expanded. `_member` bounds the actual read,
    because this check trusts numbers the archive supplied.
    """
    members = archive.infolist()
    if len(members) > MAX_MEMBERS:
        raise Refused(
            "import_too_large",
            f"the archive holds {len(members)} members; this reads at most {MAX_MEMBERS}",
        )
    declared = sum(member.file_size for member in members)
    if declared > MAX_UNCOMPRESSED_BYTES:
        raise Refused(
            "import_too_large",
            f"the archive declares {declared} bytes expanded;"
            f" this reads at most {MAX_UNCOMPRESSED_BYTES}",
        )


# --- reading the reports --------------------------------------------------------------------


def _amount(value: Any) -> Decimal:
    """A cell as an exact decimal.

    **A formula that states a number is that number; any other formula is refused.** The
    statement reports write every figure as `=2492948.04`, so reading them at all means reading
    those. A formula referencing other cells is a subtotal, and computing it would mean
    implementing a spreadsheet — where returning zero would be worse than either, because a zero
    in a financial figure reads as a fact.
    """
    if value is None:
        return Decimal(0)
    text = str(value)
    if text.startswith("="):
        stated = text[1:].strip()
        if not _LITERAL.fullmatch(stated):
            raise Refused(
                "unreadable_figure", f"{text[:40]!r} is a computed cell, not a stated figure"
            )
        return Decimal(stated)
    return Decimal(text)


def _as_date(value: Any) -> str:
    """A journal date, as ISO. QuickBooks prints `MM/DD/YYYY` as text."""
    return datetime.strptime(str(value).strip(), "%m/%d/%Y").date().isoformat()  # noqa: DTZ007


def _basis(rows: list[tuple[Any, ...]]) -> str:
    """The accounting method a report was run on, from its footer.

    QuickBooks prints it on the last labeled row — "… - Cash Basis" or "… - Accrual Basis".
    A report whose basis cannot be read is `unknown`, which callers must treat as unusable
    rather than assume.
    """
    for row in reversed(rows):
        label = row[0] if row else None
        if label is None:
            continue
        text = str(label)
        if "Cash Basis" in text:
            return "cash"
        if "Accrual Basis" in text:
            return "accrual"
        break
    return "unknown"


def _at(row: tuple[Any, ...], index: int) -> Any:
    return row[index] if index < len(row) else None


def _entries(rows: list[tuple[Any, ...]]) -> list[dict[str, Any]]:
    """Every transaction in the journal, with its lines.

    A transaction begins on the row carrying a date; its remaining lines carry none. Each group
    ends with a totals row that has amounts and no account — skipped, or every transaction would
    count twice.

    The reference is positional because QuickBooks' journal prints no stable identifier. That is
    honest about what it is: it identifies the row in *this* export, which is what a person
    tracing a posting back to the file needs, and what the server's idempotency key is built on.
    """
    entries: list[dict[str, Any]] = []
    lines: list[dict[str, str]] = []
    reference = 0
    when: str | None = None
    description = ""

    def flush() -> None:
        if when is not None:
            entries.append(
                {
                    "reference": str(reference),
                    "transaction_date": when,
                    "description": description,
                    "lines": list(lines),
                }
            )

    for row in rows[_HEADER_ROWS:]:
        if _at(row, _DATE) is not None:
            flush()
            lines = []
            reference += 1
            when = _as_date(_at(row, _DATE))
            description = str(_at(row, _MEMO) or "")
        account = _at(row, _ACCOUNT)
        if account is None or when is None:
            continue
        lines.append(
            {
                "account_code": str(account),
                "amount": str(_amount(_at(row, _DEBIT)) - _amount(_at(row, _CREDIT))),
                "commodity": COMMODITY,
            }
        )
    flush()
    return entries


def _account_types(sheets: dict[str, list[tuple[Any, ...]]]) -> dict[str, str]:
    """Map each account to a type, using the source's own statement sections.

    An account under `ASSETS` on the balance sheet is an asset; one under `Income` on the profit
    and loss is income. Guessing a type from an account's name would put our judgment into data
    whose whole value is that it is not ours.
    """
    types: dict[str, str] = {}
    for member, sections in (
        ("Balance_sheet.xlsx", _BALANCE_SHEET_SECTIONS),
        ("Profit_and_loss.xlsx", _INCOME_STATEMENT_SECTIONS),
    ):
        rows = sheets.get(member)
        if rows is None:
            continue
        current: str | None = None
        for row in rows[_HEADER_ROWS:]:
            label = row[0] if row else None
            if label is None:
                continue
            text = str(label).strip()
            if text in sections:
                current = sections[text]
                continue
            if text.upper().startswith("TOTAL") or text.startswith("Gross "):
                continue
            if current is not None and any(cell is not None for cell in row[1:]):
                types.setdefault(text, current)
    return types


def _typed(name: str, types: dict[str, str]) -> str:
    """An account's type, from the statement it appears on or from its parent's.

    QuickBooks prints a sub-account under its bare leaf name, so the full colon-separated path
    the journal uses never matches one of those rows. Walking up the path is not a guess:
    QuickBooks requires a sub-account to share its parent's type, and the path is the source
    stating the hierarchy. The bare leaf is tried last, because a leaf name can repeat under two
    parents and the more specific answer should win where there is one.
    """
    parts = name.split(":")
    for cut in range(len(parts), 0, -1):
        stated = types.get(":".join(parts[:cut]))
        if stated is not None:
            return stated
    return types.get(parts[-1], "unknown")


def _parent(name: str, accounts: set[str]) -> str:
    """The account this one sits under, where the export has one.

    A parent taking no postings of its own is not in the journal and so is not an account here;
    the child is reported as top-level rather than pointing at something absent.
    """
    parts = name.split(":")
    for cut in range(len(parts) - 1, 0, -1):
        candidate = ":".join(parts[:cut])
        if candidate in accounts:
            return candidate
    return ""


def _resolve(path: list[str], posted_to: set[str]) -> str | None:
    """The account a statement row names, from the path its indentation implies.

    Longest suffix first, because the deeper path is the more specific claim: a row nested under
    a real parent is that parent's sub-account, and one nested only under grouping headings is a
    top-level account whose leaf name is the whole of it.
    """
    for start in range(len(path)):
        candidate = ":".join(path[start:])
        if candidate in posted_to:
            return candidate
    return None


def _statement(rows: list[tuple[Any, ...]], report: str, posted_to: set[str]) -> dict[str, Any]:
    """One printed statement, by account.

    **Account paths come from the indentation.** A statement indents a sub-account under its
    parent, so `Business Development` beneath `Advertising & Marketing` is the account the
    journal calls `Advertising & Marketing:Business Development`. Reading the leaf alone would
    be
    ambiguous — `Meals` appears under two parents in a real chart.

    A statement's hierarchy is not only accounts: a balance sheet groups them under `ASSETS`,
    `Current Assets`, `Bank Accounts`, none of which anything posts to. So the path the
    indentation suggests is checked against the accounts the journal uses, and a row matching
    none is reported as unmatched rather than guessed at.

    Sign is left exactly as the source prints it. A statement shows income as positive; a
    posting
    signs it negative. The comparison is where the two conventions meet, so that is where the
    translation belongs — not here.
    """
    lines: list[dict[str, str]] = []
    unmatched: list[str] = []
    stack: list[tuple[int, str]] = []

    for row in rows[_HEADER_ROWS:]:
        label = row[0] if row else None
        if label is None:
            continue
        text = str(label)
        name = text.strip()
        if not name or name.upper().startswith("TOTAL") or name.startswith("Gross "):
            continue
        if "Basis" in name and name.endswith("Basis"):
            continue

        depth = len(text) - len(text.lstrip())
        while stack and stack[-1][0] >= depth:
            stack.pop()
        stack.append((depth, name))

        if _at(row, 1) is None:
            continue  # a heading, or a parent carrying no figure of its own

        code = _resolve([entry for _, entry in stack], posted_to)
        if code is None:
            unmatched.append(name)
            continue
        lines.append({"account_code": code, "balance": str(_amount(_at(row, 1)))})

    return {
        "report": report,
        "basis": _basis(rows),
        "lines": lines,
        "unmatched": unmatched,
    }


def _journal_total(rows: list[tuple[Any, ...]]) -> dict[str, str] | None:
    """What the journal says it sums to, from its own TOTAL row.

    **The only figure in the export carrying no accounting basis.** Every report beside it is
    run on whichever basis the company keeps — most small companies keep cash — so a
    per-account comparison against one diverges on the obligation accounts by exactly what is
    unsettled. The journal is the record rather than a view of it, so this does not
    (ADR-0050).

    Read rather than computed. Summing the rows here and calling it an oracle would be the
    reader's arithmetic checked against its own; the value of this figure is
    that QuickBooks produced it.
    """
    for row in reversed(rows):
        label = row[0] if row else None
        if label is None or str(label).strip().upper() != "TOTAL":
            continue
        stated_debits = _amount(_at(row, _DEBIT))
        stated_credits = _amount(_at(row, _CREDIT))
        return {"debits": str(stated_debits), "credits": str(stated_credits)}
    return None


def _ledger_totals(
    rows: list[tuple[Any, ...]], posted_to: set[str]
) -> tuple[list[dict[str, str]], list[dict[str, str]], str]:
    """The general ledger's own stated totals, split into balances and rollups, and its basis.

    QuickBooks closes each account's section with a "Total for <account>" row. Those are the
    source's own balances — the figure `IMP-08` reconciles against — and they cover only
    accounts
    with activity, which is why an account may be in the journal and absent here.

    Some are **subtotals over a parent and its children**, printed as "Total for X with
    sub-accounts" where the parent also takes postings of its own, and as a bare "Total for X"
    where it does not. Both are recognized, and the bare case is decided against the export's
    own
    data rather than its wording: a bare total is a rollup only when the journal posts beneath
    that parent and never to the parent itself.

    They are held apart because comparing a subtotal against a chart account would manufacture a
    divergence out of a category error.
    """
    balances: list[dict[str, str]] = []
    rollups: list[dict[str, str]] = []
    for row in rows[_HEADER_ROWS:]:
        label = row[0] if row else None
        if label is None or not str(label).startswith("Total for "):
            continue
        account = str(label)[len("Total for ") :].strip()
        parent = account.removesuffix(" with sub-accounts")
        stated = {
            "account_code": parent,
            "balance": str(_amount(_at(row, _DEBIT)) - _amount(_at(row, _CREDIT))),
        }
        has_children = any(code.startswith(parent + ":") for code in posted_to)
        if account != parent or (has_children and parent not in posted_to):
            rollups.append(stated)
        else:
            balances.append(stated)
    return balances, rollups, _basis(rows)


# --- the shape ------------------------------------------------------------------------------


def read(archive_bytes: bytes) -> dict[str, Any]:
    """One QuickBooks export, as the neutral interchange shape.

    The general ledger's own per-account totals are the oracle, not the trial balance. Every
    *report* carries its accounting method in its footer; `Journal.xlsx` carries none, because
    it
    is the raw record rather than a view of it. So the two bases come from different files and
    mean different things — and a cash-basis general ledger beside an accrual journal is
    routine,
    which ADR-0037 predicts and `IMP-08` reports rather than tolerates.
    """
    if len(archive_bytes) > MAX_ARCHIVE_BYTES:
        raise Refused(
            "import_too_large",
            f"the archive is {len(archive_bytes)} bytes;"
            f" this reads at most {MAX_ARCHIVE_BYTES}",
        )

    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as export:
        _bounded(export)
        present = set(export.namelist())
        sheets: dict[str, list[tuple[Any, ...]]] = {}
        for member in (
            "Journal.xlsx",
            "General_ledger.xlsx",
            "Balance_sheet.xlsx",
            "Profit_and_loss.xlsx",
        ):
            if member not in present:
                continue
            with zipfile.ZipFile(io.BytesIO(_member(export, member))) as workbook:
                _bounded(workbook)
                sheets[member] = _cells(workbook, member)

    if "Journal.xlsx" not in sheets:
        raise Refused("import_refused", "the export carries no Journal.xlsx to read")

    entries = _entries(sheets["Journal.xlsx"])
    posted_to = {line["account_code"] for entry in entries for line in entry["lines"]}
    used = sorted(posted_to)
    types = _account_types(sheets)

    ledger = sheets.get("General_ledger.xlsx")
    if ledger is None:
        balances, rollups, balances_basis = [], [], "unknown"
    else:
        balances, rollups, balances_basis = _ledger_totals(ledger, posted_to)

    statements = [
        _statement(sheets[member], report, posted_to)
        for member, report in (
            ("Profit_and_loss.xlsx", "profit_and_loss"),
            ("Balance_sheet.xlsx", "balance_sheet"),
        )
        if member in sheets
    ]

    return {
        "shape_version": SHAPE_VERSION,
        "system": SYSTEM,
        # Over the archive bytes, so re-reading the same export yields the same identity and a
        # different export never collides with it. This is what makes an import replayable
        # rather than duplicable: the server derives each entry's idempotency key from it and
        # the row's own reference, so a client that dies mid-import resumes by sending the same
        # batches again (ADR-0029).
        "fingerprint": hashlib.sha256(archive_bytes).hexdigest(),
        "basis": _basis(sheets["Journal.xlsx"]),
        "balances_basis": balances_basis,
        "commodity": COMMODITY,
        "accounts": [
            {
                "code": name,
                "name": name,
                "account_type": _typed(name, types),
                "parent": _parent(name, posted_to),
            }
            for name in used
        ],
        "entries": entries,
        "journal_total": _journal_total(sheets["Journal.xlsx"]),
        "balances": balances,
        "rollups": rollups,
        "statements": statements,
    }


# --- signing a person in, and posting -------------------------------------------------------


def _http(url: str, *, payload: Any = None, token: str | None = None, form: Any = None) -> Any:
    """One JSON request. `urllib` because this script depends on nothing.

    A refusal comes back as JSON carrying a stable `code` (ADR-0015), so an HTTP error is read
    rather than raised blindly: the code is what a person needs to see.
    """
    data = None
    headers = {"Accept": "application/json"}
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(url, data=data, headers=headers)  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310
            body = response.read()
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as failed:
        raw = failed.read()
        try:
            detail = json.loads(raw)
        except ValueError:
            detail = {"code": f"http_{failed.code}", "message": raw.decode(errors="replace")}
        detail["_status"] = failed.code
        return detail
    except urllib.error.URLError as unreachable:
        raise Refused("unreachable", f"{url}: {unreachable.reason}") from unreachable


def _issuer(base: str) -> str:
    """Which issuer guards this deployment, asked of the deployment itself (RFC 9728).

    Discovered rather than configured. Handing an operator a second URL to get right is the kind
    of setup step that does not survive contact with one, and `AUTH_ISSUER_URL` is the server's
    business rather than theirs.
    """
    found = _http(base.rstrip("/") + "/.well-known/oauth-protected-resource")
    servers = found.get("authorization_servers") or []
    if not servers:
        raise Refused("unreachable", f"{base} names no authorization server")
    return str(servers[0])


def sign_in(base: str, *, out: Any = sys.stderr) -> str:
    """A person's access token, by RFC 8628 device authorization.

    **A person's, not this script's.** Importing a company's books is a person's act and the
    ledger refuses a delegated one, so there is no machine credential that would work here even
    if one were available (ADR-0007, `IAM-10`).

    Nothing is cached. One sign-in per run is the price of not leaving a standing credential in
    an agent's runtime for an operation a company performs about once.
    """
    metadata = _http(_issuer(base).rstrip("/") + "/.well-known/openid-configuration")
    endpoint = metadata.get("device_authorization_endpoint")
    if not endpoint:
        raise Refused(
            "unreachable",
            "this issuer does not offer device authorization; see infra/README.md for the"
            " loopback fallback",
        )

    started = _http(endpoint, form={"client_id": CLIENT_ID})
    if "device_code" not in started:
        raise Refused("unreachable", f"the issuer refused the sign-in: {started}")

    print(
        f"\nTo import these books, approve this sign-in:\n"
        f"    {started.get('verification_uri_complete') or started['verification_uri']}\n"
        f"    code: {started['user_code']}\n",
        file=out,
    )

    interval = int(started.get("interval", 5))
    deadline = time.monotonic() + SIGN_IN_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        time.sleep(interval)
        got = _http(
            metadata["token_endpoint"],
            form={
                "client_id": CLIENT_ID,
                "device_code": started["device_code"],
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            },
        )
        if "access_token" in got:
            return str(got["access_token"])
        error = got.get("error")
        if error == "slow_down":
            interval += 5
        elif error not in {"authorization_pending", None}:
            raise Refused("not_authenticated", f"the sign-in was refused: {error}")
    raise Refused("not_authenticated", "the sign-in was not approved in time")


def post(books: dict[str, Any], base: str, entity_id: str, token: str, *, out: Any) -> int:
    """Open the import, send the entries in batches, and reconcile (`IMP-01` to `IMP-08`).

    The client holds the loop counter, which is what keeps every request short without anything
    on the server remembering where an import stopped. A run that dies is resumed by running it
    again: each entry's key is derived from this file's fingerprint and the row's own reference,
    so what already landed replays and only the remainder posts (ADR-0029).
    """
    base = base.rstrip("/")
    opened = _http(
        f"{base}/entities/{entity_id}/imports",
        payload={
            key: books[key]
            for key in (
                "shape_version",
                "system",
                "fingerprint",
                "basis",
                "balances_basis",
                "commodity",
                "accounts",
            )
        },
        token=token,
    )
    if "import_id" not in opened:
        raise Refused(
            str(opened.get("code", "import_refused")), str(opened.get("message", opened))
        )
    print(
        f"opened import {opened['import_id']}:"
        f" {opened['accounts_created']} accounts created,"
        f" {opened['accounts_already_present']} already present",
        file=out,
    )

    entries = books["entries"]
    url = f"{base}/entities/{entity_id}/imports/{opened['import_id']}/entries"
    posted = replayed = 0
    refusals: list[dict[str, Any]] = []
    for start in range(0, len(entries), BATCH):
        chunk = entries[start : start + BATCH]
        done = _http(
            url,
            payload={
                "system": books["system"],
                "fingerprint": books["fingerprint"],
                "entries": chunk,
            },
            token=token,
        )
        if "posted" not in done:
            raise Refused(
                str(done.get("code", "import_refused")), str(done.get("message", done))
            )
        posted += done["posted"]
        replayed += done["replayed"]
        refusals.extend(done["refusals"])
        print(
            f"  {min(start + BATCH, len(entries))}/{len(entries)}"
            f"  posted {posted}, replayed {replayed}, skipped {len(refusals)}",
            file=out,
        )

    checked = _http(
        f"{base}/entities/{entity_id}/imports/{opened['import_id']}/reconciliation",
        payload={
            "balances": books["balances"],
            "statements": books["statements"],
            "journal_total": books["journal_total"],
        },
        token=token,
    )
    return _report(posted, replayed, refusals, checked, out=out)


def _report(
    posted: int, replayed: int, refusals: list[dict[str, Any]], checked: Any, *, out: Any
) -> int:
    """What happened, and whether it agreed. Amounts go to stdout, progress to stderr.

    `IMP-08` is the answer an operator needs: agreement demonstrated against the figures the
    source states for itself. Anything short of exact agreement is a finding, never a rounding
    to explain away (`NFR-01`).
    """
    print(f"\nposted {posted}, replayed {replayed}, skipped {len(refusals)}", file=out)
    for refusal in refusals[:20]:
        print(
            f"  skipped {refusal['reference']}: {refusal['code']} — {refusal['detail']}",
            file=out,
        )

    if "agreed" not in checked:
        raise Refused(
            str(checked.get("code", "import_refused")), str(checked.get("message", checked))
        )
    print(f"reconciled {checked['agreed']} of {checked['compared']} accounts exactly", file=out)
    for divergence in checked["divergences"]:
        print(
            f"  DIVERGES {divergence['account_code']}:"
            f" ours {divergence['ours']} theirs {divergence['theirs']}",
            file=out,
        )
    for statement in checked["statements"]:
        print(
            f"{statement['report']}: {statement['agreed']} agree,"
            f" {len(statement['divergences'])} diverge"
            f" (theirs {statement['their_basis']}, ours {statement['our_basis']})",
            file=out,
        )
        for divergence in statement["divergences"]:
            print(
                f"  DIVERGES {divergence['account_code']}:"
                f" ours {divergence['ours']} theirs {divergence['theirs']}",
                file=out,
            )
    diverged = bool(checked["divergences"]) or any(
        statement["divergences"] for statement in checked["statements"]
    )
    return 1 if (diverged or refusals) else 0


def for_mcp(books: dict[str, Any]) -> str:
    """The chart and the transactions, in the form the MCP import tools take.

    **An account is named by its position in the chart**, not by its path. 62 accounts named
    11,580 times are 270 KB of a 509 KB payload, so indexing them halves what the model has to
    emit: about 74,000 tokens against 404,000 as JSON.

    ISO dates rather than packed ones, because a model emits `2026-06-28` more reliably and the
    7,000 tokens saved are worth less than that. Descriptions kept, because they are `IMP-04`'s
    lineage. References explicit, because ADR-0029 derives the idempotency key from them and
    implying them from line order would break a retry that batched differently.
    """
    index = {account["code"]: at for at, account in enumerate(books["accounts"])}
    chart = [f"{a['code']}|{a['account_type']}|{a['parent']}" for a in books["accounts"]]
    entries = [
        "|".join(
            [
                entry["reference"],
                entry["transaction_date"],
                entry["description"].replace("|", " "),
            ]
            + [f"{index[line['account_code']]}~{line['amount']}" for line in entry["lines"]]
        )
        for entry in books["entries"]
    ]
    stated = [f"{b['account_code']}|{b['balance']}" for b in books["balances"]]
    printed = {
        statement["report"]: [
            f"{line['account_code']}|{line['balance']}" for line in statement["lines"]
        ]
        for statement in books["statements"]
    }
    return json.dumps(
        {
            "open_import": {
                "system": books["system"],
                "fingerprint": books["fingerprint"],
                "basis": books["basis"],
                "balances_basis": books["balances_basis"],
                "commodity": books["commodity"],
                "chart": chart,
            },
            "import_entries": entries,
            "reconcile_import": {
                # The journal's own TOTAL, which carries no accounting basis — the one figure
                # that holds however the reports beside it were run (ADR-0050). Absent where the
                # source printed none; never fabricated.
                "journal_total": (
                    f"{books['journal_total']['debits']}|{books['journal_total']['credits']}"
                    if books["journal_total"]
                    else None
                ),
                "balances": stated,
                "profit_and_loss": printed.get("profit_and_loss", []),
                "balance_sheet": printed.get("balance_sheet", []),
                "their_basis": next((s["basis"] for s in books["statements"]), "unknown"),
            },
        },
        separators=(",", ":"),
    )


def summarize(books: dict[str, Any]) -> str:
    """What a person needs to see before they agree to post it (`IMP-05`).

    Counts and account names, never amounts. The figures are the operator's own revenue and
    their clients' names; the model relaying this does not need them and should not carry them.
    """
    entries = books["entries"]
    untyped = [a["code"] for a in books["accounts"] if a["account_type"] == "unknown"]
    dates = sorted(entry["transaction_date"] for entry in entries)
    lines = [
        f"{books['system']}, {books['commodity']}",
        f"  {len(entries)} transactions, {sum(len(e['lines']) for e in entries)} posting lines",
        f"  {len(books['accounts'])} accounts",
        f"  covering {dates[0]} to {dates[-1]}" if dates else "  no dated entries",
        f"  entries {books['basis']} basis, stated balances {books['balances_basis']} basis",
    ]
    if untyped:
        lines.append(f"  {len(untyped)} accounts the source states no type for: {untyped}")
    if books["balances_basis"] not in {"unknown", books["basis"]}:
        lines.append(
            "  NOTE: the stated balances were run on a different basis from the journal,"
            " so the obligation accounts will differ by what is unsettled (ADR-0037)"
        )
    return "\n".join(lines)


def _flag(flags: list[str], name: str) -> str | None:
    return flags[flags.index(name) + 1] if name in flags else None


def main(argv: list[str]) -> int:
    if not argv or argv[0] in {"-h", "--help"}:
        print(__doc__)
        return 0 if argv else 1
    path, *flags = argv
    try:
        with open(path, "rb") as handle:  # noqa: PTH123 - stdlib only, no pathlib needed
            books = read(handle.read())

        if "--post" in flags:
            base = _flag(flags, "--post")
            entity_id = _flag(flags, "--entity")
            if not base or not entity_id:
                print("--post needs a CFOKit URL and --entity <id>", file=sys.stderr)
                return 1
            # The summary first, and to stderr, so a person sees what is about to happen while
            # they are being asked to approve it (`IMP-05`).
            print(summarize(books), file=sys.stderr)
            return post(books, base, entity_id, sign_in(base), out=sys.stderr)

        if "--mcp" in flags:
            print(for_mcp(books))
        elif "--summary" in flags:
            print(summarize(books))
        else:
            json.dump(books, sys.stdout, separators=(",", ":"))
    except Refused as refusal:
        print(f"{refusal.code}: {refusal}", file=sys.stderr)
        return 1
    except (zipfile.BadZipFile, ET.ParseError) as broken:
        print(f"unreadable_archive: {broken}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
