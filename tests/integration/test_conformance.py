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

import csv
from decimal import Decimal

import pytest

# `tests` is not a package, so this is an absolute import: pytest puts the test file's
# own directory on `sys.path` under the default import mode.
from conformance import CASE_NAMES, CASES, LOADER, Case, load

from cfokit.ledger.presentation import (
    PresentedReconciliation,
    SourceBalance,
    present_balance_sheet,
    present_profit_and_loss,
    present_reconciliation,
)
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.reports import balance_sheet, profit_and_loss, trial_balance

pytestmark = pytest.mark.integration


def _chart(name: str) -> list[dict[str, str]]:
    with (CASES / name / "accounts.csv").open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


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
    it printed. Nobody here decided what the answer should be — a practicing accountant did, in
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


# --- Every case, whatever shape its answer takes -------------------------------------------


def published_totals(database: Database, case: Case) -> dict[str, Decimal]:
    """The figures a statement case's source printed, as our own statement computes them.

    Both kinds come back in one mapping: the named totals a statement claims overall, and a
    figure per account code where the source printed one. `presentation` computes both
    already, so this reads the same numbers a customer sees rather than sums assembled here.

    Per-account figures come back in the **natural** sign `StatementLine` uses — positive
    means more of what the account is — which is how a published statement prints them. A
    case's CSV therefore carries the source's figures as printed, with no sign conversion for
    a transcription to get wrong.
    """
    if case.answer == "profit_and_loss":
        assert case.since is not None, f"{case.name}: a profit and loss needs [expected].since"
        statement = present_profit_and_loss(
            profit_and_loss(
                database,
                entity_id=case.entity_id,
                principal=LOADER,
                since=case.since,
                as_of=case.as_of,
            )
        )
        return {
            "total_income": statement.total_income,
            "total_expenses": statement.total_expenses,
            "net_income": statement.net_income,
            **{line.code: line.amount for line in (*statement.income, *statement.expenses)},
        }

    sheet = present_balance_sheet(
        balance_sheet(database, entity_id=case.entity_id, principal=LOADER, as_of=case.as_of)
    )
    return {
        "total_assets": sheet.total_assets,
        "total_liabilities": sheet.total_liabilities,
        "total_equity": sheet.total_equity,
        **{
            line.code: line.amount
            for line in (*sheet.assets, *sheet.liabilities, *sheet.equity)
        },
    }


@pytest.mark.parametrize("name", CASE_NAMES, ids=str)
def test_every_case_agrees_with_its_published_answer(database: Database, name: str) -> None:
    """**This is `NFR-01`'s evidence, for the whole corpus rather than one case of it.**

    Parameterised over the fixture directory rather than over named cases, for the reason
    `tests/test_conformance_corpus.py` gives: a check written against the cases that exist
    today holds only for them, and a case added later joins the gate by being added.
    """
    case = load(database, name)

    if case.answer == "trial_balance":
        report = reconcile(database, case)
        assert report.agrees, [
            (c.account_code, str(c.ours), str(c.theirs)) for c in report.disagreements
        ]
        return

    ours = published_totals(database, case)
    assert case.totals, f"{name}: a statement answer that asserts no total asserts nothing"

    expected = {**case.totals, **case.lines}
    missing = set(expected) - set(ours)
    assert not missing, (
        f"{name}: asserts {sorted(missing)}, which the statement does not report. An account "
        "with no balance does not appear, so this is a disagreement and not an absence."
    )

    disagreements = {
        line: (str(ours[line]), str(printed))
        for line, printed in expected.items()
        if ours[line] != printed
    }
    assert not disagreements, disagreements


@pytest.mark.parametrize("name", CASE_NAMES, ids=str)
def test_a_statement_case_asserts_only_lines_that_exist(database: Database, name: str) -> None:
    """A misspelled total silently asserts nothing, because the comparison above iterates the
    lines a case names. This is the check that stops a typo reading as agreement."""
    case = load(database, name)
    if case.answer == "trial_balance":
        pytest.skip("per-account answer; the reconciler covers the missing-account case")

    codes = {row["code"] for row in _chart(name)}
    unknown = set(case.lines) - codes
    assert not unknown, (
        f"{name}: names {sorted(unknown)}, which is neither a total this statement publishes "
        f"nor an account in its chart. A misspelling asserts nothing and reads as agreement."
    )
