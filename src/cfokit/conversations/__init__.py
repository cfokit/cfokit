"""Conversations with CFOKit's runtime, and the files people attach to them.

ADR-0075 decides the runtime, ADR-0076 where its conversations are kept.

The runtime is a stateless component (ADR-0075); what it and the person said is kept here, in
core, because it is the company's record. A conversation is evidence of what the model was given
and what it did (`SOC1-06`), so it is appended to and never rewritten. Its files are content the
organization did not author (`BKP-20`), and are marked so (`SOC2-01`).

**This module stores messages and interprets none of them.** A message's content is the
runtime's own serialized form, Pydantic AI's provider-neutral JSON, and nothing here reads
inside it; the model and the skill that wrote a response are columns beside it, not fields
fished out of it. The module knows nothing of the ledger's books and never imports another
module (ADR-0022).

What is here is pure: no I/O, no clock, no database. The service does the rest.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from cfokit.conversations.errors import FileRefused, MessageInvalid

__all__ = [
    "MAX_FILE_BYTES",
    "MAX_MESSAGE_BYTES",
    "MEDIA_TYPES",
    "Kind",
    "Message",
    "check_file",
    "check_message",
    "media_type_of",
]

# What the Messages API accepts inline: a PDF, an image, or text (ADR-0076). Anything else would
# be stored and then refused by the model, which is worse than refusing it here.
MEDIA_TYPES = frozenset(
    {"application/pdf", "image/png", "image/jpeg", "image/gif", "image/webp", "text/plain"}
)

# The most the Messages API accepts in one request, and so the most a file can usefully be
# (ADR-0076). The migration holds the same figure.
MAX_FILE_BYTES = 32 * 1024 * 1024

# A message is one turn's request or response, not a document; a file is how a document arrives.
# Large enough for any tool result the published tools return, small enough that a message
# cannot be used to store what should have been a file.
MAX_MESSAGE_BYTES = 1024 * 1024


class Kind(StrEnum):
    """Which way a message went. A request was sent to the model; a response came back."""

    REQUEST = "request"
    RESPONSE = "response"


@dataclass(frozen=True, slots=True)
class Message:
    """One message as the runtime hands it over.

    `content` is opaque here. `file_ids` are the files a request carried, which is what tells
    whether a conversation holds content the organization did not author (ADR-0075 § 2).
    """

    kind: Kind
    content: Any
    file_ids: tuple[str, ...] = ()
    model: str | None = None
    model_version: str | None = None
    skill_version: str | None = None


def check_message(message: Message) -> None:
    """Refuse a message that is not one. Raises; returns nothing.

    A response names the model and the skill that produced it, because a response that does not
    is a judgment nobody can attribute (`SOC1-06`, `SOC1-35`). A request names neither, and only
    a request carries files: the person attaches them, and the model returns none.
    """
    if not isinstance(message.content, dict | list) or not message.content:
        raise MessageInvalid("a message's content is a non-empty JSON object or array")
    size = len(json.dumps(message.content, separators=(",", ":")).encode("utf-8"))
    if size > MAX_MESSAGE_BYTES:
        raise MessageInvalid(
            f"a message's content is at most {MAX_MESSAGE_BYTES} bytes; this is {size}. "
            "A document is attached as a file."
        )
    if len(set(message.file_ids)) != len(message.file_ids):
        raise MessageInvalid("a message names each file once")

    if message.kind is Kind.RESPONSE:
        if not (message.model or "").strip() or not (message.skill_version or "").strip():
            raise MessageInvalid(
                "a response names the model and the skill version that wrote it"
            )
        if message.file_ids:
            raise MessageInvalid("a response carries no files; only a request does")
    elif (
        message.model is not None
        or message.model_version is not None
        or (message.skill_version is not None)
    ):
        raise MessageInvalid("a request names no model; the response it receives does")


def check_file(media_type: str, content: bytes) -> str:
    """Refuse a file the model cannot read, and return its SHA-256 otherwise.

    The digest is the file's identity within a company: the same receipt uploaded twice is one
    file, which is also what makes an upload safe to retry.
    """
    kind = media_type.split(";", 1)[0].strip().lower()
    if kind not in MEDIA_TYPES:
        raise FileRefused(
            f"{kind or 'a file with no type'} is not a type the model reads; send a PDF, an "
            "image (PNG, JPEG, GIF or WebP) or plain text"
        )
    if not content:
        raise FileRefused("the file is empty")
    if len(content) > MAX_FILE_BYTES:
        raise FileRefused(
            f"a file is at most {MAX_FILE_BYTES} bytes, the most the model accepts; this is "
            f"{len(content)}"
        )
    return hashlib.sha256(content).hexdigest()


def media_type_of(media_type: str) -> str:
    """The media type as stored: its type and subtype, lower-cased, without parameters."""
    return media_type.split(";", 1)[0].strip().lower()
