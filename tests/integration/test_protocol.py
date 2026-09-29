"""Layer 3: both protocols, driven as a client drives them (ADR-0036).

Deterministic, no model. The point is that the two adapters produce the same effect on the
books and the same stable code for the same refusal (ADR-0009), which cannot be checked from
either side alone.

**REST** goes through FastAPI's `TestClient`, so request validation, dependency resolution,
the exception handler and JSON serialization all run.

**MCP** goes two ways. Most cases go through `MCPServer.call_tool`, the SDK's own dispatch:
argument validation against the generated schema, and the error wrapping that turns an
exception into an error result. One case drives the SDK's real client over streamable HTTP
against the app in process, which is ADR-0036's "a real MCP client from the SDK over the real
transport" — the handshake, the JSON-RPC framing and the bearer middleware, none of which
dispatch exercises. The transport is asserted on its own in `tests/test_mcp_transport.py`;
what this adds is a tool that reaches the database through it.
"""

from __future__ import annotations

import io
import uuid
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import httpx2 as httpx
import psycopg
import pytest
from fastapi.testclient import TestClient
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.server.auth.middleware.auth_context import auth_context_var
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.auth.provider import AccessToken
from mcp.types import CallToolResult

from cfokit.ledger.api import create_app
from cfokit.ledger.config import Settings
from cfokit.ledger.mcp import create_server
from cfokit.ledger.service.principal import ActorClass, Principal

pytestmark = pytest.mark.integration

PERSON = Principal(id="user:geoff", actor_class=ActorClass.PERSON)


CLAIMS: dict[str, Any] = {
    "sub": PERSON.id,
    "iss": "http://localhost:8180/realms/cfokit",
    "aud": "cfokit-ledger",
}


class StubAuthenticator:
    """Stands in for the issuer, not for the verification.

    Both adapters compose `claims_for` with `principal_from_claims`, so faking the first still
    exercises the derivation ADR-0033 turns on — a token's *shape* decides `actor_class`, and
    nothing here can assert one.
    """

    def claims_for(self, credential: str | None) -> dict[str, Any]:
        return CLAIMS


@contextmanager
def authenticated(claims: dict[str, Any]) -> Iterator[None]:
    """Present a verified token to the MCP tools, as the SDK's bearer middleware does.

    `call_tool` is dispatch rather than transport, so the middleware that would set this on a
    real request does not run. Setting the SDK's own contextvar is what keeps the tools reading
    their principal from exactly one place in tests and in production.
    """
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
def settings(owner_dsn: str, app_dsn: str) -> Settings:
    return Settings(
        database_url=app_dsn,
        public_base_url="http://localhost:8080",
        auth_issuer_url="http://localhost:8180/realms/cfokit",
        auth_audience="cfokit-ledger",
    )


@pytest.fixture
def authenticated_caller() -> Iterator[None]:
    """Every MCP test acts as a verified caller, because every tool now requires one."""
    with authenticated(CLAIMS):
        yield


@pytest.fixture
def client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings, authenticator=StubAuthenticator()))


def body(cash: str, revenue: str, amount: str = "100.00", post: bool = True) -> dict[str, Any]:
    return {
        "transaction_date": "2026-09-01",
        "description": "Invoice 1001",
        "post": post,
        "postings": [
            {"account_id": cash, "amount": amount, "commodity": "USD"},
            {"account_id": revenue, "amount": f"-{amount}", "commodity": "USD"},
        ],
    }


def headers() -> dict[str, str]:
    return {"Idempotency-Key": uuid.uuid4().hex, "X-Request-Id": f"req-{uuid.uuid4().hex[:8]}"}


# --- REST ---------------------------------------------------------------------------------


def test_rest_records_posts_and_reads_back(
    client: TestClient, books: tuple[str, str, str]
) -> None:
    entity_id, cash, revenue = books

    created = client.post(
        f"/entities/{entity_id}/transactions", json=body(cash, revenue), headers=headers()
    )
    assert created.status_code == 201
    transaction_id = created.json()["transaction_id"]
    assert created.json()["status"] == "posted"

    read = client.get(f"/entities/{entity_id}/transactions/{transaction_id}")
    assert read.status_code == 200
    payload = read.json()
    assert payload["status"] == "posted"
    assert payload["actor_principal_id"] == "user:geoff"
    assert payload["actor_class"] == "person"
    # Amounts come back as strings at the storage scale, not the scale they were written:
    # NUMERIC(28,10) is fixed-scale, so 100.00 is stored and returned as 100.0000000000.
    # That is `LED-06` working — recorded amounts carry more precision than they are shown
    # at, and the display scale is applied at presentation, not here.
    assert {p["amount"] for p in payload["postings"]} == {
        "100.0000000000",
        "-100.0000000000",
    }


def test_rest_serves_both_exports_as_downloadable_archives(
    client: TestClient, books: tuple[str, str, str]
) -> None:
    """`EXP-03`: both available "at any time … without asking anyone and without a support
    request". The REST surface is where that promise is kept, so it is where it is checked.

    Asserted through the protocol rather than the service, because a downloaded file is what
    a person actually leaves with: the media type, the filename, and the headers that tell a
    receiving deployment what it is holding.
    """
    entity_id, cash, revenue = books
    client.post(
        f"/entities/{entity_id}/transactions", json=body(cash, revenue), headers=headers()
    )

    interchange = client.get(f"/entities/{entity_id}/interchange-export")
    assert interchange.status_code == 200
    assert interchange.headers["content-type"] == "application/zip"
    assert "attachment" in interchange.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(interchange.content)) as archive:
        assert "journal.csv" in archive.namelist()

    complete = client.get(f"/entities/{entity_id}/complete-export")
    assert complete.status_code == 200
    assert complete.headers["content-type"] == "application/zip"
    # What a receiving deployment must check before reading the file, on its face.
    assert complete.headers["x-cfokit-archive-format"] == "1"
    assert complete.headers["x-cfokit-schema-version"] != ""
    with zipfile.ZipFile(io.BytesIO(complete.content)) as archive:
        names = set(archive.namelist())
    assert {"manifest.json", "tables/posting.jsonl", "interchange/journal.csv"} <= names


def test_rest_refuses_a_complete_export_in_an_entity_the_caller_holds_nothing_in(
    client: TestClient, two_entities: tuple[str, str]
) -> None:
    """Needing only the ability to read the books is not the same as needing nothing.

    `EXP-03`'s "without asking anyone" removes the gatekeeper, not the grant — and this is the
    request that would hand over every posting, payee and audit row the entity holds.
    """
    other_entity, _ = two_entities

    refused = client.get(f"/entities/{other_entity}/complete-export")

    assert refused.status_code == 403
    assert refused.json()["code"] == "not_authorized"


def test_rest_replays_an_idempotency_key_without_booking_again(
    client: TestClient, owner_conn: psycopg.Connection[Any], books: tuple[str, str, str]
) -> None:
    entity_id, cash, revenue = books
    sent = headers()

    first = client.post(
        f"/entities/{entity_id}/transactions", json=body(cash, revenue), headers=sent
    )
    second = client.post(
        f"/entities/{entity_id}/transactions", json=body(cash, revenue), headers=sent
    )

    assert second.json()["transaction_id"] == first.json()["transaction_id"]
    assert second.json()["replayed"] is True
    with owner_conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM ledger_transaction WHERE entity_id = %s", (entity_id,)
        )
        row = cur.fetchone()
    assert row is not None
    assert row[0] == 1


def test_rest_surfaces_the_stable_code_for_an_unbalanced_entry(
    client: TestClient, books: tuple[str, str, str]
) -> None:
    entity_id, cash, revenue = books
    payload = body(cash, revenue)
    payload["postings"][1]["amount"] = "-99.00"

    response = client.post(
        f"/entities/{entity_id}/transactions", json=payload, headers=headers()
    )

    assert response.status_code == 422
    assert response.json()["code"] == "unbalanced_transaction"


def test_rest_refuses_a_write_with_no_idempotency_key(
    client: TestClient, books: tuple[str, str, str]
) -> None:
    entity_id, cash, revenue = books

    response = client.post(f"/entities/{entity_id}/transactions", json=body(cash, revenue))

    assert response.status_code == 422
    assert response.json()["code"] == "idempotency_key_required"


def test_rest_reverses_a_posted_transaction(
    client: TestClient, books: tuple[str, str, str]
) -> None:
    entity_id, cash, revenue = books
    created = client.post(
        f"/entities/{entity_id}/transactions", json=body(cash, revenue), headers=headers()
    )
    original = created.json()["transaction_id"]

    reversal = client.post(
        f"/entities/{entity_id}/transactions/{original}/reversal", headers=headers()
    )

    assert reversal.status_code == 201
    read = client.get(f"/entities/{entity_id}/transactions/{reversal.json()['transaction_id']}")
    assert read.json()["reverses_id"] == original


def test_rest_refuses_an_entity_the_caller_holds_nothing_in(
    client: TestClient, books: tuple[str, str, str], two_entities: tuple[str, str]
) -> None:
    """`IAM-01`: holding no role in an entity means being able to do nothing with it.

    403 rather than 404, which does reveal that the entity exists. That is the deliberate
    trade `NotAuthorized` documents: a caller who names an entity and holds nothing in it is
    far more often someone whose access lapsed or was revoked than someone probing for ids,
    and "not found" would send them to support instead of to an administrator.
    """
    entity_id, cash, revenue = books
    created = client.post(
        f"/entities/{entity_id}/transactions", json=body(cash, revenue), headers=headers()
    )
    other_entity, _ = two_entities

    response = client.get(
        f"/entities/{other_entity}/transactions/{created.json()['transaction_id']}"
    )

    assert response.status_code == 403
    assert response.json()["code"] == "not_authorized"


def test_rest_hides_another_entitys_transaction_from_someone_who_may_read_here(
    client: TestClient,
    owner_conn: psycopg.Connection[Any],
    books: tuple[str, str, str],
    two_entities: tuple[str, str],
) -> None:
    """`NFR-04`, now that a grant is what gets you through the door.

    The caller holds a role in the *other* entity, so authorization passes and the question
    becomes what row-level security lets them see. It shows them nothing, and the answer is
    "not found" rather than "forbidden" — absent and invisible are the same answer, or the
    answer leaks which ids exist elsewhere.
    """
    entity_id, cash, revenue = books
    created = client.post(
        f"/entities/{entity_id}/transactions", json=body(cash, revenue), headers=headers()
    )
    other_entity, _ = two_entities
    with owner_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO entity_grant (entity_id, principal_id, role, granted_by)"
            " VALUES (%s, 'user:geoff', 'reader', 'test')",
            (other_entity,),
        )

    response = client.get(
        f"/entities/{other_entity}/transactions/{created.json()['transaction_id']}"
    )

    assert response.status_code == 404
    assert response.json()["code"] == "transaction_not_found"


# --- MCP ----------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_mcp_records_and_reads_back(
    authenticated_caller: None, settings: Settings, books: tuple[str, str, str]
) -> None:
    entity_id, cash, revenue = books
    server = create_server(settings, authenticator=StubAuthenticator())

    result = await server.call_tool(
        "record_transaction",
        {
            "entity_id": entity_id,
            "transaction_date": "2026-09-01",
            "idempotency_key": uuid.uuid4().hex,
            "post": True,
            "postings": [
                {"account_id": cash, "amount": "100.00", "commodity": "USD"},
                {"account_id": revenue, "amount": "-100.00", "commodity": "USD"},
            ],
        },
    )

    # These tools never elicit input, so the union is always the result arm.
    assert isinstance(result, CallToolResult)
    written = result.structured_content
    assert written is not None
    assert written["ok"] is True
    assert written["status"] == "posted"

    read = await server.call_tool(
        "read_transaction",
        {"entity_id": entity_id, "transaction_id": written["transaction_id"]},
    )
    assert isinstance(read, CallToolResult)
    assert read.structured_content is not None
    assert read.structured_content["actor_principal_id"] == "user:geoff"


@pytest.mark.anyio
async def test_mcp_surfaces_the_same_code_as_rest(
    authenticated_caller: None, settings: Settings, books: tuple[str, str, str]
) -> None:
    """ADR-0009: "Errors surface the same stable code through both protocols."

    The adapter returns the refusal rather than raising it, because the SDK renders a raised
    exception as a formatted message string and a code recoverable only by substring-parsing
    that is not a contract.
    """
    entity_id, cash, revenue = books
    server = create_server(settings, authenticator=StubAuthenticator())

    result = await server.call_tool(
        "record_transaction",
        {
            "entity_id": entity_id,
            "transaction_date": "2026-09-01",
            "idempotency_key": uuid.uuid4().hex,
            "post": True,
            "postings": [
                {"account_id": cash, "amount": "100.00", "commodity": "USD"},
                {"account_id": revenue, "amount": "-99.00", "commodity": "USD"},
            ],
        },
    )

    assert isinstance(result, CallToolResult)
    reported = result.structured_content
    assert reported is not None
    assert reported["ok"] is False
    assert reported["code"] == "unbalanced_transaction"


@pytest.mark.anyio
async def test_mcp_refuses_a_caller_with_no_verified_token(
    settings: Settings, books: tuple[str, str, str]
) -> None:
    """No `authenticated_caller` fixture, so no token is in force.

    On the wire the SDK's bearer middleware would have answered 401 before dispatch. This is
    the layer beneath that: even reached directly, a tool refuses rather than acting for an
    unidentified caller. `LED-20` requires every transaction to record what wrote it, and
    there would be nothing true to record.
    """
    entity_id, _, _ = books
    server = create_server(settings, authenticator=StubAuthenticator())

    result = await server.call_tool(
        "read_transaction", {"entity_id": entity_id, "transaction_id": str(uuid.uuid4())}
    )

    assert isinstance(result, CallToolResult)
    reported = result.structured_content
    assert reported is not None
    assert reported["ok"] is False
    assert reported["code"] == "not_authenticated"


@pytest.mark.anyio
async def test_mcp_attributes_a_delegated_write_to_both_principals(
    settings: Settings, books: tuple[str, str, str]
) -> None:
    """`IAM-11`: a skill acts for a person and the write records both (ADR-0033).

    The delegation is derived from the token's shape — an RFC 8693 `act` claim — never from a
    tool argument, so a skill cannot describe itself as someone else.
    """
    entity_id, cash, revenue = books
    server = create_server(settings, authenticator=StubAuthenticator())
    delegated = {**CLAIMS, "sub": "skill:bookkeeper", "act": {"sub": PERSON.id}}

    with authenticated(delegated):
        result = await server.call_tool(
            "record_transaction",
            {
                "entity_id": entity_id,
                "transaction_date": "2026-09-01",
                "idempotency_key": uuid.uuid4().hex,
                "postings": [
                    {"account_id": cash, "amount": "100.00", "commodity": "USD"},
                    {"account_id": revenue, "amount": "-100.00", "commodity": "USD"},
                ],
            },
        )
        assert isinstance(result, CallToolResult)
        written = result.structured_content
        assert written is not None

        read = await server.call_tool(
            "read_transaction",
            {"entity_id": entity_id, "transaction_id": written["transaction_id"]},
        )

    assert isinstance(read, CallToolResult)
    assert read.structured_content is not None
    assert read.structured_content["actor_principal_id"] == "skill:bookkeeper"
    assert read.structured_content["actor_class"] == "agent"
    assert read.structured_content["acting_for_principal_id"] == PERSON.id


@pytest.mark.anyio
async def test_a_real_client_books_over_the_transport(
    settings: Settings, books: tuple[str, str, str]
) -> None:
    """ADR-0036 layer 3, end to end: a client session, a tool call, and the books changed.

    Everything between a client and a posting runs — the streamable-HTTP handshake, JSON-RPC
    framing, the bearer middleware, argument validation, the service layer and the database.
    `call_tool` starts after the first three, so a break in any of them would not show there.

    `host="0.0.0.0"` because that is how `__main__` binds it; the SDK auto-enables DNS
    rebinding protection only for a localhost bind, and building it any other way would test a
    configuration that never ships.
    """
    entity_id, cash, revenue = books
    app = create_server(settings, authenticator=StubAuthenticator()).streamable_http_app(
        stateless_http=True,
        json_response=True,
        host="0.0.0.0",  # noqa: S104
    )

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://ledger",
            headers={"Authorization": "Bearer stub"},
        ) as http,
        streamable_http_client("http://ledger/mcp", http_client=http) as (read, write),
        ClientSession(read, write) as client,
    ):
        await client.initialize()
        written = await client.call_tool(
            "record_transaction",
            {
                "entity_id": entity_id,
                "transaction_date": "2026-09-01",
                "idempotency_key": uuid.uuid4().hex,
                "post": True,
                "postings": [
                    {"account_id": cash, "amount": "100.00", "commodity": "USD"},
                    {"account_id": revenue, "amount": "-100.00", "commodity": "USD"},
                ],
            },
        )
        assert written.structured_content is not None
        assert written.structured_content["ok"] is True
        assert written.structured_content["status"] == "posted"

        read_back = await client.call_tool(
            "read_transaction",
            {
                "entity_id": entity_id,
                "transaction_id": written.structured_content["transaction_id"],
            },
        )

    assert read_back.structured_content is not None
    assert read_back.structured_content["actor_principal_id"] == PERSON.id


# --- Reports through both surfaces (ADR-0009, RPT-09) -------------------------------------


@pytest.mark.anyio
async def test_both_surfaces_report_the_same_trial_balance(
    authenticated_caller: None,
    settings: Settings,
    books: tuple[str, str, str],
    client: TestClient,
) -> None:
    """ADR-0009: one service, two adapters, and the same books either way.

    `RPT-09` asks for exactly this — "the same books, queried twice by different callers
    phrasing the request differently, produce identical figures" — and it cannot be checked
    from either side alone, which is why it lives here.
    """
    entity_id, cash, revenue = books
    client.post(
        f"/entities/{entity_id}/transactions", json=body(cash, revenue), headers=headers()
    )
    server = create_server(settings, authenticator=StubAuthenticator())

    rest = client.get(f"/entities/{entity_id}/trial-balance", params={"as_of": "2026-12-31"})
    result = await server.call_tool(
        "trial_balance", {"entity_id": entity_id, "as_of": "2026-12-31"}
    )

    assert isinstance(result, CallToolResult)
    mcp = result.structured_content
    assert mcp is not None
    assert rest.status_code == 200
    assert mcp["total_debit"] == rest.json()["total_debit"] == "100.00"
    assert mcp["total_credit"] == rest.json()["total_credit"] == "100.00"
    assert [line["code"] for line in mcp["lines"]] == [
        line["code"] for line in rest.json()["lines"]
    ]


@pytest.mark.anyio
async def test_both_surfaces_report_the_same_statements(
    authenticated_caller: None,
    settings: Settings,
    books: tuple[str, str, str],
    client: TestClient,
) -> None:
    """The same again for the two statements, including the basis each states on its face."""
    entity_id, cash, revenue = books
    client.post(
        f"/entities/{entity_id}/transactions", json=body(cash, revenue), headers=headers()
    )
    server = create_server(settings, authenticator=StubAuthenticator())

    rest_pl = client.get(
        f"/entities/{entity_id}/profit-and-loss",
        params={"since": "2026-01-01", "as_of": "2026-12-31"},
    ).json()
    pl_result = await server.call_tool(
        "profit_and_loss",
        {"entity_id": entity_id, "since": "2026-01-01", "as_of": "2026-12-31"},
    )
    rest_bs = client.get(
        f"/entities/{entity_id}/balance-sheet", params={"as_of": "2026-12-31"}
    ).json()
    bs_result = await server.call_tool(
        "balance_sheet", {"entity_id": entity_id, "as_of": "2026-12-31"}
    )

    assert isinstance(pl_result, CallToolResult)
    assert isinstance(bs_result, CallToolResult)
    mcp_pl, mcp_bs = pl_result.structured_content, bs_result.structured_content
    assert mcp_pl is not None and mcp_bs is not None

    assert mcp_pl["net_income"] == rest_pl["net_income"] == "100.00"
    assert mcp_pl["accounting_basis"] == rest_pl["accounting_basis"] == "accrual"
    assert mcp_bs["unclosed_earnings"] == rest_bs["unclosed_earnings"] == "100.00"
    assert mcp_bs["balances"] is rest_bs["balances"] is True


@pytest.mark.anyio
async def test_a_report_refuses_a_malformed_date_with_a_code(
    authenticated_caller: None, settings: Settings, books: tuple[str, str, str]
) -> None:
    """A refusal is a result carrying `ok: false`, not an exception the SDK stringifies.

    ADR-0015 makes the code a published contract callers branch on, and a code recoverable
    only by substring-parsing a formatted message is not one.
    """
    entity_id, _, _ = books
    server = create_server(settings, authenticator=StubAuthenticator())

    result = await server.call_tool(
        "trial_balance", {"entity_id": entity_id, "as_of": "not-a-date"}
    )

    assert isinstance(result, CallToolResult)
    assert result.structured_content is not None
    assert result.structured_content["ok"] is False
    assert result.structured_content["code"] == "invalid_date"
