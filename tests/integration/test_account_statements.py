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


@contextmanager
def authenticated() -> Iterator[None]:
    token = AccessToken(
        token="stub",  # noqa: S106 — a stand-in, never validated
        client_id=OWNER.id,
        scopes=[],
        subject=OWNER.id,
        claims=CLAIMS,
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
