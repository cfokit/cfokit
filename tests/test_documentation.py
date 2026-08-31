"""Documentation integrity.

The rules in ``CLAUDE.md`` are only as good as the reasoning they point at. These tests
fail when a link rots, when a rule cites an ADR that exists in neither the accepted set
nor the written-up backlog, or when a citation resolves to a record that is not the one
it names.

That last case is the one that got us. A renumbering shifted every record up by one and
updated the prose but not the configuration, the workflow, or the schema — so the first
migration credited Postgres-only to ADR-0002 and the zero-sum trigger to ADR-0005. Every
number still existed, so an existence check passed throughout. Two gaps let it through,
and both are closed here: the scan read only markdown outside ``docs/decisions/`` when
every drifted file was YAML, SQL, or a ``.gitkeep``; and it asked whether a cited number
existed rather than whether it was the right one.

Semantic correctness is not mechanically checkable — no test can know that ADR-0010 is
the record about protocol adapters. What *is* checkable is agreement between a citation
and its target, which is the form the drift actually took.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
ADR_DIR = REPO_ROOT / "docs" / "decisions"

# Caches, virtualenvs, and vendored trees. `.github` and `.claude` are deliberately in
# scope: the CI workflow was one of the files that drifted.
EXCLUDED = {
    ".git",
    ".venv",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".import_linter_cache",
    "__pycache__",
    "node_modules",
}

# Anything that can carry an ADR citation. The drift lived in the last three.
CITING_SUFFIXES = {".md", ".py", ".toml", ".yaml", ".yml", ".sql"}
CITING_NAMES = {".gitkeep"}

# Inline markdown links, excluding images.
LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")
ADR_REFERENCE = re.compile(r"ADR-(\d{4})")
# A link whose text names a record: [ADR-0020](…/0020-identity-provider….md)
ADR_LINK = re.compile(r"\[ADR-(\d{4})\]\(([^)]+)\)")
ADR_HEADING = re.compile(r"^# ADR-(\d{4})\b", re.MULTILINE)
# An index row pointing at a record file.
INDEX_ENTRY = re.compile(r"\((\d{4}-[a-z0-9-]+\.md)\)")
# Domain-prefixed requirement ids. The `REQ-` scheme they replaced is retired.
REQUIREMENT_ID = re.compile(r"\b(?:LED|BKP|IAM|PLT|RPT|MIG|AR|NFR|SOC1|SOC2)-\d+\b")
ADR_KIND = re.compile(r'^kind: "([^"]+)"', re.MULTILINE)


def _walk() -> list[Path]:
    return sorted(
        path
        for path in REPO_ROOT.rglob("*")
        if path.is_file()
        and not any(part in EXCLUDED for part in path.relative_to(REPO_ROOT).parts)
    )


def markdown_files() -> list[Path]:
    """Project markdown, excluding caches and vendored trees."""
    return [path for path in _walk() if path.suffix == ".md"]


def citing_files() -> list[Path]:
    """Every file that could carry an ADR citation, in any language."""
    return [
        path for path in _walk() if path.suffix in CITING_SUFFIXES or path.name in CITING_NAMES
    ]


def adr_files() -> list[Path]:
    return sorted(ADR_DIR.glob("[0-9][0-9][0-9][0-9]-*.md"))


def _identify(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT))


def known_adr_numbers() -> set[str]:
    """Numbers with a record on disk, plus numbers reserved in the index's tables."""
    accepted = {path.name[:4] for path in adr_files()}
    index_text = (ADR_DIR / "README.md").read_text(encoding="utf-8")
    backlogged = set(re.findall(r"^\|\s*(\d{4})\s*\|", index_text, re.MULTILINE))
    return accepted | backlogged


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


@pytest.mark.parametrize("source", citing_files(), ids=_identify)
def test_every_cited_adr_is_accepted_or_backlogged(source: Path) -> None:
    """No file may cite an ADR that exists in neither the accepted set nor the backlog.

    Scoped to every file type rather than markdown alone, and to `docs/decisions/` as well
    as outside it. The records cite each other constantly, and a wrong number there is as
    misleading as a wrong number in a rule.
    """
    known = known_adr_numbers()
    try:
        text = source.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        pytest.skip("not text")

    dangling = sorted({n for n in ADR_REFERENCE.findall(text) if n not in known})
    assert not dangling, (
        f"{source.relative_to(REPO_ROOT)} cites ADRs that are neither accepted nor "
        f"backlogged: {dangling}"
    )


@pytest.mark.parametrize("source", markdown_files(), ids=_identify)
def test_adr_link_text_matches_its_target(source: Path) -> None:
    """A link reading [ADR-NNNN] must point at record NNNN.

    Catches the renumbering failure directly: the label and the path disagree, both halves
    resolve, and nothing else notices. The root README carried exactly this — [ADR-0021]
    pointing at `0020-identity-provider-conformance-contract.md`.
    """
    mismatched: list[str] = []
    for cited, target in ADR_LINK.findall(source.read_text(encoding="utf-8")):
        basename = target.partition("#")[0].rsplit("/", 1)[-1]
        match = re.match(r"(\d{4})-", basename)
        if match and match.group(1) != cited:
            mismatched.append(f"[ADR-{cited}] -> {target}")

    assert not mismatched, (
        f"{source.relative_to(REPO_ROOT)} has links whose text and target name different "
        f"records: {mismatched}"
    )


@pytest.mark.parametrize("source", adr_files(), ids=_identify)
def test_adr_filename_matches_its_heading(source: Path) -> None:
    """A record's number in its filename and in its own title must agree.

    Renaming a record without editing its heading leaves a file that answers to two
    numbers, which is how a citation ends up correct against one and wrong against the
    other.
    """
    heading = ADR_HEADING.search(source.read_text(encoding="utf-8"))
    assert heading, f"{source.name} has no '# ADR-NNNN' heading"
    assert heading.group(1) == source.name[:4], (
        f"{source.name} is titled ADR-{heading.group(1)}"
    )


def test_index_and_records_agree() -> None:
    """Every record is in the index, and every index row resolves to a record.

    The index is what `CLAUDE.md` sends a reader to, and what this module treats as the
    register of reserved numbers. A record missing from it is invisible; a row with no
    record is a dead link that also widens the set of numbers considered valid.
    """
    index_text = (ADR_DIR / "README.md").read_text(encoding="utf-8")
    linked = set(INDEX_ENTRY.findall(index_text))
    on_disk = {path.name for path in adr_files()}

    assert not (on_disk - linked), f"records missing from the index: {sorted(on_disk - linked)}"
    assert not (linked - on_disk), f"index rows with no record: {sorted(linked - on_disk)}"


def defined_requirement_ids() -> set[str]:
    text = (REPO_ROOT / "docs" / "product" / "requirements.md").read_text(encoding="utf-8")
    return set(REQUIREMENT_ID.findall(text))


@pytest.mark.parametrize("source", citing_files(), ids=_identify)
def test_cited_requirement_ids_exist(source: Path) -> None:
    """Every requirement id cited anywhere resolves to one in requirements.md.

    The retired `REQ-` scheme left every citation in the corpus dangling for a while, and
    nothing noticed, because no test read requirements.md at all.
    """
    defined = defined_requirement_ids()
    try:
        text = source.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        pytest.skip("not text")
    if source == REPO_ROOT / "docs" / "product" / "requirements.md":
        pytest.skip("the source of truth defines them")

    dangling = sorted({i for i in REQUIREMENT_ID.findall(text) if i not in defined})
    assert not dangling, (
        f"{source.relative_to(REPO_ROOT)} cites requirement ids that do not exist: {dangling}"
    )


@pytest.mark.parametrize("source", adr_files(), ids=_identify)
def test_requirement_driven_records_cite_a_requirement(source: Path) -> None:
    """`kind: requirement-driven` obliges a record to name what it serves.

    ADR-0001 makes this unconditional: a record answering a question the product forces
    cites the requirement ids it serves, always, at least one. A record that cannot name
    one is substrate that has been misfiled, and inventing a citation to satisfy the rule
    is worse than either.
    """
    text = source.read_text(encoding="utf-8")
    kind = ADR_KIND.search(text)
    assert kind, f"{source.name} declares no kind"
    if kind.group(1) != "requirement-driven":
        pytest.skip("substrate cites no requirement")

    assert REQUIREMENT_ID.search(text), (
        f"{source.name} is requirement-driven but cites no requirement id"
    )
