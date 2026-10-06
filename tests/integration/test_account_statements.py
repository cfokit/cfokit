"""An uploaded statement, against real books (`BKP-03`, `BKP-19`, `BKP-21`, ADR-0046).

ADR-0036 layer 3. The proof itself is covered without infrastructure in
`tests/test_activity.py`; what is new here is storage, replay, overlap, isolation, and the whole
path a Claude Desktop session takes — driven through `call_tool`, composing arguments the way
the model does, from what the previous tool returned.
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
from mcp.server.auth.middleware.auth_context import auth_context_var
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.auth.provider import AccessToken
from mcp.types import CallToolResult

from cfokit.activity import Statement, StatementLine
from cfokit.activity.errors import (
    StatementDoesNotBalance,
    StatementNotFound,
    StatementOverlaps,
)
from cfokit.activity.service import record_statement, statement_agreement
from cfokit.ledger.config import Settings
from cfokit.ledger.errors import AccountNotFound
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.administration import create_account, create_entity
from cfokit.ledger.service.principal import ActorClass, Principal
from cfokit.server import mcp_server

pytestmark = pytest.mark.integration

OWNER = Principal(id="user:geoff", actor_class=ActorClass.PERSON)


def march(account_id: str, *, closing: str = "1195.50", **over: Any) -> Statement:
    """1000.00 + 250.00 - 45.50 - 4.50 - 4.50 = 1195.50, by hand. Two identical coffees."""
    fields: dict[str, Any] = {
        "account_id": account_id,
        "period_start": date(2026, 3, 1),
        "period_end": date(2026, 3, 31),
        "opening_balance": Decimal("1000.00"),
        "closing_balance": Decimal(closing),
        "commodity": "USD",
        "lines": (
            StatementLine(date(2026, 3, 2), "Client A", Decimal("250.00")),
            StatementLine(date(2026, 3, 9), "City Utility", Decimal("-45.50")),
            StatementLine(date(2026, 3, 12), "Coffee House", Decimal("-4.50")),
            StatementLine(date(2026, 3, 12), "Coffee House", Decimal("-4.50")),
        ),
    }
    fields.update(over)
    return Statement(**fields)


def audit_rows(app_conn: psycopg.Connection[Any], entity: str) -> int:
    with app_conn.cursor() as cur:
        cur.execute("SELECT set_config('cfokit.entity_id', %s, false)", (entity,))
        cur.execute(
            "SELECT count(*) FROM audit_log WHERE entity_id = %s"
            " AND action = 'record_account_statement'",
            (entity,),
        )
        return int((cur.fetchone() or [0])[0])


def record(database: Database, entity: str, statement: Statement) -> Any:
    return record_statement(
        database,
        entity_id=entity,
        principal=OWNER,
        request_id="statement-test",
        statement=statement,
    )


# --- Recording --------------------------------------------------------------------------------


def test_a_statement_is_stored_with_every_line(
    database: Database, owned_books: tuple[str, str, str], app_conn: psycopg.Connection[Any]
) -> None:
    entity, cash, _ = owned_books

    recorded = record(database, entity, march(cash))

    assert not recorded.replayed
    assert len(recorded.stored.statement.lines) == 4
    assert audit_rows(app_conn, entity) == 1


def test_the_same_statement_sent_again_replays(
    database: Database, owned_books: tuple[str, str, str], app_conn: psycopg.Connection[Any]
) -> None:
    """A retry, or the operator uploading the same PDF twice. Nothing new, and no audit row —
    a replay is not a state change."""
    entity, cash, _ = owned_books

    first = record(database, entity, march(cash))
    again = record(database, entity, march(cash))

    assert again.replayed
    assert again.stored.id == first.stored.id
    assert audit_rows(app_conn, entity) == 1


def test_a_different_statement_over_the_same_days_is_refused(
    database: Database, owned_books: tuple[str, str, str]
) -> None:
    """Two statements claiming the same days of one account are never both genuine; the
    second is refused rather than merged."""
    entity, cash, _ = owned_books
    record(database, entity, march(cash))

    overlapping = march(
        cash,
        period_start=date(2026, 3, 15),
        period_end=date(2026, 4, 14),
        opening_balance=Decimal("1195.50"),
        lines=(),
    )
    with pytest.raises(StatementOverlaps):
        record(database, entity, overlapping)


def test_the_next_statement_follows_on(
    database: Database, owned_books: tuple[str, str, str]
) -> None:
    """`BKP-21`: continuity is reported against what the previous statement covered."""
    entity, cash, _ = owned_books
    march_id = record(database, entity, march(cash)).stored.id

    april = record(
        database,
        entity,
        march(
            cash,
            period_start=date(2026, 4, 1),
            period_end=date(2026, 4, 30),
            opening_balance=Decimal("1195.50"),
            closing="1195.50",
            lines=(),
        ),
    )

    assert april.continuity is not None
    assert april.continuity.previous_statement_id == march_id
    assert april.continuity.contiguous
    assert april.continuity.balance_continues


def test_a_statement_that_does_not_balance_stores_nothing(
    database: Database, owned_books: tuple[str, str, str], app_conn: psycopg.Connection[Any]
) -> None:
    entity, cash, _ = owned_books

    with pytest.raises(StatementDoesNotBalance):
        record(database, entity, march(cash, closing="1196.50"))

    assert audit_rows(app_conn, entity) == 0


def test_a_statement_for_an_account_the_entity_lacks_is_refused(
    database: Database, owned_books: tuple[str, str, str]
) -> None:
    entity, _, _ = owned_books

    with pytest.raises(AccountNotFound):
        record(database, entity, march(str(uuid.uuid4())))


def test_another_entitys_statement_is_not_found(database: Database, owned_books: Any) -> None:
    """Row-level security and the service's own filter, observed from the outside: the id is
    real, and from the other entity it does not exist."""
    entity, cash, _ = owned_books
    statement_id = record(database, entity, march(cash)).stored.id

    other = _other_books(database)
    with pytest.raises(StatementNotFound):
        statement_agreement(
            database, entity_id=other, principal=OWNER, statement_id=statement_id
        )


def _other_books(database: Database) -> str:
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


# --- The Claude Desktop path, over MCP --------------------------------------------------------

CLAIMS: dict[str, Any] = {
    "sub": OWNER.id,
    "iss": "http://localhost:8180/realms/cfokit",
    "aud": "cfokit-ledger",
}


class StubAuthenticator:
    def claims_for(self, credential: str | None) -> dict[str, Any]:
        return CLAIMS


# The bookkeeping skill, acting for the owner: RFC 8693's `act` names the person (ADR-0042).
AGENT_CLAIMS: dict[str, Any] = {**CLAIMS, "sub": "skill:bookkeeper", "act": {"sub": OWNER.id}}


@contextmanager
def authenticated(claims: dict[str, Any] = CLAIMS) -> Iterator[None]:
    token = AccessToken(
        token="stub",  # noqa: S106 — a stand-in, never validated
        client_id=str(claims["sub"]),
        scopes=[],
        subject=str(claims["sub"]),
        claims=claims,
    )
    reset = auth_context_var.set(AuthenticatedUser(token))
    try:
        yield
    finally:
        auth_context_var.reset(reset)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def server(app_dsn: str) -> Any:
    return mcp_server(
        Settings(
            database_url=app_dsn,
            public_base_url="http://localhost:8081",
            auth_issuer_url="http://localhost:8180/realms/cfokit",
            auth_audience="cfokit-ledger",
        ),
        authenticator=StubAuthenticator(),
    )


def reply(result: CallToolResult) -> dict[str, Any]:
    payload: dict[str, Any] = json.loads(result.content[0].text)  # type: ignore[union-attr]
    return payload


async def call(server: Any, name: str, **arguments: Any) -> dict[str, Any]:
    with authenticated():
        return reply(await server.call_tool(name, arguments))


async def call_as_agent(server: Any, name: str, **arguments: Any) -> dict[str, Any]:
    with authenticated(AGENT_CLAIMS):
        return reply(await server.call_tool(name, arguments))


@pytest.fixture
def expenses(database: Database, owned_books: tuple[str, str, str]) -> dict[str, str]:
    entity, _, _ = owned_books
    return {
        name: create_account(
            database,
            entity_id=entity,
            principal=OWNER,
            request_id="fixture",
            code=code,
            name=name,
            account_type="expense",
        )
        for name, code in (("Utilities", "6100"), ("Meals", "6300"))
    }


@pytest.mark.anyio
async def test_a_statement_read_in_desktop_reaches_the_books_and_agrees(
    server: Any,
    owned_books: tuple[str, str, str],
    expenses: dict[str, str],
    app_conn: psycopg.Connection[Any],
) -> None:
    """The whole path. The model records what it read; the statement proves itself; the
    returned candidates go to assignment unchanged; every line lands as a draft whatever
    resolved it; a person posts; and the books then agree with the statement.

    The expected closing figure is the statement's own, and the agreement is the books'
    arithmetic over the posted journal — two independent paths to one number."""
    entity, cash, revenue = owned_books
    for label, precedence, account, payee in (
        ("Client receipts", 10, revenue, "client"),
        ("Utilities", 20, expenses["Utilities"], "utility"),
        ("Coffee", 30, expenses["Meals"], "coffee"),
    ):
        approved = await call(
            server,
            "approve_assignment_rule",
            entity_id=entity,
            label=label,
            precedence=precedence,
            account_id=account,
            predicates=[{"field": "payee", "operator": "contains", "value": payee}],
        )
        assert approved["ok"], approved

    recorded = await call(
        server,
        "record_account_statement",
        entity_id=entity,
        account_id=cash,
        period_start="2026-03-01",
        period_end="2026-03-31",
        opening_balance="0.00",
        closing_balance="195.50",
        commodity="USD",
        lines=[
            {"transaction_date": "2026-03-02", "payee": "Client A", "amount": "250.00"},
            {"transaction_date": "2026-03-09", "payee": "City Utility", "amount": "-45.50"},
            {"transaction_date": "2026-03-12", "payee": "Coffee House", "amount": "-4.50"},
            {"transaction_date": "2026-03-12", "payee": "Coffee House", "amount": "-4.50"},
        ],
    )
    assert recorded["ok"], recorded
    assert recorded["lines"] == 4

    run = await call(
        server, "run_assignment", entity_id=entity, candidates=recorded["candidates"]
    )
    assert run["ok"], run
    assert run["unresolved"] == []
    # Two coffees, two transactions.
    assert len({b["transaction_id"] for b in run["booked"]}) == 4

    waiting = await call(
        server,
        "account_statement_agreement",
        entity_id=entity,
        statement_id=recorded["statement_id"],
    )
    # Every line is a draft, and drafts are not in the books.
    assert waiting["agrees"] is False
    assert Decimal(waiting["closing"]["books"]) == 0

    for booked in run["booked"]:
        posted = await call(
            server,
            "post_transaction",
            entity_id=entity,
            transaction_id=booked["transaction_id"],
            idempotency_key=f"post-{booked['transaction_id']}",
        )
        assert posted["ok"], posted

    agreed = await call(
        server,
        "account_statement_agreement",
        entity_id=entity,
        statement_id=recorded["statement_id"],
    )
    assert agreed["agrees"] is True
    assert Decimal(agreed["closing"]["books"]) == Decimal("195.50")

    # BKP-19: every transaction names the line it came from, and no two name the same one.
    with app_conn.cursor() as cur:
        cur.execute("SELECT set_config('cfokit.entity_id', %s, false)", (entity,))
        cur.execute(
            "SELECT derived_from->>'source_ref' FROM ledger_transaction WHERE entity_id = %s",
            (entity,),
        )
        refs = sorted(str(r[0]) for r in cur.fetchall())
    assert refs == sorted(c["source_ref"] for c in recorded["candidates"])
    assert len(set(refs)) == 4


@pytest.mark.anyio
async def test_a_misread_statement_is_refused_over_mcp(
    server: Any, owned_books: tuple[str, str, str]
) -> None:
    """The refusal arrives as a published code the model can act on — re-read the document —
    rather than as a stringified exception."""
    entity, cash, _ = owned_books

    refused = await call(
        server,
        "record_account_statement",
        entity_id=entity,
        account_id=cash,
        period_start="2026-03-01",
        period_end="2026-03-31",
        opening_balance="0.00",
        closing_balance="195.50",
        commodity="USD",
        lines=[
            {"transaction_date": "2026-03-02", "payee": "Client A", "amount": "250.00"},
            {"transaction_date": "2026-03-09", "payee": "City Utility", "amount": "-45.50"},
        ],
    )

    assert refused == {
        "ok": False,
        "code": "statement_does_not_balance",
        "message": refused["message"],
    }


# --- An uploaded payment of an open invoice waits for a person (ADR-0059 § 3) --------------


@pytest.mark.anyio
async def test_an_uploaded_payment_of_an_open_invoice_is_confirmed_by_a_person(
    server: Any,
    database: Database,
    owned_books: tuple[str, str, str],
    app_conn: psycopg.Connection[Any],
) -> None:
    """ADR-0059's Confirmation, over MCP as Claude Desktop drives it.

    The statement's 250.00 deposit equals the open invoice, so it is a question naming the
    obligation and no settlement is written: a settlement needs its transaction posted, and the
    session that read the document may not post what it read (ADR-0047). The delegated agent
    cannot confirm it (ADR-0042). The person confirming it posts the settling transaction and
    settles the obligation together."""
    entity, cash, revenue = owned_books
    receivable = create_account(
        database,
        entity_id=entity,
        principal=OWNER,
        request_id="fixture",
        code="1200",
        name="Accounts receivable",
        account_type="asset",
    )
    issued = await call(
        server,
        "record_transaction",
        entity_id=entity,
        transaction_date="2026-03-02",
        postings=[
            {"account_id": receivable, "amount": "250.00", "commodity": "USD"},
            {"account_id": revenue, "amount": "-250.00", "commodity": "USD"},
        ],
        description="Invoice 1001",
        idempotency_key="invoice-1001",
        post=True,
        raises_obligation="250.00",
    )
    assert issued["ok"], issued
    [owed] = (await call(server, "outstanding_obligations", entity_id=entity))["obligations"]
    assert owed["account_id"] == receivable

    recorded = await call(
        server,
        "record_account_statement",
        entity_id=entity,
        account_id=cash,
        period_start="2026-03-01",
        period_end="2026-03-31",
        opening_balance="0.00",
        closing_balance="250.00",
        commodity="USD",
        lines=[{"transaction_date": "2026-03-09", "payee": "Client A", "amount": "250.00"}],
    )
    run = await call(
        server, "run_assignment", entity_id=entity, candidates=recorded["candidates"]
    )

    assert run["booked"] == []
    [asked] = run["unresolved"]
    assert asked["outcome"] == "proposed"
    assert [(c["kind"], c["id"]) for c in asked["counterparts"]] == [
        ("obligation", owed["obligation_id"])
    ]
    [question] = (await call(server, "unresolved_transactions", entity_id=entity))["unresolved"]
    assert (question["outcome"], question["counterparts"]) == (
        "proposed",
        asked["counterparts"],
    )
    [notification] = (await call(server, "open_notifications", entity_id=entity))[
        "notifications"
    ]
    assert notification["notification_class"] == "unresolved_transaction"
    assert notification["subject_ref"] == asked["source_ref"]
    # No settlement: the invoice is owed in full.
    [still] = (await call(server, "outstanding_obligations", entity_id=entity))["obligations"]
    assert Decimal(still["outstanding"]) == Decimal("250")

    refused = await call_as_agent(
        server,
        "answer_unresolved_transaction",
        entity_id=entity,
        source_ref=asked["source_ref"],
        idempotency_key="confirm-by-agent",
        counterpart_kind="obligation",
        counterpart_id=owed["obligation_id"],
    )
    assert (refused["ok"], refused["code"]) == (False, "not_a_person")

    confirmed = await call(
        server,
        "answer_unresolved_transaction",
        entity_id=entity,
        source_ref=asked["source_ref"],
        idempotency_key="confirm-by-person",
        counterpart_kind="obligation",
        counterpart_id=owed["obligation_id"],
    )
    assert confirmed["ok"], confirmed
    assert confirmed["outcome"] == "matched"

    detail = await call(
        server, "obligation_detail", entity_id=entity, obligation_id=owed["obligation_id"]
    )
    assert Decimal(detail["obligation"]["outstanding"]) == 0
    [settlement] = detail["settlements"]
    assert settlement["transaction_id"] == confirmed["transaction_id"]
    with app_conn.cursor() as cur:
        cur.execute("SELECT set_config('cfokit.entity_id', %s, false)", (entity,))
        cur.execute(
            "SELECT status, actor_class FROM ledger_transaction WHERE id = %s",
            (confirmed["transaction_id"],),
        )
        # Posted, and the person's: they — not the session that read the document — decided
        # the payment happened (`PLT-23`).
        assert cur.fetchone() == ("posted", "person")
    assert (await call(server, "unresolved_transactions", entity_id=entity))["unresolved"] == []
    assert (await call(server, "open_notifications", entity_id=entity))["notifications"] == []
