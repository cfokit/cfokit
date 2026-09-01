"""One entity-scoped write, with the lock and the scope it must hold.

Everything a state-changing call does happens inside `Database.entity_write`, in **one
database transaction**, with two things established before any work:

1. `cfokit.entity_id` is set for the transaction, so the row-level security policies from
   migration 0001 scope every subsequent statement (ADR-0003).
2. `pg_advisory_xact_lock` is taken on the entity, so writes to it serialise (ADR-0011).

Both release at commit or rollback because both are transaction-scoped. There is no unlock to
forget and no failure path that leaks a lock.

**This class is why the service layer never imports the driver.** It hands out an `EntityWrite`
rather than a connection, so ADR-0028's "SQL lives in `repository`" survives contact with a
service that needs to do several things in one transaction.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from typing import Any

import psycopg

from cfokit.ledger.engine import Posting
from cfokit.ledger.errors import EntityNotFound
from cfokit.ledger.repository import audit, idempotency, transactions
from cfokit.ledger.repository.connection import connect
from cfokit.ledger.repository.transactions import StoredTransaction

__all__ = ["Database", "EntityWrite"]


@dataclass(frozen=True, slots=True)
class Recorded:
    """What a write produced, in the form an idempotent replay returns."""

    transaction_id: str
    status: str


class EntityWrite:
    """The operations available inside one locked, entity-scoped transaction.

    Deliberately not a general connection. A caller can only do the things listed here, which
    is what stops an adapter or a service from reaching past `repository` into SQL of its own.
    """

    def __init__(
        self, conn: psycopg.Connection[Any], entity_id: str, functional_currency: str
    ) -> None:
        self._conn = conn
        self._entity_id = entity_id
        self._functional_currency = functional_currency

    @property
    def entity_id(self) -> str:
        return self._entity_id

    @property
    def functional_currency(self) -> str:
        """The entity's declared currency (`LED-15`).

        Read from the entity inside this transaction, never taken from the caller. An amount
        in any other commodity is refused until `LED-16` activates, and a caller who could
        state the currency could state its way past that refusal.
        """
        return self._functional_currency

    # --- idempotency (ADR-0029) ----------------------------------------------------------

    def claim_idempotency(self, key: str, request_hash: str) -> dict[str, Any] | None:
        return idempotency.claim(self._conn, self._entity_id, key, request_hash)

    def store_idempotency_result(self, key: str, result: dict[str, Any]) -> None:
        idempotency.store_result(self._conn, self._entity_id, key, result)

    # --- the books -----------------------------------------------------------------------

    def insert_draft(
        self,
        *,
        transaction_date: date,
        description: str | None,
        reverses_id: str | None,
        entry_kind: str,
        actor_principal_id: str,
        actor_class: str,
        acting_for_principal_id: str | None,
    ) -> str:
        return transactions.insert_draft(
            self._conn,
            entity_id=self._entity_id,
            transaction_date=transaction_date,
            description=description,
            reverses_id=reverses_id,
            entry_kind=entry_kind,
            actor_principal_id=actor_principal_id,
            actor_class=actor_class,
            acting_for_principal_id=acting_for_principal_id,
        )

    def add_postings(self, transaction_id: str, postings: Sequence[Posting]) -> None:
        transactions.add_postings(
            self._conn,
            entity_id=self._entity_id,
            transaction_id=transaction_id,
            postings=postings,
        )

    def mark_posted(self, transaction_id: str) -> None:
        transactions.mark_posted(self._conn, transaction_id)

    def load_transaction(self, transaction_id: str) -> StoredTransaction | None:
        return transactions.load(self._conn, transaction_id)

    # --- the trail (ADR-0011) ------------------------------------------------------------

    def record_audit(
        self,
        *,
        request_id: str,
        actor: str,
        action: str,
        subject_type: str,
        subject_id: str | None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        audit.record(
            self._conn,
            entity_id=self._entity_id,
            request_id=request_id,
            actor=actor,
            action=action,
            subject_type=subject_type,
            subject_id=subject_id,
            detail=detail,
        )


class Database:
    """The database, as everything above `repository` sees it."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    @contextmanager
    def entity_write(self, entity_id: str) -> Iterator[EntityWrite]:
        """One transaction, scoped and locked to `entity_id`.

        Commits on a clean exit and rolls back on any exception, which is what makes "every
        state-changing call writes exactly one audit row" true rather than aspirational: the
        row and the change it describes cannot be separated by a failure.

        A connection per call rather than a pool. Pooling means a sixth runtime dependency,
        and runtime dependencies are decisions here — the workload is low write concurrency
        per entity (ADR-0003), so this is not the thing to optimise first.
        """
        with connect(self._dsn) as conn, conn.transaction():
            currency = self._scope_and_lock(conn, entity_id)
            yield EntityWrite(conn, entity_id, currency)

    @staticmethod
    def _scope_and_lock(conn: psycopg.Connection[Any], entity_id: str) -> str:
        """Set the RLS scope, then take the entity's lock. Order matters.

        The scope is transaction-local (`set_config(..., true)`) rather than session-level, so
        a connection cannot carry one entity's scope into a later write for another.

        The lock is taken on `entity.lock_key` — an identity column — never on a hash of
        `entity.id`. ADR-0011 requires a "documented, collision-free scheme", and a 64-bit
        hash of a uuid is collision-*resistant* at best; a collision would not fail, it would
        silently serialise two unrelated entities against each other.

        Returns the entity's functional currency, which this query fetches anyway.
        """
        with conn.cursor() as cur:
            cur.execute("SELECT set_config('cfokit.entity_id', %s, true)", (entity_id,))
            cur.execute(
                "SELECT lock_key, functional_currency FROM entity WHERE id = %s", (entity_id,)
            )
            row = cur.fetchone()
            if row is None:
                raise EntityNotFound(f"no entity {entity_id}")
            cur.execute("SELECT pg_advisory_xact_lock(%s)", (row[0],))
        return str(row[1])
