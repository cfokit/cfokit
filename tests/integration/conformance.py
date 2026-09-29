"""Loading a conformance case into the books (ADR-0036 § 2).

A case is data, not code: a manifest naming its published source, a chart, a journal, and the
answer that source printed. This reads one and posts it through the service layer — the same
path a customer's writes take, so a case exercises the product rather than a shortcut.

Not a test module itself. `tests/integration/test_conformance.py` drives it.
"""

from __future__ import annotations

import csv
import tomllib
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from cfokit.ledger.engine import Entry, Posting
from cfokit.ledger.presentation import SourceBalance
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.administration import create_account, create_entity
from cfokit.ledger.service.principal import ActorClass, Principal
from cfokit.ledger.service.write import WriteContext, record_transaction

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
CASES = FIXTURES / "conformance"
# Recognition cases (ADR-0044): a cited rule and a fact pattern of our own, rather than
# someone else's published answer. Same file shape, loaded the same way, kept in a separate
# tree so neither kind can be counted as the other.
RECOGNITION = FIXTURES / "recognition"
LOADER = Principal(id="user:conformance", actor_class=ActorClass.PERSON)

# What a case's published answer is, and which file holds it.
ANSWER_FILES = {
    "trial_balance": "trial_balance.csv",
    "profit_and_loss": "profit_and_loss.csv",
    "balance_sheet": "balance_sheet.csv",
}

# A trial balance is published account by account, and a case compares it that way. A
# statement is not: a published balance sheet summarises, printing "Capital: investment
# 20,000, net profit 6, less withdrawals 1,000" where the ledger holds three accounts. Mapping
# those summary lines back onto account codes is a step the source never published, and a
# transcription that performs it has quietly become a derivation — which is the one thing
# ADR-0036 § 5 says a conformance case may not be.
#
# So a statement case asserts the figures the source actually printed, and only those. Two
# kinds appear in one file, told apart by the name in the `line` column:
#
#   a named total  — `total_assets`, `net_income`; what the statement claims overall
#   an account code — where the source prints a figure against a single account
#
# Most published statements do both. The 1900 balance sheet in `greendlinger-1911-q04`
# summarises its equity into three narrative lines, but prints cash, bank stock, notes and
# accounts receivable, inventory and real estate individually — so those are assertable
# exactly as printed, and only the equity side is not. Asserting the totals alone would let a
# misclassification *within* one side of the statement pass unnoticed.
TOTAL_LINES = {
    "profit_and_loss": {"total_income", "total_expenses", "net_income"},
    "balance_sheet": {"total_assets", "total_liabilities", "total_equity"},
}


# Every case in the corpus. The behavioral tests parameterise over this rather than over
# named cases, so a case added later joins the gate by being added.
CASE_NAMES = sorted(child.name for child in CASES.iterdir() if child.is_dir())
RECOGNITION_NAMES = sorted(child.name for child in RECOGNITION.iterdir() if child.is_dir())


@dataclass(frozen=True, slots=True)
class Case:
    """One conformance case, loaded into an entity of its own."""

    name: str
    manifest: dict[str, Any]
    entity_id: str
    answer: str
    as_of: date
    since: date | None
    # Per-account, for a trial-balance answer. Empty for a statement.
    source: tuple[SourceBalance, ...]
    # Named totals a statement answer asserts. Empty for a trial balance.
    totals: dict[str, Decimal]
    # Per-account figures a statement answer asserts, where the source printed them.
    lines: dict[str, Decimal]
    source_is_rounded: bool


def load(database: Database, name: str, *, tree: Path = CASES) -> Case:
    """Create an entity from a case's manifest, post its journal, and return its answer.

    `tree` selects the corpus or the recognition fixtures. The two differ in what their
    manifests cite and in what that citation is worth, not in how they run — a case is data
    either way, and both go through the write path a customer's writes take.
    """
    directory = tree / name
    manifest = tomllib.loads((directory / "manifest.toml").read_text(encoding="utf-8"))
    entity = manifest["entity"]

    entity_id = create_entity(
        database,
        principal=LOADER,
        request_id="conformance",
        slug=f"{name}-{uuid.uuid4().hex[:8]}",
        name=name,
        accounting_basis=entity["accounting_basis"],
        fiscal_year_end_month=entity["fiscal_year_end_month"],
        fiscal_year_end_day=entity["fiscal_year_end_day"],
        functional_currency=entity["functional_currency"],
        time_zone="UTC",
    ).entity_id

    accounts: dict[str, str] = {}
    for row in _rows(directory / "accounts.csv"):
        accounts[row["code"]] = create_account(
            database,
            entity_id=entity_id,
            principal=LOADER,
            request_id="conformance",
            code=row["code"],
            name=row["name"],
            account_type=row["type"],
            parent_id=accounts.get(row["parent"]) if row["parent"] else None,
        )

    for ref, lines in _by_reference(directory / "journal.csv").items():
        record_transaction(
            database,
            WriteContext(
                entity_id=entity_id,
                principal=LOADER,
                request_id=f"conformance-{ref}",
                idempotency_key=uuid.uuid4().hex,
            ),
            entry=Entry(
                transaction_date=date.fromisoformat(lines[0]["date"]),
                postings=tuple(
                    Posting(
                        account_id=accounts[line["account_code"]],
                        amount=Decimal(line["amount"]),
                        commodity=line["commodity"],
                    )
                    for line in lines
                ),
                description=lines[0]["description"],
            ),
            post=True,
        )

    expected = manifest["expected"]
    answer = expected["answer"]
    rows = _rows(directory / ANSWER_FILES[answer])
    return Case(
        name=name,
        manifest=manifest,
        entity_id=entity_id,
        answer=answer,
        as_of=expected["as_of"],
        # A profit and loss covers a period, so its case states where the period starts. A
        # balance-sheet or trial-balance answer is as of a date and has no start.
        since=expected.get("since"),
        source=tuple(
            SourceBalance(account_code=row["account_code"], balance=Decimal(row["balance"]))
            for row in rows
        )
        if answer == "trial_balance"
        else (),
        totals={
            row["line"]: Decimal(row["amount"])
            for row in rows
            if answer != "trial_balance" and row["line"] in TOTAL_LINES[answer]
        },
        lines={
            row["line"]: Decimal(row["amount"])
            for row in rows
            if answer != "trial_balance" and row["line"] not in TOTAL_LINES[answer]
        },
        source_is_rounded=bool(expected["source_is_rounded"]),
    )


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _by_reference(path: Path) -> dict[str, list[dict[str, str]]]:
    """Journal lines grouped into transactions, in the order the file lists them.

    One `ref` is one transaction. The file's order is the posting order, so a case that
    depends on sequence stays reproducible.
    """
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in _rows(path):
        grouped.setdefault(row["ref"], []).append(row)
    return grouped
