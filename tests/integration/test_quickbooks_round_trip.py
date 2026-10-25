"""The QuickBooks fixture's round trip into CFOKit (ADR-0079).

Each archive's reading — what the web client's reader made of it, committed beside it — is
imported through the import endpoints as a person's import is, in the three calls and batches
of `web/src/start/importBooks.ts`, into a company of its own. Then every catalog case of the
data and archive categories runs its check against what CFOKit holds. The file cases are the
reader's to refuse, and are checked in `web/src/quickbooks/fixture.test.ts`.

**Every expected value is QuickBooks' or the catalog's, never the reading's** (ADR-0079 § 4,
ADR-0036 § 5): the month-end trial balances and the figures the archive states, which the
validation record says QuickBooks agreed with, and the outcomes the catalog names. A failing
case is a finding about the reader or the import, not a test to adjust.
"""

from __future__ import annotations

import calendar
import csv
import io
import json
import os
import tomllib
import uuid
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from synthetic_books.quickbooks_export import RENDERINGS
from synthetic_books.xlsx import contents, values

from cfokit.ledger.config import Settings
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.administration import create_entity
from cfokit.ledger.service.principal import ActorClass, Principal
from cfokit.server import rest_app

pytestmark = pytest.mark.integration

FIXTURE = Path(__file__).parents[1] / "fixtures" / "quickbooks"
PERSON = Principal(id="user:round-trip", actor_class=ActorClass.PERSON)
BATCH = 500  # entries a request, as the web client sends them

CATALOG: dict[str, dict[str, Any]] = {
    case["id"]: case for case in tomllib.loads((FIXTURE / "catalog.toml").read_text())["case"]
}
MANIFEST: dict[str, dict[str, Any]] = json.loads(
    (FIXTURE / "generated" / "manifest.json").read_text()
)["cases"]
EVENTS: dict[str, dict[str, Any]] = {
    event["id"]: event
    for event in map(
        json.loads, (FIXTURE / "generated" / "events.jsonl").read_text().splitlines()
    )
}
CHECKED = sorted(case_id for case_id, case in CATALOG.items() if case["category"] != "file")
# Cases CFOKit cannot hold yet, each with what it lacks. Strict, so a case that starts passing
# fails the suite until it comes off this list.
NOT_YET = {
    "d-cash-year-boundary": (
        "a cash-basis company's statements recognize income on settlement (AR-16); CFOKit's"
        " reports present every company's books on accrual, whatever basis it declared"
    ),
}
BALANCE_SHEET = {"asset", "liability", "equity"}
CREDIT_NATURE = {"liability", "equity", "income"}


class StubAuthenticator:
    """Stands in for the issuer, not the verification: a person's token, with its audience."""

    def claims_for(self, credential: str | None) -> dict[str, Any]:
        return {
            "sub": PERSON.id,
            "azp": "cfokit-web",
            "iss": "http://localhost:8180/realms/cfokit",
            "aud": "cfokit-ledger",
        }


@dataclass
class Imported:
    """One archive's reading, imported into a company of its own, and what CFOKit then holds."""

    archive: str
    client: TestClient
    entity: str
    reading: dict[str, Any]
    refusals: list[dict[str, Any]]
    reconciliation: dict[str, Any]
    fiscal_start_month: int
    chart: dict[str, str]  # code -> type, every account including those with nothing posted
    journal: list[dict[str, str]]

    def get(self, path: str, **query: str) -> dict[str, Any]:
        response = self.client.get(f"/entities/{self.entity}/{path}", params=query)
        assert response.status_code == 200, response.text
        result: dict[str, Any] = response.json()
        return result

    def fiscal_year_start(self, day: date) -> date:
        year = day.year if day.month >= self.fiscal_start_month else day.year - 1
        return date(year, self.fiscal_start_month, 1)

    def earnings(self, since: date, as_of: date) -> Decimal:
        """Net income over the span, debit positive, from CFOKit's own profit and loss."""
        if as_of < since:
            return Decimal(0)
        report = self.get("profit-and-loss", since=since.isoformat(), as_of=as_of.isoformat())
        return -Decimal(report["net_income"])

    def balance(self, account: str, day: date) -> Decimal:
        """CFOKit's balance for the account at `day`, debit positive, as QuickBooks presents a
        trial balance: a balance-sheet account all time; income and expense from the fiscal
        year's start. QuickBooks closes each earlier year into Retained Earnings when it
        reports; CFOKit closes a year only when a person does (`LED-12`), so its Retained
        Earnings is presented with the earlier years' earnings its own profit and loss reports.
        """
        kind = self.chart[account]
        year_start = self.fiscal_year_start(day)
        if kind in BALANCE_SHEET:
            lines = self.get("trial-balance", as_of=day.isoformat())["lines"]
            found = {
                line["code"]: Decimal(line["debit"] or 0) - Decimal(line["credit"] or 0)
                for line in lines
            }
            figure = found.get(account, Decimal(0))
            if account == "Retained Earnings":
                first = date.fromisoformat(min(event["date"] for event in EVENTS.values()))
                figure += self.earnings(first, year_start - timedelta(days=1))
            return figure
        report = self.get(
            "profit-and-loss", since=year_start.isoformat(), as_of=day.isoformat()
        )
        for line in [*report["income"], *report["expenses"]]:
            if line["code"] == account:
                amount = Decimal(line["amount"])
                return -amount if line["account_type"] in CREDIT_NATURE else amount
        return Decimal(0)


def imported(client: TestClient, database: Database, archive: str) -> Imported:
    """The archive's reading, imported as the web client imports it."""
    reading: dict[str, Any] = json.loads(
        (FIXTURE / "archives" / archive / "read.json").read_text()
    )
    assert "refused" not in reading, f"the reader refused {archive}: {reading.get('refused')}"
    books, company = reading["books"], reading["company"]
    rendering = next(r for r in RENDERINGS if r.name == archive)
    own = next(e["start_month"] for e in EVENTS.values() if e["kind"] == "set_fiscal_year")
    start = rendering.fiscal_start_month or own
    end_month = (start - 2) % 12 + 1
    entity = create_entity(
        database,
        principal=PERSON,
        request_id=f"round-trip-{archive}",
        slug=f"round-trip-{archive}-{uuid.uuid4().hex[:8]}",
        name=company["name"],
        accounting_basis=company["basis"],
        fiscal_year_end_month=end_month,
        fiscal_year_end_day=calendar.monthrange(2001, end_month)[1],
        functional_currency=books["commodity"],
        time_zone="UTC",
    ).entity_id

    base = f"/entities/{entity}/imports"
    keys = ("shape_version", "system", "fingerprint", "basis", "balances_basis", "commodity")
    opened = client.post(
        base, json={**{k: books[k] for k in keys}, "accounts": books["accounts"]}
    )
    assert opened.status_code == 201, opened.text
    at = f"{base}/{opened.json()['import_id']}"
    refusals: list[dict[str, Any]] = []
    for first in range(0, len(books["entries"]), BATCH):
        batch = {
            "system": books["system"],
            "fingerprint": books["fingerprint"],
            "entries": books["entries"][first : first + BATCH],
        }
        posted = client.post(f"{at}/entries", json=batch)
        assert posted.status_code == 200, posted.text
        refusals += posted.json()["refusals"]
    reconciled = client.post(
        f"{at}/reconciliation",
        json={
            "balances": books["balances"],
            "journal_total": books["journal_total"],
            "statements": books["statements"],
        },
    )
    assert reconciled.status_code == 201, reconciled.text

    exported = client.get(f"/entities/{entity}/interchange-export")
    assert exported.status_code == 200, exported.text
    with zipfile.ZipFile(io.BytesIO(exported.content)) as archive_file:

        def table(name: str) -> list[dict[str, str]]:
            return list(csv.DictReader(io.StringIO(archive_file.read(name).decode())))

        chart = {row["code"]: row["type"] for row in table("accounts.csv")}
        journal = table("journal.csv")
    return Imported(
        archive=archive,
        client=client,
        entity=entity,
        reading=reading,
        refusals=refusals,
        reconciliation=reconciled.json(),
        fiscal_start_month=start,
        chart=chart,
        journal=journal,
    )


@pytest.fixture(scope="module")
def imports() -> Callable[[str], Imported]:
    """Each archive imported once, the first time a case asks for it."""
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        pytest.skip("needs the compose stack: docker compose --profile test run --rm test")
    settings = Settings(
        database_url=url,
        public_base_url="http://localhost:8080",
        auth_issuer_url="http://localhost:8180/realms/cfokit",
        auth_audience="cfokit-ledger",
    )
    client = TestClient(rest_app(settings, authenticator=StubAuthenticator()))
    database = Database(url)
    done: dict[str, Imported] = {}

    def get(archive: str) -> Imported:
        if archive not in done:
            done[archive] = imported(client, database, archive)
        return done[archive]

    return get


# --- what QuickBooks says -------------------------------------------------------------------


def month_end(day: date) -> date:
    return date(day.year, day.month, calendar.monthrange(day.year, day.month)[1])


def as_of(case_id: str, check: dict[str, Any]) -> date:
    """The check's date: given, or the month end after the case's last event."""
    if check["as_of"] != "month-end":
        return date.fromisoformat(check["as_of"])
    return month_end(
        max(date.fromisoformat(EVENTS[e]["date"]) for e in MANIFEST[case_id]["events"])
    )


def their_balance(archive: str, account: str, day: date) -> Decimal:
    """QuickBooks' trial balance for the account at a month end, debit positive."""
    path = FIXTURE / "archives" / archive / "trial_balances.json"
    if not path.exists():
        path = FIXTURE / "archives" / "accrual" / "trial_balances.json"
    for line in json.loads(path.read_text())[day.isoformat()]:
        if line["account"] == account:
            return Decimal(line["debit"]) - Decimal(line["credit"])
    return Decimal(0)


def their_figure(archive: str, report: str, account: str) -> Decimal:
    """The figure an archive's statement prints for the account, on its row."""
    member = {"profit_and_loss": "Profit_and_loss.xlsx", "balance_sheet": "Balance_sheet.xlsx"}
    grid = values(
        contents((FIXTURE / "archives" / archive / "export.zip").read_bytes())[member[report]]
    )
    leaf = account.rsplit(":", 1)[-1]
    found = [row for row in grid[5:] if row and (row[0] or "").strip() == leaf]
    assert len(found) == 1, f"{leaf!r} is on {len(found)} rows of the {report}"
    return Decimal(found[0][1] or 0)


# --- the checks -----------------------------------------------------------------------------


def balance(done: Imported, case_id: str, check: dict[str, Any]) -> None:
    day = as_of(case_id, check)
    assert done.balance(check["account"], day) == their_balance(
        done.archive, check["account"], day
    )


def stated(done: Imported, case_id: str, check: dict[str, Any]) -> None:
    statement = next(
        s for s in done.reading["books"]["statements"] if s["report"] == check["report"]
    )
    lines = {line["account_code"]: Decimal(line["balance"]) for line in statement["lines"]}
    assert check["account"] in lines, f"no line read; unmatched: {statement['unmatched']}"
    assert lines[check["account"]] == their_figure(
        done.archive, check["report"], check["account"]
    )


def account(done: Imported, case_id: str, check: dict[str, Any]) -> None:
    for name in check.get("present", []):
        assert name in done.chart, f"{name!r} is not in the chart"
        if "type" in check:
            assert done.chart[name] == check["type"], f"{name!r} is {done.chart[name]}"
    for name in check.get("absent", []):
        assert name not in done.chart, f"{name!r} is in the chart"


def text(done: Imported, case_id: str, check: dict[str, Any]) -> None:
    found = any(
        row["description"] == check["description"]
        and check.get("on", row["date"]) == row["date"]
        and check.get("account", row["account_code"]) == row["account_code"]
        for row in done.journal
    )
    assert found == check.get("present", True)


def reconciliation(done: Imported, case_id: str, check: dict[str, Any]) -> None:
    recorded = done.reconciliation
    total = recorded["journal_total"]
    assert ("agrees" if total and total["agrees"] else "disagrees") == check["journal_total"], (
        total
    )
    divergences = recorded["divergences"]
    found = (
        "none"
        if not divergences
        else "nets_to_zero"
        if recorded["divergences_net_to_zero"]
        else "unexplained"
    )
    assert found == check["divergences"], divergences[:12]


CHECKS: dict[str, Callable[[Imported, str, dict[str, Any]], None]] = {
    "balance": balance,
    "stated": stated,
    "account": account,
    "text": text,
    "reconciliation": reconciliation,
}


def test_every_kind_the_catalog_uses_here_is_checked() -> None:
    assert {CATALOG[c]["check"]["kind"] for c in CHECKED} <= set(CHECKS)


def test_the_import_declines_only_what_moves_nothing(
    imports: Callable[[str], Imported],
) -> None:
    """Every row lands but a transaction of nothing (`IMP-05`: what will not be created is
    shown, not dropped). QuickBooks records a payment of nothing when a credit is applied to an
    invoice, and prints its bank side with no account, which leaves one line, of zero."""
    for archive in sorted({CATALOG[c]["check"].get("archive", "accrual") for c in CHECKED}):
        done = imports(archive)
        entries = {entry["reference"]: entry for entry in done.reading["books"]["entries"]}
        for refusal in done.refusals:
            lines = entries[refusal["reference"]]["lines"]
            assert refusal["code"] == "transaction_incomplete", (archive, refusal)
            assert all(Decimal(line["amount"]) == 0 for line in lines), (archive, refusal)


@pytest.mark.parametrize(
    "case_id",
    [
        pytest.param(c, marks=pytest.mark.xfail(strict=True, reason=NOT_YET[c]))
        if c in NOT_YET
        else c
        for c in CHECKED
    ],
)
def test_the_case_holds_in_cfokit(case_id: str, imports: Callable[[str], Imported]) -> None:
    check = CATALOG[case_id]["check"]
    CHECKS[check["kind"]](imports(check.get("archive", "accrual")), case_id, check)
