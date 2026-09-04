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

CASES = Path(__file__).resolve().parent.parent / "fixtures" / "conformance"
LOADER = Principal(id="user:conformance", actor_class=ActorClass.PERSON)


@dataclass(frozen=True, slots=True)
class Case:
    """One conformance case, loaded into an entity of its own."""

    name: str
    manifest: dict[str, Any]
    entity_id: str
    as_of: date
    source: tuple[SourceBalance, ...]
    source_is_rounded: bool


def load(database: Database, name: str) -> Case:
    """Create an entity from a case's manifest, post its journal, and return its answer."""
    directory = CASES / name
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
    return Case(
        name=name,
        manifest=manifest,
        entity_id=entity_id,
        as_of=expected["as_of"],
        source=tuple(
            SourceBalance(account_code=row["account_code"], balance=Decimal(row["balance"]))
            for row in _rows(directory / "trial_balance.csv")
        ),
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
