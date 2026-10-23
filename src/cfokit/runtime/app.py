"""The runtime's HTTP surface: one turn, streamed as AG-UI events (ADR-0075 § 1).

The chat window posts the person's message with their access token. The runtime exchanges the
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

from cfokit.runtime import Skill
from cfokit.runtime.core import Core
from cfokit.runtime.tokens import TokenRefused, TokenSource
from cfokit.runtime.tools import PublishedTools

__all__ = ["Runtime", "create_app"]

log = logging.getLogger("cfokit.runtime")

Connect = Callable[[str], AbstractAsyncContextManager[Client]]


@dataclass(frozen=True, slots=True)
class Runtime:
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


def _dump(message: ModelMessage) -> Any:
    return ModelMessagesTypeAdapter.dump_python([message], mode="json")[0]


def create_app(runtime: Runtime, *, web_origin: str | None = None) -> Starlette:
    """The runtime's app. `web_origin` is the one browser origin allowed to call it, the web
    client's; None allows none, as for a caller that is not a browser."""
    agent: Agent[None, str] | None = (
        None
        if runtime.model is None
        else Agent(runtime.model, instructions=runtime.skill.instructions, name="cfokit")
    )

    async def turn(request: Request) -> Response:
        if agent is None:
            return _refusal(
                503, "runtime_off", "no inference credential is configured, so the chat is off"
            )
        person_token = _bearer(request)
        if person_token is None:
            return _refusal(401, "not_authenticated", "a turn needs the person's bearer token")
        entity_id = request.path_params["entity_id"]
        conversation_id = request.path_params["conversation_id"]

        try:
            token = await runtime.tokens.for_person(person_token)
        except TokenRefused as refused:
            return _refusal(403, refused.code, str(refused))
        try:
            thread = await runtime.core.thread(token, entity_id, conversation_id)
        except httpx2.HTTPStatusError as failed:
            # Core's own refusal, passed on: `agent_not_allowed` with its link, or not found.
            return Response(
                failed.response.content,
                status_code=failed.response.status_code,
                media_type="application/json",
            )

        adapter = await AGUIAdapter.from_request(request, agent=agent)
        prompt = _prompt(adapter.messages)
        if prompt is None:
            return _refusal(422, "no_message", "the last message sent is not the person's")
        history = ModelMessagesTypeAdapter.validate_python([m.content for m in thread.messages])
        run_id = adapter.run_input.run_id

        # Kept before the model sees it, so a turn that fails never loses what the person said.
        await runtime.core.append(
            token,
            entity_id,
            conversation_id,
            key=f"{run_id}:prompt",
            kind="request",
            content=_dump(prompt),
        )

        async def keep(result: AgentRunResult[Any]) -> None:
            for index, message in enumerate(result.new_messages()):
                await runtime.core.append(
                    token,
                    entity_id,
                    conversation_id,
                    key=f"{run_id}:{index}",
                    kind=message.kind,
                    content=_dump(message),
                    model=getattr(message, "model_name", None),
                    skill_version=runtime.skill.version if message.kind == "response" else None,
                )
            log.info(
                "turn complete",
                extra={
                    "conversation_id": conversation_id,
                    "messages": len(result.new_messages()),
                },
            )

        async def events() -> AsyncIterator[BaseEvent]:
            async with runtime.connect(token) as client:
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
            Route("/healthz", healthz, methods=["GET"]),
        ],
        middleware=[
            Middleware(
                CORSMiddleware,
                allow_origins=[] if web_origin is None else [web_origin],
                allow_methods=["POST"],
                allow_headers=["authorization", "content-type", "accept"],
            )
        ],
    )
