"""Assignment against real books (`BKP-06` to `BKP-12`, `RPT-08`).

ADR-0036 layer 3. The matcher's invariants are proved without infrastructure in
`tests/test_assignment_engine.py`; what is new here is that a decision and the postings it
explains reach one `COMMIT`, that attribution survives on the posting, and that `BKP-06`'s
acceptance — replay — actually holds against stored rows.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

import psycopg
import pytest

from cfokit.assignment import Counterpart, CounterpartKind, Field, Operator, Outcome, Predicate
from cfokit.assignment.candidate import Candidate, SourceKind
from cfokit.assignment.errors import NotACounterpart, NothingToDecline, PrecedenceTaken
from cfokit.assignment.service import (
    answer_question,
    apply_rules,
    approve,
    open_questions,
    propose,
    replay,
)
from cfokit.ledger.engine import Entry, Posting
from cfokit.ledger.errors import NotAPerson, NotAuthorized
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.administration import create_account, create_entity, grant_role
from cfokit.ledger.service.principal import ActorClass, Principal
from cfokit.ledger.service.receivables import obligation_detail, outstanding_obligations
from cfokit.ledger.service.write import WriteContext, record_transaction

pytestmark = pytest.mark.integration

WHEN = date(2026, 3, 1)
# The owner `owned_books` creates. `approve` is a person's own act (ADR-0042), so the
# principal has to be one that actually holds the entity.
OWNER = Principal(id="user:geoff", actor_class=ActorClass.PERSON)


@pytest.fixture
def chart(database: Database, owned_books: tuple[str, str, str]) -> dict[str, str]:
    """A bank account the activity arrives on, and two it can be coded to."""
    entity_id, cash, _ = owned_books
    accounts = {"Bank": cash}
    for name, code, kind in (("Insurance", "6200", "expense"), ("Prepaid", "1400", "asset")):
        accounts[name] = create_account(
            database,
            entity_id=entity_id,
            principal=OWNER,
            request_id="assignment-test",
            code=code,
            name=name,
            account_type=kind,
        )
    return accounts


@pytest.fixture
def entity(owned_books: tuple[str, str, str]) -> str:
    return owned_books[0]


def acme(
    chart: dict[str, str],
    amount: str,
    *,
    ref: str | None = None,
    kind: SourceKind = SourceKind.FEED,
) -> Candidate:
    """An ACME line. Each call is a distinct line unless `ref` says it is the same one."""
    return Candidate(
        payee="ACME Insurance Co",
        amount=Decimal(amount),
        commodity="USD",
        source_account_id=chart["Bank"],
        transaction_date=WHEN,
        source_kind=kind,
        source_ref=ref or f"line-{uuid.uuid4()}",
    )


def payee_rule(value: str = "acme") -> tuple[Predicate, ...]:
    return (Predicate(1, Field.PAYEE, Operator.CONTAINS, value),)


# --- Applying an approved rule ------------------------------------------------------------


def test_an_approved_rule_books_the_transaction(
    database: Database, entity: str, chart: dict[str, str]
) -> None:
    """`BKP-06` end to end: a candidate in, a posted transaction out, coded by the rule."""
    approve(
        database,
        entity_id=entity,
        principal=OWNER,
        label="ACME to insurance",
        precedence=10,
        account_id=chart["Insurance"],
        predicates=payee_rule(),
    )

    applied = apply_rules(
        database,
        entity_id=entity,
        principal=OWNER,
        request_id="run-1",
        candidates=[acme(chart, "-240.00")],
    )

    assert applied.unresolved == ()
    assert [b.outcome for b in applied.booked] == [Outcome.ASSIGNED]
    assert applied.booked[0].rule_label == "ACME to insurance"


def test_the_coded_posting_names_the_rule_and_the_bank_leg_does_not(
    database: Database, entity: str, chart: dict[str, str], app_conn: psycopg.Connection[Any]
) -> None:
    """`BKP-10` and `RPT-08`, and the reason attribution is per posting rather than per
    transaction: a feed's two legs are decided by different things, and the bank leg is the
    account the money arrived on — no rule chose it."""
    version_id = approve(
        database,
        entity_id=entity,
        principal=OWNER,
        label="ACME to insurance",
        precedence=10,
        account_id=chart["Insurance"],
        predicates=payee_rule(),
    )
    apply_rules(
        database,
        entity_id=entity,
        principal=OWNER,
        request_id="run-1",
        candidates=[acme(chart, "-240.00")],
    )

    with app_conn.cursor() as cur:
        cur.execute("SELECT set_config('cfokit.entity_id', %s, false)", (entity,))
        cur.execute(
            "SELECT account_id, assigned_by_rule_version_id FROM posting"
            " WHERE entity_id = %s ORDER BY amount",
            (entity,),
        )
        rows = {str(account): rule for account, rule in cur.fetchall()}

    assert str(rows[chart["Insurance"]]) == version_id
    assert rows[chart["Bank"]] is None


def test_the_transaction_records_that_a_rule_coded_it(
    database: Database, entity: str, chart: dict[str, str], app_conn: psycopg.Connection[Any]
) -> None:
    """ADR-0042 § 4, which reserved this: `actor_class` describes why a posting was made,
    and a rule-assigned coding is the class ADR-0033 § 3 wants maximized because "an auditor
    tests it cheaply and once"."""
    approve(
        database,
        entity_id=entity,
        principal=OWNER,
        label="ACME to insurance",
        precedence=10,
        account_id=chart["Insurance"],
        predicates=payee_rule(),
    )
    apply_rules(
        database,
        entity_id=entity,
        principal=OWNER,
        request_id="run-1",
        candidates=[acme(chart, "-240.00")],
    )

    with app_conn.cursor() as cur:
        cur.execute("SELECT set_config('cfokit.entity_id', %s, false)", (entity,))
        cur.execute(
            "SELECT actor_class, actor_principal_id FROM ledger_transaction"
            " WHERE entity_id = %s",
            (entity,),
        )
        actor_class, actor = cur.fetchone() or (None, None)

    assert actor_class == "rule"
    # The caller is still named. `actor_class` says why, never who or whether they may.
    assert actor == OWNER.id


# --- BKP-12: nothing guessed, nothing parked ----------------------------------------------


def test_an_unresolved_candidate_books_nothing_postable(
    database: Database, entity: str, chart: dict[str, str], app_conn: psycopg.Connection[Any]
) -> None:
    """`BKP-12` and `NFR-16`. The draft has one leg, so the ledger itself refuses to let it
    become a posting — the refusal is structural rather than a policy anyone follows."""
    applied = apply_rules(
        database,
        entity_id=entity,
        principal=OWNER,
        request_id="run-1",
        candidates=[acme(chart, "-240.00")],
    )

    assert applied.booked == ()
    assert [b.outcome for b in applied.unresolved] == [Outcome.UNMATCHED]

    with app_conn.cursor() as cur:
        cur.execute("SELECT set_config('cfokit.entity_id', %s, false)", (entity,))
        cur.execute(
            "SELECT status, (SELECT count(*) FROM posting p WHERE p.transaction_id = t.id)"
            "  FROM ledger_transaction t WHERE t.entity_id = %s",
            (entity,),
        )
        status, legs = cur.fetchone() or (None, None)

    assert status == "draft"
    assert legs == 1


# --- BKP-08: the order is stated, and two rules may not both state it ---------------------


def test_a_second_rule_at_one_precedence_is_refused(
    database: Database, entity: str, chart: dict[str, str]
) -> None:
    """Two live rules at one precedence means the order does not say which wins, so the
    answer would fall to a tiebreak nobody chose. Refused rather than resolved."""
    approve(
        database,
        entity_id=entity,
        principal=OWNER,
        label="first",
        precedence=10,
        account_id=chart["Insurance"],
        predicates=payee_rule(),
    )

    with pytest.raises(PrecedenceTaken):
        approve(
            database,
            entity_id=entity,
            principal=OWNER,
            label="second",
            precedence=10,
            account_id=chart["Prepaid"],
            predicates=payee_rule("other"),
        )


def test_the_more_specific_rule_wins_when_the_operator_says_so(
    database: Database, entity: str, chart: dict[str, str]
) -> None:
    """`BKP-07`'s own example — one payee, two accounts, decided by the amount — with
    `BKP-08`'s stated order deciding which rule looks first."""
    approve(
        database,
        entity_id=entity,
        principal=OWNER,
        label="large ACME premiums are prepaid",
        precedence=10,
        account_id=chart["Prepaid"],
        predicates=(
            *payee_rule(),
            Predicate(2, Field.AMOUNT, Operator.LESS_THAN, Decimal("-1000")),
        ),
    )
    approve(
        database,
        entity_id=entity,
        principal=OWNER,
        label="ACME otherwise expensed",
        precedence=20,
        account_id=chart["Insurance"],
        predicates=payee_rule(),
    )

    applied = apply_rules(
        database,
        entity_id=entity,
        principal=OWNER,
        request_id="run-1",
        candidates=[acme(chart, "-2400.00"), acme(chart, "-240.00")],
    )

    assert [b.rule_label for b in applied.booked] == [
        "large ACME premiums are prepaid",
        "ACME otherwise expensed",
    ]


# --- BKP-09: the operator sees the contest before approving -------------------------------


def test_a_proposal_names_the_rule_it_would_contend_with(
    database: Database, entity: str, chart: dict[str, str]
) -> None:
    """`BKP-08`'s acceptance: "the operator can see which rule won and why **before**
    approving either". A proposal writes nothing — it is a read."""
    approve(
        database,
        entity_id=entity,
        principal=OWNER,
        label="ACME otherwise expensed",
        precedence=20,
        account_id=chart["Insurance"],
        predicates=payee_rule(),
    )

    proposal = propose(
        database,
        entity_id=entity,
        principal=OWNER,
        label="everything ACME is prepaid",
        precedence=30,
        account_id=chart["Prepaid"],
        predicates=payee_rule(),
        candidates=[acme(chart, "-240.00")],
    )

    assert proposal.would_book == ()
    assert [label for _, label in proposal.would_contend_with] == ["ACME otherwise expensed"]


# --- BKP-11: an edit reaches forwards only ------------------------------------------------


def test_editing_a_rule_leaves_what_it_already_coded_untouched(
    database: Database, entity: str, chart: dict[str, str], app_conn: psycopg.Connection[Any]
) -> None:
    """**`BKP-11`, and it holds because nothing can be updated rather than because anything
    declines to.** The version that coded the first transaction is still on its posting, and
    still says what it said."""
    rule_id = str(uuid.uuid4())
    first = approve(
        database,
        entity_id=entity,
        principal=OWNER,
        label="ACME to insurance",
        precedence=10,
        account_id=chart["Insurance"],
        predicates=payee_rule(),
        rule_id=None,
    )
    apply_rules(
        database,
        entity_id=entity,
        principal=OWNER,
        request_id="run-1",
        candidates=[acme(chart, "-240.00")],
    )

    with app_conn.cursor() as cur:
        cur.execute("SELECT set_config('cfokit.entity_id', %s, false)", (entity,))
        cur.execute("SELECT rule_id FROM assignment_rule_version WHERE id = %s", (first,))
        rule_id = str((cur.fetchone() or [""])[0])

    second = approve(
        database,
        entity_id=entity,
        principal=OWNER,
        label="ACME to prepaid now",
        precedence=10,
        account_id=chart["Prepaid"],
        predicates=payee_rule(),
        rule_id=rule_id,
    )

    with app_conn.cursor() as cur:
        cur.execute("SELECT set_config('cfokit.entity_id', %s, false)", (entity,))
        cur.execute(
            "SELECT account_id, assigned_by_rule_version_id FROM posting"
            " WHERE entity_id = %s AND assigned_by_rule_version_id IS NOT NULL",
            (entity,),
        )
        account, coded_by = cur.fetchone() or (None, None)

    assert first != second
    assert str(coded_by) == first
    assert str(account) == chart["Insurance"]


# --- BKP-06's acceptance, executable ------------------------------------------------------


def busy(chart: dict[str, str]) -> list[Candidate]:
    """A spread of candidates: some contested, some sole matches, some nothing resolves."""
    return [
        *(acme(chart, f"-{n}00.00") for n in range(1, 6)),
        *(acme(chart, f"-{n}000.00") for n in range(1, 4)),
        *(
            Candidate(
                payee=f"Unfamiliar payee {n}",
                amount=Decimal("-50.00"),
                commodity="USD",
                source_account_id=chart["Bank"],
                transaction_date=WHEN,
                source_kind=SourceKind.FEED,
                source_ref=f"unfamiliar-{n}",
            )
            for n in range(3)
        ),
    ]


def arrange(database: Database, entity: str, chart: dict[str, str]) -> None:
    approve(
        database,
        entity_id=entity,
        principal=OWNER,
        label="large ACME premiums are prepaid",
        precedence=10,
        account_id=chart["Prepaid"],
        predicates=(
            *payee_rule(),
            Predicate(2, Field.AMOUNT, Operator.LESS_THAN, Decimal("-1000")),
        ),
    )
    approve(
        database,
        entity_id=entity,
        principal=OWNER,
        label="ACME otherwise expensed",
        precedence=20,
        account_id=chart["Insurance"],
        predicates=payee_rule(),
    )
    apply_rules(
        database,
        entity_id=entity,
        principal=OWNER,
        request_id="run-1",
        candidates=busy(chart),
    )


def test_replaying_an_unchanged_rule_set_reproduces_every_assignment(
    database: Database, entity: str, chart: dict[str, str]
) -> None:
    """**`BKP-06`'s acceptance, in its own words.**

    Every decision is re-taken against the rule set reconstructed as at the moment it was
    taken, and must come out the same — same outcome, same rule version, same reason.
    """
    arrange(database, entity, chart)

    report = replay(database, entity_id=entity, principal=OWNER)

    assert report.total == len(busy(chart))
    assert report.compared == report.total
    assert report.reproduced == report.compared
    assert report.rule_set_changed == 0
    assert report.diverged == ()


def test_a_rule_edit_leaves_every_earlier_decision_reproducing(
    database: Database, entity: str, chart: dict[str, str], app_conn: psycopg.Connection[Any]
) -> None:
    """**`BKP-11` as arithmetic.** The rules change; the decisions taken before the change
    still reconstruct the set that was in force for them, so they still reproduce. Nothing
    declines to apply the new version to them — it simply is not in their rule set."""
    arrange(database, entity, chart)

    with app_conn.cursor() as cur:
        cur.execute("SELECT set_config('cfokit.entity_id', %s, false)", (entity,))
        cur.execute(
            "SELECT rule_id FROM assignment_rule_version WHERE entity_id = %s"
            " AND label = 'ACME otherwise expensed'",
            (entity,),
        )
        rule_id = str((cur.fetchone() or [""])[0])

    approve(
        database,
        entity_id=entity,
        principal=OWNER,
        label="ACME now prepaid",
        precedence=20,
        account_id=chart["Prepaid"],
        predicates=payee_rule(),
        rule_id=rule_id,
    )

    report = replay(database, entity_id=entity, principal=OWNER)

    assert report.reproduced == report.compared == report.total
    assert report.diverged == ()


def test_replay_writes_nothing(
    database: Database, entity: str, chart: dict[str, str], app_conn: psycopg.Connection[Any]
) -> None:
    """A read and a pure function, which is what makes it safe against real books."""
    arrange(database, entity, chart)

    def snapshot() -> tuple[int, ...]:
        with app_conn.cursor() as cur:
            cur.execute("SELECT set_config('cfokit.entity_id', %s, false)", (entity,))
            counts = []
            for table in ("posting", "ledger_transaction", "assignment_decision"):
                cur.execute(f"SELECT count(*) FROM {table} WHERE entity_id = %s", (entity,))  # noqa: S608
                counts.append(int((cur.fetchone() or [0])[0]))
        return tuple(counts)

    before = snapshot()
    replay(database, entity_id=entity, principal=OWNER)

    assert snapshot() == before


# --- A line's identity is its source reference, never its content (ADR-0029, ADR-0046) ----


def counts(app_conn: psycopg.Connection[Any], entity: str) -> tuple[int, int]:
    """(transactions, decisions) for the entity."""
    with app_conn.cursor() as cur:
        cur.execute("SELECT set_config('cfokit.entity_id', %s, false)", (entity,))
        cur.execute("SELECT count(*) FROM ledger_transaction WHERE entity_id = %s", (entity,))
        transactions = int((cur.fetchone() or [0])[0])
        cur.execute("SELECT count(*) FROM assignment_decision WHERE entity_id = %s", (entity,))
        decisions = int((cur.fetchone() or [0])[0])
    return transactions, decisions


def persisted(owner_conn: psycopg.Connection[Any], entity: str) -> tuple[int, int, int, int]:
    """(transactions, decisions, notifications, `record_transaction` audit rows), read as the
    schema owner so nothing a scope or policy hides could make a leftover row look absent."""
    counted = []
    with owner_conn.cursor() as cur:
        for sql in (
            "SELECT count(*) FROM ledger_transaction WHERE entity_id = %s",
            "SELECT count(*) FROM assignment_decision WHERE entity_id = %s",
            "SELECT count(*) FROM notification WHERE entity_id = %s",
            "SELECT count(*) FROM audit_log WHERE entity_id = %s"
            " AND action = 'record_transaction'",
        ):
            cur.execute(sql, (entity,))
            counted.append(int((cur.fetchone() or [0])[0]))
    return counted[0], counted[1], counted[2], counted[3]


class Interrupted(Exception):
    """A failure after the entry is written and before its decision's work is done."""


def test_an_unresolved_line_writes_its_draft_decision_and_question(
    database: Database, entity: str, chart: dict[str, str], owner_conn: psycopg.Connection[Any]
) -> None:
    """The ordinary path, as the control for the one below: one draft, the decision that
    explains it, the owner told (ADR-0052), and the write path's one audit row."""
    apply_rules(
        database,
        entity_id=entity,
        principal=OWNER,
        request_id="run-1",
        candidates=[acme(chart, "-240.00", ref="line-1")],
    )

    assert persisted(owner_conn, entity) == (1, 1, 1, 1)


def test_a_failure_after_the_entry_leaves_no_entry_decision_or_question(
    database: Database,
    entity: str,
    chart: dict[str, str],
    owner_conn: psycopg.Connection[Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADR-0045 § 1 and ADR-0022 § 3: a decision and the draft it coded reach one `COMMIT`.

    The failure is raised after the entry and its decision are written, so the only thing
    that can make all of them absent is that they shared the transaction that rolled back.
    A draft left behind would be a coding no record explains — the gap `RPT-08` closes.
    """

    def interrupted(*_: object, **__: object) -> None:
        raise Interrupted

    line = acme(chart, "-240.00", ref="line-1")
    with monkeypatch.context() as patched:
        patched.setattr("cfokit.assignment.service.notify_holders", interrupted)
        with pytest.raises(Interrupted):
            apply_rules(
                database,
                entity_id=entity,
                principal=OWNER,
                request_id="run-1",
                candidates=[line],
            )

    assert persisted(owner_conn, entity) == (0, 0, 0, 0)

    # The idempotency claim rolled back with the rest, so running the line again is a first
    # write rather than a replay of one that never committed.
    again = apply_rules(
        database, entity_id=entity, principal=OWNER, request_id="run-2", candidates=[line]
    )
    assert len(again.unresolved) == 1
    assert persisted(owner_conn, entity) == (1, 1, 1, 1)


def test_a_failure_answering_a_coded_line_leaves_nothing_posted(
    database: Database,
    entity: str,
    chart: dict[str, str],
    owner_conn: psycopg.Connection[Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The resolved path: the entry posts straight through, so a posting with no decision
    would be in the books. It must not survive its decision failing to land."""
    approve(
        database,
        entity_id=entity,
        principal=OWNER,
        label="ACME to insurance",
        precedence=10,
        account_id=chart["Insurance"],
        predicates=payee_rule(),
    )

    def interrupted(*_: object, **__: object) -> None:
        raise Interrupted

    monkeypatch.setattr("cfokit.assignment.service.answer", interrupted)
    with pytest.raises(Interrupted):
        apply_rules(
            database,
            entity_id=entity,
            principal=OWNER,
            request_id="run-1",
            candidates=[acme(chart, "-240.00", ref="line-1")],
        )

    assert persisted(owner_conn, entity) == (0, 0, 0, 0)


def test_two_identical_lines_are_two_transactions(
    database: Database, entity: str, chart: dict[str, str], app_conn: psycopg.Connection[Any]
) -> None:
    """ADR-0029's own case: "two five-dollar coffees on the same day are two transactions".
    Every fact matches; only the source says they are different lines."""
    applied = apply_rules(
        database,
        entity_id=entity,
        principal=OWNER,
        request_id="run-1",
        candidates=[acme(chart, "-5.00", ref="line-1"), acme(chart, "-5.00", ref="line-2")],
    )

    assert len({b.transaction_id for b in applied.unresolved}) == 2
    assert counts(app_conn, entity) == (2, 2)


def test_running_a_line_again_books_nothing_new(
    database: Database, entity: str, chart: dict[str, str], app_conn: psycopg.Connection[Any]
) -> None:
    """A statement sent twice must not book twice, and a retry is not a new decision."""
    approve(
        database,
        entity_id=entity,
        principal=OWNER,
        label="ACME to insurance",
        precedence=10,
        account_id=chart["Insurance"],
        predicates=payee_rule(),
    )
    line = acme(chart, "-240.00", ref="line-1")
    first = apply_rules(
        database, entity_id=entity, principal=OWNER, request_id="run-1", candidates=[line]
    )
    again = apply_rules(
        database, entity_id=entity, principal=OWNER, request_id="run-2", candidates=[line]
    )

    assert again.booked[0].transaction_id == first.booked[0].transaction_id
    assert counts(app_conn, entity) == (1, 1)


def test_an_unanswered_line_asked_again_is_still_one_question(
    database: Database, entity: str, chart: dict[str, str], app_conn: psycopg.Connection[Any]
) -> None:
    """`BKP-12`'s question is asked once per line, however often the statement is run."""
    line = acme(chart, "-240.00", ref="line-1")
    for run in ("run-1", "run-2"):
        apply_rules(
            database, entity_id=entity, principal=OWNER, request_id=run, candidates=[line]
        )

    assert counts(app_conn, entity) == (1, 1)


def test_an_answer_supersedes_the_question_it_answers(
    database: Database, entity: str, chart: dict[str, str], app_conn: psycopg.Connection[Any]
) -> None:
    """`BKP-12` answered by `BKP-09`: the operator is asked, approves a rule, and the line is
    run again. The answer is a decision of its own that names the question, since nothing
    here is updated."""
    line = acme(chart, "-240.00", ref="line-1")
    asked = apply_rules(
        database, entity_id=entity, principal=OWNER, request_id="run-1", candidates=[line]
    )
    approve(
        database,
        entity_id=entity,
        principal=OWNER,
        label="ACME to insurance",
        precedence=10,
        account_id=chart["Insurance"],
        predicates=payee_rule(),
    )
    answered = apply_rules(
        database, entity_id=entity, principal=OWNER, request_id="run-2", candidates=[line]
    )

    assert [b.rule_label for b in answered.booked] == ["ACME to insurance"]
    with app_conn.cursor() as cur:
        cur.execute("SELECT set_config('cfokit.entity_id', %s, false)", (entity,))
        cur.execute(
            "SELECT supersedes_decision_id FROM assignment_decision WHERE id = %s",
            (answered.booked[0].decision_id,),
        )
        supersedes = (cur.fetchone() or [None])[0]
    assert str(supersedes) == asked.unresolved[0].decision_id


def test_a_coded_line_is_not_recoded_when_its_rule_changes(
    database: Database, entity: str, chart: dict[str, str], app_conn: psycopg.Connection[Any]
) -> None:
    """`BKP-11`: a rule change affects future assignments only. Running an already-coded line
    again reports how it was coded rather than coding it a second way."""
    version = approve(
        database,
        entity_id=entity,
        principal=OWNER,
        label="ACME to insurance",
        precedence=10,
        account_id=chart["Insurance"],
        predicates=payee_rule(),
    )
    line = acme(chart, "-240.00", ref="line-1")
    first = apply_rules(
        database, entity_id=entity, principal=OWNER, request_id="run-1", candidates=[line]
    )
    with app_conn.cursor() as cur:
        cur.execute("SELECT set_config('cfokit.entity_id', %s, false)", (entity,))
        cur.execute("SELECT rule_id FROM assignment_rule_version WHERE id = %s", (version,))
        rule_id = str((cur.fetchone() or [""])[0])
    approve(
        database,
        entity_id=entity,
        principal=OWNER,
        label="ACME now prepaid",
        precedence=10,
        account_id=chart["Prepaid"],
        predicates=payee_rule(),
        rule_id=rule_id,
    )

    again = apply_rules(
        database, entity_id=entity, principal=OWNER, request_id="run-2", candidates=[line]
    )

    assert again.booked[0].transaction_id == first.booked[0].transaction_id
    assert again.booked[0].rule_label == "ACME to insurance"
    assert counts(app_conn, entity) == (1, 1)


# --- An uploaded line is drafted, whatever resolves it (PLT-23, ADR-0047) -----------------


def test_an_uploaded_line_a_rule_resolves_is_a_complete_draft(
    database: Database, entity: str, chart: dict[str, str], app_conn: psycopg.Connection[Any]
) -> None:
    """Its figures were read out of a document the organization did not author, in the session
    now asking to post them. The rule decides where it belongs — both legs are there — and a
    person decides that it happened."""
    approve(
        database,
        entity_id=entity,
        principal=OWNER,
        label="ACME to insurance",
        precedence=10,
        account_id=chart["Insurance"],
        predicates=payee_rule(),
    )
    applied = apply_rules(
        database,
        entity_id=entity,
        principal=OWNER,
        request_id="run-1",
        candidates=[acme(chart, "-240.00", kind=SourceKind.UPLOAD)],
    )

    assert [b.rule_label for b in applied.booked] == ["ACME to insurance"]
    with app_conn.cursor() as cur:
        cur.execute("SELECT set_config('cfokit.entity_id', %s, false)", (entity,))
        cur.execute(
            "SELECT status, (SELECT count(*) FROM posting p WHERE p.transaction_id = t.id)"
            "  FROM ledger_transaction t WHERE t.entity_id = %s",
            (entity,),
        )
        status, legs = cur.fetchone() or (None, None)
    assert status == "draft"
    assert legs == 2


def test_replay_needs_a_grant_in_the_entity(
    database: Database, entity: str, chart: dict[str, str]
) -> None:
    """`IAM-01`: a principal holding no role "can do nothing with it", and reading which
    decisions an entity took — and which diverged — is something."""
    arrange(database, entity, chart)
    stranger = Principal(id="user:stranger", actor_class=ActorClass.PERSON)

    with pytest.raises(NotAuthorized):
        replay(database, entity_id=entity, principal=stranger)


def test_an_owner_of_other_books_cannot_replay_these(
    database: Database, entity: str, chart: dict[str, str]
) -> None:
    """The case the check exists for: authenticated, and an owner — of somebody else's
    entity. Owning one set of books confers nothing in another (`LED-13`)."""
    arrange(database, entity, chart)
    elsewhere = Principal(id="user:elsewhere", actor_class=ActorClass.PERSON)
    create_entity(
        database,
        principal=elsewhere,
        request_id="replay-test",
        slug=f"elsewhere-{uuid.uuid4().hex[:12]}",
        name="Other books",
        accounting_basis="accrual",
        fiscal_year_end_month=12,
        fiscal_year_end_day=31,
        functional_currency="USD",
        time_zone="UTC",
    )

    with pytest.raises(NotAuthorized):
        replay(database, entity_id=entity, principal=elsewhere)


def test_proposing_needs_a_grant_in_the_entity(
    database: Database, entity: str, chart: dict[str, str]
) -> None:
    """A proposal names the live rules a candidate would contend with, which is these books'
    rule set — a read like any other (`IAM-01`)."""
    arrange(database, entity, chart)
    stranger = Principal(id="user:stranger", actor_class=ActorClass.PERSON)

    with pytest.raises(NotAuthorized):
        propose(
            database,
            entity_id=entity,
            principal=stranger,
            label="Probe",
            precedence=99,
            account_id=chart["Insurance"],
            predicates=payee_rule(),
            candidates=[acme(chart, "-1.00")],
        )


def test_a_stranger_running_a_coded_line_learns_nothing(
    database: Database, entity: str, chart: dict[str, str]
) -> None:
    """A line already coded is reported without reaching the write path, so the grant is
    checked before that report rather than left to the write it skips."""
    approve(
        database,
        entity_id=entity,
        principal=OWNER,
        label="ACME to insurance",
        precedence=10,
        account_id=chart["Insurance"],
        predicates=payee_rule(),
    )
    coded = acme(chart, "-240.00", ref="line-coded")
    apply_rules(
        database, entity_id=entity, principal=OWNER, request_id="run-1", candidates=[coded]
    )
    stranger = Principal(id="user:stranger", actor_class=ActorClass.PERSON)

    with pytest.raises(NotAuthorized):
        apply_rules(
            database,
            entity_id=entity,
            principal=stranger,
            request_id="run-2",
            candidates=[coded],
        )


# --- A line is matched to what the books hold before any rule codes it (ADR-0059) ---------
#
# Each expected value is ADR-0059's stated confirmation or a requirement's acceptance: an
# expected payment settles its obligation and books no income (`AR-13`, `LED-17`), an entry
# made ahead of the feed is not booked twice (`BKP-13`), a transfer leaves total income and
# total expense unchanged (`BKP-14`), equal counterparts are a question rather than a choice
# (`BKP-12`), and a leg is claimed once.

ISSUED = date(2026, 3, 2)
PAID = date(2026, 3, 10)


@pytest.fixture
def books(database: Database, owned_books: tuple[str, str, str]) -> dict[str, str]:
    """A bank and a savings account, receivables, revenue, and an expense to code to."""
    entity_id, cash, revenue = owned_books
    accounts = {"Bank": cash, "Revenue": revenue}
    for name, code, kind in (
        ("Savings", "1010", "asset"),
        ("Receivable", "1200", "asset"),
        ("Insurance", "6200", "expense"),
    ):
        accounts[name] = create_account(
            database,
            entity_id=entity_id,
            principal=OWNER,
            request_id="matching-test",
            code=code,
            name=name,
            account_type=kind,
        )
    return accounts


def by_hand(
    database: Database,
    entity: str,
    legs: tuple[tuple[str, str], ...],
    when: date,
    *,
    raises: str | None = None,
) -> str:
    """A transaction a person recorded, posted, the way anyone enters one."""
    return record_transaction(
        database,
        WriteContext(
            entity_id=entity,
            principal=OWNER,
            request_id=f"by-hand-{uuid.uuid4().hex[:8]}",
            idempotency_key=uuid.uuid4().hex,
        ),
        entry=Entry(
            transaction_date=when,
            postings=tuple(
                Posting(account, Decimal(amount), "USD") for account, amount in legs
            ),
            description="Entered by hand",
        ),
        post=True,
        raises_obligation=Decimal(raises) if raises is not None else None,
    ).transaction_id


def invoice(database: Database, entity: str, books: dict[str, str], amount: str) -> str:
    """An issued invoice: receivables debited, revenue credited, the obligation raised."""
    by_hand(
        database,
        entity,
        ((books["Receivable"], amount), (books["Revenue"], f"-{amount}")),
        ISSUED,
        raises=amount,
    )
    [owed] = outstanding_obligations(database, entity_id=entity, principal=OWNER)
    return owed.obligation_id


def arriving(
    books: dict[str, str],
    amount: str,
    *,
    ref: str,
    account: str = "Bank",
    on: date = PAID,
    payee: str = "Client A",
    kind: SourceKind = SourceKind.FEED,
) -> Candidate:
    return Candidate(
        payee=payee,
        amount=Decimal(amount),
        commodity="USD",
        source_account_id=books[account],
        transaction_date=on,
        source_kind=kind,
        source_ref=ref,
    )


def run(database: Database, entity: str, *lines: Candidate) -> Any:
    return apply_rules(
        database,
        entity_id=entity,
        principal=OWNER,
        request_id=f"run-{uuid.uuid4().hex[:8]}",
        candidates=list(lines),
    )


def posted_by_type(
    app_conn: psycopg.Connection[Any], entity: str, account_type: str
) -> Decimal:
    """What every posted posting on accounts of one type sums to."""
    with app_conn.cursor() as cur:
        cur.execute("SELECT set_config('cfokit.entity_id', %s, false)", (entity,))
        cur.execute(
            "SELECT COALESCE(SUM(p.amount), 0) FROM posting p"
            "  JOIN ledger_transaction t ON t.id = p.transaction_id"
            "  JOIN account a ON a.id = p.account_id"
            " WHERE p.entity_id = %s AND t.status = 'posted' AND a.type = %s",
            (entity, account_type),
        )
        return Decimal((cur.fetchone() or [0])[0])


def rows(app_conn: psycopg.Connection[Any], entity: str, sql: str, *args: Any) -> list[Any]:
    with app_conn.cursor() as cur:
        cur.execute("SELECT set_config('cfokit.entity_id', %s, false)", (entity,))
        cur.execute(sql, args)
        return cur.fetchall()


def client_receipts(database: Database, entity: str, books: dict[str, str]) -> None:
    """The rule that would book a client's deposit as income — and so book it twice."""
    approve(
        database,
        entity_id=entity,
        principal=OWNER,
        label="Client receipts are revenue",
        precedence=10,
        account_id=books["Revenue"],
        predicates=(Predicate(1, Field.PAYEE, Operator.CONTAINS, "client"),),
    )


def test_a_deposit_equal_to_an_open_obligation_settles_it_and_books_no_income(
    database: Database, entity: str, books: dict[str, str], app_conn: psycopg.Connection[Any]
) -> None:
    """`AR-13`: the deposit is applied to the invoice it settles, by a stored link (ADR-0037
    § 3). A rule that would code it to revenue is not consulted, so revenue is the invoice's
    1,200.00 credit and nothing more."""
    obligation = invoice(database, entity, books, "1200.00")
    client_receipts(database, entity, books)

    applied = run(database, entity, arriving(books, "1200.00", ref="deposit-1"))

    [booked] = applied.booked
    assert booked.outcome is Outcome.MATCHED
    assert booked.rule_label is None
    assert [(c.kind, c.id) for c in booked.counterparts] == [
        (CounterpartKind.OBLIGATION, obligation)
    ]
    assert outstanding_obligations(database, entity_id=entity, principal=OWNER) == ()
    [settlement] = obligation_detail(
        database, entity_id=entity, principal=OWNER, obligation_id=obligation
    ).settlements
    assert settlement.transaction_id == booked.transaction_id
    assert posted_by_type(app_conn, entity, "income") == Decimal("-1200.00")
    # Posted, against the account that carries the obligation, and attributed to no rule.
    assert sorted(
        (str(account), Decimal(amount), assigned)
        for account, amount, assigned in rows(
            app_conn,
            entity,
            "SELECT account_id, amount, assigned_by_rule_version_id FROM posting"
            " WHERE transaction_id = %s",
            booked.transaction_id,
        )
    ) == sorted(
        [(books["Bank"], Decimal("1200"), None), (books["Receivable"], Decimal("-1200"), None)]
    )
    assert rows(
        app_conn,
        entity,
        "SELECT status, actor_class FROM ledger_transaction WHERE id = %s",
        booked.transaction_id,
    ) == [("posted", "rule")]


def test_a_line_equal_to_a_hand_entered_entry_writes_no_transaction(
    database: Database, entity: str, books: dict[str, str], app_conn: psycopg.Connection[Any]
) -> None:
    """`BKP-13`: matched to the record "rather than creating a duplicate". The entry is not
    altered — not even where it says it came from — and the decision is the link."""
    entry = by_hand(
        database, entity, ((books["Insurance"], "240.00"), (books["Bank"], "-240.00")), ISSUED
    )
    approve_insurance(database, entity, books)

    applied = run(database, entity, arriving(books, "-240.00", ref="card-1", payee="ACME"))

    [booked] = applied.booked
    assert booked.outcome is Outcome.MATCHED
    assert booked.transaction_id == entry
    assert counts(app_conn, entity) == (1, 1)
    assert rows(
        app_conn, entity, "SELECT derived_from FROM ledger_transaction WHERE id = %s", entry
    ) == [(None,)]


def approve_insurance(database: Database, entity: str, books: dict[str, str]) -> None:
    approve(
        database,
        entity_id=entity,
        principal=OWNER,
        label="ACME to insurance",
        precedence=20,
        account_id=books["Insurance"],
        predicates=payee_rule(),
    )


def test_two_mirrored_feed_lines_are_one_transfer(
    database: Database,
    entity: str,
    books: dict[str, str],
    app_conn: psycopg.Connection[Any],
    owner_conn: psycopg.Connection[Any],
) -> None:
    """**`BKP-14`'s acceptance, executed**: a transfer arriving as two lines is one transfer,
    and total income and total expense are unchanged. The first line's question — nothing
    explained it when it arrived — is closed by the second arriving."""
    income, expense = (
        posted_by_type(app_conn, entity, "income"),
        posted_by_type(app_conn, entity, "expense"),
    )

    first = run(database, entity, arriving(books, "-500.00", ref="out-1", payee="To savings"))
    assert [b.outcome for b in first.unresolved] == [Outcome.UNMATCHED]
    second = run(
        database,
        entity,
        arriving(
            books, "500.00", ref="in-1", account="Savings", on=date(2026, 3, 12), payee="From"
        ),
    )

    [booked] = second.booked
    assert booked.outcome is Outcome.MATCHED
    assert [c.kind for c in booked.counterparts] == [CounterpartKind.TRANSFER]
    assert posted_by_type(app_conn, entity, "income") == income
    assert posted_by_type(app_conn, entity, "expense") == expense
    assert sorted(
        (str(account), Decimal(amount))
        for account, amount in rows(
            app_conn,
            entity,
            "SELECT account_id, amount FROM posting WHERE transaction_id = %s",
            booked.transaction_id,
        )
    ) == sorted([(books["Bank"], Decimal("-500")), (books["Savings"], Decimal("500"))])
    # Both lines now name the one transfer, and the first line's question is answered.
    assert sorted(
        str(ref)
        for (ref,) in rows(
            app_conn,
            entity,
            "SELECT candidate_source_ref FROM assignment_decision"
            " WHERE transaction_id = %s AND outcome = 'matched'",
            booked.transaction_id,
        )
    ) == ["in-1", "out-1"]
    assert open_questions(database, entity_id=entity, principal=OWNER) == ()
    assert _open_notifications(owner_conn, entity) == 0


def _open_notifications(owner_conn: psycopg.Connection[Any], entity: str) -> int:
    with owner_conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM notification n WHERE n.entity_id = %s AND NOT EXISTS"
            " (SELECT 1 FROM notification_closing c WHERE c.notification_id = n.id)",
            (entity,),
        )
        return int((cur.fetchone() or [0])[0])


def test_two_equal_counterparts_raise_one_question_per_holder_and_post_nothing(
    database: Database,
    entity: str,
    books: dict[str, str],
    app_conn: psycopg.Connection[Any],
    owner_conn: psycopg.Connection[Any],
) -> None:
    """`BKP-12` and ADR-0059 § 4: no order among equals is stated, so the line is asked about,
    with every candidate — and a rule that would code it is not reached."""
    grant_role(
        database,
        entity_id=entity,
        principal=OWNER,
        request_id="matching-test",
        to_principal="user:partner",
        role="owner",
    )
    one = by_hand(
        database, entity, ((books["Insurance"], "240.00"), (books["Bank"], "-240.00")), ISSUED
    )
    two = by_hand(
        database, entity, ((books["Insurance"], "240.00"), (books["Bank"], "-240.00")), PAID
    )
    approve_insurance(database, entity, books)
    posted = (
        "SELECT count(*) FROM ledger_transaction WHERE entity_id = %s AND status = 'posted'"
    )
    posted_before = rows(app_conn, entity, posted, entity)

    applied = run(database, entity, arriving(books, "-240.00", ref="card-1", payee="ACME"))

    [asked] = applied.unresolved
    assert asked.outcome is Outcome.AMBIGUOUS
    assert {c.id for c in asked.counterparts} == {one, two}
    assert rows(app_conn, entity, posted, entity) == posted_before
    with owner_conn.cursor() as cur:
        cur.execute(
            "SELECT recipient, subject_ref, notification_class FROM notification"
            " WHERE entity_id = %s ORDER BY recipient",
            (entity,),
        )
        raised = cur.fetchall()
    assert raised == [
        ("user:geoff", "card-1", "unresolved_transaction"),
        ("user:partner", "card-1", "unresolved_transaction"),
    ]
    [question] = open_questions(database, entity_id=entity, principal=OWNER)
    assert question.outcome is Outcome.AMBIGUOUS
    assert {c.id for c in question.counterparts} == {one, two}


def test_a_second_line_cannot_claim_a_claimed_leg(
    database: Database,
    entity: str,
    books: dict[str, str],
    owner_conn: psycopg.Connection[Any],
) -> None:
    """ADR-0059 § 1: a leg is claimed by at most one line. Two coffees on one statement are two
    lines; the first finds the entry, and the second does not find it again."""
    entry = by_hand(
        database, entity, ((books["Insurance"], "4.50"), (books["Bank"], "-4.50")), ISSUED
    )

    first = run(database, entity, arriving(books, "-4.50", ref="coffee-1"))
    second = run(database, entity, arriving(books, "-4.50", ref="coffee-2"))

    assert first.booked[0].transaction_id == entry
    assert [b.outcome for b in second.unresolved] == [Outcome.UNMATCHED]

    # And the schema's half: a second decision naming the same leg is refused outright.
    with owner_conn.cursor() as cur, pytest.raises(psycopg.errors.UniqueViolation):
        cur.execute(
            "INSERT INTO assignment_decision"
            " (entity_id, transaction_id, outcome, match_count, rule_set_digest,"
            "  counterpart_digest, evaluator_version, candidate_payee, candidate_payee_raw,"
            "  candidate_amount, candidate_commodity, candidate_source_account_id,"
            "  candidate_transaction_date, candidate_source_kind, candidate_source_ref)"
            " VALUES (%s, %s, 'matched', 0, %s, %s, 2, 'x', 'x', -4.50, 'USD', %s, %s,"
            "         'feed', 'coffee-3')",
            (entity, entry, "0" * 64, "0" * 64, books["Bank"], PAID),
        )


def test_an_entry_outside_the_window_is_not_found(
    database: Database, entity: str, books: dict[str, str]
) -> None:
    """Thirty-one days before the line is outside § 2's thirty: the line is asked about."""
    by_hand(
        database,
        entity,
        ((books["Insurance"], "240.00"), (books["Bank"], "-240.00")),
        date(2026, 2, 7),  # March 10 less 31 days
    )

    applied = run(database, entity, arriving(books, "-240.00", ref="card-1", payee="ACME"))

    assert [b.outcome for b in applied.unresolved] == [Outcome.UNMATCHED]


def test_replay_re_decides_matched_lines(
    database: Database, entity: str, books: dict[str, str]
) -> None:
    """`BKP-06` over the search as well as the rules: every match reproduces."""
    invoice(database, entity, books, "1200.00")
    by_hand(
        database, entity, ((books["Insurance"], "240.00"), (books["Bank"], "-240.00")), PAID
    )
    client_receipts(database, entity, books)
    run(
        database,
        entity,
        arriving(books, "1200.00", ref="deposit-1"),
        arriving(books, "-240.00", ref="card-1", payee="ACME"),
        arriving(books, "-500.00", ref="out-1", payee="To savings"),
        arriving(books, "500.00", ref="in-1", account="Savings", payee="From checking"),
        arriving(books, "75.00", ref="client-2"),
    )

    report = replay(database, entity_id=entity, principal=OWNER)

    # out-1 asked, then answered by in-1: six decisions for five lines.
    assert report.total == 6
    assert report.compared == report.reproduced == 6
    assert (report.books_changed, report.rule_set_changed, report.chosen) == (0, 0, 0)
    assert report.diverged == ()


def test_replay_reports_a_divergence_when_a_counterpart_is_hidden_from_the_search(
    database: Database,
    entity: str,
    books: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The failure ADR-0059 exists for, made visible: if the search does not see a
    counterpart that sat in the books, the line it explained no longer reproduces."""
    obligation = invoice(database, entity, books, "1200.00")
    applied = run(database, entity, arriving(books, "1200.00", ref="deposit-1"))

    hidden = monkeypatch_pool(monkeypatch, obligation)
    report = replay(database, entity_id=entity, principal=OWNER)

    assert hidden == [obligation]
    assert report.diverged == (applied.booked[0].decision_id,)


def test_replay_catches_a_line_a_rule_booked_while_a_counterpart_sat_in_the_books(
    database: Database,
    entity: str,
    books: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The other direction: a run whose search missed the obligation let the rule book the
    deposit as revenue a second time. Replay, seeing the books as they stood, diverges."""
    obligation = invoice(database, entity, books, "1200.00")
    client_receipts(database, entity, books)
    with monkeypatch.context() as patched:
        monkeypatch_pool(patched, obligation)
        applied = run(database, entity, arriving(books, "1200.00", ref="deposit-1"))
    assert [b.outcome for b in applied.booked] == [Outcome.ASSIGNED]

    report = replay(database, entity_id=entity, principal=OWNER)

    assert report.diverged == (applied.booked[0].decision_id,)


def monkeypatch_pool(patched: pytest.MonkeyPatch, obligation: str) -> list[str]:
    """Hide one obligation from what the search sees, and nothing else. Returns a list that
    records each time it was hidden, so a test can tell the patch was reached."""
    from cfokit.assignment import service

    real = service.counterpart_pool
    hidden: list[str] = []

    def without(*args: Any, **kwargs: Any) -> tuple[Counterpart, ...]:
        pool = real(*args, **kwargs)
        kept = tuple(c for c in pool if c.id != obligation)
        if len(kept) != len(pool):
            hidden.append(obligation)
        return kept

    patched.setattr(service, "counterpart_pool", without)
    return hidden


# --- A person answers (ADR-0059 § 4, ADR-0042) --------------------------------------------


def answering(entity: str, who: Principal = OWNER) -> WriteContext:
    return WriteContext(
        entity_id=entity,
        principal=who,
        request_id=f"answer-{uuid.uuid4().hex[:8]}",
        idempotency_key=uuid.uuid4().hex,
    )


def ambiguous_card(database: Database, entity: str, books: dict[str, str]) -> tuple[str, str]:
    one = by_hand(
        database, entity, ((books["Insurance"], "240.00"), (books["Bank"], "-240.00")), ISSUED
    )
    two = by_hand(
        database, entity, ((books["Insurance"], "240.00"), (books["Bank"], "-240.00")), PAID
    )
    run(database, entity, arriving(books, "-240.00", ref="card-1", payee="ACME"))
    return one, two


def test_a_person_names_one_of_two_counterparts(
    database: Database,
    entity: str,
    books: dict[str, str],
    owner_conn: psycopg.Connection[Any],
) -> None:
    """The person's choice closes the question, and replay counts it rather than re-deciding
    it: a choice is not a function of the inputs (§ 5)."""
    one, _ = ambiguous_card(database, entity, books)

    answered = answer_question(
        database,
        answering(entity),
        source_ref="card-1",
        counterpart=(CounterpartKind.TRANSACTION, one),
    )

    assert answered.outcome is Outcome.MATCHED
    assert answered.transaction_id == one
    assert open_questions(database, entity_id=entity, principal=OWNER) == ()
    assert _open_notifications(owner_conn, entity) == 0
    report = replay(database, entity_id=entity, principal=OWNER)
    assert (report.chosen, report.reproduced, report.diverged) == (1, 1, ())


def test_a_person_answers_none_and_the_rules_decide(
    database: Database, entity: str, books: dict[str, str], app_conn: psycopg.Connection[Any]
) -> None:
    """A third charge of the same amount: neither entry. The rules code it, posted, and the
    line is not asked about again."""
    ambiguous_card(database, entity, books)
    approve_insurance(database, entity, books)

    answered = answer_question(
        database, answering(entity), source_ref="card-1", counterpart=None
    )

    assert answered.outcome is Outcome.ASSIGNED
    assert rows(
        app_conn,
        entity,
        "SELECT status FROM ledger_transaction WHERE id = %s",
        answered.transaction_id,
    ) == [("posted",)]
    again = run(database, entity, arriving(books, "-240.00", ref="card-1", payee="ACME"))
    assert [b.decision_id for b in again.booked] == [answered.decision_id]


def test_a_person_answering_none_with_no_rule_leaves_one_question(
    database: Database, entity: str, books: dict[str, str], owner_conn: psycopg.Connection[Any]
) -> None:
    ambiguous_card(database, entity, books)

    answered = answer_question(
        database, answering(entity), source_ref="card-1", counterpart=None
    )

    assert answered.outcome is Outcome.UNMATCHED
    [question] = open_questions(database, entity_id=entity, principal=OWNER)
    assert (question.outcome, question.counterparts) == (Outcome.UNMATCHED, ())
    assert _open_notifications(owner_conn, entity) == 1
    # Run again, it is still that one question: the search is not run for it again.
    again = run(database, entity, arriving(books, "-240.00", ref="card-1", payee="ACME"))
    assert [b.decision_id for b in again.unresolved] == [answered.decision_id]


def test_a_check_that_cleared_late_is_answered_by_choosing_the_entry(
    database: Database, entity: str, books: dict[str, str]
) -> None:
    """§ 4: held to the facts, not the windows. Forty-two days is outside the search's 30."""
    check = by_hand(
        database,
        entity,
        ((books["Insurance"], "240.00"), (books["Bank"], "-240.00")),
        date(2026, 1, 27),
    )
    run(database, entity, arriving(books, "-240.00", ref="check-1012", payee="Check 1012"))

    answered = answer_question(
        database,
        answering(entity),
        source_ref="check-1012",
        counterpart=(CounterpartKind.TRANSACTION, check),
    )

    assert (answered.outcome, answered.transaction_id) == (Outcome.MATCHED, check)


def test_a_record_that_is_not_a_counterpart_is_refused(
    database: Database, entity: str, books: dict[str, str]
) -> None:
    """A different amount is not the line, whoever says so."""
    other = by_hand(
        database, entity, ((books["Insurance"], "250.00"), (books["Bank"], "-250.00")), PAID
    )
    run(database, entity, arriving(books, "-240.00", ref="card-1", payee="ACME"))

    with pytest.raises(NotACounterpart):
        answer_question(
            database,
            answering(entity),
            source_ref="card-1",
            counterpart=(CounterpartKind.TRANSACTION, other),
        )


def test_none_is_not_an_answer_to_a_line_with_no_candidates(
    database: Database, entity: str, books: dict[str, str]
) -> None:
    run(database, entity, arriving(books, "-240.00", ref="card-1", payee="ACME"))

    with pytest.raises(NothingToDecline):
        answer_question(database, answering(entity), source_ref="card-1", counterpart=None)


def test_an_agent_cannot_answer_for_the_person(
    database: Database, entity: str, books: dict[str, str]
) -> None:
    """ADR-0042: the person's own act, whatever the agent's grants."""
    one, _ = ambiguous_card(database, entity, books)
    agent = Principal(id="skill:bookkeeper", actor_class=ActorClass.AGENT, acting_for=OWNER.id)

    with pytest.raises(NotAPerson):
        answer_question(
            database,
            answering(entity, agent),
            source_ref="card-1",
            counterpart=(CounterpartKind.TRANSACTION, one),
        )


def test_confirming_a_proposed_payment_settles_it_in_one_commit(
    database: Database,
    entity: str,
    books: dict[str, str],
    owner_conn: psycopg.Connection[Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The settling transaction, its settlement and the decision land together or not at all:
    a failure after the entry is written leaves the obligation open and nothing posted."""
    obligation = invoice(database, entity, books, "1200.00")
    [asked] = run(
        database, entity, arriving(books, "1200.00", ref="upload-1", kind=SourceKind.UPLOAD)
    ).unresolved
    assert asked.outcome is Outcome.PROPOSED
    before = persisted(owner_conn, entity)

    def interrupted(*_: object, **__: object) -> None:
        raise Interrupted

    with monkeypatch.context() as patched:
        patched.setattr("cfokit.assignment.service.answer", interrupted)
        with pytest.raises(Interrupted):
            answer_question(
                database,
                answering(entity),
                source_ref="upload-1",
                counterpart=(CounterpartKind.OBLIGATION, obligation),
            )

    assert persisted(owner_conn, entity) == before
    [still] = outstanding_obligations(database, entity_id=entity, principal=OWNER)
    assert still.outstanding == Decimal("1200")

    answered = answer_question(
        database,
        answering(entity),
        source_ref="upload-1",
        counterpart=(CounterpartKind.OBLIGATION, obligation),
    )

    assert answered.outcome is Outcome.MATCHED
    assert outstanding_obligations(database, entity_id=entity, principal=OWNER) == ()
