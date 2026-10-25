"""SQL for conversations and their files. Hand-written, like the ledger's (ADR-0028).

This module's own repository: the connection and the entity scoping come from the ledger's unit
of work, which is the point of being in-process, and the conversations are here. Every statement
names its `entity_id` as well as relying on row-level security, because RLS misconfiguration is
silent (`src/cfokit/ledger/CLAUDE.md`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from cfokit.conversations import Kind, Message

__all__ = [
    "StoredConversation",
    "StoredFile",
    "StoredMessage",
    "append",
    "conversation",
    "conversations_of",
    "file_by_digest",
    "file_contents",
    "files_present",
    "insert_conversation",
    "insert_file",
    "messages_after",
]


@dataclass(frozen=True, slots=True)
class StoredConversation:
    """A conversation, and whether it holds content the organization did not author."""

    id: str
    person: str
    started_at: datetime
    holds_untrusted: bool


@dataclass(frozen=True, slots=True)
class StoredMessage:
    """A message in its place."""

    position: int
    message: Message
    recorded_by: str
    recorded_at: datetime


@dataclass(frozen=True, slots=True)
class StoredFile:
    """A file's identity, without its bytes."""

    id: str
    sha256: str
    media_type: str
    size: int


_HOLDS_UNTRUSTED = (
    "EXISTS (SELECT 1 FROM conversation_message m"
    " JOIN conversation_message_file mf ON mf.message_id = m.id"
    " JOIN conversation_file f ON f.id = mf.file_id"
    " WHERE m.conversation_id = c.id AND f.classification = 'untrusted')"
)


def insert_conversation(
    conn: psycopg.Connection[Any], *, entity_id: str, person: str, started_by: str
) -> str:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO conversation (entity_id, person, started_by)"
            " VALUES (%s, %s, %s) RETURNING id",
            (entity_id, person, started_by),
        )
        row = cur.fetchone()
    assert row is not None  # noqa: S101 - RETURNING on a successful insert always yields
    return str(row[0])


def conversation(
    conn: psycopg.Connection[Any], *, entity_id: str, person: str, conversation_id: str
) -> StoredConversation | None:
    """One of this person's conversations, or None: another person's is not theirs to see."""
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT c.id, c.person, c.started_at, {_HOLDS_UNTRUSTED}"  # noqa: S608 - a constant
            "  FROM conversation c"
            " WHERE c.entity_id = %s AND c.person = %s AND c.id = %s",
            (entity_id, person, conversation_id),
        )
        row = cur.fetchone()
    return _conversation(row) if row else None


def conversations_of(
    conn: psycopg.Connection[Any], *, entity_id: str, person: str
) -> list[StoredConversation]:
    """This person's conversations in this entity, newest first."""
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT c.id, c.person, c.started_at, {_HOLDS_UNTRUSTED}"  # noqa: S608 - a constant
            "  FROM conversation c"
            " WHERE c.entity_id = %s AND c.person = %s"
            " ORDER BY c.started_at DESC, c.id",
            (entity_id, person),
        )
        return [_conversation(row) for row in cur.fetchall()]


def _conversation(row: tuple[Any, ...]) -> StoredConversation:
    return StoredConversation(
        id=str(row[0]), person=str(row[1]), started_at=row[2], holds_untrusted=bool(row[3])
    )


def append(
    conn: psycopg.Connection[Any],
    *,
    entity_id: str,
    conversation_id: str,
    message: Message,
    recorded_by: str,
) -> int:
    """Write a message at the next place in its conversation, and the files it names.

    Called under the entity's advisory lock, so two appends cannot both take the same place
    (ADR-0011); the unique constraint is the backstop if one ever did.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT coalesce(max(position), 0) + 1 FROM conversation_message"
            " WHERE entity_id = %s AND conversation_id = %s",
            (entity_id, conversation_id),
        )
        row = cur.fetchone()
        assert row is not None  # noqa: S101 - an aggregate always yields a row
        position = int(row[0])
        cur.execute(
            "INSERT INTO conversation_message"
            " (entity_id, conversation_id, position, kind, content, model, model_version,"
            "  skill_version, recorded_by)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (
                entity_id,
                conversation_id,
                position,
                message.kind.value,
                Jsonb(message.content),
                message.model,
                message.model_version,
                message.skill_version,
                recorded_by,
            ),
        )
        inserted = cur.fetchone()
        assert inserted is not None  # noqa: S101 - RETURNING on a successful insert always yields
        cur.executemany(
            "INSERT INTO conversation_message_file (entity_id, message_id, file_id)"
            " VALUES (%s, %s, %s)",
            [(entity_id, inserted[0], file_id) for file_id in message.file_ids],
        )
    return position


def messages_after(
    conn: psycopg.Connection[Any], *, entity_id: str, conversation_id: str, after: int
) -> list[StoredMessage]:
    """The conversation's messages after `after`, in order, each with the files it carried."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT m.position, m.kind, m.content, m.model, m.model_version, m.skill_version,"
            "       m.recorded_by, m.recorded_at,"
            "       coalesce(array_agg(mf.file_id ORDER BY mf.file_id)"
            "                FILTER (WHERE mf.file_id IS NOT NULL), '{}')"
            "  FROM conversation_message m"
            "  LEFT JOIN conversation_message_file mf ON mf.message_id = m.id"
            " WHERE m.entity_id = %s AND m.conversation_id = %s AND m.position > %s"
            " GROUP BY m.id"
            " ORDER BY m.position",
            (entity_id, conversation_id, after),
        )
        return [
            StoredMessage(
                position=int(row[0]),
                message=Message(
                    kind=Kind(row[1]),
                    content=row[2],
                    file_ids=tuple(str(file_id) for file_id in row[8]),
                    model=row[3],
                    model_version=row[4],
                    skill_version=row[5],
                ),
                recorded_by=str(row[6]),
                recorded_at=row[7],
            )
            for row in cur.fetchall()
        ]


def files_present(
    conn: psycopg.Connection[Any], *, entity_id: str, file_ids: tuple[str, ...]
) -> set[str]:
    """Which of these files this entity holds."""
    if not file_ids:
        return set()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM conversation_file WHERE entity_id = %s AND id = ANY(%s::uuid[])",
            (entity_id, list(file_ids)),
        )
        return {str(row[0]) for row in cur.fetchall()}


def file_by_digest(
    conn: psycopg.Connection[Any], *, entity_id: str, sha256: str
) -> StoredFile | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, sha256, media_type, size FROM conversation_file"
            " WHERE entity_id = %s AND sha256 = %s",
            (entity_id, sha256),
        )
        row = cur.fetchone()
    return StoredFile(str(row[0]), str(row[1]), str(row[2]), int(row[3])) if row else None


def insert_file(
    conn: psycopg.Connection[Any],
    *,
    entity_id: str,
    sha256: str,
    media_type: str,
    content: bytes,
    uploaded_by: str,
) -> str:
    """Store a file as content the organization did not author, which every file is today."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO conversation_file"
            " (entity_id, sha256, media_type, size, content, classification, uploaded_by)"
            " VALUES (%s, %s, %s, %s, %s, 'untrusted', %s) RETURNING id",
            (entity_id, sha256, media_type, len(content), content, uploaded_by),
        )
        row = cur.fetchone()
    assert row is not None  # noqa: S101 - RETURNING on a successful insert always yields
    return str(row[0])


def file_contents(
    conn: psycopg.Connection[Any], *, entity_id: str, file_id: str
) -> tuple[str, bytes] | None:
    """A file's media type and bytes, or None if this entity holds no such file."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT media_type, content FROM conversation_file"
            " WHERE entity_id = %s AND id = %s",
            (entity_id, file_id),
        )
        row = cur.fetchone()
    return (str(row[0]), bytes(row[1])) if row else None
