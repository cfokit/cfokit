"""The conversations module's REST surface: a router it owns, included by `cfokit.server`.

The ledger's adapter cannot mount it — "the ledger depends on no module" is an `import-linter`
contract (ADR-0022). The agent reads and appends conversations here, as its own client acting
for the person (ADR-0075, ADR-0077); the web client reads them here too.

There is no MCP tool for any of this. A conversation is what the agent keeps about a model's
turn, not something the model itself is offered to change.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Body, Depends, Header, Path, Query, Response, status
from pydantic import BaseModel
from pydantic import Field as Described

from cfokit.conversations import MAX_FILE_BYTES, Kind, Message
from cfokit.conversations.repository import StoredConversation, StoredFile
from cfokit.conversations.service import (
    append_message,
    list_conversations,
    read_conversation,
    read_file,
    start_conversation,
    upload_file,
)
from cfokit.ledger.api import ERRORS, get_database, get_principal, get_write_context
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.principal import Principal
from cfokit.ledger.service.write import WriteContext

router = APIRouter(tags=["conversations"])


class ConversationModel(BaseModel):
    conversation_id: str
    started_at: datetime
    holds_untrusted: bool = Described(
        description="True once any message in it carried a file. Such a conversation is "
        "offered "
        "no tool that posts, for the rest of it (ADR-0075 § 2)."
    )


class MessageModel(BaseModel):
    position: int
    kind: Literal["request", "response"]
    content: dict[str, Any] | list[Any] = Described(
        description="The agent's own serialized message, stored as sent and never reshaped."
    )
    file_ids: list[str]
    model: str | None
    model_version: str | None
    skill_version: str | None
    recorded_by: str
    recorded_at: datetime


class ThreadModel(BaseModel):
    conversation: ConversationModel
    messages: list[MessageModel]


class NewMessageModel(BaseModel):
    """A message to add. A response names the model and skill that wrote it; a request names
    neither, and only a request carries files."""

    kind: Literal["request", "response"]
    content: dict[str, Any] | list[Any]
    file_ids: list[str] = Described(default_factory=list)
    model: str | None = None
    model_version: str | None = None
    skill_version: str | None = None


class FileModel(BaseModel):
    file_id: str
    sha256: str
    media_type: str
    size: int
    replayed: bool = Described(
        default=False, description="True when this company already held this exact file."
    )


def _conversation(found: StoredConversation) -> ConversationModel:
    return ConversationModel(
        conversation_id=found.id,
        started_at=found.started_at,
        holds_untrusted=found.holds_untrusted,
    )


def _file(found: StoredFile, *, replayed: bool) -> FileModel:
    return FileModel(
        file_id=found.id,
        sha256=found.sha256,
        media_type=found.media_type,
        size=found.size,
        replayed=replayed,
    )


@router.post(
    "/entities/{entity_id}/conversations",
    status_code=status.HTTP_201_CREATED,
    summary="Start a conversation for the person the caller is, or acts for",
    responses=ERRORS,
)
def create_conversation(
    context: Annotated[WriteContext, Depends(get_write_context)],
    database: Annotated[Database, Depends(get_database)],
) -> dict[str, Any]:
    """Requires an `Idempotency-Key`. The conversation is the person's (`PLT-04`)."""
    started = start_conversation(database, context)
    return {"conversation_id": started.conversation_id, "replayed": started.replayed}


@router.get(
    "/entities/{entity_id}/conversations",
    summary="The person's conversations in this company, newest first",
    responses=ERRORS,
)
def conversations(
    entity_id: Annotated[str, Path()],
    principal: Annotated[Principal, Depends(get_principal)],
    database: Annotated[Database, Depends(get_database)],
) -> dict[str, list[ConversationModel]]:
    found = list_conversations(database, entity_id=entity_id, principal=principal)
    return {"conversations": [_conversation(one) for one in found]}


@router.get(
    "/entities/{entity_id}/conversations/{conversation_id}",
    summary="A conversation and its messages after a place in it",
    responses=ERRORS,
)
def conversation(
    entity_id: Annotated[str, Path()],
    conversation_id: Annotated[str, Path()],
    principal: Annotated[Principal, Depends(get_principal)],
    database: Annotated[Database, Depends(get_database)],
    after: Annotated[int, Query(ge=0, description="The last place the caller holds.")] = 0,
) -> ThreadModel:
    """Another person's conversation is not found, so a caller cannot learn that it exists."""
    thread = read_conversation(
        database,
        entity_id=entity_id,
        principal=principal,
        conversation_id=conversation_id,
        after=after,
    )
    return ThreadModel(
        conversation=_conversation(thread.conversation),
        messages=[
            MessageModel(
                position=stored.position,
                kind=stored.message.kind.value,
                content=stored.message.content,
                file_ids=list(stored.message.file_ids),
                model=stored.message.model,
                model_version=stored.message.model_version,
                skill_version=stored.message.skill_version,
                recorded_by=stored.recorded_by,
                recorded_at=stored.recorded_at,
            )
            for stored in thread.messages
        ],
    )


@router.post(
    "/entities/{entity_id}/conversations/{conversation_id}/messages",
    status_code=status.HTTP_201_CREATED,
    summary="Add a message at the end of a conversation",
    responses=ERRORS,
)
def add_message(
    body: NewMessageModel,
    conversation_id: Annotated[str, Path()],
    context: Annotated[WriteContext, Depends(get_write_context)],
    database: Annotated[Database, Depends(get_database)],
) -> dict[str, Any]:
    """Requires an `Idempotency-Key`; replaying one returns the place the message was given."""
    appended = append_message(
        database,
        context,
        conversation_id=conversation_id,
        message=Message(
            kind=Kind(body.kind),
            content=body.content,
            file_ids=tuple(body.file_ids),
            model=body.model,
            model_version=body.model_version,
            skill_version=body.skill_version,
        ),
    )
    return {"position": appended.position, "replayed": appended.replayed}


@router.post(
    "/entities/{entity_id}/files",
    status_code=status.HTTP_201_CREATED,
    summary="Store a file a person attached, once per company",
    responses=ERRORS,
)
def store_file(
    content: Annotated[
        bytes,
        Body(
            media_type="application/octet-stream",
            description=f"The file itself, at most {MAX_FILE_BYTES} bytes, with its type in "
            "`Content-Type`: a PDF, a PNG, JPEG, GIF or WebP image, or plain text.",
        ),
    ],
    entity_id: Annotated[str, Path()],
    principal: Annotated[Principal, Depends(get_principal)],
    database: Annotated[Database, Depends(get_database)],
    content_type: Annotated[str, Header()] = "",
    request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> FileModel:
    """The same file sent again replays: its identity is its SHA-256. Every file is stored as
    content the organization did not author (`BKP-20`)."""
    uploaded = upload_file(
        database,
        entity_id=entity_id,
        principal=principal,
        request_id=request_id or f"req-{uuid.uuid4().hex}",
        media_type=content_type,
        content=content,
    )
    return _file(uploaded.file, replayed=uploaded.replayed)


@router.get(
    "/entities/{entity_id}/files/{file_id}",
    summary="A file's bytes, with its type",
    responses=ERRORS,
    response_class=Response,
)
def file(
    entity_id: Annotated[str, Path()],
    file_id: Annotated[str, Path()],
    principal: Annotated[Principal, Depends(get_principal)],
    database: Annotated[Database, Depends(get_database)],
) -> Response:
    media_type, content = read_file(
        database, entity_id=entity_id, principal=principal, file_id=file_id
    )
    # Served as an attachment, never rendered in place: the bytes are a third party's, and a
    # browser must not treat them as part of CFOKit's own origin (ADR-0049 § 6).
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": "attachment",
            "X-Content-Type-Options": "nosniff",
        },
    )
