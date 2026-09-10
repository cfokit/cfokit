"""Importing over MCP, for a runtime that cannot reach CFOKit (ADR-0041 § 6).

Driven through `call_tool`, which is the dispatch a Desktop session reaches — the model composes
the arguments and these tests compose them the same way, from what the reader emits.

**What is being tested is the encoding.** The service layer beneath is already covered by
`test_import_ingest.py` over REST; what is new here is that a chart sent as an index and
transactions sent as lines reconstruct exactly the same books, and that a wrong index or an
unparseable figure is refused rather than guessed at.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from mcp.server.auth.middleware.auth_context import auth_context_var
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.auth.provider import AccessToken
from mcp.types import CallToolResult

from cfokit.ledger.config import Settings
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.administration import create_entity
from cfokit.ledger.service.principal import ActorClass, Principal
from cfokit.server import mcp_server

pytestmark = pytest.mark.integration

PERSON = Principal(id="user:geoff", actor_class=ActorClass.PERSON)
CLAIMS: dict[str, Any] = {
    "sub": PERSON.id,
    "iss": "http://localhost:8180/realms/cfokit",
    "aud": "cfokit-ledger",
}
FINGERPRINT = "c" * 64

CHART = [
    "Checking|asset|",
    "Income|income|",
    "Income:Consulting|income|Income",
]


class StubAuthenticator:
    def claims_for(self, credential: str | None) -> dict[str, Any]:
        return CLAIMS


@contextmanager
def authenticated() -> Iterator[None]:
    """Present a verified token, as the SDK's bearer middleware does on a real request."""
    token = AccessToken(
        token="stub",  # noqa: S106 — a stand-in, never validated
        client_id=PERSON.id,
        scopes=[],
        subject=PERSON.id,
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


@pytest.fixture
def entity(database: Database) -> str:
    return create_entity(
        database,
        principal=PERSON,
        request_id="fixture",
        slug=f"mcp-import-{uuid.uuid4().hex[:8]}",
        name="Synthetic Co",
        accounting_basis="accrual",
        fiscal_year_end_month=12,
        fiscal_year_end_day=31,
        functional_currency="USD",
        time_zone="UTC",
    ).entity_id


def reply(result: CallToolResult) -> dict[str, Any]:
    payload: dict[str, Any] = json.loads(result.content[0].text)  # type: ignore[union-attr]
    return payload


async def call(server: Any, name: str, **arguments: Any) -> dict[str, Any]:
    with authenticated():
        return reply(await server.call_tool(name, arguments))


async def opened(server: Any, entity: str, **over: Any) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        "entity_id": entity,
        "system": "QuickBooks Online",
        "fingerprint": FINGERPRINT,
        "basis": "unknown",
        "balances_basis": "cash",
        "commodity": "USD",
        "chart": CHART,
    }
    arguments.update(over)
    return await call(server, "open_import", **arguments)


# --- the encoding round-trips ----------------------------------------------------------------


@pytest.mark.anyio
async def test_a_chart_sent_as_lines_creates_the_accounts(server: Any, entity: str) -> None:
    result = await opened(server, entity)

    assert result["ok"]
    assert result["accounts_created"] == 3


@pytest.mark.anyio
async def test_an_account_is_named_by_its_position_in_the_chart(
    server: Any, entity: str
) -> None:
    """**The whole economy of this surface.** 62 accounts named 11,580 times are 270 KB of a
    509 KB payload; an index halves it."""
    import_id = (await opened(server, entity))["import_id"]

    posted = await call(
        server,
        "import_entries",
        entity_id=entity,
        import_id=import_id,
        fingerprint=FINGERPRINT,
        system="QuickBooks Online",
        chart=CHART,
        entries=["1|2026-01-15|Consulting|0~1200.00|2~-1200.00"],
    )

    assert posted["posted"] == 1
    assert posted["skipped"] == 0

    checked = await call(
        server,
        "reconcile_import",
        entity_id=entity,
        balances=["Checking|1200.00", "Income:Consulting|-1200.00"],
    )
    assert checked["reconciled"]
    assert checked["agreed"] == 2


@pytest.mark.anyio
async def test_an_index_outside_the_chart_is_refused(server: Any, entity: str) -> None:
    """A wrong index is the one thing a caller can get wrong invisibly, so it must not reach for
    a neighbouring account."""
    import_id = (await opened(server, entity))["import_id"]

    result = await call(
        server,
        "import_entries",
        entity_id=entity,
        import_id=import_id,
        fingerprint=FINGERPRINT,
        system="QuickBooks Online",
        chart=CHART,
        entries=["1|2026-01-15|Consulting|0~1200.00|9~-1200.00"],
    )

    assert not result["ok"]
    assert result["code"] == "invalid_argument"


@pytest.mark.anyio
async def test_an_unparseable_amount_is_refused_rather_than_zeroed(
    server: Any, entity: str
) -> None:
    """A figure that arrives as zero is indistinguishable from a real zero, and in a set of
    books the difference is everything."""
    import_id = (await opened(server, entity))["import_id"]

    result = await call(
        server,
        "import_entries",
        entity_id=entity,
        import_id=import_id,
        fingerprint=FINGERPRINT,
        system="QuickBooks Online",
        chart=CHART,
        entries=["1|2026-01-15|Consulting|0~one thousand|2~-1200.00"],
    )

    assert not result["ok"]
    assert result["code"] == "invalid_argument"


@pytest.mark.anyio
async def test_a_malformed_date_is_refused(server: Any, entity: str) -> None:
    import_id = (await opened(server, entity))["import_id"]

    result = await call(
        server,
        "import_entries",
        entity_id=entity,
        import_id=import_id,
        fingerprint=FINGERPRINT,
        system="QuickBooks Online",
        chart=CHART,
        entries=["1|15/01/2026|Consulting|0~1200.00|2~-1200.00"],
    )

    assert not result["ok"]
    assert "ISO date" in result["message"]


# --- the properties the REST path has, over this transport ------------------------------------


@pytest.mark.anyio
async def test_the_same_batch_twice_posts_once(server: Any, entity: str) -> None:
    """The model may resend a batch after a disconnection, and the books must not double."""
    import_id = (await opened(server, entity))["import_id"]
    batch = {
        "entity_id": entity,
        "import_id": import_id,
        "fingerprint": FINGERPRINT,
        "system": "QuickBooks Online",
        "chart": CHART,
        "entries": ["1|2026-01-15|Consulting|0~1200.00|2~-1200.00"],
    }

    first = await call(server, "import_entries", **batch)
    second = await call(server, "import_entries", **batch)

    assert (first["posted"], first["replayed"]) == (1, 0)
    assert (second["posted"], second["replayed"]) == (0, 1)


@pytest.mark.anyio
async def test_an_unbalanced_entry_is_skipped_and_the_batch_proceeds(
    server: Any, entity: str
) -> None:
    import_id = (await opened(server, entity))["import_id"]

    result = await call(
        server,
        "import_entries",
        entity_id=entity,
        import_id=import_id,
        fingerprint=FINGERPRINT,
        system="QuickBooks Online",
        chart=CHART,
        entries=[
            "1|2026-01-15|Good|0~1200.00|2~-1200.00",
            "2|2026-01-16|Bad|0~100.00|2~-90.00",
        ],
    )

    assert result["posted"] == 1
    assert [row["code"] for row in result["skipped_detail"]] == ["unbalanced"]


@pytest.mark.anyio
async def test_a_conflicting_basis_is_refused_at_open(server: Any, entity: str) -> None:
    result = await opened(server, entity, basis="cash")

    assert not result["ok"]
    assert result["code"] == "import_refused"


@pytest.mark.anyio
async def test_a_basis_mismatch_is_flagged_rather_than_refused(
    server: Any, entity: str
) -> None:
    """An accrual journal against cash-basis reports differs by what is unsettled. ADR-0037
    predicts it, so a person reads it as expected rather than as broken."""
    result = await opened(server, entity)

    assert result["ok"]
    assert result["expect_obligation_accounts_to_differ"]


@pytest.mark.anyio
async def test_a_statement_is_compared_by_account(server: Any, entity: str) -> None:
    import_id = (await opened(server, entity))["import_id"]
    await call(
        server,
        "import_entries",
        entity_id=entity,
        import_id=import_id,
        fingerprint=FINGERPRINT,
        system="QuickBooks Online",
        chart=CHART,
        entries=["1|2026-01-15|Consulting|0~1200.00|2~-1200.00"],
    )

    checked = await call(
        server,
        "reconcile_import",
        entity_id=entity,
        balances=[],
        profit_and_loss=["Income:Consulting|1200.00"],
        their_basis="cash",
    )

    statement = checked["statements"][0]
    assert statement["report"] == "profit_and_loss"
    assert statement["agreed"] == 1
    assert statement["divergences"] == []


@pytest.mark.anyio
async def test_a_divergence_is_reported_with_both_figures(server: Any, entity: str) -> None:
    """`NFR-01`: a tolerance is a defect, not a target. This is also what catches a figure the
    model retyped wrongly, which is the cost of it being the bridge."""
    import_id = (await opened(server, entity))["import_id"]
    await call(
        server,
        "import_entries",
        entity_id=entity,
        import_id=import_id,
        fingerprint=FINGERPRINT,
        system="QuickBooks Online",
        chart=CHART,
        entries=["1|2026-01-15|Consulting|0~1200.00|2~-1200.00"],
    )

    checked = await call(
        server, "reconcile_import", entity_id=entity, balances=["Checking|1190.00"]
    )

    assert not checked["reconciled"]
    assert checked["divergences"][0]["account"] == "Checking"
    assert checked["divergences"][0]["ours"] == "1200.0000000000"
    assert checked["divergences"][0]["theirs"] == "1190.00"
