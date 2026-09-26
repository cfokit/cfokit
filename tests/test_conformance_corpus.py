"""Every conformance case cites a source we may redistribute, and the coverage map is honest.

**The one mechanical control behind the provenance rule.** ADR-0036 § 5 requires an assertion's
expected value to come from outside the implementation, and says plainly that authorship cannot
be the control because every commit here is generated. What it puts in its place is provenance,
and provenance is only a control where something checks it. This is that something: layer 2
carries `NFR-01` while the differential oracle stays deferred (ADR-0010), so it is the layer
where the check has to be mechanical rather than reviewed.

Three things are checked here, and they are three because ADR-0043 and ADR-0044 draw two lines
a reader would otherwise blur.

*Redistribution.* A fixture ships in an Apache 2.0 repository, so its source must impose nothing
on a fork (`NFR-14`). ADR-0044 narrows that to public domain and CC0, and requires a case to
record *how* the work reached the public domain rather than merely asserting that it did.

*Two kinds of evidence, kept apart.* A conformance case transcribes someone else's published
**answer**. A recognition case cites a published **rule** and derives the answer itself, which
is weaker because we did the derivation. They live in separate directories and a recognition
case can never satisfy an area that wants the stronger kind.

*The map says what is evidenced, in both directions.* `docs/conformance/coverage.md` states a
claim per area and what stands behind it. An area claiming a case must have one; an area
claiming none must have none. The second direction is the one that holds over time, because it
fails when a case is added without the map being told, or when the map keeps claiming evidence
that was deleted.

A static read of the fixtures, deliberately outside the integration tier. It needs no database,
so it gates every commit rather than only the runs that have a stack up — and a case cannot
enter the corpus uncited on a developer's laptop either.

Whether a case's figures agree with its published answer is
`tests/integration/test_conformance.py`, which needs the books loaded.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

# `pythonpath = ["scripts"]` puts the gate scripts on the path, as `tests/test_money_gate.py`
# already relies on. Importing the requirement parser rather than writing a second one means
# there is one definition of "a live requirement id" and it cannot drift.
from check_decisions import defined_requirements

REPO_ROOT = Path(__file__).resolve().parent.parent
CASES = Path(__file__).resolve().parent / "fixtures" / "conformance"
RECOGNITION = Path(__file__).resolve().parent / "fixtures" / "recognition"
COVERAGE = REPO_ROOT / "docs" / "conformance" / "coverage.md"

# Works published before this year are public domain in the United States on the 95-year term.
# It advances every 1 January and is reviewed then (ADR-0044). A constant rather than a value
# computed from the clock: a gate whose verdict changes with the date fails on a Tuesday for a
# reason nobody can reproduce.
PUBLIC_DOMAIN_CUTOFF = 1931

REDISTRIBUTABLE = {"public-domain", "cc0"}
PD_BASES = {"term-expired", "not-renewed", "us-government"}
ANSWERS = {"trial_balance", "profit_and_loss", "balance_sheet"}

# Which kind of case an area's status demands. ADR-0043's bands decide this: a claim that the
# ledger enforces or presents something is answerable by a published answer, and a claim that a
# treatment is merely recordable is not, because nobody published an answer to a question we
# made up.
NEEDS_CONFORMANCE = {"enforced", "presented"}
NEEDS_RECOGNITION = {"recordable"}
NEEDS_NOTHING = {"declined", "gap"}
VALID_STATUS = NEEDS_CONFORMANCE | NEEDS_RECOGNITION | NEEDS_NOTHING
VALID_EVIDENCE = {"case", "none", "—"}

# | **area-slug** | 250 | `enforced` | `none` | LED-08, RPT-01 |
AREA_ROW = re.compile(
    r"^\|\s*\*\*([a-z0-9-]+)\*\*\s*\|\s*([^|]*?)\s*\|\s*`([a-z-]+)`\s*\|\s*(`[a-z]+`|—)\s*\|\s*([^|]*?)\s*\|$",
    re.M,
)
REQUIREMENT_ID = re.compile(r"\b([A-Z0-9]+-\d+)\b")


@dataclass(frozen=True, slots=True)
class Area:
    """One row of the coverage map: a claim, and what stands behind it."""

    name: str
    status: str
    evidence: str
    requirements: frozenset[str]

    @property
    def claims_a_case(self) -> bool:
        return self.evidence == "case"


def _areas() -> dict[str, Area]:
    text = COVERAGE.read_text(encoding="utf-8")
    return {
        m.group(1): Area(
            name=m.group(1),
            status=m.group(3),
            evidence=m.group(4).strip("`"),
            requirements=frozenset(REQUIREMENT_ID.findall(m.group(5))),
        )
        for m in AREA_ROW.finditer(text)
    }


def _names(directory: Path) -> list[str]:
    if not directory.is_dir():
        return []
    return sorted(child.name for child in directory.iterdir() if child.is_dir())


def _manifest(directory: Path, case: str) -> dict[str, Any]:
    return tomllib.loads((directory / case / "manifest.toml").read_text(encoding="utf-8"))


AREAS = _areas()
CASE_NAMES = _names(CASES)
RECOGNITION_NAMES = _names(RECOGNITION)


# --------------------------------------------------------------------------------------
# The corpus exists at all
# --------------------------------------------------------------------------------------


def test_the_corpus_is_not_empty() -> None:
    """The parameterised checks below pass vacuously over an empty directory, and an empty
    corpus is `NFR-01` carrying nothing."""
    assert CASE_NAMES


def test_the_coverage_map_is_not_empty() -> None:
    """Same argument, one level up: an unparseable map makes every cross-check vacuous, and a
    silently vacuous gate is worse than none because it reports success."""
    assert AREAS, f"no area rows parsed from {COVERAGE}"


# --------------------------------------------------------------------------------------
# The coverage map is well-formed (ADR-0043)
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("area", sorted(_areas()), ids=str)
def test_an_area_states_a_valid_claim(area: str) -> None:
    """A status outside the set is a claim nobody defined, and the cross-checks below would
    silently skip it rather than fail."""
    row = AREAS[area]

    assert row.status in VALID_STATUS, (
        f"{area}: status {row.status!r} is not one of {sorted(VALID_STATUS)}"
    )
    assert row.evidence in VALID_EVIDENCE, f"{area}: evidence {row.evidence!r} is undefined"

    if row.status in NEEDS_NOTHING:
        assert row.evidence == "—", (
            f"{area}: status {row.status!r} admits no evidence, so Evidence must be '—'"
        )
    else:
        assert row.evidence in {"case", "none"}, (
            f"{area}: status {row.status!r} is a claim, so Evidence must be `case` or `none`"
        )


@pytest.mark.parametrize("area", sorted(_areas()), ids=str)
def test_an_area_cites_live_requirements(area: str) -> None:
    """ADR-0001: derivation runs vision -> requirements -> decision records -> rules. A map row
    citing a requirement that no longer exists has been left behind by a change to the product,
    and its claim is about something nobody promised any more."""
    live = defined_requirements()

    for rid in sorted(AREAS[area].requirements):
        assert rid in live, f"{area}: cites {rid}, which requirements.md does not define"


# --------------------------------------------------------------------------------------
# A conformance case: someone else's published answer (ADR-0036 § 2, ADR-0044)
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("case", CASE_NAMES, ids=str)
def test_a_case_names_a_source_a_reader_can_find(case: str) -> None:
    """ADR-0036 § 2: "Each `manifest.toml` cites book, edition, year and problem number, so a
    human can check the transcription against the scan."

    A case with no citation is a unit test that has been misfiled — it asserts what we already
    believed, which is the blind spot layer 2 exists to close.
    """
    source = _manifest(CASES, case)["source"]

    for field in ("title", "author", "year", "problem", "scan"):
        assert source.get(field), f"{case}: [source] states no {field}"
    assert str(source["scan"]).startswith("http")


@pytest.mark.parametrize("case", CASE_NAMES, ids=str)
def test_a_case_is_redistributable(case: str) -> None:
    """`NFR-14`: no component imposes an obligation inconsistent with permissive licensing on
    anyone who runs, modifies, or forks it. ADR-0044 narrows this to the two licences that
    impose nothing at all, and requires the *basis* for a public-domain claim rather than the
    claim alone — "public domain" is a conclusion, and this checks the premise.
    """
    source = _manifest(CASES, case)["source"]
    licence = source["licence"]

    assert licence in REDISTRIBUTABLE, (
        f"{case}: licence {licence!r} is not one of {sorted(REDISTRIBUTABLE)}. A "
        "share-alike or non-commercial source cannot ship here at all (ADR-0044)."
    )
    if licence != "public-domain":
        return

    basis = source.get("pd_basis")
    assert basis in PD_BASES, (
        f"{case}: [source].pd_basis {basis!r} is not one of {sorted(PD_BASES)}"
    )

    if basis == "term-expired":
        assert source["year"] < PUBLIC_DOMAIN_CUTOFF, (
            f"{case}: published {source['year']}, which the "
            f"{PUBLIC_DOMAIN_CUTOFF} term rule "
            "does not reach. A later work needs a different basis."
        )
    if basis == "not-renewed":
        # We never make this determination ourselves (ADR-0044). The case cites a library that
        # already published one.
        determination = str(source.get("pd_determination", ""))
        assert determination.startswith("http"), (
            f"{case}: pd_basis is 'not-renewed', which requires [source].pd_determination — a "
            "URL to someone else's published determination, never our own renewal search."
        )


@pytest.mark.parametrize("case", CASE_NAMES, ids=str)
def test_a_case_declares_what_it_covers(case: str) -> None:
    """A case nobody can locate on the map is evidence for nothing in particular, and the map
    cannot report coverage it is not told about."""
    manifest = _manifest(CASES, case)
    coverage = manifest.get("coverage", {})
    live = defined_requirements()

    areas = coverage.get("areas", [])
    assert areas, f"{case}: [coverage] names no areas"
    for area in areas:
        assert area in AREAS, f"{case}: covers {area!r}, which coverage.md does not define"
        assert AREAS[area].status in NEEDS_CONFORMANCE, (
            f"{case}: covers {area!r}, whose status is {AREAS[area].status!r}. A published "
            "answer evidences `enforced` and `presented` areas; nothing else asks for one."
        )

    for rid in coverage.get("requirements", []):
        assert rid in live, f"{case}: cites {rid}, which requirements.md does not define"

    answer = manifest["expected"].get("answer")
    assert answer in ANSWERS, (
        f"{case}: [expected].answer {answer!r} is not one of {sorted(ANSWERS)}"
    )


# --------------------------------------------------------------------------------------
# A recognition case: a cited rule, our fact pattern (ADR-0044)
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("case", RECOGNITION_NAMES, ids=str)
def test_a_recognition_case_cites_a_rule(case: str) -> None:
    """These are the weaker evidence class and the gate says so by asking for different things.
    A conformance case is checked for a published *answer*; this is checked for a published
    *rule*, a locator precise enough to find it, and which basis the rule comes from — because
    tax authority and GAAP diverge, and a case that blurs them is worse than no case.
    """
    manifest = _manifest(RECOGNITION, case)
    rule = manifest["rule"]

    for field in ("authority", "locator", "url", "licence", "basis"):
        assert rule.get(field), f"{case}: [rule] states no {field}"
    assert str(rule["url"]).startswith("http")
    assert rule["licence"] in REDISTRIBUTABLE, (
        f"{case}: [rule].licence {rule['licence']!r} is not redistributable. A rule may "
        "be cited from anywhere, but a case quoting one must be shippable (ADR-0044)."
    )
    assert rule["basis"] in {"tax", "gaap"}, (
        f"{case}: [rule].basis {rule['basis']!r} is neither 'tax' nor 'gaap'. Where the two "
        "diverge the case must say which it followed."
    )


@pytest.mark.parametrize("case", RECOGNITION_NAMES, ids=str)
def test_a_recognition_case_covers_only_recordable_areas(case: str) -> None:
    """The line ADR-0044 draws, enforced. A cited rule is weaker evidence than a published
    answer because we did the derivation, so it may not be counted where the stronger kind was
    claimed."""
    live = defined_requirements()
    coverage = _manifest(RECOGNITION, case).get("coverage", {})

    areas = coverage.get("areas", [])
    assert areas, f"{case}: [coverage] names no areas"
    for area in areas:
        assert area in AREAS, f"{case}: covers {area!r}, which coverage.md does not define"
        assert AREAS[area].status in NEEDS_RECOGNITION, (
            f"{case}: covers {area!r}, whose status is {AREAS[area].status!r}. A cited rule "
            "evidences a `recordable` area and may never stand in for a published answer."
        )

    for rid in coverage.get("requirements", []):
        assert rid in live, f"{case}: cites {rid}, which requirements.md does not define"


# --------------------------------------------------------------------------------------
# The map and the corpus agree, in both directions
# --------------------------------------------------------------------------------------


def _covered(directory: Path, names: list[str]) -> dict[str, list[str]]:
    covered: dict[str, list[str]] = {}
    for case in names:
        for area in _manifest(directory, case).get("coverage", {}).get("areas", []):
            covered.setdefault(area, []).append(case)
    return covered


@pytest.mark.parametrize("area", sorted(_areas()), ids=str)
def test_the_map_reports_the_coverage_that_exists(area: str) -> None:
    """Both directions, and the second is the one that holds over time.

    Forwards: an area claiming a case must have one, or the map overstates what is evidenced.
    Backwards: an area claiming none must have none, which fails the moment a case is added
    without the map being told — the failure mode a one-directional check never catches, and
    the reason a coverage document drifts into fiction.
    """
    row = AREAS[area]
    conformance = _covered(CASES, CASE_NAMES).get(area, [])
    recognition = _covered(RECOGNITION, RECOGNITION_NAMES).get(area, [])
    found = conformance + recognition

    if not row.claims_a_case:
        assert not found, (
            f"{area}: Evidence is {row.evidence!r} but {found} covers it. Add the case to the "
            "map by setting Evidence to `case`, or remove the claim from the case."
        )
        return

    wanted = conformance if row.status in NEEDS_CONFORMANCE else recognition
    assert wanted, (
        f"{area}: Evidence is `case` but no case of the kind status {row.status!r} requires "
        "covers it. Either the case was deleted or the map was written ahead of it."
    )
