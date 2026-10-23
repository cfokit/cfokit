"""Starting, appending to and reading a person's conversations, and their files (ADR-0076).

**A conversation is one person's** (`PLT-04`). The person is the principal itself when it is a
person, and the person an agent acts for when it is an agent, which is how CFOKit's runtime
appends to the conversation of whoever it is serving (ADR-0077). Another person's conversation
is not found, never refused, so a caller cannot learn that it exists.

**Reading a conversation needs `read`, and so does adding to one.** A conversation records what
was said about the books, not a change to them; whatever the model changes, it changes through
the published tools, under their own capabilities. An agent's authority is the intersection of
its grants and its person's (`IAM-11`), checked by `authorize` as everywhere else.

Every change writes one `audit_log` row naming identifiers and counts, never what was said.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass

from cfokit.conversations import Message, check_file, check_message, media_type_of
from cfokit.conversations.errors import (
    ConversationNotFound,
    FileNotFound,
    MessageInvalid,
    NotForAPerson,
)
from cfokit.conversations.repository import (
    StoredConversation,
    StoredFile,
    StoredMessage,
    append,
    conversation,
    conversations_of,
    file_by_digest,
    file_contents,
    files_present,
    insert_conversation,
    insert_file,
    messages_after,
)
from cfokit.ledger.errors import IdempotencyKeyRequired
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.authorization import Capability, authorize
from cfokit.ledger.service.principal import ActorClass, Principal
from cfokit.ledger.service.write import WriteContext

__all__ = [
    "Appended",
    "Started",
    "Thread",
    "Uploaded",
    "append_message",
    "list_conversations",
    "read_conversation",
    "read_file",
    "start_conversation",
    "upload_file",
]


@dataclass(frozen=True, slots=True)
class Started:
    conversation_id: str
    replayed: bool = False


@dataclass(frozen=True, slots=True)
class Appended:
    position: int
    replayed: bool = False


@dataclass(frozen=True, slots=True)
class Thread:
    """A conversation and the messages asked for."""

    conversation: StoredConversation
    messages: list[StoredMessage]


@dataclass(frozen=True, slots=True)
class Uploaded:
    file: StoredFile
    replayed: bool


def person_of(principal: Principal) -> str:
    """Whose conversation this principal is in: its own, or the person it acts for."""
    if principal.acting_for is not None:
        return principal.acting_for
    if principal.actor_class is ActorClass.PERSON:
        return principal.id
    raise NotForAPerson(f"{principal.id} acts for nobody, so it has no conversation")


def _is_id(value: str) -> bool:
    """Whether `value` could name a row at all; one that cannot is simply not found."""
    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True


def _request_hash(*parts: object) -> str:
    """A digest of the parameters, to detect a key reused for a different request (ADR-0029).

    Duplicated from the ledger's write path rather than shared, as every module does.
    """
    canonical = json.dumps(parts, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def start_conversation(database: Database, context: WriteContext) -> Started:
    """Start a conversation for the person the caller is, or acts for."""
    if not context.idempotency_key:
        raise IdempotencyKeyRequired("every write requires an idempotency key")
    person = person_of(context.principal)
    digest = _request_hash("start_conversation", person)

    with database.entity_write(context.entity_id) as write:
        authorize(write, Capability.READ, context.principal)
        replay = write.claim_idempotency(context.idempotency_key, digest)
        if replay is not None:
            return Started(conversation_id=str(replay["conversation_id"]), replayed=True)

        conversation_id = insert_conversation(
            write.connection,
            entity_id=context.entity_id,
            person=person,
            started_by=context.principal.audit_actor,
        )
        write.record_audit(
            request_id=context.request_id,
            actor=context.principal.audit_actor,
            action="start_conversation",
            subject_type="conversation",
            subject_id=conversation_id,
            detail={},
        )
        write.store_idempotency_result(
            context.idempotency_key, {"conversation_id": conversation_id}
        )
    return Started(conversation_id=conversation_id)


def list_conversations(
    database: Database, *, entity_id: str, principal: Principal
) -> list[StoredConversation]:
    """The person's conversations in this entity, newest first. A read: no audit row."""
    person = person_of(principal)
    with database.entity_write(entity_id) as write:
        authorize(write, Capability.READ, principal)
        return conversations_of(write.connection, entity_id=entity_id, person=person)


def read_conversation(
    database: Database,
    *,
    entity_id: str,
    principal: Principal,
    conversation_id: str,
    after: int = 0,
) -> Thread:
    """A conversation and its messages after `after`, in order. A read: no audit row.

    `holds_untrusted` on the conversation is what ADR-0075 § 2 reads to decide which tools the
    model is offered.
    """
    person = person_of(principal)
    with database.entity_write(entity_id) as write:
        authorize(write, Capability.READ, principal)
        found = (
            conversation(
                write.connection,
                entity_id=entity_id,
                person=person,
                conversation_id=conversation_id,
            )
            if _is_id(conversation_id)
            else None
        )
        if found is None:
            raise ConversationNotFound(
                f"no conversation {conversation_id} here for this person"
            )
        return Thread(
            conversation=found,
            messages=messages_after(
                write.connection,
                entity_id=entity_id,
                conversation_id=conversation_id,
                after=max(after, 0),
            ),
        )


def append_message(
    database: Database, context: WriteContext, *, conversation_id: str, message: Message
) -> Appended:
    """Add a message at the end of one of the person's conversations.

    Refused whole if a file it names is not this entity's. The same key replays the place the
    message was given, so a runtime retrying after a dropped response does not add it twice.
    """
    if not context.idempotency_key:
        raise IdempotencyKeyRequired("every write requires an idempotency key")
    check_message(message)
    person = person_of(context.principal)
    digest = _request_hash(
        "append_message",
        conversation_id,
        message.kind.value,
        message.content,
        sorted(message.file_ids),
        message.model,
        message.model_version,
        message.skill_version,
    )

    with database.entity_write(context.entity_id) as write:
        authorize(write, Capability.READ, context.principal)
        replay = write.claim_idempotency(context.idempotency_key, digest)
        if replay is not None:
            return Appended(position=int(replay["position"]), replayed=True)

        conn = write.connection
        if not _is_id(conversation_id) or (
            conversation(
                conn,
                entity_id=context.entity_id,
                person=person,
                conversation_id=conversation_id,
            )
            is None
        ):
            raise ConversationNotFound(
                f"no conversation {conversation_id} here for this person"
            )
        named = tuple(file_id for file_id in message.file_ids if _is_id(file_id))
        missing = set(message.file_ids) - files_present(
            conn, entity_id=context.entity_id, file_ids=named
        )
        if missing:
            raise MessageInvalid(f"no file {sorted(missing)[0]} in this entity")

        position = append(
            conn,
            entity_id=context.entity_id,
            conversation_id=conversation_id,
            message=message,
            recorded_by=context.principal.audit_actor,
        )
        write.record_audit(
            request_id=context.request_id,
            actor=context.principal.audit_actor,
            action="append_conversation_message",
            subject_type="conversation",
            subject_id=conversation_id,
            # Identifiers and counts. Never what was said.
            detail={
                "position": position,
                "kind": message.kind.value,
                "files": len(message.file_ids),
                "model": message.model,
            },
        )
        write.store_idempotency_result(context.idempotency_key, {"position": position})
    return Appended(position=position)


def upload_file(
    database: Database,
    *,
    entity_id: str,
    principal: Principal,
    request_id: str,
    media_type: str,
    content: bytes,
) -> Uploaded:
    """Store a file a person attached, once per company by its SHA-256.

    **The same file sent twice replays**, as a statement does (ADR-0046): its identity is its
    content, so a retried upload finds what the first one stored and writes nothing. That is
    what makes the upload safe to repeat without a separate idempotency key.
    """
    sha256 = check_file(media_type, content)
    kind = media_type_of(media_type)
    with database.entity_write(entity_id) as write:
        authorize(write, Capability.READ, principal)
        conn = write.connection
        existing = file_by_digest(conn, entity_id=entity_id, sha256=sha256)
        if existing is not None:
            # No work, and deliberately no audit row: a replay is not a state change.
            return Uploaded(file=existing, replayed=True)

        file_id = insert_file(
            conn,
            entity_id=entity_id,
            sha256=sha256,
            media_type=kind,
            content=content,
            uploaded_by=principal.audit_actor,
        )
        write.record_audit(
            request_id=request_id,
            actor=principal.audit_actor,
            action="upload_conversation_file",
            subject_type="conversation_file",
            subject_id=file_id,
            detail={"media_type": kind, "size": len(content)},
        )
    return Uploaded(
        file=StoredFile(id=file_id, sha256=sha256, media_type=kind, size=len(content)),
        replayed=False,
    )


def read_file(
    database: Database, *, entity_id: str, principal: Principal, file_id: str
) -> tuple[str, bytes]:
    """A file's media type and bytes. A company's file is its record, readable with `read`."""
    with database.entity_write(entity_id) as write:
        authorize(write, Capability.READ, principal)
        found = (
            file_contents(write.connection, entity_id=entity_id, file_id=file_id)
            if _is_id(file_id)
            else None
        )
    if found is None:
        raise FileNotFound(f"no file {file_id} in this entity")
    return found
