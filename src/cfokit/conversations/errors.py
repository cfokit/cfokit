"""This module's refusals, subclassing the ledger's so both adapters render them alike.

Every code is published in `docs/contracts/error-codes.json` the moment the class exists.
"""

from __future__ import annotations

from cfokit.ledger.errors import LedgerError

__all__ = [
    "ConversationNotFound",
    "FileNotFound",
    "FileRefused",
    "MessageInvalid",
    "NotForAPerson",
]


class MessageInvalid(LedgerError):
    """A message that cannot be stored as one: empty content, a response naming no model, a
    request naming one, or files on a response."""

    code = "message_invalid"
    status = 422


class FileRefused(LedgerError):
    """A file the model could not read: a type it does not accept, an empty file, or one larger
    than a request to it may be (ADR-0076)."""

    code = "file_refused"
    status = 422


class ConversationNotFound(LedgerError):
    """No conversation with this id for this person in this entity.

    Another person's conversation is indistinguishable from an absent one, for the reason
    `entity_not_found` gives: saying otherwise would tell a caller it exists (`PLT-04`).
    """

    code = "conversation_not_found"
    status = 404


class FileNotFound(LedgerError):
    """No file with this id in this entity."""

    code = "file_not_found"
    status = 404


class NotForAPerson(LedgerError):
    """A principal acting for nobody asked for a conversation.

    A conversation is a person's (`PLT-04`). A component running unattended has no person, so
    it has no conversation to start or read; what it leaves for one goes through core's own
    handlers instead (ADR-0077 § 2).
    """

    code = "not_for_a_person"
    status = 403
