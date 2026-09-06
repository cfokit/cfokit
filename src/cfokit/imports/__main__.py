"""``python -m cfokit.imports`` — plan or apply an import from a file on disk.

One of the entrypoints this image provides (ADR-0023).

    python -m cfokit.imports plan    <entity-id> <path>
    python -m cfokit.imports apply   <entity-id> <path>
    python -m cfokit.imports compare <entity-id> <path>

**The path is read by this process, not sent to it.** Nothing between the file and the database
holds the transactions — not a request body, not a model's context. For an export of several
thousand transactions that is an engineering constraint before it is a privacy one: it does not
fit usefully in a context, and anything asked to carry it is a lossy pipe that adds nothing.
Reading the loaded books afterwards is what a model is for, and `PLT-02` puts that runtime in
the organisation's own hands.

**`plan` first.** `IMP-05` requires an import validated before anything is posted, with the
operator seeing what will be created and what will not, and able to abandon it. That is two
commands rather than a flag, because a flag is easy to forget and a command is not.

**Figures go to a file, not to stdout.** A reconciliation names accounts and amounts; on a real
company's books those are client names and revenue. The summary says how many agreed, and the
detail is written where a person can open it.
"""

from __future__ import annotations

import json
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

from cfokit.imports import Plan, apply, compare, plan, quickbooks
from cfokit.ledger.config import require_env
from cfokit.ledger.errors import LedgerError
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.principal import ActorClass, Principal

USAGE = (
    "usage: python -m cfokit.imports {plan|apply|compare} <entity-id> <path> [--as <principal>]"
)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    principal_id = "user:operator"
    if "--as" in args:
        at = args.index("--as")
        principal_id = args[at + 1]
        del args[at : at + 2]
    if len(args) != 3 or args[0] not in {"plan", "apply", "compare"}:
        print(USAGE)
        return 2

    command, entity_id, location = args
    # `DATABASE_URL` alone, not the whole settings object. This entrypoint serves no traffic
    # and says nothing about itself, so `PUBLIC_BASE_URL` and the auth surface are not its
    # business — the same reason the migrate entrypoint reads one variable (ADR-0004).
    database = Database(require_env("DATABASE_URL"))
    principal = Principal(id=principal_id, actor_class=ActorClass.PERSON)
    books = quickbooks.read(Path(location).read_bytes())

    if command == "compare":
        return _compare(database, entity_id, principal, books, location)

    print(
        f"source: {books.system}, {books.commodity},"
        f" entries {books.basis} basis, stated balances {books.balances_basis} basis"
    )

    try:
        proposed = plan(database, entity_id=entity_id, principal=principal, books=books)
    except LedgerError as refused:
        print(f"refused: {refused.code}: {refused}")
        return 1

    print(
        f"plan: {proposed.transactions} transactions,"
        f" {proposed.postings} postings,"
        f" {len(proposed.accounts_to_create)} accounts to create,"
        f" {len(proposed.accounts_already_present)} already present"
    )
    if proposed.earliest is not None:
        print(f"  covering {proposed.earliest} to {proposed.latest}")
    if proposed.untyped_accounts:
        print(
            f"  {len(proposed.untyped_accounts)} accounts the source states no type for;"
            " they will be created as assets and are listed in the report"
        )
    if proposed.refusals:
        print(f"  {len(proposed.refusals)} rows will be skipped; see the report")
    if proposed.oracle_differs_in_basis:
        print(
            f"  NOTE: the stated balances are {proposed.balances_basis} basis and these books"
            " are accrual — expect the obligation accounts to differ by what is unsettled"
        )
    if not proposed.can_apply:
        print(f"BLOCKED: {proposed.blocked}")
        return 1

    if command == "plan":
        print(_report(location, {"plan": _planned(proposed)}))
        return 0

    result = apply(
        database,
        entity_id=entity_id,
        principal=principal,
        request_id=f"import-{uuid.uuid4().hex[:8]}",
        books=books,
    )
    print(
        f"applied: import {result.import_id},"
        f" {result.accounts_created} accounts created,"
        f" {result.transactions_posted} transactions posted,"
        f" {len(result.refusals)} skipped"
    )
    print(f"reconciled: {result.agreed} of {result.compared} accounts agree exactly")
    if result.divergences:
        print(f"  {len(result.divergences)} divergences; see the report")
    print(
        _report(
            location,
            {
                "plan": _planned(proposed),
                "result": {
                    "import_id": result.import_id,
                    "accounts_created": result.accounts_created,
                    "transactions_posted": result.transactions_posted,
                    "refusals": [
                        {
                            "reference": r.reference,
                            "date": r.when.isoformat() if r.when else None,
                            "code": r.code,
                            "detail": r.detail,
                        }
                        for r in result.refusals
                    ],
                    "reconciliation": {
                        "agreed": result.agreed,
                        "compared": result.compared,
                        "divergences": [
                            {"account": code, "ours": str(ours), "theirs": str(theirs)}
                            for code, ours, theirs in result.divergences
                        ],
                    },
                },
            },
        )
    )
    return 0 if result.reconciled and not result.refusals else 1


def _compare(
    database: Database, entity_id: str, principal: Principal, books: object, location: str
) -> int:
    """Every statement the source printed, against the one CFOKit produces.

    Reads only. This is `IMP-08` pointed at the statements rather than the balances: agreement
    demonstrated against the source's own figures, with every disagreement reported and none
    tolerated (`NFR-01`).
    """
    assert isinstance(books, quickbooks.SourceBooks)  # noqa: S101 - narrowing for the reader
    comparisons = compare(database, entity_id=entity_id, principal=principal, books=books)
    if not comparisons:
        print("the export prints no statements to compare against")
        return 1

    exact = True
    detail: dict[str, object] = {}
    for comparison in comparisons:
        print(
            f"\n{comparison.report}: {comparison.agreed} of {comparison.compared}"
            f" accounts agree exactly"
        )
        print(f"  basis — theirs {comparison.their_basis}, ours {comparison.our_basis}")
        if comparison.their_basis not in {"unknown", comparison.our_basis}:
            print(
                "  NOTE: the statements are on different bases, so the obligation accounts"
                " differ by what is unsettled (ADR-0037)"
            )
        for code, mine, printed in comparison.divergences:
            print(f"    DIVERGES {code}: ours {mine} theirs {printed}")
        if comparison.only_theirs:
            print(f"  {len(comparison.only_theirs)} accounts only they report")
        if comparison.only_ours:
            print(f"  {len(comparison.only_ours)} accounts only we report")
        if comparison.unmatched:
            print(f"  {len(comparison.unmatched)} rows are not accounts; see the report")
        exact = exact and comparison.agrees
        detail[comparison.report] = {
            "agreed": comparison.agreed,
            "compared": comparison.compared,
            "their_basis": comparison.their_basis,
            "our_basis": comparison.our_basis,
            "divergences": [
                {"account": code, "ours": str(mine), "theirs": str(printed)}
                for code, mine, printed in comparison.divergences
            ],
            "only_ours": list(comparison.only_ours),
            "only_theirs": list(comparison.only_theirs),
            "not_accounts": list(comparison.unmatched),
        }

    print(_report(location, {"statements": detail}))
    return 0 if exact else 1


def _planned(proposed: Plan) -> dict[str, object]:
    return {
        "system": proposed.system,
        "basis": proposed.basis,
        "balances_basis": proposed.balances_basis,
        "commodity": proposed.commodity,
        "accounts_to_create": list(proposed.accounts_to_create),
        "accounts_already_present": list(proposed.accounts_already_present),
        "untyped_accounts": list(proposed.untyped_accounts),
        "transactions": proposed.transactions,
        "postings": proposed.postings,
        "earliest": proposed.earliest.isoformat() if proposed.earliest else None,
        "latest": proposed.latest.isoformat() if proposed.latest else None,
        "refusals": [
            {
                "reference": r.reference,
                "date": r.when.isoformat() if r.when else None,
                "code": r.code,
                "detail": r.detail,
            }
            for r in proposed.refusals
        ],
    }


def _report(location: str, payload: dict[str, object]) -> str:
    """Write the detail beside the file it came from, and return where it went.

    Beside the source rather than into the repository or a log: it names accounts and amounts,
    which on a real company's books are client names and revenue. Whoever holds the export
    already holds those; nothing else needs to.
    """
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    destination = Path(location).parent / f"cfokit-import-{stamp}.json"
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return f"report: {destination}"


if __name__ == "__main__":
    sys.exit(main())
