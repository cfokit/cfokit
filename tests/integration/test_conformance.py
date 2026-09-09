"""ADR-0036 layer 2: the conformance corpus, and the reconciler that reads it.

> "Worked examples taken from **published sources with published answers**, asserted directly
> against the expected result… This is what replaces the oracle's independence property… it
> tests whether the answer is **right** rather than whether it **matches**."

`NFR-01` wants "a source of truth CFOKit did not author". Every case here has one, named in its
manifest, and a reader can check the transcription against the scan.

The negative cases matter as much as the positive one. A reconciler that cannot fail is worse
than no reconciler, because it reports agreement it never established.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

# `tests` is not a package, so this is an absolute import: pytest puts the test file's
# own directory on `sys.path` under the default import mode.
from conformance import LOADER, Case, load

from cfokit.ledger.presentation import (
    PresentedReconciliation,
    SourceBalance,
    present_reconciliation,
)
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.reports import trial_balance

pytestmark = pytest.mark.integration


def reconcile(
    database: Database, case: Case, source: tuple[SourceBalance, ...] | None = None
) -> PresentedReconciliation:
    return present_reconciliation(
        trial_balance(database, entity_id=case.entity_id, principal=LOADER, as_of=case.as_of),
        source if source is not None else case.source,
        source_is_rounded=case.source_is_rounded,
    )


@pytest.fixture
def washington_1907(database: Database) -> Case:
    """Greendlinger 1911, Question 25 — State of Washington Examination, September 1907."""
    return load(database, "greendlinger-1911-q25")


# --- The published answer -----------------------------------------------------------------


def test_the_books_agree_with_the_published_trial_balance(
    database: Database, washington_1907: Case
) -> None:
    """**This is `NFR-01`'s evidence.**

    The entries are the ones the published solution drafted; the expected balances are the ones
    it printed. Nobody here decided what the answer should be — a practising accountant did, in
    1911, answering a state examination set in 1907.
    """
    report = reconcile(database, washington_1907)

    assert report.agrees, [
        (c.account_code, str(c.ours), str(c.theirs)) for c in report.disagreements
    ]


def test_the_published_totals_are_reproduced(database: Database, washington_1907: Case) -> None:
    """The source prints $355,000.00 in each column. Ours must too, or the agreement above is
    an agreement about the wrong books."""
    report = reconcile(database, washington_1907)
    debits = sum((c.ours for c in report.comparisons if c.ours and c.ours > 0), Decimal(0))
    credited = -sum((c.ours for c in report.comparisons if c.ours and c.ours < 0), Decimal(0))

    assert debits == credited == Decimal("355000.00")


# --- The reconciler must be able to fail --------------------------------------------------


def test_a_transposed_figure_is_caught(database: Database, washington_1907: Case) -> None:
    """The classic bookkeeping error, and the one a tolerance would hide."""
    altered = tuple(
        SourceBalance(account_code=b.account_code, balance=Decimal("95300.00"))
        if b.account_code == "1100"
        else b
        for b in washington_1907.source
    )

    report = reconcile(database, washington_1907, altered)

    assert not report.agrees
    assert [c.account_code for c in report.disagreements] == ["1100"]
    assert report.disagreements[0].difference == Decimal("-1800.00")


def test_a_penny_is_a_disagreement(database: Database, washington_1907: Case) -> None:
    """`NFR-01`'s ledger target: "exactness, not accuracy within a tolerance. A tolerance is a
    defect, not a target." A reconciliation that passes within a penny will one day hide a
    penny that mattered."""
    altered = tuple(
        SourceBalance(account_code=b.account_code, balance=b.balance + Decimal("0.01"))
        if b.account_code == "1000"
        else b
        for b in washington_1907.source
    )

    assert not reconcile(database, washington_1907, altered).agrees


def test_an_account_missing_from_the_source_is_reported(
    database: Database, washington_1907: Case
) -> None:
    """Not dropped. An account silently missing from one side is the most tolerable-looking
    disagreement there is, and it differs by the whole of the side it is on."""
    altered = tuple(b for b in washington_1907.source if b.account_code != "1400")

    report = reconcile(database, washington_1907, altered)

    assert [c.account_code for c in report.disagreements] == ["1400"]
    assert report.disagreements[0].only_ours
    assert report.disagreements[0].theirs is None
    assert report.disagreements[0].difference == Decimal("15000.00")


def test_an_account_the_source_has_and_we_do_not_is_reported(
    database: Database, washington_1907: Case
) -> None:
    """The mirror case, and the one that catches an import that dropped a record."""
    altered = (
        *washington_1907.source,
        SourceBalance(account_code="9999", balance=Decimal("1.00")),
    )

    report = reconcile(database, washington_1907, altered)

    assert [c.account_code for c in report.disagreements] == ["9999"]
    assert report.disagreements[0].only_theirs
    assert report.disagreements[0].difference == Decimal("-1.00")


def test_a_sign_flip_is_caught(database: Database, washington_1907: Case) -> None:
    """A credit recorded as a debit ties to the same magnitude and is wrong by twice it."""
    altered = tuple(
        SourceBalance(account_code=b.account_code, balance=-b.balance)
        if b.account_code == "3000"
        else b
        for b in washington_1907.source
    )

    report = reconcile(database, washington_1907, altered)

    assert [c.account_code for c in report.disagreements] == ["3000"]
    assert report.disagreements[0].difference == Decimal("-30000.00")


def test_agreement_is_not_the_default(database: Database, washington_1907: Case) -> None:
    """The positive control on every test above: an empty source agrees with nothing.

    Without this, a reconciler that returned `agrees` for an empty comparison list would pass
    each negative case by reporting the wrong thing.
    """
    report = reconcile(database, washington_1907, ())

    assert not report.agrees
    assert len(report.disagreements) == len(washington_1907.source)
    assert all(c.only_ours for c in report.disagreements)
