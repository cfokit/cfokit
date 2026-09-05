"""Reconcile a real accounting export against the books CFOKit builds from it.

Run on demand, never in CI, and never against anything in this repository:

    CFOKIT_RECONCILE_EXPORT="/path/to/export.zip" \\
    DATABASE_URL=... DATABASE_OWNER_URL=... \\
    uv run python tests/integration/reconcile_export.py

This is `NFR-01`'s evidence at scale — "demonstrably correct against a source of truth CFOKit
did not author" — and `IMP-08`'s reconciliation pointed at a real book.

**The oracle is the source's own stated balances**, not a figure this program computes. A
QuickBooks general ledger prints a total per account; those totals are the source doing the
arithmetic over its own data. Summing the journal ourselves and calling it an oracle would be
comparing our arithmetic against itself.

**Every disagreement is reported, none tolerated** (`NFR-01`). This prints them; deciding what
one means is a person's job, because a comparison detects difference and cannot say which side
is wrong (ADR-0010).

Three kinds of figure come out of one export, and conflating them manufactures divergences that
are really category errors:

- **Account balances.** The source's total for an account, against ours. The comparison.
- **Rollups.** A subtotal the source prints over a parent and everything beneath it. Nothing
  posts to one, so it has no counterpart in a chart; it is checked by summing our accounts under
  that parent instead.
- **Zero balances.** `RPT-01` reports accounts with a non-zero balance, so an account the source
  states zero for is simply absent from ours. The reconciler never reads absence as zero, which
  is right — so the two are reconciled here, by name, rather than by teaching it to.

**A divergence on the obligation accounts, and nowhere else, is the accounting method.**
ADR-0037 makes basis a presentation property and lets no posting path branch on it, so books
loaded from an accrual journal and compared against a cash-basis oracle differ by exactly what
is unsettled: receivables, and the income not yet recognised against them, equal and opposite.
That is a resolved divergence, not a tolerated one — the figure is predicted, and the prediction
is what makes a *different* figure a defect. This prints the basis so the two can be told apart.
"""

from __future__ import annotations

import os
import sys
import uuid
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from pathlib import Path

from quickbooks import Converted, convert

from cfokit.ledger.engine import Entry, Posting
from cfokit.ledger.errors import LedgerError
from cfokit.ledger.presentation import SourceBalance, present_reconciliation
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.administration import create_account, create_entity
from cfokit.ledger.service.principal import ActorClass, Principal
from cfokit.ledger.service.reports import TrialBalance, trial_balance
from cfokit.ledger.service.write import WriteContext, record_transaction

OPERATOR = Principal(id="user:reconcile", actor_class=ActorClass.PERSON)
# An account the source states no type for. The chart's CHECK constraint admits five types and
# none of them means "unknown", so a placeholder is needed; `asset` is inert for a trial
# balance, which groups by sign rather than by type.
FALLBACK_TYPE = "asset"


def load(database: Database, converted: Converted) -> tuple[str, int, list[str]]:
    """Create an entity, its chart and its journal. Returns what was skipped and why."""
    entity_id = create_entity(
        database,
        principal=OPERATOR,
        request_id="reconcile",
        slug=f"reconcile-{uuid.uuid4().hex[:8]}",
        name="Reconciliation",
        accounting_basis="accrual",
        fiscal_year_end_month=12,
        fiscal_year_end_day=31,
        functional_currency="USD",
        time_zone="UTC",
    ).entity_id

    # Sorted, so a parent is created before anything under it: a path sorts before every path
    # it prefixes, which is the ordering the chart's foreign key needs.
    accounts: dict[str, str] = {}
    for account in sorted(converted.accounts, key=lambda a: a["code"]):
        accounts[account["code"]] = create_account(
            database,
            entity_id=entity_id,
            principal=OPERATOR,
            request_id="reconcile",
            code=account["code"],
            name=account["name"],
            account_type=(account["type"] if account["type"] != "unknown" else FALLBACK_TYPE),
            parent_id=accounts.get(account["parent"]) if account["parent"] else None,
        )

    grouped: dict[str, list[dict[str, str]]] = {}
    for line in converted.journal:
        grouped.setdefault(line["ref"], []).append(line)

    posted, skipped = 0, []
    for ref, lines in grouped.items():
        try:
            record_transaction(
                database,
                WriteContext(
                    entity_id=entity_id,
                    principal=OPERATOR,
                    request_id=f"reconcile-{ref}",
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
                    description=lines[0]["description"][:200] or None,
                ),
                post=True,
            )
            posted += 1
        except LedgerError as refused:
            # Refusals are the interesting output, not a reason to stop. `NFR-01` wants every
            # disagreement resolved, and a transaction the ledger declines is one of them.
            skipped.append(f"{lines[0]['date']} ref {ref}: {refused.code} ({len(lines)} lines)")
    return entity_id, posted, skipped


def rollups(
    report: TrialBalance, stated: Sequence[dict[str, str]]
) -> list[tuple[str, Decimal, Decimal]]:
    """Check each subtotal the source printed against the accounts beneath it.

    A rollup is not an account, so it cannot go through `present_reconciliation` — nothing in
    our chart is its counterpart. It is still a figure the source computed over its own data,
    and ignoring it would discard the only check there is on whether the two systems agree
    about the *shape* of the chart as well as its balances.

    Children are found by the code path, which is what QuickBooks names a sub-account with.
    **The parent's own balance is part of its subtotal**, which is the whole point of the "with
    sub-accounts" wording: the parent takes postings too, and its rollup covers both. Summing
    only the children understates every such row by exactly the parent's direct activity.
    """
    checked: list[tuple[str, Decimal, Decimal]] = []
    for row in stated:
        parent = row["account_code"]
        ours = sum(
            (
                line.balance
                for line in report.rows
                if line.code == parent or line.code.startswith(parent + ":")
            ),
            Decimal(0),
        )
        checked.append((parent, ours, Decimal(row["balance"])))
    return checked


def main() -> int:
    location = os.environ.get("CFOKIT_RECONCILE_EXPORT")
    if not location:
        print("set CFOKIT_RECONCILE_EXPORT to an export outside this repository")
        return 2
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("set DATABASE_URL to a running CFOKit database")
        return 2

    converted = convert(Path(location).read_bytes())
    print(f"export: {converted.transactions} transactions, {len(converted.accounts)} accounts")
    print(
        f"basis — general ledger: {converted.ledger_basis}, "
        f"trial balance: {converted.trial_balance_basis}"
    )

    if not converted.ledger_totals:
        print(
            "no general ledger totals in this export; nothing independent to reconcile against"
        )
        return 1

    database = Database(dsn)
    entity_id, posted, skipped = load(database, converted)
    print(f"posted {posted} transactions; refused {len(skipped)}")
    for line in skipped:
        print(f"  refused: {line}")

    as_of = max(date.fromisoformat(line["date"]) for line in converted.journal)
    trial = trial_balance(database, entity_id=entity_id, principal=OPERATOR, as_of=as_of)
    report = present_reconciliation(
        trial,
        [
            SourceBalance(account_code=row["account_code"], balance=Decimal(row["balance"]))
            for row in converted.ledger_totals
        ],
    )

    print(f"\nreconciled as of {as_of} against the source's own general ledger totals")
    if converted.ledger_basis != "accrual":
        # ADR-0037: basis is a presentation property and no posting path branches on it, so
        # every divergence a cash-basis oracle produces lands on the obligation accounts and
        # nowhere else. Said here rather than left for a reader to work out.
        print(
            f"  NOTE: those totals are {converted.ledger_basis} basis and our books are"
            " accrual — expect the obligation accounts to differ by what is unsettled"
        )

    stated = [c for c in report.comparisons if not c.only_ours]
    agreed = [c for c in stated if c.agrees]
    # `RPT-01` reports accounts with a non-zero balance, so an account the source states zero
    # for is simply absent from ours. Reported under its own heading rather than counted as a
    # disagreement: the two systems state the same figure in different ways, and calling that
    # a divergence would bury the ones that are real.
    zeroes = [c for c in stated if c.only_theirs and c.theirs == 0]
    divergences = [c for c in stated if not c.agrees and c not in zeroes]

    print(f"  accounts: {len(agreed)} of {len(stated) - len(zeroes)} agree exactly")
    for comparison in divergences:
        print(
            f"    DIVERGES {comparison.account_code}: "
            f"ours {comparison.ours} theirs {comparison.theirs} "
            f"difference {comparison.difference}"
        )
    for comparison in zeroes:
        print(f"    zero and omitted: {comparison.account_code}")

    checked = rollups(trial, converted.ledger_rollups)
    off = [(name, ours, theirs) for name, ours, theirs in checked if ours != theirs]
    print(f"  rollups: {len(checked) - len(off)} of {len(checked)} agree exactly")
    for name, ours, theirs in off:
        print(f"    DIVERGES {name}: ours {ours} theirs {theirs} difference {ours - theirs}")

    return 0 if not divergences and not off else 1


if __name__ == "__main__":
    sys.exit(main())
