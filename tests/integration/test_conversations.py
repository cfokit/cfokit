"""Conversations and their files, against a real database (ADR-0075, ADR-0076, ADR-0077).

ADR-0036 layer 3. The rules a message and a file must meet are covered without infrastructure
in `tests/test_conversation_rules.py`; what is new here is storage, order, who can see what, the
company boundary, append-only, replay, the audit trail and the complete export. Expected values
are the records' stated rules: a conversation is its person's (`PLT-04`), a company's rows reach
no other company (`SOC2-16`), and nothing stored is ever changed (`SOC1-06`).
"""

from __future__ import annotations

import io
import json
import uuid
import zipfile
from typing import Any

import psycopg
import pytest

from cfokit.conversations import Kind, Message
from cfokit.conversations.errors import (
    ConversationNotFound,
    FileNotFound,
    MessageInvalid,
)
from cfokit.conversations.service import (
    append_message,
    list_conversations,
    read_conversation,
    read_file,
    start_conversation,
    upload_file,
)
from cfokit.ledger.errors import IdempotencyKeyRequired, IdempotencyKeyReused, NotAuthorized
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.administration import create_entity, grant_role
from cfokit.ledger.service.interchange import export_complete
from cfokit.ledger.service.principal import ActorClass, Principal
from cfokit.ledger.service.write import WriteContext

pytestmark = pytest.mark.integration

OWNER = Principal(id="user:geoff", actor_class=ActorClass.PERSON)
COLLEAGUE = Principal(id="user:sam", actor_class=ActorClass.PERSON)
AGENT = Principal(id="skill:agent", actor_class=ActorClass.AGENT, acting_for=OWNER.id)
STRANGER = Principal(id="user:nobody", actor_class=ActorClass.PERSON)

ASKED = {"parts": [{"part_kind": "user-prompt", "content": "How did we do last quarter?"}]}
ANSWERED = {"parts": [{"part_kind": "text", "content": "Revenue was 1,200.00."}]}
RECEIPT = b"%PDF-1.7\n% a receipt\n"


def context(entity: str, principal: Principal = OWNER, key: str | None = None) -> WriteContext:
    return WriteContext(
        entity_id=entity,
        principal=principal,
        request_id="req-test",
        idempotency_key=key if key is not None else uuid.uuid4().hex,
    )


def start(database: Database, entity: str, principal: Principal = OWNER) -> str:
    return start_conversation(database, context(entity, principal)).conversation_id


def asked(*file_ids: str) -> Message:
    return Message(kind=Kind.REQUEST, content=ASKED, file_ids=file_ids)


def answered() -> Message:
    return Message(
        kind=Kind.RESPONSE,
        content=ANSWERED,
        model="claude-opus-5-5",
        model_version="claude-opus-5-5",
        skill_version="bookkeeper@1",
    )


def upload(database: Database, entity: str, content: bytes = RECEIPT) -> Any:
    return upload_file(
        database,
        entity_id=entity,
        principal=OWNER,
        request_id="req-test",
        media_type="application/pdf",
        content=content,
    )


def another_company(database: Database) -> str:
    return create_entity(
        database,
        principal=OWNER,
        request_id="fixture",
        slug=f"other-{uuid.uuid4().hex[:12]}",
        name="Other",
        accounting_basis="accrual",
        fiscal_year_end_month=12,
        fiscal_year_end_day=31,
        functional_currency="USD",
        time_zone="UTC",
    ).entity_id


def audit_count(app_conn: psycopg.Connection[Any], entity: str, action: str) -> int:
    with app_conn.cursor() as cur:
        cur.execute("SELECT set_config('cfokit.entity_id', %s, false)", (entity,))
        cur.execute(
            "SELECT count(*) FROM audit_log WHERE entity_id = %s AND action = %s",
            (entity, action),
        )
        return int((cur.fetchone() or [0])[0])


def test_messages_are_kept_in_the_order_they_were_added(
    database: Database, owned_books: tuple[str, str, str]
) -> None:
    entity, _, _ = owned_books
    conversation_id = start(database, entity)

    first = append_message(
        database, context(entity), conversation_id=conversation_id, message=asked()
    )
    second = append_message(
        database, context(entity), conversation_id=conversation_id, message=answered()
    )

    assert (first.position, second.position) == (1, 2)
    thread = read_conversation(
        database, entity_id=entity, principal=OWNER, conversation_id=conversation_id
    )
    assert [m.position for m in thread.messages] == [1, 2]
    assert thread.messages[0].message.content == ASKED
    assert thread.messages[1].message.model == "claude-opus-5-5"
    assert thread.messages[1].message.skill_version == "bookkeeper@1"
    assert not thread.conversation.holds_untrusted


def test_reading_after_a_place_returns_only_what_came_later(
    database: Database, owned_books: tuple[str, str, str]
) -> None:
    entity, _, _ = owned_books
    conversation_id = start(database, entity)
    for message in (asked(), answered(), asked()):
        append_message(
            database, context(entity), conversation_id=conversation_id, message=message
        )

    later = read_conversation(
        database, entity_id=entity, principal=OWNER, conversation_id=conversation_id, after=2
    )
    assert [m.position for m in later.messages] == [3]


def test_a_conversation_holding_a_file_says_so(
    database: Database, owned_books: tuple[str, str, str]
) -> None:
    """What ADR-0075 § 2 reads to withhold every posting tool for the rest of it (`PLT-23`)."""
    entity, _, _ = owned_books
    conversation_id = start(database, entity)
    receipt = upload(database, entity).file

    append_message(
        database, context(entity), conversation_id=conversation_id, message=asked(receipt.id)
    )
    append_message(
        database, context(entity), conversation_id=conversation_id, message=answered()
    )

    thread = read_conversation(
        database, entity_id=entity, principal=OWNER, conversation_id=conversation_id
    )
    assert thread.conversation.holds_untrusted
    assert thread.messages[0].message.file_ids == (receipt.id,)


def test_a_conversation_is_its_person_s_alone(
    database: Database, owned_books: tuple[str, str, str]
) -> None:
    """`PLT-04`. A colleague in the same company neither sees it listed nor can read it."""
    entity, _, _ = owned_books
    grant_role(
        database,
        entity_id=entity,
        principal=OWNER,
        request_id="req",
        to_principal=COLLEAGUE.id,
        role="owner",
    )
    conversation_id = start(database, entity)

    assert list_conversations(database, entity_id=entity, principal=COLLEAGUE) == []
    with pytest.raises(ConversationNotFound):
        read_conversation(
            database, entity_id=entity, principal=COLLEAGUE, conversation_id=conversation_id
        )
    with pytest.raises(ConversationNotFound):
        append_message(
            database,
            context(entity, COLLEAGUE),
            conversation_id=conversation_id,
            message=asked(),
        )


def test_an_agent_acting_for_the_person_works_in_their_conversation(
    database: Database, owned_books: tuple[str, str, str]
) -> None:
    """The agent appends to the conversation of whoever it serves (ADR-0077)."""
    entity, _, _ = owned_books
    grant_role(
        database,
        entity_id=entity,
        principal=OWNER,
        request_id="req",
        to_principal=AGENT.id,
        role="owner",
    )
    conversation_id = start(database, entity, AGENT)

    append_message(
        database, context(entity, AGENT), conversation_id=conversation_id, message=answered()
    )

    mine = list_conversations(database, entity_id=entity, principal=OWNER)
    assert [c.id for c in mine] == [conversation_id]
    thread = read_conversation(
        database, entity_id=entity, principal=OWNER, conversation_id=conversation_id
    )
    assert thread.messages[0].recorded_by == f"{AGENT.id} for {OWNER.id}"


def test_a_stranger_is_refused(database: Database, owned_books: tuple[str, str, str]) -> None:
    entity, _, _ = owned_books
    with pytest.raises(NotAuthorized):
        start(database, entity, STRANGER)
    with pytest.raises(NotAuthorized):
        list_conversations(database, entity_id=entity, principal=STRANGER)


def test_an_unknown_or_malformed_conversation_is_not_found(
    database: Database, owned_books: tuple[str, str, str]
) -> None:
    entity, _, _ = owned_books
    for conversation_id in (str(uuid.uuid4()), "not-an-id"):
        with pytest.raises(ConversationNotFound):
            read_conversation(
                database, entity_id=entity, principal=OWNER, conversation_id=conversation_id
            )


def test_a_message_needs_an_idempotency_key(
    database: Database, owned_books: tuple[str, str, str]
) -> None:
    entity, _, _ = owned_books
    conversation_id = start(database, entity)
    with pytest.raises(IdempotencyKeyRequired):
        append_message(
            database, context(entity, key=""), conversation_id=conversation_id, message=asked()
        )


def test_the_same_key_replays_the_place_and_adds_nothing(
    database: Database, owned_books: tuple[str, str, str], app_conn: psycopg.Connection[Any]
) -> None:
    """ADR-0029: an agent retrying after a dropped response must not add the message twice."""
    entity, _, _ = owned_books
    conversation_id = start(database, entity)
    once = context(entity, key="retry-me")

    first = append_message(database, once, conversation_id=conversation_id, message=asked())
    again = append_message(database, once, conversation_id=conversation_id, message=asked())

    assert (again.position, again.replayed) == (first.position, True)
    thread = read_conversation(
        database, entity_id=entity, principal=OWNER, conversation_id=conversation_id
    )
    assert len(thread.messages) == 1
    assert audit_count(app_conn, entity, "append_conversation_message") == 1


def test_a_key_reused_for_a_different_message_is_refused(
    database: Database, owned_books: tuple[str, str, str]
) -> None:
    entity, _, _ = owned_books
    conversation_id = start(database, entity)
    append_message(
        database, context(entity, key="once"), conversation_id=conversation_id, message=asked()
    )
    with pytest.raises(IdempotencyKeyReused):
        append_message(
            database,
            context(entity, key="once"),
            conversation_id=conversation_id,
            message=answered(),
        )


def test_a_file_is_stored_once_per_company(
    database: Database, owned_books: tuple[str, str, str], app_conn: psycopg.Connection[Any]
) -> None:
    """Its identity is its SHA-256, so the same receipt twice is one file and one audit row."""
    entity, _, _ = owned_books
    first = upload(database, entity)
    again = upload(database, entity)

    assert not first.replayed and again.replayed
    assert again.file.id == first.file.id
    assert audit_count(app_conn, entity, "upload_conversation_file") == 1
    assert read_file(database, entity_id=entity, principal=OWNER, file_id=first.file.id) == (
        "application/pdf",
        RECEIPT,
    )


def test_a_message_cannot_name_another_company_s_file(
    database: Database, owned_books: tuple[str, str, str]
) -> None:
    """`SOC2-16`: a file id from one company names nothing in another."""
    entity, _, _ = owned_books
    other = another_company(database)
    theirs = upload(database, other, b"their receipt").file
    conversation_id = start(database, entity)

    with pytest.raises(MessageInvalid):
        append_message(
            database,
            context(entity),
            conversation_id=conversation_id,
            message=asked(theirs.id),
        )
    with pytest.raises(FileNotFound):
        read_file(database, entity_id=entity, principal=OWNER, file_id=theirs.id)


def test_another_company_s_rows_are_invisible_to_the_application(
    database: Database, owned_books: tuple[str, str, str], app_conn: psycopg.Connection[Any]
) -> None:
    """Row-level security, the second of two layers (`src/cfokit/ledger/CLAUDE.md`)."""
    entity, _, _ = owned_books
    other = another_company(database)
    start(database, other)
    upload(database, other, b"their receipt")

    with app_conn.cursor() as cur:
        cur.execute("SELECT set_config('cfokit.entity_id', %s, false)", (entity,))
        cur.execute("SELECT count(*) FROM conversation WHERE entity_id = %s", (other,))
        assert (cur.fetchone() or [None])[0] == 0
        cur.execute("SELECT count(*) FROM conversation_file WHERE entity_id = %s", (other,))
        assert (cur.fetchone() or [None])[0] == 0


def test_a_message_can_never_join_another_company_s_conversation(
    database: Database, owned_books: tuple[str, str, str], owner_conn: psycopg.Connection[Any]
) -> None:
    """A foreign key is checked past row-level security, so the key itself names the company."""
    entity, _, _ = owned_books
    other = another_company(database)
    theirs = start(database, other)

    with owner_conn.cursor() as cur, pytest.raises(psycopg.errors.ForeignKeyViolation):
        cur.execute(
            "INSERT INTO conversation_message"
            " (entity_id, conversation_id, position, kind, content, recorded_by)"
            " VALUES (%s, %s, 1, 'request', '{\"x\": 1}', 'user:geoff')",
            (entity, theirs),
        )


def test_nothing_stored_is_ever_changed(
    database: Database, owned_books: tuple[str, str, str], owner_conn: psycopg.Connection[Any]
) -> None:
    """`SOC1-06`: what the model saw is recoverable because no row is rewritten or removed."""
    entity, _, _ = owned_books
    conversation_id = start(database, entity)
    receipt = upload(database, entity).file
    append_message(
        database, context(entity), conversation_id=conversation_id, message=asked(receipt.id)
    )

    for statement in (
        "UPDATE conversation_message SET content = '{\"x\": 1}' WHERE conversation_id = %s",
        "DELETE FROM conversation_message_file WHERE entity_id = %s"
        " AND message_id IN (SELECT id FROM conversation_message WHERE conversation_id = %s)",
        "DELETE FROM conversation WHERE id = %s",
    ):
        params = (entity, conversation_id) if statement.count("%s") == 2 else (conversation_id,)
        with owner_conn.cursor() as cur, pytest.raises(psycopg.errors.RestrictViolation):
            cur.execute(statement, params)
    with owner_conn.cursor() as cur, pytest.raises(psycopg.errors.RestrictViolation):
        cur.execute(
            "UPDATE conversation_file SET media_type = 'text/plain' WHERE id = %s",
            (receipt.id,),
        )


def test_every_change_writes_one_audit_row(
    database: Database, owned_books: tuple[str, str, str], app_conn: psycopg.Connection[Any]
) -> None:
    entity, _, _ = owned_books
    conversation_id = start(database, entity)
    append_message(database, context(entity), conversation_id=conversation_id, message=asked())
    read_conversation(
        database, entity_id=entity, principal=OWNER, conversation_id=conversation_id
    )

    assert audit_count(app_conn, entity, "start_conversation") == 1
    assert audit_count(app_conn, entity, "append_conversation_message") == 1


def test_the_complete_export_carries_conversations_and_their_files(
    database: Database, owned_books: tuple[str, str, str]
) -> None:
    """`EXP-02`: the record of what an agent did, and the documents it was given."""
    entity, _, _ = owned_books
    conversation_id = start(database, entity)
    receipt = upload(database, entity).file
    append_message(
        database, context(entity), conversation_id=conversation_id, message=asked(receipt.id)
    )

    bundle = export_complete(
        database, entity_id=entity, principal=OWNER, request_id="req"
    ).archive
    with zipfile.ZipFile(io.BytesIO(bundle)) as opened:
        assert opened.read(f"files/{receipt.sha256}") == RECEIPT
        messages = [
            json.loads(line)
            for line in opened.read("tables/conversation_message.jsonl").decode().splitlines()
        ]
        files = [
            json.loads(line)
            for line in opened.read("tables/conversation_file.jsonl").decode().splitlines()
        ]
    assert [m["content"] for m in messages] == [ASKED]
    assert [f["classification"] for f in files] == ["untrusted"]
    assert "content" not in files[0]
