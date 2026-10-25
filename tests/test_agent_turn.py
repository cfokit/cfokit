"""A turn through the agent, end to end in-process (ADR-0075, ADR-0077).

ADR-0036 layer 3, with no infrastructure and no credential: the agent's real Starlette app, a
real MCP server from the official SDK standing in for CFOKit's tool surface, Pydantic AI's
`FunctionModel` standing in for Claude, and in-memory stand-ins for core and the issuer. What is
asserted is what a turn leaves behind — the messages kept and the tools offered — never prose.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

import httpx2
from mcp import Client
from mcp.server import MCPServer
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, DeltaToolCalls, FunctionModel
from starlette.testclient import TestClient

from cfokit.agent import Skill
from cfokit.agent.app import Services, create_app
from cfokit.agent.core import Stored, Thread
from cfokit.agent.scripted import scripted_model
from cfokit.agent.tokens import TokenRefused

ENTITY = "0b9a6c86-2a7e-4f43-8f4a-1f0d6c2c1e11"
CONVERSATION = "5f1e2d3c-4b5a-4968-8778-695a4b3c2d1e"
TURN = f"/entities/{ENTITY}/conversations/{CONVERSATION}/turn"
PERSON = "geoff-token"
STRANGER = "someone-else"
WEB = "https://books.example"
SKILL = Skill(name="bookkeeper", instructions="You keep the books.", version="bookkeeper@abc")

books = MCPServer("cfokit")

# Every session the agent opened on the tool surface, by the token it opened it with.
SESSIONS: list[str] = []


@books.tool()
def profit_and_loss(entity_id: str) -> str:
    """The profit and loss for a period."""
    return "Revenue 1200.00"


@books.tool()
def post_transaction(entity_id: str, transaction_id: str) -> str:
    """Post a draft."""
    return "posted"


@dataclass
class Core:
    """Core's conversation, in memory: what the agent reads and appends over REST."""

    holds_untrusted: bool = False
    kept: list[dict[str, Any]] = field(default_factory=list)
    keys: set[str] = field(default_factory=set)
    missing: bool = False
    not_allowed: bool = False

    async def thread(self, token: str, entity_id: str, conversation_id: str) -> Thread:
        assert token == "agent-token-for-geoff"  # noqa: S105 - a fixture's stand-in
        if self.missing or self.not_allowed:
            status, code = (
                (403, "agent_not_allowed")
                if self.not_allowed
                else (
                    404,
                    "conversation_not_found",
                )
            )
            request = httpx2.Request("GET", "http://core")
            raise httpx2.HTTPStatusError(
                code,
                request=request,
                response=httpx2.Response(status, json={"code": code}, request=request),
            )
        return Thread(
            holds_untrusted=self.holds_untrusted,
            messages=[Stored(i + 1, kept["content"]) for i, kept in enumerate(self.kept)],
        )

    async def append(
        self,
        token: str,
        entity_id: str,
        conversation_id: str,
        *,
        key: str,
        kind: str,
        content: Any,
        model: str | None = None,
        skill_version: str | None = None,
    ) -> int:
        assert key not in self.keys, "a key is used once per message"
        self.keys.add(key)
        self.kept.append(
            {"kind": kind, "content": content, "model": model, "skill_version": skill_version}
        )
        return len(self.kept)


class Tokens:
    async def for_person(self, person_token: str) -> str:
        if person_token != PERSON:
            raise TokenRefused("the issuer refused the exchange (400)")
        return "agent-token-for-geoff"


@asynccontextmanager
async def connect(token: str) -> AsyncIterator[Client]:
    SESSIONS.append(token)
    async with Client(books) as client:
        yield client


@dataclass
class Bookkeeper:
    """A model that asks for the profit and loss, then answers, noting what it was offered."""

    offered: list[list[str]] = field(default_factory=list)
    told: list[str] = field(default_factory=list)

    async def __call__(
        self, messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str | DeltaToolCalls]:
        self.offered.append(sorted(tool.name for tool in info.function_tools))
        self.told.append(info.instructions or "")
        if any(part.part_kind == "tool-return" for part in messages[-1].parts):
            yield "Revenue was "
            yield "1,200.00."
        else:
            yield {0: DeltaToolCall("profit_and_loss", json.dumps({"entity_id": ENTITY}))}


def app(core: Core, model: Bookkeeper | None) -> TestClient:
    return TestClient(
        create_app(
            Services(
                model=None
                if model is None
                else FunctionModel(stream_function=model, model_name="claude-opus-5-5"),
                skill=SKILL,
                tokens=Tokens(),
                core=core,
                connect=connect,
            ),
            web_origin=WEB,
        )
    )


def asked(text: str = "How did we do last quarter?") -> dict[str, Any]:
    return {
        "threadId": CONVERSATION,
        "runId": "run-1",
        "state": {},
        "messages": [{"id": "m1", "role": "user", "content": text}],
        "tools": [],
        "context": [],
        "forwardedProps": {},
    }


def post(client: TestClient, body: dict[str, Any], token: str | None = PERSON) -> Any:
    headers = {"Accept": "text/event-stream"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    return client.post(TURN, json=body, headers=headers)


def test_a_turn_streams_its_answer_and_keeps_every_message() -> None:
    core, model = Core(), Bookkeeper()
    response = post(app(core, model), asked())

    assert response.status_code == 200
    events = [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    assert "RUN_FINISHED" in [event["type"] for event in events]
    assert "Revenue was 1,200.00." in "".join(
        event.get("delta", "") for event in events if event["type"] == "TEXT_MESSAGE_CONTENT"
    )

    # The person's message first, kept before the model saw it; then the model's call, the
    # tool's answer, and the reply.
    assert [kept["kind"] for kept in core.kept] == [
        "request",
        "response",
        "request",
        "response",
    ]
    responses = [kept for kept in core.kept if kept["kind"] == "response"]
    assert {(r["model"], r["skill_version"]) for r in responses} == {
        ("claude-opus-5-5", "bookkeeper@abc")
    }
    assert all(kept["skill_version"] is None for kept in core.kept if kept["kind"] == "request")


def test_the_stored_conversation_is_the_history_the_model_is_given() -> None:
    """A second turn continues from what core kept, not what the window sends (ADR-0076)."""
    core, model = Core(), Bookkeeper()
    client = app(core, model)
    post(client, asked())
    kept_after_first = len(core.kept)

    second = asked("And the quarter before?")
    second["runId"] = "run-2"
    post(client, second)

    assert len(core.kept) == kept_after_first + 4


def test_every_tool_is_offered_while_nothing_untrusted_is_held() -> None:
    core, model = Core(), Bookkeeper()
    post(app(core, model), asked())
    assert model.offered[0] == ["post_transaction", "profit_and_loss"]


def test_a_conversation_holding_untrusted_content_is_offered_nothing_that_posts() -> None:
    """`PLT-23`, by what the model is offered rather than by what it is told."""
    core, model = Core(holds_untrusted=True), Bookkeeper()
    post(app(core, model), asked())
    assert all("post_transaction" not in tools for tools in model.offered)
    assert model.offered[0] == ["profit_and_loss"]


def test_with_no_inference_credential_the_chat_is_off() -> None:
    core = Core()
    response = post(app(core, None), asked())
    assert (response.status_code, response.json()["code"]) == (503, "agent_off")
    assert core.kept == []


def test_a_turn_needs_the_person_s_token() -> None:
    response = post(app(Core(), Bookkeeper()), asked(), token=None)
    assert (response.status_code, response.json()["code"]) == (401, "not_authenticated")


def test_a_token_the_issuer_will_not_exchange_acts_for_nobody() -> None:
    core = Core()
    response = post(app(core, Bookkeeper()), asked(), token=STRANGER)
    assert (response.status_code, response.json()["code"]) == (403, "token_refused")
    assert core.kept == []


def test_core_s_refusal_is_passed_on() -> None:
    """Another person's conversation is not found in core, and so not found here."""
    response = post(app(Core(missing=True), Bookkeeper()), asked())
    assert (response.status_code, response.json()["code"]) == (404, "conversation_not_found")


def preflight(origin: str) -> Any:
    return app(Core(), Bookkeeper()).options(
        TURN,
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )


def test_the_web_client_s_origin_may_call_the_agent() -> None:
    """The agent has its own address, so the chat window's call is cross-origin (ADR-0075 §
    1); the Fetch standard's CORS preflight is what lets the browser make it."""
    response = preflight(WEB)
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == WEB


def test_no_other_origin_may() -> None:
    response = preflight("https://elsewhere.example")
    assert "access-control-allow-origin" not in response.headers


def history(client: TestClient, token: str | None = PERSON) -> Any:
    headers = {} if token is None else {"Authorization": f"Bearer {token}"}
    return client.get(f"/entities/{ENTITY}/conversations/{CONVERSATION}", headers=headers)


def test_the_conversation_so_far_is_served_as_ag_ui_messages() -> None:
    """AG-UI's message model: the question, the call and its result, then the answer."""
    core = Core()
    client = app(core, Bookkeeper())
    post(client, asked())

    messages = history(client).json()["messages"]

    assert [m["role"] for m in messages] == ["user", "assistant", "tool", "assistant"]
    assert messages[0]["content"] == "How did we do last quarter?"
    assert [c["function"]["name"] for c in messages[1]["toolCalls"]] == ["profit_and_loss"]
    assert messages[2]["toolCallId"] == messages[1]["toolCalls"][0]["id"]
    assert messages[3]["content"] == "Revenue was 1,200.00."


def test_what_was_said_stays_readable_with_the_chat_off() -> None:
    core = Core()
    post(app(core, Bookkeeper()), asked())
    assert len(history(app(core, None)).json()["messages"]) == 4


def test_reading_the_conversation_needs_the_person_s_token() -> None:
    response = history(app(Core(), Bookkeeper()), token=None)
    assert (response.status_code, response.json()["code"]) == (401, "not_authenticated")


def test_an_agent_not_yet_allowed_connects_so_the_person_can_allow_it() -> None:
    """ADR-0066 § 3: a person allows an agent that has connected for them, and the server
    records a connection when an agent opens a session. Refused, the agent opens one, then
    passes on the refusal and its link (ADR-0077 § 1)."""
    SESSIONS.clear()
    response = history(app(Core(not_allowed=True), Bookkeeper()))
    assert (response.status_code, response.json()["code"]) == (403, "agent_not_allowed")
    assert SESSIONS == ["agent-token-for-geoff"]


def test_no_other_refusal_opens_a_session() -> None:
    SESSIONS.clear()
    history(app(Core(missing=True), Bookkeeper()))
    assert SESSIONS == []


def test_the_refusal_still_reaches_the_person_when_connecting_fails() -> None:
    """The session is opened so the person can allow the agent; failing to open it must not hide
    the refusal and its link, which is how they find where to allow it (ADR-0077 § 1)."""

    class Unreachable:
        async def __aenter__(self) -> Client:
            raise httpx2.ConnectError("the MCP service is down")

        async def __aexit__(self, *exc: object) -> None:
            return None

    def unreachable(token: str) -> Unreachable:
        return Unreachable()

    client = TestClient(
        create_app(
            Services(
                model=None,
                skill=SKILL,
                tokens=Tokens(),
                core=Core(not_allowed=True),
                connect=unreachable,
            ),
            web_origin=WEB,
        )
    )
    response = history(client)
    assert (response.status_code, response.json()["code"]) == (403, "agent_not_allowed")


def test_the_model_is_told_which_company_the_conversation_is_in() -> None:
    """Every tool call names its entity and there is no current one (the bookkeeper skill), so
    the turn tells the model the company the window posted to rather than leaving it to ask."""
    model = Bookkeeper()
    post(app(Core(), model), asked())
    assert all(f"entity_id {ENTITY}" in told for told in model.told)
    assert all(SKILL.instructions in told for told in model.told)


# The scripted stand-in the documentation is recorded with (ADR-0074), through the real app.
# Expected values: the tool's published inputs (`profit_and_loss` takes `entity_id` and
# `since`), the figures the stand-in tool returned, which the answer repeats rather than
# computes, and `SOC1-35`, by which a response records the model that wrote it.

scripted_books = MCPServer("cfokit-scripted")
CALLS: list[dict[str, str]] = []


@scripted_books.tool(name="profit_and_loss")
def scripted_profit_and_loss(entity_id: str, since: str) -> dict[str, Any]:
    """Income and expense between two dates, as the published tool returns it: a dict."""
    CALLS.append({"entity_id": entity_id, "since": since})
    return {
        "ok": True,
        "company": "Synthetic Co",
        "since": since,
        "income": [{"name": "Income:Consulting", "amount": "1200.00"}],
        "expenses": [{"name": "Meals:Client Meals", "amount": "12.50"}],
        "total_income": "1200.00",
        "total_expenses": "12.50",
        "net_income": "1187.50",
    }


@asynccontextmanager
async def connect_scripted(token: str) -> AsyncIterator[Client]:
    async with Client(scripted_books) as client:
        yield client


def scripted_turn(core: Core) -> Any:
    client = TestClient(
        create_app(
            Services(
                model=scripted_model(),
                skill=SKILL,
                tokens=Tokens(),
                core=core,
                connect=connect_scripted,
            )
        )
    )
    return client.post(
        TURN,
        json=asked(),
        headers={"Accept": "text/event-stream", "Authorization": f"Bearer {PERSON}"},
    )


def test_it_reads_the_profit_and_loss_to_date_for_the_conversation_s_company() -> None:
    CALLS.clear()
    scripted_turn(Core())
    assert CALLS == [{"entity_id": ENTITY, "since": "0001-01-01"}]


def test_it_answers_with_the_figures_the_tool_returned_and_says_it_is_scripted() -> None:
    core = Core()
    scripted_turn(core)
    answer = core.kept[-1]
    assert answer["kind"] == "response"
    assert answer["model"] == "scripted"
    text = "".join(
        part.get("content", "")
        for part in answer["content"]["parts"]
        if part["part_kind"] == "text"
    )
    for figure in ("Synthetic Co", "1,200.00", "12.50", "1,187.50"):
        assert figure in text
