#!/usr/bin/env python3
"""CI gate 6: the decision corpus is well-formed (ADR-0001).

ADR-0001 names this check in its Confirmation section. Until it existed, the record
governing every other record was enforced by review alone, which is weaker than every
other gate in this repository.

Eight assertions, each one ADR-0001 makes:

1.  **Frontmatter parses**, and carries `status`, `kind`, `date` and `decision-makers`.
2.  **`status` is valid** — one of the six values the template names.
3.  **`kind` is valid** — `requirement-driven` or `substrate`. This field is what makes
    assertion 6 checkable; without it the rule is a judgment call, and a judgment call
    is not a gate.
4.  **`superseded by ADR-NNNN` resolves** to a file that exists. A dangling supersession
    is worse than none: the reader is sent somewhere and finds nothing.
5.  **`README.md` lists exactly the records present**, with matching link targets and
    status column. An index that disagrees with the directory sends readers to the wrong
    record.
6.  **Every `requirement-driven` record cites at least one live requirement id**, and
    every id it cites is defined in `requirements.md`. Substrate records cite none —
    a manufactured trace to a requirement is worse than no record.
7.  **`requirements.md` and `vision.md` cite no decision record.** Derivation runs
    vision -> requirements -> decision records -> rules, and the arrow never reverses.
    A requirement constrained by a decision has been quietly rewritten to match what was
    built.
8.  **The template is followed** — the mandatory sections are present, and Pros and Cons
    refutes at least as many options as Considered Options names. A record that names
    alternatives without refuting each one does not prevent re-litigation, which is the
    main thing a record is for.
Exits non-zero listing every offense, so CI fails loudly.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DECISIONS = REPO_ROOT / "docs" / "decisions"
REQUIREMENTS = REPO_ROOT / "docs" / "product" / "requirements.md"
VISION = REPO_ROOT / "docs" / "product" / "vision.md"
INDEX = DECISIONS / "README.md"

RECORD_NAME = re.compile(r"^(\d{4})-[a-z0-9-]+\.md$")


VALID_STATUS = {"draft", "proposed", "accepted", "rejected", "deprecated"}
SUPERSEDED = re.compile(r"^superseded by ADR-(\d{4})$")
VALID_KIND = {"requirement-driven", "substrate"}

# A requirement is *defined* by its row in requirements.md: | **LED-09** | ... |
REQUIREMENT_DEF = re.compile(r"^\|\s*\*\*([A-Z0-9]+-\d+)\*\*\s*\|")
REQUIREMENTS_SERVED = re.compile(r"^\*\*Requirements served:\*\*\s*(.+?)\.?\s*$", re.MULTILINE)
REQUIREMENT_ID = re.compile(r"\b([A-Z0-9]+-\d+)\b")

# A citation of a decision record, in any of the forms the corpus uses.
RECORD_CITATION = re.compile(r"ADR-\d{4}|docs/decisions/|\]\(\d{4}-[a-z0-9-]+\.md\)")

INDEX_ROW = re.compile(
    r"^\|\s*\[(\d{4})\]\(([^)]+)\)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*$",
)

# Sections the template requires. ADR-0001 makes "Considered Options" and "Pros and Cons
# of the Options" mandatory where MADR marks the second optional, and adds "Revisit when".
MANDATORY_SECTIONS = (
    "## Context and Problem Statement",
    "## Decision Drivers",
    "## Considered Options",
    "## Decision Outcome",
    "### Consequences",
    "### Confirmation",
    "## Pros and Cons of the Options",
    "## Revisit when",
)


def parse_frontmatter(text: str) -> dict[str, str] | None:
    """Return the YAML frontmatter as flat key -> string, or None if it is absent.

    Hand-parsed rather than pulling in a YAML dependency: the frontmatter is four to six
    scalar keys and the template fixes its shape.
    """
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end == -1:
        return None
    fields: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, sep, value = line.partition(":")
        if not sep:
            continue
        fields[key.strip()] = value.strip().strip('"').strip("'")
    return fields


def section_body(text: str, heading: str) -> str:
    """Return the lines under `heading`, stopping at the next heading of the same depth."""
    depth = len(heading) - len(heading.lstrip("#"))
    stop = re.compile(rf"^#{{1,{depth}}} ")
    out: list[str] = []
    collecting = False
    for line in text.splitlines():
        if line.strip() == heading:
            collecting = True
            continue
        if collecting:
            if stop.match(line):
                break
            out.append(line)
    return "\n".join(out)


def defined_requirements() -> set[str]:
    return {
        m.group(1)
        for line in REQUIREMENTS.read_text().splitlines()
        if (m := REQUIREMENT_DEF.match(line))
    }


def check_record(path: Path, text: str, live: set[str], numbers: set[str]) -> list[str]:
    """Assertions 1-4, 6 and 8, for a single record."""
    bad: list[str] = []
    name = path.name

    front = parse_frontmatter(text)
    if front is None:
        return [f"{name}: no YAML frontmatter"]

    for key in ("status", "kind", "date", "decision-makers"):
        if not front.get(key):
            bad.append(f"{name}: frontmatter is missing `{key}`")

    status = front.get("status", "")
    if status and status not in VALID_STATUS:
        if m := SUPERSEDED.match(status):
            if m.group(1) not in numbers:
                bad.append(
                    f"{name}: `superseded by ADR-{m.group(1)}` names no record that exists"
                )
        else:
            bad.append(f"{name}: status {status!r} is not a valid status")

    kind = front.get("kind", "")
    if kind and kind not in VALID_KIND:
        bad.append(f"{name}: kind {kind!r} is not `requirement-driven` or `substrate`")

    served = REQUIREMENTS_SERVED.search(text)
    cited = set(REQUIREMENT_ID.findall(served.group(1))) if served else set()

    if kind == "requirement-driven":
        if not cited:
            bad.append(
                f"{name}: kind is requirement-driven but it cites no requirement. "
                "Either cite one, or it is substrate."
            )
        for rid in sorted(cited - live):
            bad.append(f"{name}: cites {rid}, which requirements.md does not define")
    elif kind == "substrate" and cited:
        bad.append(
            f"{name}: kind is substrate but it cites {', '.join(sorted(cited))}. "
            "A substrate decision has no requirement to cite."
        )

    for heading in MANDATORY_SECTIONS:
        if not re.search(rf"^{re.escape(heading)}\s*$", text, re.MULTILINE):
            bad.append(f"{name}: missing mandatory section `{heading}`")

    options = [
        ln
        for ln in section_body(text, "## Considered Options").splitlines()
        if ln.startswith("* ")
    ]
    refuted = [
        ln
        for ln in section_body(text, "## Pros and Cons of the Options").splitlines()
        if ln.startswith("### ")
    ]
    if options and len(refuted) < len(options):
        bad.append(
            f"{name}: Considered Options names {len(options)} options but Pros and Cons "
            f"refutes {len(refuted)}. Every option needs its own subsection."
        )

    return bad


# Artifacts a record can name in its Confirmation: a gate script, a task, a test file. Each
# is a claim about something that exists, and each is checkable.
CITED_SCRIPT = re.compile(r"`(scripts/[A-Za-z0-9_./-]+\.py)`")
CITED_TASK = re.compile(r"`uv run task ([a-z][a-z0-9-]*)")
CITED_TEST = re.compile(r"`(tests/[A-Za-z0-9_./-]+\.py)`")


def defined_tasks() -> set[str]:
    """Task names from the taskipy table, which is the only place they are defined."""
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    block = re.search(r"\[tool\.taskipy\.tasks\]\n(.*?)(?=\n\[|\Z)", text, re.S)
    if not block:
        return set()
    return set(re.findall(r'^"?([a-z][a-z0-9-]*)"?\s*=', block.group(1), re.M))


def check_cited_artifacts(path: Path, text: str, tasks: set[str]) -> list[str]:
    """Every script, task and test a record names must actually exist.

    ADR-0001's template says a Confirmation records "how compliance is verified: a CI gate, a
    linter contract, a test, a review step. If nothing enforces this, say so plainly — an
    unenforced decision is a convention, not a constraint."

    A record naming a gate that does not exist is worse than one admitting the gap, because
    it stops the next reader going to look for the real protection. Four such claims were
    found by hand before this check existed: ADR-0020's Confirmation, ADR-0028's driver
    contract, `CLAUDE.md`'s `cfokit.connectors` contract, and a `uv sync` check that a
    layout change had removed.

    This cannot tell whether a *test* proves what a record says it proves — only that the
    thing named is there at all. That is the mechanical half; the rest is review.
    """
    problems: list[str] = []

    for cited in sorted(set(CITED_SCRIPT.findall(text))):
        if not (REPO_ROOT / cited).is_file():
            problems.append(f"{path.name}: cites `{cited}`, which does not exist")

    for cited in sorted(set(CITED_TEST.findall(text))):
        if not (REPO_ROOT / cited).is_file():
            problems.append(f"{path.name}: cites `{cited}`, which does not exist")

    for cited in sorted(set(CITED_TASK.findall(text))):
        if cited not in tasks:
            problems.append(
                f"{path.name}: cites `uv run task {cited}`, undefined in pyproject.toml"
            )

    return problems


def check_index(records: dict[str, Path], statuses: dict[str, str]) -> list[str]:
    """Assertion 5: the index lists exactly the records present."""
    bad: list[str] = []
    listed: dict[str, tuple[str, str]] = {}
    for line in INDEX.read_text().splitlines():
        if m := INDEX_ROW.match(line):
            listed[m.group(1)] = (m.group(2), m.group(4))

    for number in sorted(set(records) - set(listed)):
        bad.append(f"README.md: {records[number].name} is not listed in the index")
    for number in sorted(set(listed) - set(records)):
        bad.append(
            f"README.md: the index lists ADR-{number}, which is not a file in this directory"
        )

    for number in sorted(set(records) & set(listed)):
        target, shown = listed[number]
        if target != records[number].name:
            bad.append(
                f"README.md: ADR-{number} links to {target}, "
                f"but the file is {records[number].name}"
            )
        expected = statuses.get(number, "")
        if shown.lower() != expected.lower():
            bad.append(
                f"README.md: ADR-{number} is shown as {shown!r} "
                f"but its frontmatter says {expected!r}"
            )

    return bad


def check_derivation() -> list[str]:
    """Assertion 7: the arrow never reverses."""
    bad: list[str] = []
    for doc in (REQUIREMENTS, VISION):
        for number, line in enumerate(doc.read_text().splitlines(), start=1):
            if RECORD_CITATION.search(line):
                rel = doc.relative_to(REPO_ROOT)
                bad.append(
                    f"{rel}:{number}: cites a decision record. Requirements and the vision "
                    "cite nothing downstream of them — the decision exists to satisfy the "
                    "requirement, not the other way round."
                )
    return bad


def main() -> int:
    records = {
        m.group(1): p
        for p in sorted(DECISIONS.glob("*.md"))
        if (m := RECORD_NAME.match(p.name))
    }
    if not records:
        print(f"error: no decision records found under {DECISIONS}", file=sys.stderr)
        return 1

    live = defined_requirements()
    if not live:
        print(f"error: no requirement ids found in {REQUIREMENTS}", file=sys.stderr)
        return 1

    bad: list[str] = []
    statuses: dict[str, str] = {}
    tasks = defined_tasks()

    for number, path in records.items():
        text = path.read_text()
        front = parse_frontmatter(text) or {}
        statuses[number] = front.get("status", "")
        bad.extend(check_record(path, text, live, set(records)))
        bad.extend(check_cited_artifacts(path, text, tasks))

    bad.extend(check_index(records, statuses))
    bad.extend(check_derivation())

    if bad:
        print(f"Decision corpus: {len(bad)} problem(s).\n", file=sys.stderr)
        for problem in bad:
            print(f"  {problem}", file=sys.stderr)
        print(
            "\nADR-0001 governs the corpus; adr-template.md is the starting point.",
            file=sys.stderr,
        )
        return 1

    accepted = sum(1 for s in statuses.values() if s == "accepted")
    print(
        f"Decision corpus: {len(records)} records ({accepted} accepted), "
        f"{len(live)} live requirement ids, all checks pass."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
