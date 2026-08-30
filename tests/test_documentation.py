"""Documentation integrity.

The rules in ``CLAUDE.md`` are only as good as the reasoning they point at. These tests
fail when a link rots or a rule cites an ADR that exists in neither the accepted set nor
the written-up backlog — which is exactly the situation that gets a rule argued with.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
ADR_DIR = REPO_ROOT / "docs" / "decisions"

# Inline markdown links, excluding images.
LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")
ADR_REFERENCE = re.compile(r"ADR-(\d{4})")


def markdown_files() -> list[Path]:
    """Project markdown, excluding anything inside a dot-directory.

    Skipping every dot-directory keeps collection deterministic. `.pytest_cache/README.md`
    is a cache artifact that appears only after the first run, so globbing it made the test
    count depend on whether a cache existed. It also excludes vendored `.claude/` and
    vendored `.claude/` content, whose links are not ours to fix.
    """
    return sorted(
        path
        for path in REPO_ROOT.rglob("*.md")
        if not any(part.startswith(".") for part in path.relative_to(REPO_ROOT).parts)
    )


def _identify(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT))


@pytest.mark.parametrize("source", markdown_files(), ids=_identify)
def test_relative_links_resolve(source: Path) -> None:
    """Every relative markdown link points at something that exists."""
    broken: list[str] = []
    for target in LINK.findall(source.read_text(encoding="utf-8")):
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        path, _, _anchor = target.partition("#")
        if not path:
            continue
        if not (source.parent / path).exists():
            broken.append(target)

    assert not broken, f"{source.relative_to(REPO_ROOT)} has broken links: {broken}"


def test_adr_index_lives_with_the_adrs() -> None:
    """CLAUDE.md cites docs/decisions/README.md as the index; it must actually be there."""
    index = ADR_DIR / "README.md"
    assert index.is_file(), "the ADR index must live alongside the ADRs it links to"
    assert "# Decision records" in index.read_text(encoding="utf-8")


def test_every_cited_adr_is_accepted_or_backlogged() -> None:
    """No rule may cite an ADR that exists in neither the accepted set nor the backlog."""
    accepted = {path.name[:4] for path in ADR_DIR.glob("[0-9][0-9][0-9][0-9]-*.md")}
    index_text = (ADR_DIR / "README.md").read_text(encoding="utf-8")
    backlogged = set(re.findall(r"^\|\s*(\d{4})\s*\|", index_text, re.MULTILINE))
    known = accepted | backlogged

    cited: dict[str, set[str]] = {}
    for source in markdown_files():
        if ADR_DIR in source.parents:
            continue
        for number in ADR_REFERENCE.findall(source.read_text(encoding="utf-8")):
            cited.setdefault(number, set()).add(str(source.relative_to(REPO_ROOT)))

    dangling = {number: sorted(files) for number, files in cited.items() if number not in known}
    assert not dangling, f"ADRs cited but neither accepted nor backlogged: {dangling}"
