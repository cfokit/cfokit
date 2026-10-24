"""``python -m cfokit.agent`` — serve the agent (ADR-0023: one image, many entrypoints).

Composed here rather than in `cfokit.server`, which composes the ledger and its modules: the
agent is a separate component that reaches them only over HTTP (ADR-0022, ADR-0075).
"""

from __future__ import annotations

import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx2
import uvicorn
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from pydantic_ai.models import Model

from cfokit.agent import read_skill
from cfokit.agent.app import Services, create_app
from cfokit.agent.config import AgentSettings, ConfigError
from cfokit.agent.core import CoreAPI
from cfokit.agent.tokens import Exchange

log = logging.getLogger("cfokit.agent")


def _model(settings: AgentSettings) -> Model | None:
    """Claude through Pydantic AI, or None when no inference credential is configured.

    Imported here, not at module scope, so the provider's SDK loads only where it is used
    (ADR-0004).
    """
    if settings.anthropic_api_key is None:
        log.warning("no inference credential is configured; the chat is off")
        return None
    from pydantic_ai.models.anthropic import AnthropicModel
    from pydantic_ai.providers.anthropic import AnthropicProvider

    return AnthropicModel(
        settings.model, provider=AnthropicProvider(api_key=settings.anthropic_api_key)
    )


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    try:
        settings = AgentSettings.from_env()
    except ConfigError as missing:
        log.error("%s: %s", missing.code, missing)
        return 2

    http = httpx2.AsyncClient(timeout=30)

    @asynccontextmanager
    async def connect(token: str) -> AsyncIterator[Client]:
        async with (
            httpx2.AsyncClient(headers={"Authorization": f"Bearer {token}"}) as signed_in,
            Client(streamable_http_client(settings.mcp_url, http_client=signed_in)) as client,
        ):
            yield client

    services = Services(
        model=_model(settings),
        skill=read_skill(settings.skill_path.read_text(encoding="utf-8")),
        tokens=Exchange(
            issuer_url=settings.issuer_url,
            client_id=settings.client_id,
            client_secret=settings.client_secret,
            http=http,
        ),
        core=CoreAPI(api_url=settings.api_url, http=http),
        connect=connect,
    )
    uvicorn.run(
        create_app(services, web_origin=settings.web_origin),
        host="0.0.0.0",  # noqa: S104 - inside a container
        port=settings.port,
        ssl_certfile=settings.tls_cert_file,
        ssl_keyfile=settings.tls_key_file,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
