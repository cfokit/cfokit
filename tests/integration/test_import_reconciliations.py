"""An import's reconciliation, recorded with it and read back (`IMP-08`, ADR-0058).

**The books are the synthetic export's** (`web/src/quickbooks/synthetic.ts`): two transactions,
and the figures QuickBooks prints for itself beside them — the journal's own total, the general
ledger's account totals, and an accrual profit and loss and balance sheet. Every expected value
below is one of those printed figures, or a deliberate misstatement of one; none is read back
from a first run (ADR-0036).

The import is sent as the neutral shape the web client's reader produces from that export, so
these tests start where the browser hands over.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient
from mcp.server.auth.middleware.auth_context import auth_context_var
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.auth.provider import AccessToken
from mcp.types import CallToolResult

from cfokit.ledger.config import Settings
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.administration import create_entity, grant_role
from cfokit.ledger.service.principal import ActorClass, Principal
from cfokit.server import mcp_server, rest_app

pytestmark = pytest.mark.integration

PERSON = Principal(id="user:geoff", actor_class=ActorClass.PERSON)
AGENT = Principal(id="agent:skill", actor_class=ActorClass.AGENT, acting_for="user:geoff")
FINGERPRINT = "c" * 64

# The synthetic export's chart, journal and printed figures.
ACCOUNTS = [
    {"code": "Accounts Receivable", "name": "Accounts Receivable", "account_type": "asset"},
    {"code": "Checking", "name": "Checking", "account_type": "asset"},
    {"code": "Income", "name": "Income", "account_type": "income"},
    {"code": "Income:Consulting", "name": "Consulting", "account_type": "income"},
    {"code": "Meals", "name": "Meals", "account_type": "expense"},
    {"code": "Meals:Client Meals", "name": "Client Meals", "account_type": "expense"},
]
PARENTS = {"Income:Consulting": "Income", "Meals:Client Meals": "Meals"}
ENTRIES = [
    {
        "reference": "1001",
        "transaction_date": "2026-01-15",
        "description": "Consulting",
        "lines": [
            {"account_code": "Accounts Receivable", "amount": "1200.00", "commodity": "USD"},
            {"account_code": "Income:Consulting", "amount": "-1200.00", "commodity": "USD"},
        ],
    },
    {
        "reference": "expense-2026-02-02",
        "transaction_date": "2026-02-02",
        "description": "Coffee",
        "lines": [
            {"account_code": "Meals:Client Meals", "amount": "12.50", "commodity": "USD"},
            {"account_code": "Checking", "amount": "-12.50", "commodity": "USD"},
        ],
    },
]
# The general ledger's "Total for …" rows, signed as postings: debit positive.
STATED_BALANCES = [
    {"account_code": "Accounts Receivable", "balance": "1200.00"},
    {"account_code": "Income:Consulting", "balance": "-1200.00"},
    {"account_code": "Meals:Client Meals", "balance": "12.50"},
    {"account_code": "Checking", "balance": "-12.50"},
]
# The journal's own TOTAL row.
JOURNAL_TOTAL = {"debits": "1212.50", "credits": "1212.50"}
# The profit and loss and balance sheet, signed as printed.
STATEMENTS = [
    {
        "report": "profit_and_loss",
        "basis": "accrual",
        "lines": [
            {"account_code": "Income:Consulting", "balance": "1200.00"},
            {"account_code": "Meals:Client Meals", "balance": "12.50"},
        ],
    },
    {
        "report": "balance_sheet",
        "basis": "accrual",
        "lines": [
            {"account_code": "Checking", "balance": "-12.50"},
            {"account_code": "Accounts Receivable", "balance": "1200.00"},
        ],
    },
]


class StubAuthenticator:
    """Stands in for the issuer; a token's shape still decides who is acting (ADR-0033)."""

    def __init__(self, principal: Principal = PERSON) -> None:
        self._principal = principal

    def claims_for(self, credential: str | None) -> dict[str, Any]:
        claims: dict[str, Any] = {
            "sub": self._principal.id,
            "iss": "http://localhost:8180/realms/cfokit",
            "aud": "cfokit-ledger",
        }
        if self._principal.acting_for is not None:
            claims["act"] = {"sub": self._principal.acting_for}
        return claims


@pytest.fixture
def settings(app_dsn: str) -> Settings:
    return Settings(
        database_url=app_dsn,
        public_base_url="http://localhost:8080",
        auth_issuer_url="http://localhost:8180/realms/cfokit",
        auth_audience="cfokit-ledger",
    )


@pytest.fixture
def client(settings: Settings) -> TestClient:
    return TestClient(rest_app(settings, authenticator=StubAuthenticator()))


@pytest.fixture
def entity(database: Database) -> str:
    return create_entity(
        database,
        principal=PERSON,
        request_id="reconciliations",
        slug=f"reconciled-{uuid.uuid4().hex[:8]}",
        name="Synthetic Co",
        accounting_basis="accrual",
        fiscal_year_end_month=12,
        fiscal_year_end_day=31,
        functional_currency="USD",
        time_zone="UTC",
    ).entity_id


def imported(client: TestClient, entity: str) -> str:
    """Open the import and post the synthetic journal, as the getting-started pages do."""
    response = client.post(
        f"/entities/{entity}/imports",
        json={
            "shape_version": "1",
            "system": "QuickBooks Online",
            "fingerprint": FINGERPRINT,
            "basis": "accrual",
            "balances_basis": "cash",
            "commodity": "USD",
            "accounts": [
                {**account, "parent": PARENTS.get(str(account["code"]), "")}
                for account in ACCOUNTS
            ],
        },
    )
    assert response.status_code == 201, response.text
    import_id = str(response.json()["import_id"])
    posted = client.post(
        f"/entities/{entity}/imports/{import_id}/entries",
        json={"system": "QuickBooks Online", "fingerprint": FINGERPRINT, "entries": ENTRIES},
    )
    assert posted.json()["posted"] == len(ENTRIES), posted.text
    return import_id


def reconcile(client: TestClient, entity: str, import_id: str, **over: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "balances": STATED_BALANCES,
        "journal_total": JOURNAL_TOTAL,
        "statements": STATEMENTS,
    }
    body.update(over)
    response = client.post(f"/entities/{entity}/imports/{import_id}/reconciliation", json=body)
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


def test_the_books_match_what_quickbooks_printed(client: TestClient, entity: str) -> None:
    """Every figure the export states for itself agrees, with nothing absorbed."""
    import_id = imported(client, entity)

    found = reconcile(client, entity, import_id)

    assert (found["agreed"], found["compared"], found["divergences"]) == (4, 4, [])
    assert found["journal_total"]["agrees"] is True
    assert Decimal(found["journal_total"]["stated_debits"]) == Decimal("1212.50")
    assert Decimal(found["journal_total"]["our_debits"]) == Decimal("1212.50")
    assert [(s["report"], s["agreed"], s["divergences"]) for s in found["statements"]] == [
        ("profit_and_loss", 2, []),
        ("balance_sheet", 2, []),
    ]


def test_what_was_recorded_is_what_is_read_back(client: TestClient, entity: str) -> None:
    """The record carries the comparison as the person was shown it."""
    import_id = imported(client, entity)
    shown = reconcile(client, entity, import_id)

    read = client.get(f"/entities/{entity}/imports/reconciliations")

    assert read.status_code == 200
    assert read.json()["reconciliations"] == [shown]


def test_a_misstated_figure_is_recorded_with_both_sides(
    client: TestClient, entity: str
) -> None:
    """Checking stated as 12.00 overdrawn where the journal posted 12.50: a difference that does
    not net to zero, and so not a basis difference but a defect (ADR-0050)."""
    import_id = imported(client, entity)
    misstated = [
        {"account_code": "Checking", "balance": "-12.00"}
        if line["account_code"] == "Checking"
        else line
        for line in STATED_BALANCES
    ]

    reconcile(client, entity, import_id, balances=misstated)
    [found] = client.get(f"/entities/{entity}/imports/reconciliations").json()[
        "reconciliations"
    ]

    assert found["agreed"] == 3
    assert [
        (d["account_code"], Decimal(d["ours"]), Decimal(d["theirs"]))
        for d in found["divergences"]
    ] == [("Checking", Decimal("-12.50"), Decimal("-12.00"))]
    assert found["divergences_net_to_zero"] is False


def test_the_latest_comes_first(client: TestClient, entity: str) -> None:
    import_id = imported(client, entity)
    first = reconcile(client, entity, import_id, statements=[])
    second = reconcile(client, entity, import_id)

    found = client.get(f"/entities/{entity}/imports/reconciliations").json()["reconciliations"]

    assert [r["reconciliation_id"] for r in found] == [
        second["reconciliation_id"],
        first["reconciliation_id"],
    ]


def test_an_agent_reads_what_a_person_recorded(
    settings: Settings, database: Database, entity: str
) -> None:
    """The agent's first question is answered from the record; it never writes one."""
    grant_role(
        database,
        entity_id=entity,
        principal=PERSON,
        request_id="grant",
        to_principal=AGENT.id,
        role="owner",
    )
    person = TestClient(rest_app(settings, authenticator=StubAuthenticator()))
    import_id = imported(person, entity)
    reconcile(person, entity, import_id)
    agent = TestClient(rest_app(settings, authenticator=StubAuthenticator(AGENT)))

    read = agent.get(f"/entities/{entity}/imports/reconciliations")

    assert read.status_code == 200
    assert len(read.json()["reconciliations"]) == 1


def test_one_audit_row_per_reconciliation(
    client: TestClient, entity: str, owner_conn: psycopg.Connection[Any]
) -> None:
    """Identifiers and counts, never a figure (CLAUDE.md, Observability)."""
    import_id = imported(client, entity)
    recorded = reconcile(client, entity, import_id)

    with owner_conn.cursor() as cur:
        cur.execute(
            "SELECT actor, subject_id, detail FROM audit_log"
            " WHERE entity_id = %s AND action = 'record_import_reconciliation'",
            (entity,),
        )
        rows = cur.fetchall()

    assert len(rows) == 1
    actor, subject, detail = rows[0]
    assert (actor, str(subject)) == ("user:geoff", recorded["reconciliation_id"])
    assert detail == {"import_id": import_id, "compared": 4, "divergences": 0, "statements": 2}


def test_two_statements_of_one_report_are_refused_not_a_server_error(
    client: TestClient, entity: str
) -> None:
    """One comparison per report is what is recorded, so a repeat is refused up front."""
    import_id = imported(client, entity)

    response = client.post(
        f"/entities/{entity}/imports/{import_id}/reconciliation",
        json={"statements": [STATEMENTS[0], STATEMENTS[0]]},
    )

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "import_refused"
    assert (
        client.get(f"/entities/{entity}/imports/reconciliations").json()["reconciliations"]
        == []
    )


def test_a_reconciliation_cannot_be_rewritten(
    client: TestClient, entity: str, app_conn: psycopg.Connection[Any]
) -> None:
    """Append-only (ADR-0007): what the person was shown stays what they were shown."""
    reconcile(client, entity, imported(client, entity))

    with pytest.raises(psycopg.Error), app_conn.cursor() as cur:
        cur.execute("SELECT set_config('cfokit.entity_id', %s, false)", (entity,))
        cur.execute(
            "UPDATE import_reconciliation SET as_of = '2000-01-01' WHERE entity_id = %s",
            (entity,),
        )


# --- over MCP, as Claude reads it ---------------------------------------------------------


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def reply(result: CallToolResult) -> dict[str, Any]:
    payload: dict[str, Any] = json.loads(result.content[0].text)  # type: ignore[union-attr]
    return payload


@contextmanager
def authenticated() -> Iterator[None]:
    claims = StubAuthenticator().claims_for(None)
    token = AccessToken(
        token="stub",  # noqa: S106 — a stand-in, never validated
        client_id=PERSON.id,
        scopes=[],
        subject=PERSON.id,
        claims=claims,
    )
    reset = auth_context_var.set(AuthenticatedUser(token))
    try:
        yield
    finally:
        auth_context_var.reset(reset)


@pytest.mark.anyio
async def test_claude_reads_it_over_mcp(
    settings: Settings, client: TestClient, entity: str
) -> None:
    """The tool answers with the same figures, as strings, so none passes through a float."""
    import_id = imported(client, entity)
    reconcile(client, entity, import_id)
    server: Any = mcp_server(settings, authenticator=StubAuthenticator())

    with authenticated():
        found = reply(await server.call_tool("import_reconciliations", {"entity_id": entity}))

    assert found["ok"] is True
    [only] = found["reconciliations"]
    assert only["import_id"] == import_id
    assert only["journal_total"]["agrees"] is True
    assert only["balances"]["agreed"] == 4
    assert only["balances"]["divergences"] == []
