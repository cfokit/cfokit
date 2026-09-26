"""ADR-0044's third evidence class: a cited rule, and a fact pattern of our own.

A conformance case transcribes a published *answer*, and that is what makes it independent —
somebody else computed it, before us and without us. A recognition case cannot have that,
because the question is one we asked. What it has instead is a published *rule*, cited to a
locator a reader can open, and a derivation short enough to check by hand.

That is weaker, and the separation is the point. These live in their own fixture tree, under
their own gate, and `tests/test_conformance_corpus.py` refuses to let one stand where a
published answer was claimed. ADR-0043 band 3 says CFOKit declines to decide accounting
policy; these cases show that a policy decided elsewhere is recorded and presented correctly,
which is a different and smaller claim.
"""

from __future__ import annotations

import pytest

# `tests` is not a package, so this is an absolute import: pytest puts the test file's
# own directory on `sys.path` under the default import mode.
from conformance import RECOGNITION, RECOGNITION_NAMES, TOTAL_LINES, load
from test_conformance import published_totals

from cfokit.ledger.repository.unit_of_work import Database

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("name", RECOGNITION_NAMES, ids=str)
def test_the_postings_follow_from_the_cited_rule(database: Database, name: str) -> None:
    """The treatment the rule determines, recorded and presented.

    Parameterised over the fixture tree for the same reason the corpus is: a check written
    against the cases that exist today holds only for them.
    """
    case = load(database, name, tree=RECOGNITION)
    assert case.totals, f"{name}: a case that asserts no figure asserts nothing"

    unknown = set(case.totals) - TOTAL_LINES[case.answer]
    assert not unknown, f"{name}: names {sorted(unknown)}, which no statement publishes"

    ours = published_totals(database, case)
    disagreements = {
        line: (str(ours[line]), str(derived))
        for line, derived in case.totals.items()
        if ours[line] != derived
    }
    assert not disagreements, disagreements


@pytest.mark.parametrize("name", RECOGNITION_NAMES, ids=str)
def test_the_derivation_is_written_down(database: Database, name: str) -> None:
    """A recognition case's expected figures are ours, so the manifest has to show the work.

    This checks the work is there, not that it is right — nothing mechanical can do the
    second. What it prevents is the failure that matters: a case whose figures came from
    running CFOKit and were written down afterwards, which ADR-0036 § 5 says is never a
    specification. A derivation nobody wrote is the signature of one.

    The reasoning lives in comments, as `[transcription]` does throughout the corpus, so this
    reads the file rather than the parsed table — an empty `[derivation]` header parses to an
    empty mapping and would satisfy a check on the parse.
    """
    text = (RECOGNITION / name / "manifest.toml").read_text(encoding="utf-8")
    assert "[derivation]" in text, (
        f"{name}: no [derivation]. A cited rule without the reasoning from rule to figures "
        "is an assertion, and an assertion is what this evidence class exists to avoid."
    )

    section = text.split("[derivation]", 1)[1]
    written = [line for line in section.splitlines() if line.strip().startswith("#")]
    assert len(written) >= 3, (
        f"{name}: [derivation] has {len(written)} lines of reasoning. Show the fact pattern, "
        "the rule it turns on, and the arithmetic — a reader has to be able to redo it."
    )


@pytest.mark.parametrize("name", RECOGNITION_NAMES, ids=str)
def test_a_recognition_case_still_balances(database: Database, name: str) -> None:
    """The floor under every case, whatever it is evidence for: the books it creates are
    books. A fact pattern of our own invention could be arithmetically impossible in a way a
    published one cannot, so this is checked here and not in the corpus."""
    case = load(database, name, tree=RECOGNITION)
    ours = published_totals(database, case)

    if case.answer == "profit_and_loss":
        assert ours["net_income"] == ours["total_income"] - ours["total_expenses"], (
            f"{name}: the profit and loss does not net"
        )
    else:
        assert ours["total_assets"] == ours["total_liabilities"] + ours["total_equity"], (
            f"{name}: the balance sheet does not balance"
        )
