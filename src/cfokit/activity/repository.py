"""SQL for account statements. Hand-written, like the ledger's (ADR-0028).

This module's own repository: the connection and the entity scoping come from the ledger's unit
of work, which is the point of being in-process, and the statements are here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

import psycopg

from cfokit.activity import Statement, StatementLine

__all__ = [
    "StoredStatement",
    "insert_statement",
    "load_statement",
    "overlapping",
    "previous",
]


@dataclass(frozen=True, slots=True)
class StoredStatement:
    """A statement as recorded, with the id its lines are referenced by."""

    id: str
    content_digest: str
    statement: Statement


def overlapping(
    conn: psycopg.Connection[Any],
    *,
    entity_id: str,
    account_id: str,
    period_start: date,
    period_end: date,
) -> list[tuple[str, date, date, str]]:
    """Statements for this account sharing any day with the period, as (id, start, end, digest).

    Read under the entity's advisory lock, so two uploads of overlapping statements cannot both
    see the other as absent (ADR-0011).
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, period_start, period_end, content_digest FROM account_statement"
            " WHERE entity_id = %s AND account_id = %s"
            "   AND period_start <= %s AND period_end >= %s"
            " ORDER BY period_start",
            (entity_id, account_id, period_end, period_start),
        )
        return [(str(r[0]), r[1], r[2], str(r[3])) for r in cur.fetchall()]


def previous(
    conn: psycopg.Connection[Any], *, entity_id: str, account_id: str, before: date
) -> tuple[str, date, Decimal] | None:
    """The latest statement for this account ending before `before`, as (id, end, closing)."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, period_end, closing_balance FROM account_statement"
            " WHERE entity_id = %s AND account_id = %s AND period_end < %s"
            " ORDER BY period_end DESC LIMIT 1",
            (entity_id, account_id, before),
        )
        row = cur.fetchone()
    return (str(row[0]), row[1], Decimal(row[2])) if row else None


def insert_statement(
    conn: psycopg.Connection[Any],
    *,
    entity_id: str,
    statement: Statement,
    content_digest: str,
    recorded_by: str,
) -> str:
    """Write the statement and its lines, numbered in the order they were printed."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO account_statement"
            " (entity_id, account_id, period_start, period_end, opening_balance,"
            "  closing_balance, commodity, source_kind, content_digest, recorded_by)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, 'upload', %s, %s) RETURNING id",
            (
                entity_id,
                statement.account_id,
                statement.period_start,
                statement.period_end,
                statement.opening_balance,
                statement.closing_balance,
                statement.commodity,
                content_digest,
                recorded_by,
            ),
        )
        row = cur.fetchone()
        assert row is not None  # noqa: S101 - RETURNING on a successful insert always yields
        statement_id = str(row[0])

        cur.executemany(
            "INSERT INTO account_statement_line"
            " (entity_id, statement_id, line, transaction_date, payee, description, amount)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s)",
            [
                (
                    entity_id,
                    statement_id,
                    position,
                    line.transaction_date,
                    line.payee,
                    line.description,
                    line.amount,
                )
                for position, line in enumerate(statement.lines, start=1)
            ],
        )
    return statement_id


def load_statement(
    conn: psycopg.Connection[Any], *, entity_id: str, statement_id: str
) -> StoredStatement | None:
    """One statement and its lines, in printed order, or None if this entity has no such one."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, account_id, period_start, period_end, opening_balance,"
            "       closing_balance, commodity, content_digest"
            "  FROM account_statement WHERE entity_id = %s AND id = %s",
            (entity_id, statement_id),
        )
        head = cur.fetchone()
        if head is None:
            return None
        cur.execute(
            "SELECT transaction_date, payee, description, amount"
            "  FROM account_statement_line WHERE entity_id = %s AND statement_id = %s"
            " ORDER BY line",
            (entity_id, statement_id),
        )
        lines = tuple(
            StatementLine(
                transaction_date=r[0], payee=r[1], description=r[2], amount=Decimal(r[3])
            )
            for r in cur.fetchall()
        )

    return StoredStatement(
        id=str(head[0]),
        content_digest=str(head[7]),
        statement=Statement(
            account_id=str(head[1]),
            period_start=head[2],
            period_end=head[3],
            opening_balance=Decimal(head[4]),
            closing_balance=Decimal(head[5]),
            commodity=str(head[6]),
            lines=lines,
        ),
    )
