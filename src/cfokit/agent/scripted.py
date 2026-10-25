"""A scripted stand-in for Claude, for recording CFOKit's documentation with no credential.

ADR-0074 cuts a use case's clips from a passing run, and CI holds no inference credential
(ADR-0004), so a recorded run cannot call a real model. This one is a script, chosen only by
`CFOKIT_AGENT_MODEL=scripted`: asked anything, it reads the profit and loss to date through the
published tool, against the real books, and answers with the figures the tool returned, without
arithmetic of its own. Every response it writes is recorded with the model name "scripted", so
nothing it says can pass for Claude's in the conversation's history (`SOC1-35`).
"""

from __future__ import annotations

import datetime
import json
import re
from collections.abc import AsyncIterator
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic_ai.messages import ModelMessage, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, DeltaToolCalls, FunctionModel

__all__ = ["NAME", "scripted_model"]

NAME = "scripted"

_ENTITY = re.compile(r"entity_id ([0-9a-fA-F-]{36})")


def _figure(amount: str) -> str:
    """An amount the tool presented, with thousands separated: formatting, never rounding."""
    try:
        return f"{Decimal(amount):,}"
    except InvalidOperation:
        return amount


def _answer(result: Any) -> str:
    """The profit and loss as the tool returned it, in words and a table."""
    report = json.loads(result) if isinstance(result, str) else result
    if not isinstance(report, dict) or not report.get("ok", True) or "net_income" not in report:
        return "I couldn't read the profit and loss for this company."
    company = report.get("company") or "This company"
    if isinstance(company, dict):
        company = company.get("name") or "This company"
    rows = [
        f"| {line['name']} | {_figure(line['amount'])} |"
        for line in [*report.get("income", []), *report.get("expenses", [])]
    ]
    return "\n".join(
        [
            f"Here is **{company}**'s profit and loss to date.",
            "",
            "| Account | Amount |",
            "|---|---|",
            *rows,
            f"| Total income | {_figure(report['total_income'])} |",
            f"| Total expenses | {_figure(report['total_expenses'])} |",
            f"| **Net income** | **{_figure(report['net_income'])}** |",
        ]
    )


async def _script(
    messages: list[ModelMessage], info: AgentInfo
) -> AsyncIterator[str | DeltaToolCalls]:
    returned = [
        part
        for part in messages[-1].parts
        if isinstance(part, ToolReturnPart) and part.tool_name == "profit_and_loss"
    ]
    if returned:
        yield _answer(returned[-1].content)
        return
    entity = _ENTITY.search(info.instructions or "")
    if entity is None:
        yield "Which company do you mean?"
        return
    # Everything recorded, rather than this year, so a recording does not depend on its date.
    since = datetime.date.min.isoformat()
    yield {
        0: DeltaToolCall(
            "profit_and_loss", json.dumps({"entity_id": entity.group(1), "since": since})
        )
    }


def scripted_model() -> FunctionModel:
    return FunctionModel(stream_function=_script, model_name=NAME)
