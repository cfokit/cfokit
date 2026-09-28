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

from cfokit.assignment import Field, Operator, Outcome, Predicate
from cfokit.assignment.candidate import Candidate, SourceKind
from cfokit.assignment.errors import PrecedenceTaken
from cfokit.assignment.service import apply_rules, approve, propose, replay
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.administration import create_account
from cfokit.ledger.service.principal import ActorClass, Principal

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


def acme(chart: dict[str, str], amount: str) -> Candidate:
    return Candidate(
        payee="ACME Insurance Co",
        amount=Decimal(amount),
        commodity="USD",
        source_account_id=chart["Bank"],
        transaction_date=WHEN,
        source_kind=SourceKind.UPLOAD,
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
    and a rule-assigned coding is the class ADR-0033 § 3 wants maximised because "an auditor
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

    report = replay(database, entity_id=entity)

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

    report = replay(database, entity_id=entity)

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
    replay(database, entity_id=entity)

    assert snapshot() == before
