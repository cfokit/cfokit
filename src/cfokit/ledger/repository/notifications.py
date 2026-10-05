"""Notifications and their closing rows. Hand-written SQL (ADR-0028).

Both tables are insert-only (ADR-0052 § 1). Whether a notification is open is a query over its
closing rows, exactly as whether a statement is superseded is a query over `posted_at`: nothing
sets a flag, so nothing can fail to.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import psycopg

__all__ = [
    "Notification",
    "answer",
    "dismiss",
    "insert_notification",
    "notification",
    "open_for",
]


@dataclass(frozen=True, slots=True)
class Notification:
    """A notification as stored: identifiers and a link, never a figure (ADR-0052 § 6)."""

    id: str
    entity_id: str
    recipient: str
    notification_class: str
    subject_ref: str
    link: str
    raised_at: datetime
    dismissed: bool
    answered: bool

    @property
    def is_open(self) -> bool:
        return not (self.dismissed or self.answered)


def _row(row: tuple[Any, ...]) -> Notification:
    return Notification(
        id=str(row[0]),
        entity_id=str(row[1]),
        recipient=str(row[2]),
        notification_class=str(row[3]),
        subject_ref=str(row[4]),
        link=str(row[5]),
        raised_at=row[6],
        dismissed=bool(row[7]),
        answered=bool(row[8]),
    )


def insert_notification(
    conn: psycopg.Connection[Any],
    *,
    entity_id: str,
    recipient: str,
    notification_class: str,
    subject_ref: str,
    link: str,
) -> str:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO notification"
            " (entity_id, recipient, notification_class, subject_ref, link)"
            " VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (entity_id, recipient, notification_class, subject_ref, link),
        )
        row = cur.fetchone()
    if row is None:  # pragma: no cover
        raise RuntimeError("insert returned no id")
    return str(row[0])


def answer(
    conn: psycopg.Connection[Any],
    *,
    entity_id: str,
    notification_class: str,
    subject_ref: str,
    closed_by: str,
    act_ref: str,
) -> int:
    """Close every recipient's notification of this class about this subject; return how many.

    Per subject, not per recipient (ADR-0056 § 1): when one owner answers, the question no
    longer needs the other. A dismissed one gains its answer too; one already answered is left
    alone, which is what makes a repeated answer harmless.
    """
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO notification_closing"
            " (entity_id, notification_id, kind, closed_by, act_ref)"
            " SELECT n.entity_id, n.id, 'answered', %s, %s FROM notification n"
            "  WHERE n.entity_id = %s AND n.notification_class = %s AND n.subject_ref = %s"
            "    AND NOT EXISTS (SELECT 1 FROM notification_closing c"
            "                     WHERE c.notification_id = n.id AND c.kind = 'answered')",
            (closed_by, act_ref, entity_id, notification_class, subject_ref),
        )
        return cur.rowcount


def dismiss(
    conn: psycopg.Connection[Any], *, entity_id: str, notification_id: str, dismissed_by: str
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO notification_closing"
            " (entity_id, notification_id, kind, closed_by)"
            " VALUES (%s, %s, 'dismissed', %s)",
            (entity_id, notification_id, dismissed_by),
        )


def notification(
    conn: psycopg.Connection[Any], *, entity_id: str, notification_id: str
) -> Notification | None:
    """One notification in this entity, open or not, or None if there is no such one."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT n.id, n.entity_id, n.recipient, n.notification_class, n.subject_ref,"
            "       n.link, n.raised_at,"
            "       EXISTS (SELECT 1 FROM notification_closing c"
            "                WHERE c.notification_id = n.id AND c.kind = 'dismissed'),"
            "       EXISTS (SELECT 1 FROM notification_closing c"
            "                WHERE c.notification_id = n.id AND c.kind = 'answered')"
            "  FROM notification n"
            " WHERE n.entity_id = %s AND n.id = %s",
            (entity_id, notification_id),
        )
        row = cur.fetchone()
    return _row(row) if row is not None else None


def open_for(
    conn: psycopg.Connection[Any], *, entity_id: str, recipient: str
) -> list[Notification]:
    """This recipient's open notifications in this entity, oldest first.

    Only the recipient's own. A co-owner's are not listed even within an entity both hold
    (ADR-0056 § 4).
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT n.id, n.entity_id, n.recipient, n.notification_class, n.subject_ref,"
            "       n.link, n.raised_at, false, false"
            "  FROM notification n"
            " WHERE n.entity_id = %s AND n.recipient = %s"
            "   AND NOT EXISTS (SELECT 1 FROM notification_closing c"
            "                    WHERE c.notification_id = n.id)"
            " ORDER BY n.raised_at, n.id",
            (entity_id, recipient),
        )
        return [_row(row) for row in cur.fetchall()]
