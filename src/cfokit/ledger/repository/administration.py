"""Creating entities, reading what one declared, and moving grants around. Hand-written SQL
(ADR-0028).

Separate from `unit_of_work` because creating an entity is not an entity-scoped write: it
happens before there is an entity to scope to or lock on.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import psycopg

__all__ = [
    "Entity",
    "entity",
    "grant_entity_role",
    "insert_entity",
    "revoke_entity_grant",
    "role_of_grant",
    "would_remove_last_owner",
]


def insert_entity(
    conn: psycopg.Connection[Any],
    *,
    slug: str,
    name: str,
    accounting_basis: str,
    fiscal_year_end_month: int,
    fiscal_year_end_day: int,
    functional_currency: str,
    time_zone: str,
) -> str:
    """Create an entity. `LED-14` and `LED-15` make every one of these declared at creation."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO entity
                (slug, name, accounting_basis, fiscal_year_end_month, fiscal_year_end_day,
                 functional_currency, time_zone)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                slug,
                name,
                accounting_basis,
                fiscal_year_end_month,
                fiscal_year_end_day,
                functional_currency,
                time_zone,
            ),
        )
        row = cur.fetchone()
    if row is None:  # pragma: no cover
        raise RuntimeError("insert returned no id")
    return str(row[0])


@dataclass(frozen=True, slots=True)
class Entity:
    """What an entity declared at creation (`LED-14`, `LED-15`, `PLT-08`)."""

    id: str
    slug: str
    name: str
    accounting_basis: str
    fiscal_year_end_month: int
    fiscal_year_end_day: int
    functional_currency: str
    time_zone: str


def entity(conn: psycopg.Connection[Any], *, entity_id: str) -> Entity | None:
    """One entity's declarations, or None if there is no such entity.

    `entity` carries no row-level security policy — it is the table the scope is keyed on — so
    the filter on `id` is the only thing keeping this to one entity, and it is explicit.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, slug, name, accounting_basis, fiscal_year_end_month,"
            "       fiscal_year_end_day, functional_currency, time_zone"
            "  FROM entity WHERE id = %s",
            (entity_id,),
        )
        row = cur.fetchone()
    if row is None:
        return None
    return Entity(
        id=str(row[0]),
        slug=str(row[1]),
        name=str(row[2]),
        accounting_basis=str(row[3]),
        fiscal_year_end_month=int(row[4]),
        fiscal_year_end_day=int(row[5]),
        functional_currency=str(row[6]),
        time_zone=str(row[7]),
    )


def grant_entity_role(
    conn: psycopg.Connection[Any],
    *,
    entity_id: str,
    principal_id: str,
    role: str,
    granted_by: str,
    lapses_at: datetime | None,
) -> str:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO entity_grant"
            " (entity_id, principal_id, role, granted_by, lapses_at)"
            " VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (entity_id, principal_id, role, granted_by, lapses_at),
        )
        row = cur.fetchone()
    if row is None:  # pragma: no cover
        raise RuntimeError("insert returned no id")
    return str(row[0])


def revoke_entity_grant(
    conn: psycopg.Connection[Any], *, grant_id: str, revoked_by: str
) -> bool:
    """Revoke a grant. False if there was no unrevoked grant with that id to revoke.

    An `UPDATE` rather than a delete, and the only `UPDATE` the append-only trigger permits on
    this table: the row stays so `IAM-14` can still report what was held before it ended.
    """
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE entity_grant SET revoked_at = now(), revoked_by = %s"
            " WHERE id = %s AND revoked_at IS NULL",
            (revoked_by, grant_id),
        )
        return cur.rowcount == 1


def role_of_grant(
    conn: psycopg.Connection[Any], *, entity_id: str, grant_id: str
) -> str | None:
    """The role an unrevoked grant in this entity carries, or None if there is no such grant.

    Revoking an owner takes a different capability from revoking anyone else (`IAM-21`), so the
    check needs the target's role before it can decide.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT role FROM entity_grant"
            " WHERE id = %s AND entity_id = %s AND revoked_at IS NULL",
            (grant_id, entity_id),
        )
        row = cur.fetchone()
    return str(row[0]) if row is not None else None


def would_remove_last_owner(
    conn: psycopg.Connection[Any], *, entity_id: str, grant_id: str, at: datetime
) -> bool:
    """Whether revoking `grant_id` would leave this entity unheld (`IAM-04`, `IAM-21`).

    Counts distinct principals rather than grants, because one person holding `owner` twice is
    still one owner, and revoking one of their grants leaves the entity held.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM entity_grant WHERE id = %s AND entity_id = %s"
            " AND role = 'owner' AND revoked_at IS NULL",
            (grant_id, entity_id),
        )
        if cur.fetchone() is None:
            # Revoking any other grant can never remove the last owner.
            return False

        cur.execute(
            """
            SELECT count(DISTINCT principal_id)
              FROM entity_grant
             WHERE entity_id = %s
               AND role = 'owner'
               AND id <> %s
               AND granted_at <= %s
               AND (lapses_at IS NULL OR lapses_at > %s)
               AND (revoked_at IS NULL OR revoked_at > %s)
            """,
            (entity_id, grant_id, at, at, at),
        )
        row = cur.fetchone()

    return (int(row[0]) if row is not None else 0) == 0
