"""Every conformance case cites a published source (ADR-0036 § 2 and § 5).

**The one mechanical control behind the provenance rule.** ADR-0036 § 5 requires an assertion's
expected value to come from outside the implementation, and says plainly that authorship cannot
be the control because every commit here is generated. What it puts in its place is provenance,
and provenance is only a control where something checks it. This is that something: layer 2
carries `NFR-01` while the differential oracle stays deferred (ADR-0010), so it is the layer
where the check has to be mechanical rather than reviewed.

A static read of the fixtures, deliberately outside the integration tier. It needs no database,
so it gates every commit rather than only the runs that have a stack up — and a case cannot
enter the corpus uncited on a developer's laptop either.

The corpus itself — whether each case's figures agree with its published answer — is
`tests/integration/test_conformance.py`, which needs the books loaded.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

import pytest

CASES = Path(__file__).resolve().parent / "fixtures" / "conformance"
CASE_NAMES = sorted(directory.name for directory in CASES.iterdir() if directory.is_dir())


def test_the_corpus_is_not_empty() -> None:
    """The parameterised checks below pass vacuously over an empty directory, and an empty
    corpus is `NFR-01` carrying nothing."""
    assert CASE_NAMES


@pytest.mark.parametrize("case", CASE_NAMES, ids=str)
def test_a_case_names_a_source_a_reader_can_find(case: str) -> None:
    """ADR-0036 § 2: "Each `manifest.toml` cites book, edition, year and problem number, so a
    human can check the transcription against the scan."

    A case with no citation is a unit test that has been misfiled — it asserts what we already
    believed, which is the blind spot layer 2 exists to close.
    """
    source = _manifest(case)["source"]

    for field in ("title", "author", "year", "problem", "scan"):
        assert source.get(field), f"{case}: [source] states no {field}"
    assert str(source["scan"]).startswith("http")


@pytest.mark.parametrize("case", CASE_NAMES, ids=str)
def test_a_case_is_redistributable(case: str) -> None:
    """`NFR-14`: no component imposes an obligation inconsistent with permissive licensing on
    anyone who runs, modifies, or forks it. A case whose licence is unrecorded cannot be shipped
    with confidence, and one under a share-alike or non-commercial licence cannot be shipped at
    all."""
    source = _manifest(case)["source"]

    assert source["licence"] in {"public-domain", "cc0", "cc-by-4.0"}
    if source["licence"] == "public-domain":
        # The United States pre-1931 rule, which is what puts the current corpus in the clear.
        # A later work needs its own recorded basis rather than this one.
        assert source["year"] < 1931


def _manifest(case: str) -> dict[str, Any]:
    return tomllib.loads((CASES / case / "manifest.toml").read_text(encoding="utf-8"))
