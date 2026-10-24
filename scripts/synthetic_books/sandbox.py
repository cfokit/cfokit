"""Validate the fixture against a QuickBooks Online sandbox company (ADR-0075).

    PYTHONPATH=scripts uv run python -m synthetic_books.sandbox post
    PYTHONPATH=scripts uv run python -m synthetic_books.sandbox validate

`post` sends every payload, in order, to an **empty** sandbox company. A payload QuickBooks
rejects stops the run: it means an event was modeled wrong, and the generator is fixed, never
the post. It resumes where it stopped: each payload's id is QuickBooks' `requestid`, and the ids
QuickBooks assigned are kept under `.local/qbo-sandbox/`.

`validate` asks the Reports API what QuickBooks makes of those postings — the journal, the
general ledger's totals, both statements, and the trial balance at every month end, on each
basis and under each rendering's settings — and compares it with what our writer put in the
archives. QuickBooks' answers and the differences are written under `.local/qbo-sandbox/`, which
git ignores: **nothing QuickBooks returns is ever committed**. What is committed is the record
that it agreed, `tests/fixtures/quickbooks/validation.json`, written only when every comparison
does.

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
is checked once, by hand, against a real Export Data download (`compare-export`).
"""

from __future__ import annotations

import base64
import difflib
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from synthetic_books.business import END, START
from synthetic_books.events import dumps
from synthetic_books.quickbooks_export import RENDERINGS, Rendering, month_ends
from synthetic_books.xlsx import contents, rows

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
                return json.loads(response.read(), parse_float=Decimal)
        except urllib.error.HTTPError as error:
            detail = error.read().decode(errors="replace")[:2000]
            raise SystemExit(f"{method} {path}: HTTP {error.code}\n{detail}") from None

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
        raise SystemExit(f"the company has no {subtype} account; escalate (ADR-0075)")
    return str(accounts[0]["Id"])


def current(sandbox: Sandbox, entity: str, entity_id: str | None) -> Json:
    if entity == "Preferences":
        return sandbox.call("GET", "preferences", {})["Preferences"]
    return sandbox.call("GET", f"{entity.lower()}/{entity_id}", {})[entity]


def post(sandbox: Sandbox) -> None:
    ids_file = sandbox.state / "ids.json"
    ids: dict[str, str] = json.loads(ids_file.read_text()) if ids_file.exists() else {}
    done: set[str] = set(ids.pop("$done", "").split(",")) - {""}
    payloads = [
        json.loads(line, parse_float=Decimal)
        for line in (FIXTURE / "generated" / "payloads.jsonl").read_text().splitlines()
    ]
    for payload in payloads:
        if payload["id"] in done:
            continue
        for target in _references(payload["body"]):
            if target.startswith("system:") and target not in ids:
                ids[target] = system_account(sandbox, target.removeprefix("system:"))
        body = resolve(payload["body"], ids)
        entity, operation = payload["entity"], payload["operation"]
        query = {"requestid": payload["id"]}
        if operation in ("update", "void"):
            existing = current(sandbox, entity, body.get("Id"))
            body = {"Id": existing["Id"], "SyncToken": existing["SyncToken"], **body}
            if operation == "update":
                body["sparse"] = True
            else:
                query["operation"] = "void"
        path = "preferences" if entity == "Preferences" else entity.lower()
        answer = sandbox.call("POST", path, query, encode(body))
        if payload["defines"]:
            ids[payload["defines"]] = str(answer[entity]["Id"])
        done.add(payload["id"])
        ids_file.write_text(json.dumps({**ids, "$done": ",".join(sorted(done))}))
        print(f"{payload['id']} {entity} {operation}: ok")
    print(f"posted {len(done)} of {len(payloads)} payloads")


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


# --- what our archives say, in the same terms -----------------------------------------------


def ours(rendering: Rendering, member: str) -> list[tuple[str, ...]]:
    archive = (FIXTURE / "archives" / rendering.name / "export.zip").read_bytes()
    grid = rows(contents(archive)[member])[5:]  # past the title and header rows
    body = [comparable(row) for row in grid if any(cell is not None for cell in row)]
    return [row for row in body if row and not row[0].startswith(("Wednesday,",))]


def our_trial_balances(rendering: Rendering) -> dict[str, list[tuple[str, ...]]]:
    path = FIXTURE / "archives" / rendering.name / "trial_balances.json"
    if not path.exists():
        path = FIXTURE / "archives" / "accrual" / "trial_balances.json"
    saved = json.loads(path.read_text())
    return {
        day: [comparable((r["account"], r["debit"], r["credit"])) for r in lines]
        for day, lines in saved.items()
    }


# --- validate -------------------------------------------------------------------------------


def differences(
    name: str, expected: list[tuple[str, ...]], actual: list[tuple[str, ...]]
) -> list[str]:
    left = [" | ".join(row) for row in expected]
    right = [" | ".join(row) for row in actual]
    return list(
        difflib.unified_diff(left, right, f"ours/{name}", f"quickbooks/{name}", lineterm="")
    )


def set_preferences(sandbox: Sandbox, rendering: Rendering) -> None:
    """The company's settings for this rendering: its fiscal year and its account numbers."""
    prefs = current(sandbox, "Preferences", None)
    body = {
        "Id": prefs["Id"],
        "SyncToken": prefs["SyncToken"],
        "sparse": True,
        "AccountingInfoPrefs": {
            "FiscalYearStartMonth": "January" if rendering.fiscal_start_month == 1 else "July",
            "UseAccountNumbers": rendering.numbers,
        },
    }
    sandbox.call("POST", "preferences", {}, encode(body))


def validate(sandbox: Sandbox) -> int:
    comparisons: dict[str, int] = {}
    failed: dict[str, int] = {}
    raw = sandbox.state / "reports"
    raw.mkdir(exist_ok=True)

    def check(name: str, expected: list[tuple[str, ...]], answer: Json) -> None:
        (raw / f"{name}.json").write_text(json.dumps(answer, default=str, indent=1))
        actual = [comparable(row) for row in flatten(answer)]
        diff = differences(name, expected, actual)
        comparisons[name] = len(expected)
        (raw / f"{name}.diff").write_text("\n".join(diff))
        if diff:
            failed[name] = sum(1 for line in diff if line.startswith(("+", "-")))
        print(f"{name}: {'agrees' if not diff else f'{failed[name]} lines differ'}")

    for rendering in RENDERINGS:
        set_preferences(sandbox, rendering)
        method = rendering.basis.title()
        start = (rendering.start or START).isoformat()
        span = {"start_date": start, "end_date": END.isoformat(), "accounting_method": method}
        check(
            f"{rendering.name}-journal",
            ours(rendering, "Journal.xlsx"),
            sandbox.report("JournalReport", **span),
        )
        check(
            f"{rendering.name}-profit-and-loss",
            ours(rendering, "Profit_and_loss.xlsx"),
            sandbox.report("ProfitAndLoss", **span),
        )
        as_of = {
            "start_date": START.isoformat(),
            "end_date": END.isoformat(),
            "accounting_method": method,
        }
        check(
            f"{rendering.name}-balance-sheet",
            ours(rendering, "Balance_sheet.xlsx"),
            sandbox.report("BalanceSheet", **as_of),
        )
        if rendering.start is None:
            months = our_trial_balances(rendering)
            for day in month_ends():
                check(
                    f"{rendering.name}-trial-balance-{day.isoformat()}",
                    months[day.isoformat()],
                    sandbox.report(
                        "TrialBalance", end_date=day.isoformat(), accounting_method=method
                    ),
                )
    set_preferences(sandbox, RENDERINGS[0])

    if failed:
        print(f"{len(failed)} of {len(comparisons)} comparisons differ; diffs in {raw}")
        return 1
    record = {
        "validated_on": datetime.now(UTC).date().isoformat(),
        "archives": {r.name: archive_digest(r) for r in RENDERINGS},
        "comparisons": len(comparisons),
        "rows_compared": sum(comparisons.values()),
        "result": "agrees",
    }
    (FIXTURE / "validation.json").write_text(json.dumps(record, indent=1) + "\n")
    print(f"all {len(comparisons)} comparisons agree; wrote {FIXTURE / 'validation.json'}")
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


def compare_export(path: Path, rendering_name: str) -> int:
    """Our archive against one Export Data download, cell by cell, report by report.

    The download is read from wherever it was saved and never copied into the repository. Cells
    that differ by nature — the time a report was run — are expected to differ and are listed.
    """
    rendering = next(r for r in RENDERINGS if r.name == rendering_name)
    theirs = contents(path.read_bytes())
    mine = contents((FIXTURE / "archives" / rendering.name / "export.zip").read_bytes())
    status = 0
    for member in sorted(set(theirs) | set(mine)):
        if member not in mine or member not in theirs:
            print(f"{member}: only in {'their export' if member in theirs else 'ours'}")
            status = 1
            continue
        actual = [comparable(row) for row in rows(theirs[member])]
        expected = [comparable(row) for row in rows(mine[member])]
        diff = differences(member, expected, actual)
        print(f"{member}: {'same cells' if not diff else f'{len(diff)} diff lines'}")
        for line in diff[:40]:
            print("   " + line)
        status = status or (1 if diff else 0)
    return status


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in ("post", "validate", "compare-export"):
        print(__doc__)
        return 2
    if argv[0] == "compare-export":
        return compare_export(Path(argv[1]), argv[2] if len(argv) > 2 else "accrual")
    sandbox = Sandbox()
    if argv[0] == "post":
        post(sandbox)
        return 0
    return validate(sandbox)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
