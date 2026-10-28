"""Validate the fixture against a QuickBooks Online sandbox company (ADR-0078).

    PYTHONPATH=scripts uv run python -m synthetic_books.sandbox post
    PYTHONPATH=scripts uv run python -m synthetic_books.sandbox validate

`post` sends every payload, in order, to an **empty** sandbox company. A payload QuickBooks
rejects stops the run: it means an event was modeled wrong, and the generator is fixed, never
the post. So does one QuickBooks accepts but keeps differently from how it was sent — a field
it dropped or changed, a void that left an amount — since that is a rejection made silently.
It resumes where it stopped: the ids QuickBooks assigned, and a digest of each payload posted,
are kept under `.local/qbo-sandbox/`. A payload that changed after it was posted stops the
run, because the company holds the old one: clear the company, delete that state, post again.
Each payload's id, with a token drawn when the state is first written, is QuickBooks'
`requestid`, so a retry is a replay rather than a second transaction, and a cleared company
never receives an answer QuickBooks remembers from before.

`validate` asks the Reports API what QuickBooks makes of those postings — the journal, the
general ledger, both statements, and the trial balance at every month end, on each basis and
under each rendering's settings, and A/R and A/P Aging Detail as of the books' last day — and
compares it with what our writer put in the archives. The
API reports by the company's fiscal year but cannot change it, so a person changes it in
QuickBooks between runs: each run compares the
renderings the company's settings allow, remembers those that agreed, and names the setting the
next one needs. The API prints account numbers only with "Show account numbers" set, and then
in a column the export does not have, so validation runs with it off and the numbered rendering
is left to `compare-export`, and the record says so. QuickBooks' answers and the
differences are written under `.local/qbo-sandbox/`, which git ignores: **nothing QuickBooks
returns is ever committed**. What is committed is the record that it agreed,
`tests/fixtures/quickbooks/validation.json`, written only when every rendering has.

Setting up a sandbox, and where the values below come from, is in `CONTRIBUTING.md`, under "The
synthetic QuickBooks fixture". Credentials come from the environment and are never printed or
committed: `QBO_REALM_ID` (the
sandbox company's id) and either `QBO_ACCESS_TOKEN`, an access token good for an hour, or
`QBO_CLIENT_ID`, `QBO_CLIENT_SECRET` and `QBO_REFRESH_TOKEN`, from which the tool gets access
tokens itself as each one expires. A refresh token lasts about 100 days, which suits a variable
set once in an environment's settings. Intuit may answer a refresh with a new refresh token;
the newest is kept under `.local/qbo-sandbox/`, readable by its owner only, and used in
preference to the variable. `QBO_BASE_URL` defaults to the sandbox host.

The layout — header rows, indentation, formulas, footers — is not something the API can show. It
is checked once, by hand, against a real Export Data download (`compare-export`), and each aging
report against a download of it (`compare-aging`).
"""

from __future__ import annotations

import base64
import difflib
import hashlib
import json
import os
import re
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterator, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from synthetic_books import business, quickbooks_books, quickbooks_export
from synthetic_books.business import END, START
from synthetic_books.events import PAYABLE, dumps
from synthetic_books.quickbooks import MONTHS
from synthetic_books.quickbooks_export import (
    AGING,
    COMPANY,
    CREDIT_NATURE,
    RENDERINGS,
    Rendering,
    Report,
    month_ends,
)
from synthetic_books.xlsx import cells, contents, values

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "quickbooks"
STATE = ROOT / ".local" / "qbo-sandbox"
MINOR_VERSION = "75"
PAUSE = 0.15  # seconds between calls: well inside 500 requests a minute per company

type Json = Any


# --- references -----------------------------------------------------------------------------


def resolve(value: Json, ids: dict[str, str]) -> Json:
    """A payload body with its placeholders replaced by the ids QuickBooks assigned.

    `{"$ref": "kind:key", ...}` becomes `{"value": id, ...}`; `{"$id": "kind:key"}` becomes the
    id. A placeholder nothing defined is an error, never a guess.
    """
    if isinstance(value, dict):
        if "$id" in value:
            return ids[value["$id"]]
        out = {k: resolve(v, ids) for k, v in value.items() if k != "$ref"}
        if "$ref" in value:
            out = {"value": ids[value["$ref"]], **out}
        return out
    if isinstance(value, list):
        return [resolve(item, ids) for item in value]
    return value


def encode(value: Json) -> bytes:
    """JSON with a `Decimal` as its exact digits, as the payloads were written."""
    return dumps(value).encode()


# --- the API --------------------------------------------------------------------------------


TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"  # noqa: S105 — a URL
TOKEN_LIFETIME = 50 * 60  # seconds; Intuit's access tokens last an hour
REFRESHING = ("QBO_CLIENT_ID", "QBO_CLIENT_SECRET", "QBO_REFRESH_TOKEN")


class Sandbox:
    def __init__(self) -> None:
        realm = os.environ.get("QBO_REALM_ID")
        if not realm:
            raise SystemExit("QBO_REALM_ID is not set; see this module's docstring")
        base = os.environ.get("QBO_BASE_URL", "https://sandbox-quickbooks.api.intuit.com")
        self.base = f"{base}/v3/company/{realm}"
        # The state directory is named by a hash, so a realm id never lands in a path either.
        self.state = STATE / hashlib.sha256(realm.encode()).hexdigest()[:12]
        self.state.mkdir(parents=True, exist_ok=True)
        self._token = os.environ.get("QBO_ACCESS_TOKEN", "")
        self._issued = time.monotonic()
        self._refreshes = all(os.environ.get(name) for name in REFRESHING)
        if not self._token and not self._refreshes:
            missing = [name for name in REFRESHING if not os.environ.get(name)]
            raise SystemExit(
                f"QBO_ACCESS_TOKEN is not set, and neither is {', '.join(missing)}; "
                "see this module's docstring"
            )
        if not self._token:
            self.refresh()

    def refresh(self) -> None:
        """A new access token from the refresh token, keeping the newest refresh token."""
        kept = self.state / "refresh_token"
        refresh_token = (
            kept.read_text().strip() if kept.exists() else os.environ["QBO_REFRESH_TOKEN"]
        )
        pair = f"{os.environ['QBO_CLIENT_ID']}:{os.environ['QBO_CLIENT_SECRET']}"
        request = urllib.request.Request(
            TOKEN_URL,
            data=urllib.parse.urlencode(
                {"grant_type": "refresh_token", "refresh_token": refresh_token}
            ).encode(),
            method="POST",
            headers={
                "Authorization": "Basic " + base64.b64encode(pair.encode()).decode(),
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
                answer = json.loads(response.read())
        except urllib.error.HTTPError as error:
            # Intuit's error body names the problem (`invalid_grant`); it carries no token.
            raise SystemExit(
                f"refreshing the access token failed: HTTP {error.code} "
                f"{error.read().decode(errors='replace')[:300]}"
            ) from None
        self._token = answer["access_token"]
        self._issued = time.monotonic()
        if answer.get("refresh_token") and answer["refresh_token"] != refresh_token:
            kept.write_text(answer["refresh_token"])
            kept.chmod(0o600)

    def call(
        self, method: str, path: str, query: dict[str, str], body: bytes | None = None
    ) -> Json:
        if self._refreshes and time.monotonic() - self._issued > TOKEN_LIFETIME:
            self.refresh()
        query = {"minorversion": MINOR_VERSION, **query}
        request = urllib.request.Request(  # noqa: S310 — the host is fixed above
            f"{self.base}/{path}?{urllib.parse.urlencode(query)}",
            data=body,
            method=method,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
        time.sleep(PAUSE)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
                answer = json.loads(response.read(), parse_float=Decimal)
        except urllib.error.HTTPError as error:
            detail = error.read().decode(errors="replace")[:2000]
            raise SystemExit(f"{method} {path}: HTTP {error.code}\n{detail}") from None
        if "Fault" in answer:  # QuickBooks refuses some requests with a 200
            raise SystemExit(f"{method} {path}: {json.dumps(answer['Fault'], default=str)}")
        return answer

    def query(self, statement: str) -> Json:
        return self.call("GET", "query", {"query": statement})

    def report(self, name: str, **params: str) -> Json:
        return self.call("GET", f"reports/{name}", params)


# --- post -----------------------------------------------------------------------------------


def system_account(sandbox: Sandbox, subtype: str) -> str:
    # The subtype comes from our own payloads, never from input.
    found = sandbox.query(f"select Id from Account where AccountSubType = '{subtype}'")  # noqa: S608
    accounts = found["QueryResponse"].get("Account", [])
    if not accounts:
        raise SystemExit(f"the company has no {subtype} account; escalate (ADR-0078)")
    return str(accounts[0]["Id"])


def default_account(sandbox: Sandbox, name: str) -> str:
    # The name comes from our own payloads, never from input.
    found = sandbox.query(f"select * from Account where Name = '{name}'")  # noqa: S608
    accounts = [a for a in found["QueryResponse"].get("Account", []) if not a["SubAccount"]]
    if not accounts:
        raise SystemExit(f"the company has no default account {name}; escalate (ADR-0078)")
    return str(accounts[0]["Id"])


def current(sandbox: Sandbox, entity: str, entity_id: str | None) -> Json:
    if entity == "Preferences":
        return sandbox.call("GET", "preferences", {})["Preferences"]
    return sandbox.call("GET", f"{entity.lower()}/{entity_id}", {})[entity]


# Where a person makes each setting the API ignores: Settings, Account and settings, Advanced.
BY_HAND = {
    "FirstMonthOfFiscalYear": "Accounting, First month of fiscal year",
    "UseAccountNumbers": "Chart of accounts, Enable account numbers",
    "AutoApplyCredit": "Automation, Automatically apply credits",
}


def require(sandbox: Sandbox, settings: Json) -> list[str]:
    """What a person must still change in QuickBooks for the company to have `settings`."""
    have = current(sandbox, "Preferences", None)
    return [
        f"{BY_HAND[field]}: {value}"
        for section, fields in settings.items()
        for field, value in fields.items()
        if have[section][field] != value
    ]


def by_hand(needed: list[str]) -> str:
    return (
        "the API ignores these settings, so set them in the sandbox company "
        "(Settings, Account and settings, Advanced), then run this again:\n  "
        + "\n  ".join(needed)
    )


def digest(payload: Json) -> str:
    return hashlib.sha256(encode(payload)).hexdigest()[:16]


def disagreements(sent: Json, kept: Json, where: str = "") -> list[str]:
    """The fields QuickBooks did not keep as sent. Lines are left to the reports to judge:
    QuickBooks numbers them and adds its own subtotal line."""
    out: list[str] = []
    for key, value in sent.items():
        if key in ("sparse", "SyncToken") or isinstance(value, list):
            continue
        if key not in kept:
            out.append(f"{where}{key} was dropped")
        elif isinstance(value, dict):
            out += disagreements(value, kept[key], f"{where}{key}.")
        elif isinstance(value, bool) or isinstance(kept[key], bool):
            if value != kept[key]:
                out.append(f"{where}{key} sent {value}, kept {kept[key]}")
        elif isinstance(value, int | Decimal):
            if Decimal(str(value)) != Decimal(str(kept[key])):
                out.append(f"{where}{key} sent {value}, kept {kept[key]}")
        elif str(value) != str(kept[key]):
            out.append(f"{where}{key} sent {value!r}, kept {kept[key]!r}")
    return out


def payloads() -> list[Json]:
    return [
        json.loads(line, parse_float=Decimal)
        for line in (FIXTURE / "generated" / "payloads.jsonl").read_text().splitlines()
    ]


def post(sandbox: Sandbox) -> None:
    ids_file = sandbox.state / "ids.json"
    state: Json = (
        json.loads(ids_file.read_text())
        if ids_file.exists()
        else {"run": secrets.token_hex(4), "ids": {}, "posted": {}}
    )
    ids: dict[str, str] = state["ids"]
    posted: dict[str, str] = state["posted"]
    stream = payloads()
    for payload in stream:
        if payload["id"] in posted:
            if posted[payload["id"]] != digest(payload):
                raise SystemExit(
                    f"{payload['id']} changed after it was posted, so the company holds the "
                    f"old one: clear the company, delete {sandbox.state}, and post again"
                )
            continue
        if payload["operation"] == "require":
            needed = require(sandbox, payload["body"])
            if needed:
                raise SystemExit(f"{payload['id']}: {by_hand(needed)}")
            posted[payload["id"]] = digest(payload)
            ids_file.write_text(json.dumps(state))
            print(f"{payload['id']} {payload['entity']} require: ok")
            continue
        for target in _references(payload["body"]):
            if target.startswith("system:") and target not in ids:
                ids[target] = system_account(sandbox, target.removeprefix("system:"))
            if target.startswith("default:") and target not in ids:
                ids[target] = default_account(sandbox, target.removeprefix("default:"))
        body = resolve(payload["body"], ids)
        entity, operation = payload["entity"], payload["operation"]
        query = {"requestid": f"{state['run']}-{payload['id']}"}
        if operation in ("update", "void"):
            existing = current(sandbox, entity, body.get("Id"))
            body = {"Id": existing["Id"], "SyncToken": existing["SyncToken"], **body}
            if operation == "update":
                body["sparse"] = True
            elif entity == "Invoice":
                query["operation"] = "void"
            else:  # a payment is voided by an update that includes the void
                body["sparse"] = True
                query |= {"operation": "update", "include": "void"}
        path = "preferences" if entity == "Preferences" else entity.lower()
        kept = sandbox.call("POST", path, query, encode(body))[entity]
        if payload["defines"]:
            ids[payload["defines"]] = str(kept["Id"])
        posted[payload["id"]] = digest(payload)
        ids_file.write_text(json.dumps(state))
        problems = disagreements(body, kept)
        if operation == "void" and Decimal(str(kept.get("TotalAmt", 0))) != 0:
            problems.append(f"the void left TotalAmt {kept['TotalAmt']}")
        if problems:
            raise SystemExit(
                f"{payload['id']} {entity} {operation}: QuickBooks accepted it but kept it "
                f"differently; the event is modeled wrong, so fix the generator:\n  "
                + "\n  ".join(problems)
            )
        print(f"{payload['id']} {entity} {operation}: ok")
    print(f"posted {len(posted)} of {len(stream)} payloads")


def _references(value: Json) -> Iterator[str]:
    if isinstance(value, dict):
        for key in ("$ref", "$id"):
            if key in value:
                yield str(value[key])
        for item in value.values():
            yield from _references(item)
    elif isinstance(value, list):
        for item in value:
            yield from _references(item)


# --- reading reports ------------------------------------------------------------------------


def flatten(report: Json) -> list[tuple[str, ...]]:
    """A Reports API answer as rows of cell text, in order: section headers, data and summaries.

    Every report the API returns nests the same way — a row is `Data` with `ColData`, or a
    `Section` with a `Header`, `Rows` and a `Summary` — so one walk reads them all.
    """
    out: list[tuple[str, ...]] = []

    def cells(row: Json) -> tuple[str, ...]:
        return tuple(str(cell.get("value", "")) for cell in row.get("ColData", []))

    def walk(container: Json) -> None:
        for row in container.get("Rows", {}).get("Row", []):
            if "Header" in row:
                out.append(cells(row["Header"]))
            if row.get("type") == "Data" or ("ColData" in row and "Rows" not in row):
                out.append(cells(row))
            if "Rows" in row:
                walk(row)
            if "Summary" in row:
                out.append(cells(row["Summary"]))

    walk(report)
    return out


def figure(text: str | None) -> Decimal | None:
    """A cell as a figure, or `None` where it holds none."""
    if text is None or text.strip() == "":
        return None
    try:
        return Decimal(text.replace(",", ""))
    except ArithmeticError:
        return None


def comparable(row: Sequence[str | None]) -> tuple[str, ...]:
    """A row reduced to what both sides state: trimmed text, and figures as exact decimals with
    zeros and blanks alike. Indentation is layout; the API carries none."""
    out: list[str] = []
    for cell in row:
        number = figure(cell)
        if number is not None:
            out.append("" if number == 0 else format(number.normalize(), "f"))
        else:
            out.append("" if cell is None else cell.strip())
    while out and out[-1] == "":
        out.pop()
    return tuple(out)


def api_date(text: str) -> str:
    """A date as the export prints it. The API writes `0-00-00` where a row has none."""
    if text == "0-00-00":
        return ""
    if len(text) == 10 and text[4] == text[7] == "-":
        return f"{text[5:7]}/{text[8:10]}/{text[:4]}"
    return text


def api_rows(answer: Json) -> list[tuple[str, ...]]:
    """An answer's rows in the archive's terms, without the blank rows the API puts between a
    journal's transactions."""
    out = [comparable([api_date(cell) for cell in row]) for row in flatten(answer)]
    return [row for row in out if row]


def amount(text: str | None) -> Decimal:
    return figure(text) or Decimal(0)


def ledger_rows(items: list[tuple[Any, ...]]) -> list[tuple[str, ...]]:
    """A general ledger's entries as rows to compare, whoever wrote it.

    QuickBooks sorts a ledger by date and leaves a day's entries in no settled order: the same
    day comes back differently for different date ranges. So a day's entries are compared as a
    set, and the running balance where the day ends.
    """
    out: list[tuple[str, ...]] = []
    day: list[tuple[Any, ...]] = []

    def flush() -> None:
        if day:
            out.extend(sorted((p, d, *f, format(a, "f")) for p, d, f, a, _ in day))
            out.append((day[-1][0], day[-1][1], "balance", format(day[-1][4], "f")))
            day.clear()

    for kind, *rest in items:
        if kind == "entry":
            if day and day[-1][:2] != tuple(rest[:2]):
                flush()
            day.append(tuple(rest))
        else:
            flush()
            out.append(tuple(str(part) for part in rest))
    flush()
    return [comparable(row) for row in out]


def api_ledger(answer: Json) -> list[tuple[str, ...]]:
    """The API's general ledger, each account named by its full path as the export names it."""
    items: list[tuple[Any, ...]] = []

    def walk(container: Json, path: str) -> None:
        for row in container.get("Rows", {}).get("Row", []):
            here = path
            if "Header" in row:
                leaf = row["Header"]["ColData"][0]["value"]
                here = f"{path}:{leaf}" if path else leaf
            if "ColData" in row:
                c = [str(cell.get("value", "")) for cell in row["ColData"]]
                if c[0] == "Beginning Balance":
                    items.append(("begin", path, "Beginning Balance", amount(c[7])))
                else:  # the API's Split, which the export does not print, is left out
                    fields = tuple(c[1:5])
                    items.append(
                        ("entry", path, api_date(c[0]), fields, amount(c[6]), amount(c[7]))
                    )
            if "Rows" in row:
                walk(row, here)
            if "Summary" in row:
                c = [str(cell.get("value", "")) for cell in row["Summary"]["ColData"]]
                own = c[0].removeprefix("Total for ")
                suffix = " with sub-accounts" if own.endswith(" with sub-accounts") else ""
                label = c[0]
                if own.removesuffix(suffix) == here.rsplit(":", 1)[-1]:
                    label = f"Total for {here}{suffix}"
                items.append(("total", label, amount(c[6])))

    walk(answer, "")
    return ledger_rows(items)


# --- what our archives say, in the same terms -----------------------------------------------


def grid(rendering: Rendering, member: str) -> list[list[str | None]]:
    """A member's body, past its title and header rows, each formula worked out."""
    archive = (FIXTURE / "archives" / rendering.name / "export.zip").read_bytes()
    return values(contents(archive)[member])[5:]


def ours(rendering: Rendering, member: str) -> list[tuple[str, ...]]:
    body = [comparable(row) for row in grid(rendering, member)]
    body = [row for row in body if row and not row[0].startswith(("Wednesday,",))]
    if member == "Journal.xlsx":  # the first column holds nothing but the TOTAL label
        body = [(row[0] or row[1], *row[2:]) if len(row) > 1 else row for row in body]
    return body


def our_ledger(rendering: Rendering) -> list[tuple[str, ...]]:
    """Our general ledger in the API's terms: each amount on the account's natural side, as
    the API states it, rather than as a debit or a credit."""
    report = Report(quickbooks_books.record(COMPANY, business.write()), rendering)
    return ledger_of(report, grid(rendering, "General_ledger.xlsx"))


def ledger_of(report: Report, ledger: list[list[str | None]]) -> list[tuple[str, ...]]:
    """A general ledger as the export lays it out, read back into its entries: each account
    named by its leaf, indented three spaces a level, and a parent's own total a level in."""
    sign = {
        report.path(k): -1 if report.type_of(k) in CREDIT_NATURE else 1
        for k in report.books.accounts
    }
    items: list[tuple[Any, ...]] = []
    open_: list[str] = []  # the open accounts' paths, one a level

    def leaf(path: str) -> str:
        return path.rsplit(":", 1)[-1]

    for row in ledger:
        c = [*row, *[None] * (10 - len(row))]
        raw = c[0] or ""
        label, level = raw.strip(), (len(raw) - len(raw.lstrip(" "))) // 3
        if label.startswith("Total for "):
            name = label.removeprefix("Total for ")
            suffix = " with sub-accounts" if name.endswith(" with sub-accounts") else ""
            own = name.removesuffix(suffix)
            if level < len(open_) and leaf(open_[level]) == own:
                path = open_[level]
                del open_[level:]
            elif 0 < level <= len(open_) and leaf(open_[level - 1]) == own:
                path = open_[level - 1]  # a parent's own entries, totalled a level in
            else:
                raise ValueError(f"{label!r} totals no open account")
            change = sign[path] * (amount(c[7]) - amount(c[8]))
            items.append(("total", f"Total for {path}{suffix}", change))
        elif label and RUN_TIME.match(label) is None and not any(c[1:]):
            del open_[level:]
            open_.append(f"{open_[-1]}:{label}" if open_ else label)
        elif (c[1] or "").strip() == "Beginning Balance":  # indented to its account's level
            items.append(("begin", open_[-1], "Beginning Balance", amount(c[9])))
        elif c[1]:
            if c[6] not in (open_[-1], None):
                raise ValueError(f"an entry under {open_[-1]} names {c[6]}")
            fields = tuple(cell or "" for cell in c[2:6])
            change = sign[open_[-1]] * (amount(c[7]) - amount(c[8]))
            items.append(("entry", open_[-1], c[1], fields, change, amount(c[9])))
    return ledger_rows(items)


def our_trial_balances(rendering: Rendering) -> dict[str, list[tuple[str, ...]]]:
    path = FIXTURE / "archives" / rendering.name / "trial_balances.json"
    if not path.exists():
        path = FIXTURE / "archives" / "accrual" / "trial_balances.json"
    saved = json.loads(path.read_text())
    out: dict[str, list[tuple[str, ...]]] = {}
    for day, lines in saved.items():
        debit = sum((Decimal(r["debit"]) for r in lines), Decimal(0))
        credit = sum((Decimal(r["credit"]) for r in lines), Decimal(0))
        out[day] = [
            *(comparable((r["account"], r["debit"], r["credit"])) for r in lines),
            comparable(("TOTAL", format(debit, "f"), format(credit, "f"))),
        ]
    return out


def by_group(rows: list[tuple[str, ...]]) -> list[tuple[str, ...]]:
    """An aging with each group's rows in one order. The API lists rows of one due date in the
    reverse of the export's order, so neither side's order within a group is compared; the
    export's is checked against a download (`compare-aging`)."""
    out: list[tuple[str, ...]] = []
    group: list[tuple[str, ...]] = []
    for row in rows:
        if len(row) > 1 and row[0] == "" and DATE.match(row[1]):
            group.append(row)
            continue
        out += sorted(group)
        group.clear()
        out.append(row)
    return out + sorted(group)


def our_aging(file: str, account: str) -> list[tuple[str, ...]]:
    """Our aging past its title and header rows, without its footer, and on A/P without the
    Past due column, which counts to the day the report is run."""
    body = [comparable(row) for row in values((FIXTURE / "aging" / file).read_bytes())[5:]]
    body = [row for row in body if row and not AGING_RUN_TIME.match(row[0])]
    if account == PAYABLE:
        body = [row[:6] + row[7:] if len(row) > 6 else row for row in body]
    return by_group(body)


def api_aging(answer: Json) -> list[tuple[str, ...]]:
    """An aging answer in the export's terms: its groups named as the export names them, and
    A/P's vendor where the export prints it, without the Past due the API counts to today."""
    titles = [c["MetaData"][0]["Value"] for c in answer["Columns"]["Column"]]
    keep = ["tx_date", "txn_type", "doc_num", "cust_name", "due_date", "subt_amount"]
    keep += ["subt_open_bal"]
    if "vend_name" in titles:
        keep = ["tx_date", "txn_type", "doc_num", "vend_name", "due_date"]
        keep += ["subt_neg_amount", "subt_neg_open_bal"]
    out: list[tuple[str, ...]] = []
    for row in flatten(answer):
        cell = dict(zip(titles, row, strict=True))
        label = row[0].replace("Current", "CURRENT")
        if DATE.match(api_date(row[0])):
            out.append(comparable(["", *(api_date(cell[k]) for k in keep)]))
        elif label.startswith(("Total for ", "TOTAL")):
            amount, open_ = cell[keep[5]], cell[keep[6]]
            out.append(comparable([label, *[""] * 5, amount, open_]))
        else:
            out.append(comparable([label]))
    return by_group(out)


def aging_digest() -> str:
    """The aging reports' identity by content, as an archive's."""
    digest = hashlib.sha256()
    for file, _ in sorted(AGING):
        workbook = contents((FIXTURE / "aging" / file).read_bytes())
        for part in sorted(workbook):
            digest.update(f"{file}/{part}\n".encode())
            digest.update(workbook[part])
    return digest.hexdigest()


# --- validate -------------------------------------------------------------------------------


def differences(
    name: str, expected: list[tuple[str, ...]], actual: list[tuple[str, ...]]
) -> list[str]:
    left = [" | ".join(row) for row in expected]
    right = [" | ".join(row) for row in actual]
    return list(
        difflib.unified_diff(left, right, f"ours/{name}", f"quickbooks/{name}", lineterm="")
    )


# Renderings the Reports API cannot show, and why: they are checked by `compare-export` alone.
NOT_COMPARED = {
    "account-numbers": (
        'the Reports API prints account numbers only with "Show account numbers" set, which'
        " validation runs without; compare-export is its check"
    ),
}


def settings(rendering: Rendering) -> Json:
    """The settings QuickBooks must have to report this rendering: its fiscal year, or the
    company's own as the adapter requires it."""
    company = next(p for p in payloads() if p["operation"] == "require")["body"]
    month = rendering.fiscal_start_month
    own = company["AccountingInfoPrefs"]["FirstMonthOfFiscalYear"]
    return {
        "AccountingInfoPrefs": {"FirstMonthOfFiscalYear": MONTHS[month - 1] if month else own}
    }


def validate(sandbox: Sandbox) -> int:
    """Compare every rendering the company's settings allow now, and remember those that agree.

    The API cannot change the settings a rendering prints under, so a person changes them
    between runs; `validation.json` is written once every rendering, as it is now, has agreed.
    """
    progress_file = sandbox.state / "validated.json"
    progress: dict[str, Json] = (
        json.loads(progress_file.read_text()) if progress_file.exists() else {}
    )
    raw = sandbox.state / "reports"
    raw.mkdir(exist_ok=True)
    waiting: list[tuple[Rendering, list[str]]] = []
    failed: dict[str, int] = {}

    def compare(
        name: str,
        expected: list[tuple[str, ...]],
        answer: Json,
        counted: dict[str, int],
        read: Callable[[Json], list[tuple[str, ...]]] = api_rows,
    ) -> None:
        (raw / f"{name}.json").write_text(json.dumps(answer, default=str, indent=1))
        actual = read(answer)
        diff = differences(name, expected, actual)
        counted[name] = len(expected)
        (raw / f"{name}.diff").write_text("\n".join(diff))
        if diff:
            failed[name] = sum(1 for line in diff if line.startswith(("+", "-")))
        print(f"{name}: {'agrees' if not diff else f'{failed[name]} lines differ'}")

    for rendering in RENDERINGS:
        if rendering.name in NOT_COMPARED:
            print(f"{rendering.name}: not compared; {NOT_COMPARED[rendering.name]}")
            continue
        archive = archive_digest(rendering)
        if progress.get(rendering.name, {}).get("archive") == archive:
            print(f"{rendering.name}: agreed already")
            continue
        needed = require(sandbox, settings(rendering))
        if needed:
            waiting.append((rendering, needed))
            continue
        comparisons: dict[str, int] = {}
        method = rendering.basis.title()
        # As Export Data runs each report: over all dates, or from the rendering's start.
        if rendering.start is None:
            span = {"date_macro": "All", "accounting_method": method}
            as_of = span
        else:
            span = {
                "start_date": rendering.start.isoformat(),
                "end_date": END.isoformat(),
                "accounting_method": method,
            }
            as_of = {**span, "start_date": START.isoformat()}
        compare(
            f"{rendering.name}-journal",
            ours(rendering, "Journal.xlsx"),
            sandbox.report("JournalReport", **span),
            comparisons,
        )
        compare(
            f"{rendering.name}-profit-and-loss",
            ours(rendering, "Profit_and_loss.xlsx"),
            sandbox.report("ProfitAndLoss", **span),
            comparisons,
        )
        compare(
            f"{rendering.name}-general-ledger",
            our_ledger(rendering),
            sandbox.report("GeneralLedger", **span),
            comparisons,
            api_ledger,
        )
        compare(
            f"{rendering.name}-balance-sheet",
            ours(rendering, "Balance_sheet.xlsx"),
            sandbox.report("BalanceSheet", **as_of),
            comparisons,
        )
        compare(
            f"{rendering.name}-trial-balance",
            ours(rendering, "Trial_balance.xlsx"),
            sandbox.report("TrialBalance", **as_of),
            comparisons,
        )
        if rendering.start is None:
            months = our_trial_balances(rendering)
            for day in month_ends():
                compare(
                    f"{rendering.name}-trial-balance-{day.isoformat()}",
                    months[day.isoformat()],
                    # Without a start the API reports the fiscal year to today, whatever
                    # the end; income and expense are the fiscal year's to the end either way.
                    sandbox.report(
                        "TrialBalance",
                        start_date=START.isoformat(),
                        end_date=day.isoformat(),
                        accounting_method=method,
                    ),
                    comparisons,
                )
        if not any(name in failed for name in comparisons):
            progress[rendering.name] = {
                "archive": archive,
                "comparisons": len(comparisons),
                "rows": sum(comparisons.values()),
            }
            progress_file.write_text(json.dumps(progress, indent=1))

    aging = aging_digest()
    if progress.get("aging", {}).get("archive") == aging:
        print("aging: agreed already")
    else:
        comparisons = {}
        for file, account in AGING:
            report = "AgedPayableDetail" if account == PAYABLE else "AgedReceivableDetail"
            compare(
                f"aging-{'payable' if account == PAYABLE else 'receivable'}",
                our_aging(file, account),
                sandbox.report(report, report_date=END.isoformat(), aging_method="Report_Date"),
                comparisons,
                api_aging,
            )
        if not any(name in failed for name in comparisons):
            progress["aging"] = {
                "archive": aging,
                "comparisons": len(comparisons),
                "rows": sum(comparisons.values()),
            }
            progress_file.write_text(json.dumps(progress, indent=1))

    if failed:
        print(f"{len(failed)} comparisons differ; diffs in {raw}")
        return 1
    if waiting:
        rendering, needed = waiting[0]
        others = ", ".join(r.name for r, _ in waiting[1:])
        print(f"{rendering.name} waits on its settings: {by_hand(needed)}")
        if others:
            print(f"after it: {others}")
        return 1
    compared = [r.name for r in RENDERINGS if r.name not in NOT_COMPARED] + ["aging"]
    record = {
        "validated_on": datetime.now(UTC).date().isoformat(),
        "archives": {name: progress[name]["archive"] for name in compared},
        "not_compared": NOT_COMPARED,
        "comparisons": sum(progress[name]["comparisons"] for name in compared),
        "rows_compared": sum(progress[name]["rows"] for name in compared),
        "result": "agrees",
    }
    (FIXTURE / "validation.json").write_text(json.dumps(record, indent=1) + "\n")
    print(f"every rendering agrees; wrote {FIXTURE / 'validation.json'}")
    return 0


def archive_digest(rendering: Rendering) -> str:
    """The archive's identity by content, not bytes: a zip's bytes depend on its zlib."""
    members = contents((FIXTURE / "archives" / rendering.name / "export.zip").read_bytes())
    digest = hashlib.sha256()
    for name in sorted(members):
        workbook = contents(members[name])
        for part in sorted(workbook):
            digest.update(f"{name}/{part}\n".encode())
            digest.update(workbook[part])
    return digest.hexdigest()


# --- the layout, against one real download --------------------------------------------------


# Cells an export and ours differ in by nature, listed rather than compared.
BY_NATURE = (
    "each member's first row: the company's name, which is the sandbox company's own",
    "each footer's time: when the report was run",
)
RUN_TIME = re.compile(r"\w+day, \w{3} \d{2}, \d{4} \d{2}:\d{2}:\d{2} [AP]M GMT[+-]\d+")
AGING_RUN_TIME = re.compile(r" ?\w+day, \w+ \d{1,2}, \d{4} \d{2}:\d{2} [AP]M GMT\w*")
DATE = re.compile(r"\d{2}/\d{2}/\d{4}$")


def exact(data: bytes) -> list[tuple[str, ...]]:
    """A worksheet's cells exactly, but for what differs by nature: a string as it is, spaces
    and all; a number by its value, however many zeros it is written with; a formula as its
    text."""
    out: list[tuple[str, ...]] = []
    for at, row in enumerate(cells(data)):
        text = [
            ""
            if cell is None
            else f"={cell[1]}"
            if cell[0] == "f"
            else format(Decimal(cell[1]).normalize(), "f")
            if cell[0] == "n"
            else cell[1]
            for cell in row
        ]
        while text and text[-1] == "":
            text.pop()
        if at == 0 and text:
            text[0] = "<company>"
        if text and RUN_TIME.match(text[0]):
            text[0] = RUN_TIME.sub("<run time>", text[0])
        out.append(tuple(text))
    return out


def settled(ledger: list[tuple[str, ...]]) -> list[tuple[str, ...]]:
    """A general ledger with each day's entries in one order, and the balance the day ends on.
    QuickBooks writes a day's entries in no settled order, so neither side's is compared."""
    out: list[tuple[str, ...]] = []
    day: list[tuple[str, ...]] = []

    def flush() -> None:
        if day:
            out.extend(sorted(row[:9] for row in day))
            out.append(("", day[-1][1], "<the day ends on>", *day[-1][9:]))
            day.clear()

    for row in ledger:
        if len(row) > 1 and DATE.match(row[1]):
            if day and day[-1][1] != row[1]:
                flush()
            day.append(row)
        else:
            flush()
            out.append(row)
    flush()
    return out


def compare_export(path: Path, rendering_name: str, *, numbers_shown: bool = False) -> int:
    """Our archive against one Export Data download, cell by cell, member by member.

    The download is read from wherever it was saved and never copied into the repository. The
    cells that differ by nature are listed, not compared; a general ledger's days are compared
    as sets, because QuickBooks orders a day's entries differently from one run to the next.

    `numbers_shown` compares a download made with "Show account numbers" set against the
    rendering with numbers, written for the comparison and not committed: how numbers print is
    checked on its own, so a rendering checked with them is checked without them too.
    """
    rendering = next(r for r in RENDERINGS if r.name == rendering_name)
    theirs = contents(path.read_bytes())
    if numbers_shown and not rendering.numbers:
        books = quickbooks_books.record(COMPANY, business.write())
        numbered = Rendering(
            rendering.name,
            basis=rendering.basis,
            numbers=True,
            start=rendering.start,
            fiscal_start_month=rendering.fiscal_start_month,
        )
        mine = contents(quickbooks_export.export(books, numbered))
    else:
        mine = contents((FIXTURE / "archives" / rendering.name / "export.zip").read_bytes())
    print("not compared, by nature: " + "; ".join(BY_NATURE))
    status = 0
    for member in sorted(set(theirs) | set(mine)):
        if member not in mine or member not in theirs:
            print(f"{member}: only in {'their export' if member in theirs else 'ours'}")
            status = 1
            continue
        actual, expected = exact(theirs[member]), exact(mine[member])
        if member == "General_ledger.xlsx":
            actual, expected = settled(actual), settled(expected)
        diff = differences(member, expected, actual)
        print(f"{member}: {'same cells' if not diff else f'{len(diff)} diff lines'}")
        for line in diff[:40]:
            print("   " + line)
        status = status or (1 if diff else 0)
    return status


def compare_aging(path: Path) -> int:
    """Our aging report against a download of it, cell by cell, in order. Which report the
    download is, is read from its title. The company, the time it was run and each Past due,
    which counts to that time, differ by nature and are not compared."""
    theirs = path.read_bytes()
    title = cells(theirs)[1][0]
    payable = title is not None and title[1].startswith("A/P")
    file = next(f for f, account in AGING if (account == PAYABLE) == payable)
    mine = (FIXTURE / "aging" / file).read_bytes()

    def normal(data: bytes) -> list[tuple[str, ...]]:
        out: list[tuple[str, ...]] = []
        for row in exact(data):
            text = list(row)
            if text and AGING_RUN_TIME.fullmatch(text[0]):
                text[0] = "<run time>"
            if payable and len(text) > 6 and DATE.match(text[1]) and text[6]:
                text[6] = "<days to the run time>"
            out.append(tuple(text))
        return out

    print("not compared, by nature: the company, the time the report was run, each Past due")
    diff = differences(file, normal(mine), normal(theirs))
    print(f"{file}: {'same cells' if not diff else f'{len(diff)} diff lines'}")
    for line in diff[:40]:
        print("   " + line)
    return 1 if diff else 0


def main(argv: list[str]) -> int:
    if argv and argv[0] == "compare-aging" and len(argv) == 2:
        return compare_aging(Path(argv[1]))
    if not argv or argv[0] not in ("post", "validate", "compare-export"):
        print(__doc__)
        return 2
    if argv[0] == "compare-export":
        rest = [arg for arg in argv[2:] if arg != "--numbers-shown"]
        return compare_export(
            Path(argv[1]),
            rest[0] if rest else "accrual",
            numbers_shown="--numbers-shown" in argv[2:],
        )
    sandbox = Sandbox()
    if argv[0] == "post":
        post(sandbox)
        return 0
    return validate(sandbox)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
