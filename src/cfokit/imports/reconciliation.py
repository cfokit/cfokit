"""An import's reconciliation, recorded with it and read back (`IMP-08`, ADR-0058).

Two calls.

`record_reconciliation` compares the books with the figures the source states for itself — its
balances, its journal total, and every statement it printed — and stores the comparison. The
getting-started pages call it when an import finishes, as the person who imported.

`reconciliations` reads them back, so a later conversation can answer "do my books match
QuickBooks, and why not?" from what the person was shown, rather than from a comparison rerun
against books that have moved on since.
"""

from __future__ import annotations

from datetime import date

from cfokit.imports import Comparison, check_total, compare
from cfokit.imports import _reconcile as reconcile_balances
from cfokit.imports.repository import (
    BALANCES,
    Reconciled,
    insert_reconciliation,
    load_reconciliations,
)
from cfokit.imports.source import SourceBooks
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.authorization import Capability, authorize, authorize_own_act
from cfokit.ledger.service.principal import Principal

__all__ = ["Reconciled", "reconciliations", "record_reconciliation"]


def record_reconciliation(
    database: Database,
    *,
    entity_id: str,
    principal: Principal,
    request_id: str,
    import_id: str,
    books: SourceBooks,
    since: date | None = None,
    as_of: date | None = None,
) -> Reconciled:
    """Compare the books with what the source states, and record the comparison.

    **A person's act, like the import it finishes** (ADR-0007): the record says what the person
    who imported was shown. An agent reads it with `reconciliations`; it does not write one.

    Recorded every time it is run, never replaced: a second run after a correction sits beside
    the first, and the later one is the current answer.
    """
    with database.entity_write(entity_id) as write:
        authorize_own_act(write, principal)

    agreed, _, divergences = reconcile_balances(
        database, entity_id=entity_id, principal=principal, books=books, as_of=as_of
    )
    balances = Comparison(
        report=BALANCES, their_basis="", our_basis="", agreed=agreed, divergences=divergences
    )
    total = check_total(
        database, entity_id=entity_id, principal=principal, books=books, as_of=as_of
    )
    statements = compare(
        database,
        entity_id=entity_id,
        principal=principal,
        books=books,
        since=since,
        as_of=as_of,
    )

    with database.entity_write(entity_id) as write:
        authorize_own_act(write, principal)
        reconciliation_id = insert_reconciliation(
            write.connection,
            entity_id=entity_id,
            import_id=import_id,
            since=since,
            as_of=as_of,
            total=total,
            balances=balances,
            statements=statements,
            recorded_by=principal.id,
        )
        write.record_audit(
            request_id=request_id,
            actor=principal.audit_actor,
            action="record_import_reconciliation",
            subject_type="import_reconciliation",
            subject_id=reconciliation_id,
            # Identifiers and counts. Never balances or amounts.
            detail={
                "import_id": import_id,
                "compared": balances.compared,
                "divergences": len(balances.divergences),
                "statements": len(statements),
            },
        )
        # Read back rather than echoed, so what the person is shown is what was stored.
        [recorded] = load_reconciliations(
            write.connection, entity_id=entity_id, only=reconciliation_id
        )
    return recorded


def reconciliations(
    database: Database, *, entity_id: str, principal: Principal
) -> tuple[Reconciled, ...]:
    """Every reconciliation recorded for this entity, newest first. A read."""
    with database.entity_write(entity_id) as write:
        authorize(write, Capability.READ, principal)
        return tuple(load_reconciliations(write.connection, entity_id=entity_id))
