"""The conversation, read and appended through the published REST API (ADR-0076).

The agent holds no database credential and no state: at the start of a turn it reads the
conversation from core, and it appends each message it means to keep. Every call carries the
token exchanged for the person (ADR-0077), so core sees the agent acting for them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import httpx2

__all__ = ["Core", "CoreAPI", "Stored", "Thread"]


@dataclass(frozen=True, slots=True)
class Stored:
    """One stored message: its place and its content, the agent's own serialized form."""

    position: int
    content: Any


@dataclass(frozen=True, slots=True)
class Thread:
    holds_untrusted: bool
    messages: list[Stored]


class Core(Protocol):
    async def thread(self, token: str, entity_id: str, conversation_id: str) -> Thread: ...

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
    ) -> int: ...


class CoreAPI:
    """Core over HTTP, as any client reaches it."""

    def __init__(self, *, api_url: str, http: httpx2.AsyncClient) -> None:
        self._api_url = api_url.rstrip("/")
        self._http = http

    def _url(self, entity_id: str, conversation_id: str, suffix: str = "") -> str:
        return f"{self._api_url}/entities/{entity_id}/conversations/{conversation_id}{suffix}"

    async def thread(self, token: str, entity_id: str, conversation_id: str) -> Thread:
        response = await self._http.get(
            self._url(entity_id, conversation_id),
            headers={"Authorization": f"Bearer {token}"},
        )
        response.raise_for_status()
        body = response.json()
        return Thread(
            holds_untrusted=bool(body["conversation"]["holds_untrusted"]),
            messages=[Stored(int(m["position"]), m["content"]) for m in body["messages"]],
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
        """Append one message. `key` names it stably within its turn, so sending it again
        replays the place it was given rather than adding it twice (ADR-0029)."""
        response = await self._http.post(
            self._url(entity_id, conversation_id, "/messages"),
            headers={
                "Authorization": f"Bearer {token}",
                "Idempotency-Key": key,
            },
            json={
                "kind": kind,
                "content": content,
                "model": model,
                "model_version": model,
                "skill_version": skill_version,
            },
        )
        response.raise_for_status()
        return int(response.json()["position"])
