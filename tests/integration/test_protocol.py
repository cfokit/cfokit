"""Layer 3: both protocols, driven as a client drives them (ADR-0036).

Deterministic, no model. The point is that the two adapters produce the same effect on the
books and the same stable code for the same refusal (ADR-0009), which cannot be checked from
either side alone.

**REST** goes through FastAPI's `TestClient`, so request validation, dependency resolution,
the exception handler and JSON serialisation all run.

**MCP** goes through `MCPServer.call_tool`, which is the SDK's own dispatch: argument
validation against the generated schema, and the error wrapping that turns an exception into
an error result. It is not the wire transport, so `stdio` framing is not covered here — ADR-0036
asks for "a real MCP client from the SDK over the real transport", and that half remains.
"""

from __future__ import annotations

import uuid
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient
from mcp.types import CallToolResult

from cfokit.ledger.api import create_app
from cfokit.ledger.config import Settings
from cfokit.ledger.mcp import create_server
from cfokit.ledger.service.principal import ActorClass, Principal

pytestmark = pytest.mark.integration

PERSON = Principal(id="user:geoff", actor_class=ActorClass.PERSON)


class StubAuthenticator:
    """Stands in for the token validation that ADR-0019 requires and nothing implements.

    A test double for a seam, not for a mechanism: there is no authenticator to fake, which
    is the gap `api/auth.py` states.
    """

    def principal_for(self, credential: str | None) -> Principal:
        return PERSON


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def settings(owner_dsn: str, app_dsn: str) -> Settings:
    return Settings(
        database_url=app_dsn,
        public_base_url="http://localhost:8080",
        auth_issuer_url="http://localhost:4444",
        auth_audience="cfokit-ledger",
    )


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
    trade `NotAuthorised` documents: a caller who names an entity and holds nothing in it is
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
    assert response.json()["code"] == "not_authorised"


def test_rest_hides_another_entitys_transaction_from_someone_who_may_read_here(
    client: TestClient,
    owner_conn: psycopg.Connection[Any],
    books: tuple[str, str, str],
    two_entities: tuple[str, str],
) -> None:
    """`NFR-04`, now that a grant is what gets you through the door.

    The caller holds a role in the *other* entity, so authorisation passes and the question
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
    settings: Settings, books: tuple[str, str, str]
) -> None:
    entity_id, cash, revenue = books
    server = create_server(settings, principal=PERSON)

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
    settings: Settings, books: tuple[str, str, str]
) -> None:
    """ADR-0009: "Errors surface the same stable code through both protocols."

    The adapter returns the refusal rather than raising it, because the SDK renders a raised
    exception as a formatted message string and a code recoverable only by substring-parsing
    that is not a contract.
    """
    entity_id, cash, revenue = books
    server = create_server(settings, principal=PERSON)

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
async def test_mcp_refuses_when_no_principal_is_configured(
    settings: Settings, books: tuple[str, str, str]
) -> None:
    """The default server writes nothing, for the same reason the REST default returns 401."""
    entity_id, _, _ = books
    server = create_server(settings)

    result = await server.call_tool(
        "read_transaction", {"entity_id": entity_id, "transaction_id": str(uuid.uuid4())}
    )

    assert isinstance(result, CallToolResult)
    reported = result.structured_content
    assert reported is not None
    assert reported["ok"] is False
    assert reported["code"] == "not_authenticated"
