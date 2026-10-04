"""US English everywhere.

A British spelling in any tracked text file fails here. The list is the spellings that have
actually appeared in this repository and their closest relatives, not a dictionary: a new one
that slips through is added when it is found. Third-party texts carried verbatim, such as the
fonts' licenses, are not ours to respell, and this file is exempt because its
pattern and its test inputs must write the British forms.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

TEXT = re.compile(r"\.(md|py|ts|tsx|mjs|js|css|html|json|ya?ml|toml|sql|txt|sh)$")
VERBATIM = re.compile(
    r"(^|/)(licenses/|tests/test_us_english\.py$|.*-OFL\.txt$|pnpm-lock\.yaml$|uv\.lock$)"
)

# -ise, -ised, -ising, -isation on stems that take -ize in US English.
_STEMS = (
    "authori|organi|recogni|synchroni|locali|materiali|generali|virtuali|tokeni|optimi|normali|"
    "seriali|initiali|summari|prioriti|categori|finali|customi|utili|minimi|maximi|standardi|"
    "speciali|centrali|capitali|characteri|memori|saniti|paralleli|stabili|visuali|reali|apologi|"
    "critici"
)
BRITISH = re.compile(
    r"\b(?:"
    rf"(?:{_STEMS})s(?:e|ed|es|ing|ation|ations)"
    r"|colour(?:s|ed|ing)?|behaviours?|honour(?:s|ed|ing)?|favour(?:s|ed|ite|able)?"
    r"|centre[sd]?|labell(?:ed|ing)|cancell(?:ed|ing)|travell(?:ed|ing|er)|modell(?:ed|ing)"
    r"|catalogues?|licences?|defence|analys(?:e|ed|es|ing)"
    r")\b",
    re.IGNORECASE,
)


def tracked_text_files() -> list[Path]:
    if not (ROOT / ".git").exists() or shutil.which("git") is None:
        pytest.skip("needs a git checkout")
    names = subprocess.run(
        ["git", "ls-files"],  # noqa: S607 — git from PATH, as every contributor runs it
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    return [ROOT / n for n in names if TEXT.search(n) and not VERBATIM.search(n)]


def test_no_british_spellings() -> None:
    found = [
        f"{path.relative_to(ROOT)}:{number}: {match.group(0)}"
        for path in tracked_text_files()
        for number, line in enumerate(path.read_text(errors="ignore").splitlines(), 1)
        for match in BRITISH.finditer(line)
    ]
    assert not found, "British spellings (use US English):\n" + "\n".join(found)


def test_the_check_catches_what_it_is_for() -> None:
    for british in (
        "colour",
        "labelled",
        "organisation",
        "synchronised",
        "centred",
        "optimise",
    ):
        assert BRITISH.search(british), british
    for us in (
        "color",
        "labeled",
        "organization",
        "synchronized",
        "centered",
        "optimize",
        "honored",
    ):
        assert not BRITISH.search(us), us
    for unrelated in ("promise", "exercise", "otherwise", "rising", "emphasis"):
        assert not BRITISH.search(unrelated), unrelated
