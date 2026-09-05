"""The two exports: interchange (`EXP-01`) and complete (`EXP-02`).

> "The books in a form another accounting system can read: chart of accounts, transactions, and
> balances."

> *Acceptance:* "The export is a single self-contained archive, and a trial balance derived from
> the archive alone agrees, line for line, with the trial balance CFOKit produces for the same
> date. What a receiving system then computes is outside our control and is not part of this
> requirement."

**Self-contained means the archive answers its own question.** It carries the journal *and* the
trial balance, so a reader can derive the balances and check them against ours without asking us
anything. That is also what makes the acceptance testable: reconcile the archive's trial balance
against the live books and every line must agree.

**The same three files a conformance case uses.** The format a reconciliation consumes and the
format an export produces are one artifact, or they drift and the acceptance above becomes a
test of two formats agreeing rather than of the export being right.

**The two are deliberately not interchangeable.** The interchange export is for a *foreign*
system: three CSVs, posted transactions only, balances a spreadsheet can open. The complete
export is for *another CFOKit deployment* (`EXP-04`): every row the entity holds, drafts and
audit trail included, as stored.

**The complete export is JSON Lines, and the interchange files inside it stay CSV.** CSV cannot
tell an absent value from an empty one, and a round-trip that turned a null description into
`""` would not have reproduced the books. The interchange files keep CSV because their reader is
another accounting system, or a person with a spreadsheet, and neither has that problem.

**Both need only `READ` and neither writes.** `EXP-03` requires them "at any time, in any entity
state short of deletion, without asking anyone", so a privilege beyond reading the books would
be a way for an entity to become unexportable.

Amounts are written at full recorded precision, not at display scale. A receiving system
should get what was recorded; rounding is a presentation act and belongs to whoever
presents (ADR-0025).
"""

from __future__ import annotations

import csv
import io
import json
import zipfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from cfokit.ledger.repository import archive
from cfokit.ledger.repository.unit_of_work import Database, EntityWrite
from cfokit.ledger.service.authorisation import Capability, require
from cfokit.ledger.service.principal import Principal
from cfokit.ledger.service.reports import trial_balance

__all__ = ["Complete", "Interchange", "export_complete", "export_interchange"]

# The archive's own version, not the application's. A receiving deployment reads this to decide
# whether it understands the file; bumping it is a decision about what an older CFOKit can
# still read, which is why it does not follow anything else.
ARCHIVE_FORMAT = 1

ACCOUNT_COLUMNS = ("code", "name", "type", "parent")
JOURNAL_COLUMNS = ("ref", "date", "description", "account_code", "amount", "commodity")
TRIAL_BALANCE_COLUMNS = ("account_code", "balance")


@dataclass(frozen=True, slots=True)
class Interchange:
    """One archive, and what it says about itself."""

    as_of: date
    watermark: datetime | None
    accounting_basis: str
    functional_currency: str
    archive: bytes
    accounts: int
    postings: int


def export_interchange(
    database: Database,
    *,
    entity_id: str,
    principal: Principal,
    as_of: date,
    watermark: datetime | None = None,
) -> Interchange:
    """Everything posted up to `as_of`, as a zip of three CSVs.

    `EXP-03` requires this "at any time, in any entity state short of deletion, without asking
    anyone", so it needs nothing but `READ` and never writes.

    Posted transactions only. A draft is not in the books (`LED-07`), and an archive carrying
    one would not reconcile against a trial balance that excludes it.
    """
    report = trial_balance(
        database, entity_id=entity_id, principal=principal, as_of=as_of, watermark=watermark
    )

    with database.entity_write(entity_id) as write:
        _require_read(write, principal)
        accounts = write.chart()
        postings = write.exportable_postings(as_of=as_of, watermark=watermark)

    buffer = io.BytesIO()
    # No compression: an archive a person may open in a spreadsheet is worth more than a smaller
    # one, and `ZIP_STORED` keeps a diff of two exports legible.
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as archive:
        archive.writestr(
            "accounts.csv",
            _csv(
                ACCOUNT_COLUMNS,
                (
                    (
                        account.code,
                        account.name,
                        account.account_type,
                        account.parent_code or "",
                    )
                    for account in accounts
                ),
            ),
        )
        archive.writestr(
            "journal.csv",
            _csv(
                JOURNAL_COLUMNS,
                (
                    (
                        posting.transaction_id,
                        posting.transaction_date.isoformat(),
                        posting.description or "",
                        posting.account_code,
                        str(posting.amount),
                        posting.commodity,
                    )
                    for posting in postings
                ),
            ),
        )
        archive.writestr(
            "trial_balance.csv",
            _csv(
                TRIAL_BALANCE_COLUMNS,
                ((row.code, str(row.balance)) for row in report.rows),
            ),
        )

    return Interchange(
        as_of=as_of,
        watermark=watermark,
        accounting_basis=report.accounting_basis,
        functional_currency=report.functional_currency,
        archive=buffer.getvalue(),
        accounts=len(accounts),
        postings=len(postings),
    )


def _csv(columns: tuple[str, ...], rows: Iterable[tuple[str, ...]]) -> str:
    """One CSV, with `\\n` line endings so two exports diff legibly.

    `csv.writer` defaults to `\\r\\n`, which is correct for the format and unhelpful in a diff.
    """
    out = io.StringIO(newline="")
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(columns)
    writer.writerows(rows)
    return out.getvalue()


def _require_read(write: EntityWrite, principal: Principal) -> None:
    now = datetime.now(UTC)
    actor = write.privileges_in_force(principal.id, now)
    acted_for = (
        write.privileges_in_force(principal.acting_for, now)
        if principal.acting_for is not None
        else frozenset()
    )
    require(Capability.READ, principal, actor, acted_for)


@dataclass(frozen=True, slots=True)
class Complete:
    """One complete archive, and what it says about itself."""

    entity_id: str
    slug: str
    taken_at: datetime
    schema_version: str
    archive: bytes
    rows: dict[str, int]


def export_complete(
    database: Database, *, entity_id: str, principal: Principal, request_id: str
) -> Complete:
    """Everything the entity holds, as a zip of JSON Lines plus the interchange files.

    No `as_of` and no watermark. `EXP-02` is "everything the entity holds", and a complete
    export that took a position on which moment counts would be a report rather than the books.

    Drafts are included, where the interchange export excludes them. A draft is not in the books
    (`LED-07`) and so is absent from any statement — but it is something the entity holds, and
    `EXP-04` requires the receiving deployment to reproduce what was there, not a tidied version
    of it.

    Writes no audit row, because it changes nothing. That an export happened is worth knowing,
    and it is the adapter's request log that knows it: an entity that could be made
    unexportable by a failure to write a row would fail `EXP-03`.
    """
    taken_at = datetime.now(UTC)

    with database.entity_write(entity_id) as write:
        _require_read(write, principal)
        tables = {name: write.archived(name) for name, _ in archive.TABLES}
        schema_version = write.schema_version()

    # From the archive rather than from `EntitySettings`, which does not carry it and should
    # not learn to: the manifest describes the file, so it names the entity the same way the
    # file's own `entity` row does.
    entity_columns, entity_rows = tables["entity"]
    slug = str(dict(zip(entity_columns, entity_rows[0], strict=True))["slug"])

    interchange = export_interchange(
        database,
        entity_id=entity_id,
        principal=principal,
        as_of=date.max,
    )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as bundle:
        bundle.writestr(
            "manifest.json",
            json.dumps(
                {
                    "archive_format": ARCHIVE_FORMAT,
                    "schema_version": schema_version,
                    "entity_id": entity_id,
                    "slug": slug,
                    "taken_at": taken_at.isoformat(),
                    "request_id": request_id,
                    "rows": {name: len(rows) for name, (_, rows) in tables.items()},
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )
        for name, (columns, rows) in tables.items():
            bundle.writestr(f"tables/{name}.jsonl", _jsonl(columns, rows))
        with zipfile.ZipFile(io.BytesIO(interchange.archive)) as inner:
            for member in sorted(inner.namelist()):
                bundle.writestr(f"interchange/{member}", inner.read(member))

    return Complete(
        entity_id=entity_id,
        slug=slug,
        taken_at=taken_at,
        schema_version=schema_version,
        archive=buffer.getvalue(),
        rows={name: len(rows) for name, (_, rows) in tables.items()},
    )


def _jsonl(columns: Sequence[str], rows: Iterable[tuple[Any, ...]]) -> str:
    """One row per line, keys sorted, as a receiving deployment reads it.

    Sorted keys and no whitespace variation, so two exports of unchanged books are
    byte-identical and a diff between them shows only what changed — the same property the
    interchange CSVs have.
    """
    return "".join(
        json.dumps(
            dict(zip(columns, (_scalar(value) for value in row), strict=True)), sort_keys=True
        )
        + "\n"
        for row in rows
    )


def _scalar(value: Any) -> Any:
    """One stored value, as JSON carries it.

    `Decimal` becomes a string rather than a number: JSON's number is a float in every reader
    that matters, and `LED-04` allows no representation error (ADR-0005). `date`, `datetime` and
    `UUID` become their ISO or canonical text. Anything already JSON — `jsonb` columns — is
    passed through as the structure it is, so a round-trip does not double-encode it.
    """
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    return value
