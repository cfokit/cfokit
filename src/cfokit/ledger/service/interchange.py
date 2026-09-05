"""Interchange export: the books in a form another accounting system can read (`EXP-01`).

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

**Not the complete export.** `EXP-02` carries supporting documents, raw payloads, rule
definitions, approvals and the audit trail; `EXP-04` requires that one to reproduce the books in
another deployment. This is the interchange half, and the two are deliberately not
interchangeable.

Amounts are written at full recorded precision, not at display scale. A receiving system
should get what was recorded; rounding is a presentation act and belongs to whoever
presents (ADR-0025).
"""

from __future__ import annotations

import csv
import io
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime

from cfokit.ledger.repository.unit_of_work import Database, EntityWrite
from cfokit.ledger.service.authorisation import Capability, require
from cfokit.ledger.service.principal import Principal
from cfokit.ledger.service.reports import trial_balance

__all__ = ["Interchange", "export_interchange"]

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
