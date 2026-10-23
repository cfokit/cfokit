"""The published MCP tools, offered to the model as a Pydantic AI toolset (ADR-0075 § 2).

Our own small adapter over the official `mcp` SDK, which CFOKit already depends on, rather than
Pydantic AI's `MCPToolset`, which needs `fastmcp` and would double the server's dependency tree.
It uses the toolset interface Pydantic AI documents for exactly this.

The model is offered the published tools and nothing else: no file, shell or web tool. Which of
them depends on the conversation (`offered`), and a call to a tool that was not offered is
refused here as well as never being presented, so the rule holds even against a model that names
one.
"""

from __future__ import annotations

from typing import Any

import pydantic_core
from mcp import Client
from mcp.types import TextContent
from pydantic_ai.tools import RunContext, ToolDefinition
from pydantic_ai.toolsets import AbstractToolset
from pydantic_ai.toolsets.abstract import ToolsetTool

from cfokit.runtime import offered

__all__ = ["PublishedTools", "ToolWithheld"]

# The arguments are a JSON object the server validates against its own schema; validating them
# twice would only let the two disagree.
_ANY_OBJECT = pydantic_core.SchemaValidator(
    schema=pydantic_core.core_schema.dict_schema(
        pydantic_core.core_schema.str_schema(), pydantic_core.core_schema.any_schema()
    )
)


class ToolWithheld(Exception):
    """A call to a tool this conversation was not offered."""


class PublishedTools(AbstractToolset[Any]):
    """CFOKit's MCP tools, through a client already signed in as the runtime acting for a
    person."""

    def __init__(self, client: Client, *, holds_untrusted: bool) -> None:
        self._client = client
        self._holds_untrusted = holds_untrusted
        self._offered: frozenset[str] = frozenset()

    @property
    def id(self) -> str | None:
        return "cfokit"

    async def get_tools(self, ctx: RunContext[Any]) -> dict[str, ToolsetTool[Any]]:
        published = []
        cursor: str | None = None
        while True:
            page = await self._client.list_tools(cursor=cursor)
            published.extend(page.tools)
            cursor = page.next_cursor
            if not cursor:
                break
        names = offered(
            (tool.name for tool in published), holds_untrusted=self._holds_untrusted
        )
        self._offered = frozenset(names)
        return {
            tool.name: ToolsetTool(
                toolset=self,
                tool_def=ToolDefinition(
                    name=tool.name,
                    description=tool.description,
                    parameters_json_schema=tool.input_schema,
                ),
                max_retries=ctx.max_retries,
                args_validator=_ANY_OBJECT,
            )
            for tool in published
            if tool.name in self._offered
        }

    async def call_tool(
        self, name: str, tool_args: dict[str, Any], ctx: RunContext[Any], tool: ToolsetTool[Any]
    ) -> Any:
        if name not in self._offered:
            raise ToolWithheld(f"{name} is not offered in this conversation")
        result = await self._client.call_tool(name, tool_args)
        # CFOKit's tools answer with structured content, refusals included (`ok: false` and a
        # `code`), so the model reads a refusal as an answer rather than as a failed call.
        if result.structured_content is not None:
            return result.structured_content
        return "\n".join(part.text for part in result.content if isinstance(part, TextContent))
