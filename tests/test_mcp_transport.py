"""ADR-0036 layer 3, over the real transport rather than `call_tool` dispatch.

The record asks for "a real MCP client from the SDK over the real transport". This drives the
SDK's own client against the ASGI app in process, so the JSON-RPC framing, the streamable-HTTP
session handshake and the bearer middleware all run — none of which `call_tool` exercises,
because it starts after the point where all three could have failed.

No database. Initialising a session and listing tools reaches nothing below the adapter, which
is what lets the transport be asserted in the unit suite; the tool bodies are exercised against
a database in `tests/integration/`.

The app is built with `host="0.0.0.0"` because that is how `__main__` binds it, and the SDK
auto-enables DNS rebinding protection only for a localhost bind. Building it any other way here
would test a configuration that never ships.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx2 as httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import MCPError

from cfokit.ledger.config import Settings
from cfokit.ledger.mcp import create_server

pytestmark = pytest.mark.anyio

TOOLS = {"post_transaction", "read_transaction", "record_transaction", "reverse_transaction"}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def settings() -> Settings:
    return Settings(
        database_url="postgresql://unused/unused",
        public_base_url="http://localhost:8081",
        auth_issuer_url="http://localhost:4444",
        auth_audience="cfokit-ledger",
    )


class Accepts:
    """Stands in for the issuer. Verification is asserted in `test_mcp_auth.py`."""

    def claims_for(self, credential: str | None) -> dict[str, Any]:
        return {"sub": "user:ana"}


@asynccontextmanager
async def session(
    settings: Settings, *, credential: str | None
) -> AsyncIterator[ClientSession]:
    """A real SDK client session, over streamable HTTP, against the app in process."""
    app = create_server(settings, authenticator=Accepts()).streamable_http_app(
        stateless_http=True,
        json_response=True,
        host="0.0.0.0",  # noqa: S104
    )
    headers = {"Authorization": credential} if credential else {}
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://ledger", headers=headers
        ) as http,
        streamable_http_client("http://ledger/mcp", http_client=http) as (read, write),
        ClientSession(read, write) as client,
    ):
        yield client


async def test_a_client_can_open_a_session(settings: Settings) -> None:
    """The handshake itself: protocol negotiation over the wire, which dispatch skips."""
    async with session(settings, credential="Bearer stub") as client:
        result = await client.initialize()

    assert result.server_info.name == "cfokit-ledger"


async def test_a_client_sees_the_published_tools(settings: Settings) -> None:
    """The same four names CI gate 5 diffs, reached the way a client reaches them."""
    async with session(settings, credential="Bearer stub") as client:
        await client.initialize()
        listed = await client.list_tools()

    assert {tool.name for tool in listed.tools} == TOOLS


async def test_the_instructions_reach_the_client(settings: Settings) -> None:
    """A refusal arrives as `ok: false` rather than as an error result, so the instructions
    saying so are the only thing that tells a client to look."""
    async with session(settings, credential="Bearer stub") as client:
        result = await client.initialize()

    assert result.instructions is not None
    assert "'ok'" in result.instructions


async def test_a_session_cannot_be_opened_without_a_token(settings: Settings) -> None:
    """The middleware rejects at the handshake, so there is never a session to call a tool on.

    Asserted at the leaves because the SDK's task groups wrap the failure: what matters is
    that an `MCPError` is what a client sees, not that something somewhere raised.
    """
    with pytest.raises(BaseExceptionGroup) as caught:
        async with session(settings, credential=None) as client:
            await client.initialize()

    def leaves(error: BaseException) -> list[BaseException]:
        if isinstance(error, BaseExceptionGroup):
            return [leaf for sub in error.exceptions for leaf in leaves(sub)]
        return [error]

    assert any(isinstance(leaf, MCPError) for leaf in leaves(caught.value))
