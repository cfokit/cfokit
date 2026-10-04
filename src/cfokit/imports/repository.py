"""SQL for import reconciliations. Hand-written, like the ledger's (ADR-0028).

This module's own repository: the connection and the entity scoping come from the ledger's unit
of work, which is the point of being in-process, and the reconciliations are here.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import psycopg

from cfokit.imports import Comparison, TotalAgreement, nets_to_zero

__all__ = ["BALANCES", "Reconciled", "insert_reconciliation", "load_reconciliations"]

# The `report` the source's stated balances are filed under, beside its printed statements.
BALANCES = "balances"


@dataclass(frozen=True, slots=True)
class Reconciled:
    """One recorded reconciliation. No tolerance: `NFR-01` calls one a defect."""

    id: str
    import_id: str
    since: date | None
    as_of: date | None
    recorded_at: datetime
    total: TotalAgreement | None
    balances: Comparison
    """The source's stated balances against ours, in posting signs."""
    statements: tuple[Comparison, ...]

    @property
    def divergences_net_to_zero(self) -> bool:
        """Whether the balance divergences are consistent with a basis difference (ADR-0050)."""
        return nets_to_zero(self.balances.divergences)


def insert_reconciliation(
    conn: psycopg.Connection[Any],
    *,
    entity_id: str,
    import_id: str,
    since: date | None,
    as_of: date | None,
    total: TotalAgreement | None,
    balances: Comparison,
    statements: tuple[Comparison, ...],
    recorded_by: str,
) -> str:
    """Write the reconciliation and every comparison in it; return its id."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO import_reconciliation"
            " (entity_id, import_id, since, as_of, stated_debits, stated_credits,"
            "  our_debits, our_credits, recorded_by)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (
                entity_id,
                import_id,
                since,
                as_of,
                None if total is None else total.stated_debits,
                None if total is None else total.stated_credits,
                None if total is None else total.our_debits,
                None if total is None else total.our_credits,
                recorded_by,
            ),
        )
        row = cur.fetchone()
        assert row is not None  # noqa: S101 - RETURNING on a successful insert always yields
        reconciliation_id = str(row[0])

        for position, comparison in enumerate((balances, *statements), start=1):
            stated = comparison.report != BALANCES
            cur.execute(
                "INSERT INTO import_reconciliation_comparison"
                " (entity_id, reconciliation_id, position, report, their_basis, our_basis,"
                "  agreed)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
                (
                    entity_id,
                    reconciliation_id,
                    position,
                    comparison.report,
                    comparison.their_basis if stated else None,
                    comparison.our_basis if stated else None,
                    comparison.agreed,
                ),
            )
            head = cur.fetchone()
            assert head is not None  # noqa: S101 - as above
            lines: list[tuple[str, str, Decimal | None, Decimal | None]] = [
                ("divergence", code, ours, theirs)
                for code, ours, theirs in comparison.divergences
            ]
            lines += [("only_ours", code, None, None) for code in comparison.only_ours]
            lines += [("only_theirs", code, None, None) for code in comparison.only_theirs]
            lines += [("unmatched", code, None, None) for code in comparison.unmatched]
            cur.executemany(
                "INSERT INTO import_reconciliation_line"
                " (entity_id, comparison_id, kind, account_code, ours, theirs)"
                " VALUES (%s, %s, %s, %s, %s, %s)",
                [(entity_id, head[0], *line) for line in lines],
            )
    return reconciliation_id


def load_reconciliations(
    conn: psycopg.Connection[Any], *, entity_id: str, only: str | None = None
) -> list[Reconciled]:
    """Every reconciliation recorded for this entity, newest first — or `only` that one."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, import_id, since, as_of, stated_debits, stated_credits,"
            "       our_debits, our_credits, recorded_at"
            "  FROM import_reconciliation"
            " WHERE entity_id = %s AND (%s::uuid IS NULL OR id = %s::uuid)"
            " ORDER BY recorded_at DESC, id",
            (entity_id, only, only),
        )
        heads = cur.fetchall()
        cur.execute(
            "SELECT c.reconciliation_id, c.id, c.report, c.their_basis, c.our_basis, c.agreed"
            "  FROM import_reconciliation_comparison c WHERE c.entity_id = %s"
            " ORDER BY c.position",
            (entity_id,),
        )
        comparisons = cur.fetchall()
        cur.execute(
            "SELECT comparison_id, kind, account_code, ours, theirs"
            "  FROM import_reconciliation_line WHERE entity_id = %s"
            " ORDER BY account_code, id",
            (entity_id,),
        )
        lines_by_comparison: dict[str, list[tuple[Any, ...]]] = defaultdict(list)
        for line in cur.fetchall():
            lines_by_comparison[str(line[0])].append(line)

    by_reconciliation: dict[str, list[Comparison]] = defaultdict(list)
    for reconciliation_id, comparison_id, report, their_basis, our_basis, agreed in comparisons:
        lines = lines_by_comparison[str(comparison_id)]

        def codes(kind: str, lines: list[tuple[Any, ...]] = lines) -> tuple[str, ...]:
            return tuple(str(line[2]) for line in lines if line[1] == kind)

        by_reconciliation[str(reconciliation_id)].append(
            Comparison(
                report=str(report),
                their_basis=their_basis or "",
                our_basis=our_basis or "",
                agreed=int(agreed),
                divergences=tuple(
                    (str(line[2]), Decimal(line[3]), Decimal(line[4]))
                    for line in lines
                    if line[1] == "divergence"
                ),
                only_ours=codes("only_ours"),
                only_theirs=codes("only_theirs"),
                unmatched=codes("unmatched"),
            )
        )

    stored: list[Reconciled] = []
    for head in heads:
        found = by_reconciliation[str(head[0])]
        stored.append(
            Reconciled(
                id=str(head[0]),
                import_id=str(head[1]),
                since=head[2],
                as_of=head[3],
                recorded_at=head[8],
                total=(
                    None
                    if head[4] is None
                    else TotalAgreement(
                        stated_debits=Decimal(head[4]),
                        stated_credits=Decimal(head[5]),
                        our_debits=Decimal(head[6]),
                        our_credits=Decimal(head[7]),
                    )
                ),
                balances=next(c for c in found if c.report == BALANCES),
                statements=tuple(c for c in found if c.report != BALANCES),
            )
        )
    return stored
