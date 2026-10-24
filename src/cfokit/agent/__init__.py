"""CFOKit's own agent, the chat behind the web app (ADR-0034 § 4, ADR-0075).

**A component, not a module** (ADR-0022 § 3): it holds the inference credential and long-lived
streams, and it reaches CFOKit only through the published interfaces, the MCP tools for the
books and the REST API for its conversations, as its own client acting for a person (ADR-0077).
It imports nothing of the ledger or any module, and `import-linter` holds it to that.

**It is built on Pydantic AI and speaks AG-UI** (ADR-0075). A turn is one Pydantic AI run: the
bookkeeper skill as its instructions, the published tools as its only tools, the conversation's
stored history as its history. What is here is CFOKit's own: which tools a conversation is
offered, and what the skill says.

What is in this file is pure: no I/O, no clock, no network.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass

__all__ = ["POSTS_NOTHING", "Skill", "offered", "read_skill"]

# The published tools that post nothing, offered in a conversation that holds content the
# organization did not author (`PLT-23`, ADR-0075 § 2). An allowlist rather than a list of what
# posts: a tool added to the surface later is withheld from such a conversation until someone
# decides it posts nothing, which is the safe way for that decision to be missed.
#
# Absent on purpose: `record_transaction` posts straight through when asked to, `run_assignment`
# posts what a rule resolves, and `answer_unresolved_transaction`, `approve_assignment_rule`,
# `reverse_transaction`, `post_transaction`, `issue_statement` and `create_entity` write as
# their names say.
POSTS_NOTHING = frozenset(
    {
        "account_detail",
        "account_statement_agreement",
        "balance_sheet",
        "comparative_profit_and_loss",
        "import_reconciliations",
        "issued_statements",
        "list_entities",
        "obligation_detail",
        "open_balances",
        "open_notifications",
        "outstanding_obligations",
        "profit_and_loss",
        "propose_assignment_rule",
        "read_entity",
        "read_transaction",
        "reconcile",
        "record_account_statement",
        "replay_assignments",
        "trial_balance",
        "unresolved_transactions",
    }
)


def offered(names: Iterable[str], *, holds_untrusted: bool) -> list[str]:
    """Which of the published tools the model is offered in this conversation, in their order.

    Every one, until the conversation holds content the organization did not author; then only
    those that post nothing, for the rest of it. The rule is enforced by what is offered, never
    by an instruction (`PLT-23`): a model cannot call a tool it was not given.
    """
    return [name for name in names if not holds_untrusted or name in POSTS_NOTHING]


@dataclass(frozen=True, slots=True)
class Skill:
    """A skill as the image carries it: its instructions, and the version they are recorded
    as."""

    name: str
    instructions: str
    version: str


def read_skill(text: str) -> Skill:
    """The skill a `SKILL.md` describes.

    Its frontmatter names it; its body is the instructions. The version is the name and the
    first twelve hex digits of the file's SHA-256, so it changes exactly when the text the model
    is given changes, and a response records which text that was (`SOC1-06`, `SOC1-34`).
    """
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
    body = text
    name = "skill"
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end == -1:
            raise ValueError("a SKILL.md whose frontmatter is never closed")
        for line in text[4:end].splitlines():
            key, _, value = line.partition(":")
            if key.strip() == "name" and value.strip():
                name = value.strip()
        body = text[end + len("\n---\n") :]
    instructions = body.strip()
    if not instructions:
        raise ValueError("a SKILL.md with no instructions")
    return Skill(name=name, instructions=instructions, version=f"{name}@{digest}")
