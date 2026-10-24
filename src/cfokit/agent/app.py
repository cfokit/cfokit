"""The agent's HTTP surface: one turn, streamed as AG-UI events (ADR-0075 § 1).

The chat window posts the person's message with their access token. The agent exchanges the
token for its own (ADR-0077), reads the conversation from core, keeps the person's message, runs
the turn, streams it back, and keeps what the turn produced. It holds nothing between turns.

A turn cut off mid-way keeps the person's message and whatever completed before the cut; every
write a tool made carried an idempotency key and an uploaded line is only drafted (ADR-0047), so
nothing is left half-booked (ADR-0075 § 1).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Any

import httpx2
from ag_ui.core import BaseEvent
from mcp import Client
from pydantic_ai import Agent
from pydantic_ai.agent import AgentRunResult
from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelRequest,
    UserPromptPart,
)
from pydantic_ai.models import Model
from pydantic_ai.ui.ag_ui import AGUIAdapter
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from cfokit.agent import Skill
from cfokit.agent.core import Core, Thread
from cfokit.agent.tokens import TokenRefused, TokenSource
from cfokit.agent.tools import PublishedTools

__all__ = ["Services", "create_app"]

log = logging.getLogger("cfokit.agent")

Connect = Callable[[str], AbstractAsyncContextManager[Client]]


@dataclass(frozen=True, slots=True)
class Services:
    """What a turn needs. `model` is None when no inference credential is configured."""

    model: Model | None
    skill: Skill
    tokens: TokenSource
    core: Core
    connect: Connect


def _refusal(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"code": code, "message": message}, status_code=status)


def _bearer(request: Request) -> str | None:
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    return token.strip() or None if scheme.lower() == "bearer" else None


def _prompt(messages: list[ModelMessage]) -> ModelRequest | None:
    """The person's new message: the user prompt in the last message the window sent.

    Only that. The window sends the whole thread, and the stored one is what the model is given
    (ADR-0076), so nothing else the window sends can rewrite what was said.
    """
    if not messages or not isinstance(messages[-1], ModelRequest):
        return None
    parts = [part for part in messages[-1].parts if isinstance(part, UserPromptPart)]
    return ModelRequest(parts=parts) if parts else None


def _code(response: httpx2.Response) -> str | None:
    try:
        body = response.json()
    except ValueError:
        return None
    return body.get("code") if isinstance(body, dict) else None


def _dump(message: ModelMessage) -> Any:
    return ModelMessagesTypeAdapter.dump_python([message], mode="json")[0]


def create_app(services: Services, *, web_origin: str | None = None) -> Starlette:
    """The agent's app. `web_origin` is the one browser origin allowed to call it, the web
    client's; None allows none, as for a caller that is not a browser."""
    agent: Agent[None, str] | None = (
        None
        if services.model is None
        else Agent(services.model, instructions=services.skill.instructions, name="cfokit")
    )

    async def opened(request: Request) -> tuple[str, Thread] | Response:
        """The agent's token for the person asking, and the conversation they named; or the
        refusal to answer with."""
        person_token = _bearer(request)
        if person_token is None:
            return _refusal(401, "not_authenticated", "the person's bearer token is required")
        try:
            token = await services.tokens.for_person(person_token)
        except TokenRefused as refused:
            return _refusal(403, refused.code, str(refused))
        entity_id = request.path_params["entity_id"]
        try:
            thread = await services.core.thread(
                token, entity_id, request.path_params["conversation_id"]
            )
        except httpx2.HTTPStatusError as failed:
            if _code(failed.response) == "agent_not_allowed":
                # The person allows an agent that has connected for them, and an agent connects
                # by opening a session on the MCP surface, which records it (ADR-0066 § 3). The
                # agent opens one only to work, which it may not do yet, so it opens one now:
                # without it the person's allowing would be refused, and the chat never start.
                # Best effort: the refusal and its link still reach the person if it fails.
                try:
                    async with services.connect(token):
                        pass
                except Exception:
                    log.exception("agent connection not opened", extra={"entity_id": entity_id})
            # Core's own refusal, passed on: `agent_not_allowed` with its link, or not found.
            return Response(
                failed.response.content,
                status_code=failed.response.status_code,
                media_type="application/json",
            )
        return token, thread

    async def history(request: Request) -> Response:
        """The conversation so far, as AG-UI messages, for the window to show on opening.

        Converted here, by the same library that wrote it, so the window reads the protocol it
        already speaks and never the stored form (ADR-0076). Served with the chat off too: what
        was said stays readable without an inference credential.
        """
        found = await opened(request)
        if isinstance(found, Response):
            return found
        _, thread = found
        stored = ModelMessagesTypeAdapter.validate_python([m.content for m in thread.messages])
        return JSONResponse(
            {
                "messages": [
                    message.model_dump(mode="json", by_alias=True, exclude_none=True)
                    for message in AGUIAdapter.dump_messages(stored)
                ]
            }
        )

    async def turn(request: Request) -> Response:
        if agent is None:
            return _refusal(
                503, "agent_off", "no inference credential is configured, so the chat is off"
            )
        found = await opened(request)
        if isinstance(found, Response):
            return found
        token, thread = found
        entity_id = request.path_params["entity_id"]
        conversation_id = request.path_params["conversation_id"]

        adapter = await AGUIAdapter.from_request(request, agent=agent)
        prompt = _prompt(adapter.messages)
        if prompt is None:
            return _refusal(422, "no_message", "the last message sent is not the person's")
        history = ModelMessagesTypeAdapter.validate_python([m.content for m in thread.messages])
        run_id = adapter.run_input.run_id

        # Kept before the model sees it, so a turn that fails never loses what the person said.
        await services.core.append(
            token,
            entity_id,
            conversation_id,
            key=f"{run_id}:prompt",
            kind="request",
            content=_dump(prompt),
        )

        async def keep(result: AgentRunResult[Any]) -> None:
            for index, message in enumerate(result.new_messages()):
                await services.core.append(
                    token,
                    entity_id,
                    conversation_id,
                    key=f"{run_id}:{index}",
                    kind=message.kind,
                    content=_dump(message),
                    model=getattr(message, "model_name", None),
                    skill_version=services.skill.version
                    if message.kind == "response"
                    else None,
                )
            log.info(
                "turn complete",
                extra={
                    "conversation_id": conversation_id,
                    "messages": len(result.new_messages()),
                },
            )

        async def events() -> AsyncIterator[BaseEvent]:
            async with services.connect(token) as client:
                tools = PublishedTools(client, holds_untrusted=thread.holds_untrusted)
                async for event in adapter.run_stream(
                    message_history=[*history, prompt], toolsets=[tools], on_complete=keep
                ):
                    yield event

        return adapter.streaming_response(events())

    async def healthz(_: Request) -> Response:
        return JSONResponse({"status": "ok"})

    return Starlette(
        routes=[
            Route(
                "/entities/{entity_id}/conversations/{conversation_id}/turn",
                turn,
                methods=["POST"],
            ),
            Route(
                "/entities/{entity_id}/conversations/{conversation_id}",
                history,
                methods=["GET"],
            ),
            Route("/healthz", healthz, methods=["GET"]),
        ],
        middleware=[
            Middleware(
                CORSMiddleware,
                allow_origins=[] if web_origin is None else [web_origin],
                allow_methods=["GET", "POST"],
                allow_headers=["authorization", "content-type", "accept"],
            )
        ],
    )
