"""Which tools the agent offers, and how it reads a skill (ADR-0075 § 2, `PLT-23`).

ADR-0036 layer 1. Expected values come from `PLT-23` ("cannot post to the books in that
session"), from the published tool descriptions committed in `_tools.json`, and from FIPS
180-2's SHA-256 vector for "abc"; never from running the code.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cfokit.agent import POSTS_NOTHING, offered, read_skill

ROOT = Path(__file__).resolve().parents[1]
PUBLISHED = [
    tool["name"]
    for tool in json.loads(
        (ROOT / "skills/cfokit/evals/mocks/cfokit/_tools.json").read_text(encoding="utf-8")
    )["tools"]
]

# Each of these posts, or can post, by its own published description.
POSTS = {
    "post_transaction",
    "record_transaction",
    "reverse_transaction",
    "run_assignment",
    "answer_unresolved_transaction",
    "approve_assignment_rule",
    "issue_statement",
}


def test_a_conversation_holding_nothing_untrusted_is_offered_every_tool() -> None:
    assert offered(PUBLISHED, holds_untrusted=False) == PUBLISHED


def test_a_conversation_holding_untrusted_content_is_offered_nothing_that_posts() -> None:
    """`PLT-23`: once it has read what the organization did not author, it cannot post."""
    given = set(offered(PUBLISHED, holds_untrusted=True))
    assert not given & POSTS
    assert {"profit_and_loss", "trial_balance", "record_account_statement"} <= given


def test_a_tool_nobody_has_judged_is_withheld_from_such_a_conversation() -> None:
    """An allowlist: a tool added later is withheld until someone decides it posts nothing."""
    assert offered(["profit_and_loss", "a_new_tool"], holds_untrusted=True) == [
        "profit_and_loss"
    ]


def test_every_tool_said_to_post_nothing_is_one_the_surface_publishes() -> None:
    """A name here that the surface does not publish is a rename this list missed."""
    assert set(POSTS_NOTHING) <= set(PUBLISHED)


def test_a_skill_is_its_frontmatter_name_and_its_body() -> None:
    skill = read_skill(
        "---\nname: bookkeeper\ndescription: keeps books: carefully\n---\n\nBody.\n"
    )
    assert skill.name == "bookkeeper"
    assert skill.instructions == "Body."


def test_a_skill_s_version_changes_exactly_when_its_text_does() -> None:
    """FIPS 180-2 Appendix B.1: SHA-256("abc") begins ba7816bf8f01."""
    assert read_skill("abc").version == "skill@ba7816bf8f01"


def test_the_shipped_bookkeeper_skill_reads() -> None:
    skill = read_skill((ROOT / "skills/cfokit/bookkeeper/SKILL.md").read_text(encoding="utf-8"))
    assert skill.name == "bookkeeper"
    assert skill.version.startswith("bookkeeper@")


@pytest.mark.parametrize("text", ["", "---\nname: x\n---\n", "---\nname: x\nnever closed"])
def test_a_skill_with_no_instructions_is_refused(text: str) -> None:
    with pytest.raises(ValueError):
        read_skill(text)
