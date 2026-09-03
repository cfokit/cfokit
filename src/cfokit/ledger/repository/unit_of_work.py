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
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import psycopg

from cfokit.ledger.engine import Posting
from cfokit.ledger.engine.periods import FiscalYear, Period
from cfokit.ledger.errors import EntityNotFound
from cfokit.ledger.repository import (
    accounts,
    administration,
    audit,
    closes,
    grants,
    idempotency,
    periods,
    reports,
    transactions,
)
from cfokit.ledger.repository.connection import connect
from cfokit.ledger.repository.transactions import StoredTransaction

__all__ = ["Database", "EntitySettings", "EntityWrite", "UnscopedWrite"]


@dataclass(frozen=True, slots=True)
class Recorded:
    """What a write produced, in the form an idempotent replay returns."""

    transaction_id: str
    status: str


@dataclass(frozen=True, slots=True)
class EntitySettings:
    """What the entity declared at creation, read inside the transaction that uses it.

    Never taken from the caller. A caller who could state the currency could state its way
    past `LED-15`'s refusal, and one who could state the fiscal year end could choose which
    year a close applied to.
    """

    functional_currency: str
    accounting_basis: str
    fiscal_year_end_month: int
    fiscal_year_end_day: int
    retained_earnings_account_id: str | None


class EntityWrite:
    """The operations available inside one locked, entity-scoped transaction.

    Deliberately not a general connection. A caller can only do the things listed here, which
    is what stops an adapter or a service from reaching past `repository` into SQL of its own.
    """

    def __init__(
        self, conn: psycopg.Connection[Any], entity_id: str, settings: EntitySettings
    ) -> None:
        self._conn = conn
        self._entity_id = entity_id
        self._settings = settings

    @property
    def entity_id(self) -> str:
        return self._entity_id

    @property
    def settings(self) -> EntitySettings:
        return self._settings

    @property
    def functional_currency(self) -> str:
        """The entity's declared currency (`LED-15`)."""
        return self._settings.functional_currency

    # --- idempotency (ADR-0029) ----------------------------------------------------------

    def claim_idempotency(self, key: str, request_hash: str) -> dict[str, Any] | None:
        return idempotency.claim(self._conn, self._entity_id, key, request_hash)

    def store_idempotency_result(self, key: str, result: dict[str, Any]) -> None:
        idempotency.store_result(self._conn, self._entity_id, key, result)

    # --- grants (IAM-01, ADR-0011) -------------------------------------------------------

    def privileges_in_force(self, principal_id: str, at: datetime) -> frozenset[str]:
        """Every privilege this principal holds here at `at`, across all its roles.

        Read inside the locked transaction, so a revocation committed a moment ago is already
        in force (`IAM-15`)."""
        return grants.privileges_in_force(self._conn, self._entity_id, principal_id, at)

    def grant_role(
        self, *, principal_id: str, role: str, granted_by: str, lapses_at: datetime | None
    ) -> str:
        return administration.grant_entity_role(
            self._conn,
            entity_id=self._entity_id,
            principal_id=principal_id,
            role=role,
            granted_by=granted_by,
            lapses_at=lapses_at,
        )

    def revoke_grant(self, grant_id: str, *, revoked_by: str) -> bool:
        return administration.revoke_entity_grant(
            self._conn, grant_id=grant_id, revoked_by=revoked_by
        )

    def role_definition(self, name: str) -> grants.RoleDefinition | None:
        """The catalogue entry for a role, or None if this deployment defines no such role."""
        return grants.role_definition(self._conn, name)

    def role_of_grant(self, grant_id: str) -> str | None:
        """The role an unrevoked grant in this entity carries, or None if there is none."""
        return administration.role_of_grant(
            self._conn, entity_id=self._entity_id, grant_id=grant_id
        )

    def would_remove_last_owner(self, grant_id: str, at: datetime) -> bool:
        """Whether revoking this grant would leave the entity unheld.

        `IAM-04`: "An entity always has at least one identity holding it. The last owner cannot
        be revoked or demoted." Counted inside the locked transaction, so two concurrent
        revocations cannot each see the other's owner.
        """
        return administration.would_remove_last_owner(
            self._conn, entity_id=self._entity_id, grant_id=grant_id, at=at
        )

    # --- periods (LED-11, ADR-0030) ------------------------------------------------------

    def close_in_force(self, period: Period) -> str | None:
        """The id of the close in force for this period, or None if it is open.

        Read inside the locked transaction, so a close committed a moment ago already refuses
        a posting and two concurrent writes cannot disagree about it (ADR-0011).
        """
        return periods.close_in_force(self._conn, entity_id=self._entity_id, period=period)

    def close_period(self, period: Period, *, closed_by: str) -> str:
        return periods.insert_close(
            self._conn, entity_id=self._entity_id, period=period, closed_by=closed_by
        )

    def reopen_close(self, close_id: str, *, reopened_by: str, reason: str) -> bool:
        return periods.reopen(
            self._conn, close_id=close_id, reopened_by=reopened_by, reason=reason
        )

    # --- accounts and the year-end close (LED-01, LED-12, ADR-0027) ----------------------

    def create_account(
        self, *, code: str, name: str, account_type: str, parent_id: str | None
    ) -> str:
        return accounts.insert_account(
            self._conn,
            entity_id=self._entity_id,
            code=code,
            name=name,
            account_type=account_type,
            parent_id=parent_id,
        )

    def set_retained_earnings_account(self, account_id: str) -> None:
        accounts.set_retained_earnings_account(
            self._conn, entity_id=self._entity_id, account_id=account_id
        )

    def income_statement_balances(self, year: FiscalYear) -> list[tuple[str, Decimal, str]]:
        """Income and expense balances for the fiscal year, as (account, balance, commodity)."""
        return accounts.income_statement_balances(
            self._conn, entity_id=self._entity_id, start=year.start, end=year.end
        )

    def account_balances(
        self,
        *,
        as_of: date,
        since: date | None = None,
        types: tuple[str, ...] | None = None,
        watermark: datetime | None = None,
    ) -> list[reports.AccountBalance]:
        """Non-zero balances, filtered to a window and a set of types (`RPT-01`, `RPT-11`)."""
        return reports.account_balances(
            self._conn,
            entity_id=self._entity_id,
            as_of=as_of,
            since=since,
            types=types,
            watermark=watermark,
        )

    def account(self, account_id: str) -> reports.Account | None:
        """One account in this entity, or None if there is no such account."""
        return reports.account(self._conn, entity_id=self._entity_id, account_id=account_id)

    def account_detail(
        self,
        *,
        account_id: str,
        since: date,
        as_of: date,
        watermark: datetime | None = None,
    ) -> tuple[Decimal, list[reports.AccountEntry]]:
        """Postings against one account in a period, and the balance it opened with."""
        return reports.account_detail(
            self._conn,
            entity_id=self._entity_id,
            account_id=account_id,
            since=since,
            as_of=as_of,
            watermark=watermark,
        )

    def closing_entries(self, year: FiscalYear) -> list[str]:
        return closes.closing_entries(
            self._conn, entity_id=self._entity_id, start=year.start, end=year.end
        )

    def posted_after(self, year: FiscalYear, close_id: str) -> int:
        """How many ordinary postings entered this year after `close_id` was computed."""
        return closes.posted_after(
            self._conn,
            entity_id=self._entity_id,
            start=year.start,
            end=year.end,
            close_id=close_id,
        )

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


class UnscopedWrite:
    """The operations available in one transaction that is not scoped to an entity.

    Creating an entity is the only act with no entity to scope to or lock on, because the
    entity does not exist until it commits (`IAM-06`). Separate from `EntityWrite` so neither
    offers the other's operations by accident.
    """

    def __init__(self, conn: psycopg.Connection[Any]) -> None:
        self._conn = conn

    def create_entity(
        self,
        *,
        slug: str,
        name: str,
        accounting_basis: str,
        fiscal_year_end_month: int,
        fiscal_year_end_day: int,
        functional_currency: str,
        time_zone: str,
    ) -> str:
        return administration.insert_entity(
            self._conn,
            slug=slug,
            name=name,
            accounting_basis=accounting_basis,
            fiscal_year_end_month=fiscal_year_end_month,
            fiscal_year_end_day=fiscal_year_end_day,
            functional_currency=functional_currency,
            time_zone=time_zone,
        )

    def scope_to(self, entity_id: str) -> None:
        """Scope the rest of this transaction to an entity that now exists.

        Creating an entity starts unscoped — there is nothing to scope to — and the audit row
        that records it belongs to the entity it created. Row-level security applies to the
        insert as well as to reads, so the scope has to be set before it (ADR-0003).
        """
        with self._conn.cursor() as cur:
            cur.execute("SELECT set_config('cfokit.entity_id', %s, true)", (entity_id,))

    def grant_entity_role(
        self, *, entity_id: str, principal_id: str, role: str, granted_by: str
    ) -> str:
        return administration.grant_entity_role(
            self._conn,
            entity_id=entity_id,
            principal_id=principal_id,
            role=role,
            granted_by=granted_by,
            lapses_at=None,
        )

    def record_audit(
        self,
        *,
        entity_id: str | None,
        request_id: str,
        actor: str,
        action: str,
        subject_type: str,
        subject_id: str | None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        audit.record(
            self._conn,
            entity_id=entity_id,
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
    def unscoped_write(self) -> Iterator[UnscopedWrite]:
        """One transaction, scoped to nothing and locking nothing.

        There is no entity to scope to and no per-entity lock to take. That is not a gap: the
        one act this serves — creating an entity — cannot contend on an entity, and a lock
        keyed on one that does not exist yet would be theatre.
        """
        with connect(self._dsn) as conn, conn.transaction():
            yield UnscopedWrite(conn)

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
            settings = self._scope_and_lock(conn, entity_id)
            yield EntityWrite(conn, entity_id, settings)

    @staticmethod
    def _scope_and_lock(conn: psycopg.Connection[Any], entity_id: str) -> EntitySettings:
        """Set the RLS scope, then take the entity's lock. Order matters.

        The scope is transaction-local (`set_config(..., true)`) rather than session-level, so
        a connection cannot carry one entity's scope into a later write for another.

        The lock is taken on `entity.lock_key` — an identity column — never on a hash of
        `entity.id`. ADR-0011 requires a "documented, collision-free scheme", and a 64-bit
        hash of a uuid is collision-*resistant* at best; a collision would not fail, it would
        silently serialise two unrelated entities against each other.

        Returns what the entity declared, which this query fetches anyway.
        """
        with conn.cursor() as cur:
            cur.execute("SELECT set_config('cfokit.entity_id', %s, true)", (entity_id,))
            cur.execute(
                "SELECT lock_key, functional_currency, accounting_basis, fiscal_year_end_month,"
                "       fiscal_year_end_day, retained_earnings_account_id"
                "  FROM entity WHERE id = %s",
                (entity_id,),
            )
            row = cur.fetchone()
            if row is None:
                raise EntityNotFound(f"no entity {entity_id}")
            cur.execute("SELECT pg_advisory_xact_lock(%s)", (row[0],))
        return EntitySettings(
            functional_currency=str(row[1]),
            accounting_basis=str(row[2]),
            fiscal_year_end_month=int(row[3]),
            fiscal_year_end_day=int(row[4]),
            retained_earnings_account_id=str(row[5]) if row[5] is not None else None,
        )
