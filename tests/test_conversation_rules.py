"""What a message and a file must be before a conversation stores them (ADR-0075, ADR-0076).

ADR-0036 layer 1: the pure rules, with no database. Expected values come from the records'
stated rules and, for the digest, from the SHA-256 test vector FIPS 180-2 publishes for "abc"
(Appendix B.1), never from running the code.
"""

from __future__ import annotations

import pytest

from cfokit.conversations import (
    MAX_FILE_BYTES,
    MAX_MESSAGE_BYTES,
    Kind,
    Message,
    check_file,
    check_message,
    media_type_of,
)
from cfokit.conversations.errors import FileRefused, MessageInvalid, NotForAPerson
from cfokit.conversations.service import person_of
from cfokit.ledger.service.principal import ActorClass, Principal

PART = {"parts": [{"part_kind": "user-prompt", "content": "How did we do last quarter?"}]}


def response(**over: object) -> Message:
    fields: dict[str, object] = {
        "kind": Kind.RESPONSE,
        "content": PART,
        "model": "claude-opus-5-5",
        "skill_version": "bookkeeper@1",
    }
    fields.update(over)
    return Message(**fields)  # type: ignore[arg-type]


def test_a_request_with_content_is_a_message() -> None:
    check_message(Message(kind=Kind.REQUEST, content=PART))


def test_a_response_naming_its_model_and_skill_is_a_message() -> None:
    check_message(response())


@pytest.mark.parametrize("content", [{}, [], "text", 7, None])
def test_content_is_a_non_empty_json_object_or_array(content: object) -> None:
    with pytest.raises(MessageInvalid):
        check_message(Message(kind=Kind.REQUEST, content=content))


@pytest.mark.parametrize("missing", ["model", "skill_version"])
def test_a_response_that_names_no_model_or_skill_is_refused(missing: str) -> None:
    """`SOC1-06`, `SOC1-35`: a judgment nobody can attribute is not kept as one."""
    with pytest.raises(MessageInvalid):
        check_message(response(**{missing: None}))


def test_a_request_names_no_model() -> None:
    with pytest.raises(MessageInvalid):
        check_message(Message(kind=Kind.REQUEST, content=PART, model="claude-opus-5-5"))


def test_only_a_request_carries_files() -> None:
    """The person attaches files; the model returns none (ADR-0076 § 1)."""
    file_id = "0b9a6c86-2a7e-4f43-8f4a-1f0d6c2c1e11"
    check_message(Message(kind=Kind.REQUEST, content=PART, file_ids=(file_id,)))
    with pytest.raises(MessageInvalid):
        check_message(response(file_ids=(file_id,)))


def test_a_message_names_each_file_once() -> None:
    file_id = "0b9a6c86-2a7e-4f43-8f4a-1f0d6c2c1e11"
    with pytest.raises(MessageInvalid):
        check_message(Message(kind=Kind.REQUEST, content=PART, file_ids=(file_id, file_id)))


def test_a_message_larger_than_its_limit_is_refused() -> None:
    with pytest.raises(MessageInvalid):
        check_message(Message(kind=Kind.REQUEST, content={"text": "x" * MAX_MESSAGE_BYTES}))


def test_a_files_identity_is_its_sha256() -> None:
    """FIPS 180-2 Appendix B.1: SHA-256("abc")."""
    assert check_file("text/plain", b"abc") == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


@pytest.mark.parametrize(
    "media_type",
    ["application/pdf", "image/png", "image/jpeg", "image/gif", "image/webp", "text/plain"],
)
def test_the_types_the_model_reads_are_accepted(media_type: str) -> None:
    check_file(media_type, b"%PDF")


@pytest.mark.parametrize("media_type", ["", "application/zip", "text/html", "image/svg+xml"])
def test_a_type_the_model_does_not_read_is_refused(media_type: str) -> None:
    with pytest.raises(FileRefused):
        check_file(media_type, b"content")


def test_an_empty_file_is_refused() -> None:
    with pytest.raises(FileRefused):
        check_file("application/pdf", b"")


def test_a_file_larger_than_a_request_to_the_model_is_refused() -> None:
    """32 MB is the most the Messages API accepts in one request (ADR-0076)."""
    check_file("text/plain", b"x" * MAX_FILE_BYTES)
    with pytest.raises(FileRefused):
        check_file("text/plain", b"x" * (MAX_FILE_BYTES + 1))


def test_a_media_type_is_stored_without_its_parameters() -> None:
    assert media_type_of("Text/Plain; charset=utf-8") == "text/plain"
    check_file("text/plain; charset=utf-8", b"abc")


def test_a_person_s_conversation_is_their_own() -> None:
    assert person_of(Principal(id="user:geoff", actor_class=ActorClass.PERSON)) == "user:geoff"


def test_an_agent_s_conversation_is_its_person_s() -> None:
    """The agent appends to the conversation of whoever it serves (ADR-0077)."""
    agent = Principal(
        id="client:cfokit-agent", actor_class=ActorClass.AGENT, acting_for="user:geoff"
    )
    assert person_of(agent) == "user:geoff"


def test_a_principal_acting_for_nobody_has_no_conversation() -> None:
    with pytest.raises(NotForAPerson):
        person_of(Principal(id="client:slack", actor_class=ActorClass.AGENT))
