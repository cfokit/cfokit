"""Notifications for lines no rule resolved, against real books (`PLT-07`, `BKP-12`).

ADR-0036 layer 3. Each expected value is ADR-0052's or ADR-0056's stated confirmation: a
notification is committed with its act or not at all, it reaches only someone holding a role in
its entity, the act that answers its subject closes it for every recipient, and a dismissal is
the recipient's own act, for them alone, with one audit row.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient
from mcp.server.auth.middleware.auth_context import auth_context_var
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.auth.provider import AccessToken

from cfokit.assignment import Field, Operator, Predicate
from cfokit.assignment.candidate import Candidate, SourceKind
from cfokit.assignment.service import (
    UNRESOLVED_TRANSACTION,
    apply_rules,
    approve,
    open_questions,
)
from cfokit.ledger.config import Settings
from cfokit.ledger.errors import NotAPerson, NotificationNotFound, RecipientHoldsNoRole
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.administration import create_account, grant_role
from cfokit.ledger.service.notifications import dismiss, notify, open_notifications
from cfokit.ledger.service.principal import ActorClass, Principal
from cfokit.ledger.service.write import WriteContext
from cfokit.server import mcp_server, rest_app

pytestmark = pytest.mark.integration

OWNER = Principal(id="user:geoff", actor_class=ActorClass.PERSON)
CO_OWNER = Principal(id="user:partner", actor_class=ActorClass.PERSON)
READER = Principal(id="user:onlyreads", actor_class=ActorClass.PERSON)
AGENT = Principal(id="skill:bookkeeper", actor_class=ActorClass.AGENT, acting_for=OWNER.id)


@pytest.fixture
def entity(database: Database, owned_books: tuple[str, str, str]) -> str:
    """Books held by two owners, read by one more, with the bookkeeping skill granted a reader
    role so it can act for an owner under the intersection of both (`IAM-11`)."""
    entity_id = owned_books[0]
    for to, role in (
        (CO_OWNER.id, "owner"),
        (READER.id, "reader"),
        (AGENT.id, "reader"),
    ):
        grant_role(
            database,
            entity_id=entity_id,
            principal=OWNER,
            request_id="notifications-test",
            to_principal=to,
            role=role,
        )
    return entity_id


@pytest.fixture
def chart(database: Database, entity: str, owned_books: tuple[str, str, str]) -> dict[str, str]:
    return {
        "Bank": owned_books[1],
        "Insurance": create_account(
            database,
            entity_id=entity,
            principal=OWNER,
            request_id="notifications-test",
            code="6200",
            name="Insurance",
            account_type="expense",
        ),
    }


def line(chart: dict[str, str], ref: str) -> Candidate:
    return Candidate(
        payee="ACME Insurance Co",
        amount=Decimal("-240.00"),
        commodity="USD",
        source_account_id=chart["Bank"],
        transaction_date=date(2026, 3, 1),
        source_kind=SourceKind.FEED,
        source_ref=ref,
    )


def run(database: Database, entity: str, *candidates: Candidate) -> None:
    apply_rules(
        database,
        entity_id=entity,
        principal=OWNER,
        request_id=f"run-{uuid.uuid4().hex}",
        candidates=list(candidates),
    )


def approve_acme(database: Database, entity: str, chart: dict[str, str]) -> None:
    approve(
        database,
        entity_id=entity,
        principal=OWNER,
        label="ACME to insurance",
        precedence=10,
        account_id=chart["Insurance"],
        predicates=(Predicate(1, Field.PAYEE, Operator.CONTAINS, "acme"),),
    )


def opened(database: Database, entity: str, who: Principal) -> list[str]:
    return [
        n.subject_ref for n in open_notifications(database, entity_id=entity, principal=who)
    ]


def rows(conn: psycopg.Connection[Any], sql: str, *params: object) -> list[tuple[Any, ...]]:
    """Read as the schema owner, which sees every row whatever the entity scope."""
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def dismissal(entity: str, who: Principal, key: str | None = None) -> WriteContext:
    return WriteContext(
        entity_id=entity,
        principal=who,
        request_id="dismissal-test",
        idempotency_key=key or f"dismiss-{uuid.uuid4().hex}",
    )


# --- Raised with the question ---------------------------------------------------------------


def test_an_unresolved_line_asks_everyone_who_could_answer_it(
    database: Database, entity: str, chart: dict[str, str]
) -> None:
    """Whoever may approve a rule is asked, and nobody else: a reader cannot answer by
    approving, so a question in their list is one they can do nothing about."""
    run(database, entity, line(chart, "line-1"))

    assert opened(database, entity, OWNER) == ["line-1"]
    assert opened(database, entity, CO_OWNER) == ["line-1"]
    assert opened(database, entity, READER) == []


def test_the_notification_carries_no_figure(
    database: Database, entity: str, chart: dict[str, str]
) -> None:
    """ADR-0052 § 6: identifiers, a class and a link — nothing a lock screen should show."""
    run(database, entity, line(chart, "line-1"))

    [found] = open_notifications(database, entity_id=entity, principal=OWNER)
    assert found.notification_class == UNRESOLVED_TRANSACTION
    assert found.link == f"/app/companies/{entity}/questions"
    assert "240" not in found.subject_ref + found.link
    assert "acme" not in (found.subject_ref + found.link).lower()


def test_running_an_unanswered_line_again_asks_once(
    database: Database, entity: str, chart: dict[str, str]
) -> None:
    """A re-run replays the question rather than raising it again."""
    run(database, entity, line(chart, "line-1"))
    run(database, entity, line(chart, "line-1"))

    assert opened(database, entity, OWNER) == ["line-1"]


def test_a_resolved_line_raises_nothing(
    database: Database, entity: str, chart: dict[str, str]
) -> None:
    approve_acme(database, entity, chart)
    run(database, entity, line(chart, "line-1"))

    assert opened(database, entity, OWNER) == []


def test_a_rolled_back_act_leaves_no_notification(
    database: Database, entity: str, owner_conn: psycopg.Connection[Any]
) -> None:
    """ADR-0052's first confirmation: the notification is in the act's commit or nowhere."""

    class Abandoned(Exception):
        pass

    with pytest.raises(Abandoned), database.entity_write(entity) as write:
        notify(
            write,
            recipient=OWNER.id,
            notification_class=UNRESOLVED_TRANSACTION,
            subject_ref="never-committed",
            link="/app/",
        )
        raise Abandoned

    assert rows(owner_conn, "SELECT 1 FROM notification WHERE entity_id = %s", entity) == []


def test_a_recipient_with_no_role_is_refused(database: Database, entity: str) -> None:
    """ADR-0052 § 1: checked before the row is written."""
    with pytest.raises(RecipientHoldsNoRole), database.entity_write(entity) as write:
        notify(
            write,
            recipient="user:stranger",
            notification_class=UNRESOLVED_TRANSACTION,
            subject_ref="line-1",
            link="/app/",
        )


# --- Closed by the answer -------------------------------------------------------------------


def test_the_answer_closes_it_for_every_recipient(
    database: Database,
    entity: str,
    chart: dict[str, str],
    owner_conn: psycopg.Connection[Any],
) -> None:
    """ADR-0056 § 1: the owner approving a rule and the line being run again answers the
    question, so neither owner is still asked — and the closing row names the act."""
    run(database, entity, line(chart, "line-1"))
    approve_acme(database, entity, chart)
    run(database, entity, line(chart, "line-1"))

    assert opened(database, entity, OWNER) == []
    assert opened(database, entity, CO_OWNER) == []

    closings = rows(
        owner_conn,
        "SELECT c.kind, c.act_ref, d.outcome FROM notification_closing c"
        "  JOIN assignment_decision d ON d.id::text = c.act_ref"
        " WHERE c.entity_id = %s",
        entity,
    )
    assert closings == [("answered", closings[0][1], "assigned")] * 2


def test_answering_one_line_leaves_the_others_open(
    database: Database, entity: str, chart: dict[str, str]
) -> None:
    run(database, entity, line(chart, "line-1"), line(chart, "line-2"))
    approve_acme(database, entity, chart)
    run(database, entity, line(chart, "line-1"))

    assert opened(database, entity, OWNER) == ["line-2"]


def test_the_worklist_lists_the_question_until_it_is_answered(
    database: Database, entity: str, chart: dict[str, str]
) -> None:
    """`BKP-12`: what the person is shown is what is still unanswered."""
    run(database, entity, line(chart, "line-1"))

    [question] = open_questions(database, entity_id=entity, principal=AGENT)
    assert question.candidate.source_ref == "line-1"
    assert question.candidate.payee == "ACME Insurance Co"
    assert question.candidate.amount == Decimal("-240.00")

    approve_acme(database, entity, chart)
    run(database, entity, line(chart, "line-1"))

    assert open_questions(database, entity_id=entity, principal=OWNER) == ()


# --- Read by the person, and by the agent acting for them ----------------------------------


def test_an_agent_reads_the_notifications_of_the_person_it_acts_for(
    database: Database, entity: str, chart: dict[str, str]
) -> None:
    """ADR-0056 § 4: the agent reads what the person was asked, never a list of its own."""
    run(database, entity, line(chart, "line-1"))

    assert opened(database, entity, AGENT) == ["line-1"]


# --- Dismissed by the recipient, as themselves ----------------------------------------------


def test_a_dismissal_closes_it_for_the_recipient_alone(
    database: Database,
    entity: str,
    chart: dict[str, str],
    owner_conn: psycopg.Connection[Any],
) -> None:
    run(database, entity, line(chart, "line-1"))
    [mine] = open_notifications(database, entity_id=entity, principal=OWNER)

    dismiss(database, dismissal(entity, OWNER), notification_id=mine.id)

    assert opened(database, entity, OWNER) == []
    assert opened(database, entity, CO_OWNER) == ["line-1"]
    assert rows(
        owner_conn,
        "SELECT actor, subject_id::text FROM audit_log"
        " WHERE entity_id = %s AND action = 'dismiss_notification'",
        entity,
    ) == [(OWNER.id, mine.id)]


def test_a_repeated_dismissal_writes_nothing_more(
    database: Database,
    entity: str,
    chart: dict[str, str],
    owner_conn: psycopg.Connection[Any],
) -> None:
    """A retry under the same key replays (ADR-0029); a second key finds it already closed."""
    run(database, entity, line(chart, "line-1"))
    [mine] = open_notifications(database, entity_id=entity, principal=OWNER)

    dismiss(database, dismissal(entity, OWNER, "same-key"), notification_id=mine.id)
    again = dismiss(database, dismissal(entity, OWNER, "same-key"), notification_id=mine.id)
    dismiss(database, dismissal(entity, OWNER), notification_id=mine.id)

    assert again.replayed
    assert (
        len(
            rows(
                owner_conn,
                "SELECT 1 FROM audit_log"
                " WHERE entity_id = %s AND action = 'dismiss_notification'",
                entity,
            )
        )
        == 1
    )


def test_an_agent_cannot_dismiss(
    database: Database, entity: str, chart: dict[str, str]
) -> None:
    """ADR-0056 § 2: an agent that could dismiss a question it raised could make it look
    resolved (`NFR-16`), whatever the person it acts for may do."""
    run(database, entity, line(chart, "line-1"))
    [theirs] = open_notifications(database, entity_id=entity, principal=OWNER)

    with pytest.raises(NotAPerson):
        dismiss(database, dismissal(entity, AGENT), notification_id=theirs.id)

    assert opened(database, entity, OWNER) == ["line-1"]


def test_nobody_dismisses_another_persons_notification(
    database: Database, entity: str, chart: dict[str, str]
) -> None:
    """Refused as not found: a caller sees only what is addressed to them."""
    run(database, entity, line(chart, "line-1"))
    [theirs] = open_notifications(database, entity_id=entity, principal=OWNER)

    with pytest.raises(NotificationNotFound):
        dismiss(database, dismissal(entity, CO_OWNER), notification_id=theirs.id)

    assert opened(database, entity, OWNER) == ["line-1"]


def test_a_dismissed_question_answered_later_gains_its_answer(
    database: Database,
    entity: str,
    chart: dict[str, str],
    owner_conn: psycopg.Connection[Any],
) -> None:
    """ADR-0056 § 2: nothing re-opens, and the record still says what answered it."""
    run(database, entity, line(chart, "line-1"))
    [mine] = open_notifications(database, entity_id=entity, principal=OWNER)
    dismiss(database, dismissal(entity, OWNER), notification_id=mine.id)

    approve_acme(database, entity, chart)
    run(database, entity, line(chart, "line-1"))

    assert sorted(
        kind
        for (kind,) in rows(
            owner_conn,
            "SELECT kind FROM notification_closing WHERE notification_id = %s",
            mine.id,
        )
    ) == ["answered", "dismissed"]
    assert opened(database, entity, OWNER) == []


# --- Over the published interfaces, as a client drives them ---------------------------------

ISSUER = "http://localhost:8180/realms/cfokit"


def claims(who: Principal) -> dict[str, Any]:
    """A verified token's claims. An agent's carries RFC 8693's `act`, naming the person."""
    found: dict[str, Any] = {"sub": who.id, "iss": ISSUER, "aud": "cfokit-ledger"}
    if who.acting_for is not None:
        found["act"] = {"sub": who.acting_for}
    return found


class StubAuthenticator:
    """Stands in for the issuer; the claims still go through `principal_from_claims`."""

    def __init__(self, who: Principal) -> None:
        self._who = who

    def claims_for(self, credential: str | None) -> dict[str, Any]:
        return claims(self._who)


def settings(app_dsn: str) -> Settings:
    return Settings(
        database_url=app_dsn,
        public_base_url="http://localhost:8080",
        auth_issuer_url=ISSUER,
        auth_audience="cfokit-ledger",
    )


def rest(app_dsn: str, who: Principal) -> TestClient:
    return TestClient(rest_app(settings(app_dsn), authenticator=StubAuthenticator(who)))


@contextmanager
def authenticated(who: Principal) -> Iterator[None]:
    """Present a verified token to the MCP tools, as the SDK's bearer middleware does."""
    token = AccessToken(
        token="stub",  # noqa: S106 — a stand-in, never validated
        client_id=who.id,
        scopes=[],
        subject=who.id,
        claims=claims(who),
    )
    reset = auth_context_var.set(AuthenticatedUser(token))
    try:
        yield
    finally:
        auth_context_var.reset(reset)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def test_rest_lists_answers_and_dismisses(
    app_dsn: str, entity: str, chart: dict[str, str]
) -> None:
    """The web client's path: the worklist, the person's notifications, and a dismissal."""
    run(database := Database(app_dsn), entity, line(chart, "line-1"))
    owner = rest(app_dsn, OWNER)

    worklist = owner.get(f"/entities/{entity}/unresolved-transactions")
    assert worklist.status_code == 200
    assert [q["source_ref"] for q in worklist.json()["unresolved"]] == ["line-1"]

    listed = owner.get(f"/entities/{entity}/notifications")
    assert listed.status_code == 200
    [notification] = listed.json()["notifications"]
    assert notification["notification_class"] == "unresolved_transaction"
    assert notification["subject_ref"] == "line-1"

    dismissed = owner.post(
        f"/entities/{entity}/notifications/{notification['notification_id']}/dismissal",
        headers={"Idempotency-Key": uuid.uuid4().hex},
    )
    assert dismissed.status_code == 201
    assert owner.get(f"/entities/{entity}/notifications").json()["notifications"] == []
    assert opened(database, entity, CO_OWNER) == ["line-1"]


def test_rest_refuses_an_agents_dismissal(
    app_dsn: str, entity: str, chart: dict[str, str]
) -> None:
    run(Database(app_dsn), entity, line(chart, "line-1"))
    [notification] = (
        rest(app_dsn, OWNER).get(f"/entities/{entity}/notifications").json()["notifications"]
    )

    refused = rest(app_dsn, AGENT).post(
        f"/entities/{entity}/notifications/{notification['notification_id']}/dismissal",
        headers={"Idempotency-Key": uuid.uuid4().hex},
    )

    assert refused.status_code == 403
    assert refused.json()["code"] == "not_a_person"


@pytest.mark.anyio
async def test_the_agent_reads_the_question_and_its_line_over_mcp(
    app_dsn: str, entity: str, chart: dict[str, str]
) -> None:
    """What the bookkeeping skill does when a notification opens a conversation: read what
    the person was asked, then the line it is about."""
    run(Database(app_dsn), entity, line(chart, "line-1"))
    server: Any = mcp_server(settings(app_dsn), authenticator=StubAuthenticator(AGENT))

    async def call(name: str) -> dict[str, Any]:
        result = await server.call_tool(name, {"entity_id": entity})
        payload: dict[str, Any] = json.loads(result.content[0].text)
        return payload

    with authenticated(AGENT):
        notifications = await call("open_notifications")
        unresolved = await call("unresolved_transactions")

    assert [n["subject_ref"] for n in notifications["notifications"]] == ["line-1"]
    assert [q["source_ref"] for q in unresolved["unresolved"]] == ["line-1"]
    assert unresolved["unresolved"][0]["amount"] == "-240.0000000000"
