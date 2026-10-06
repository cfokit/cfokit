"""SQL for rules and the decisions they produce. Hand-written, like the ledger's (ADR-0028).

**This module's own repository, not the ledger's.** ADR-0022 forbids the ledger from
depending on a module, and reaching into the ledger's `EntityWrite` for these tables would
have put rule SQL inside the ledger by another route. The connection comes from the ledger's
unit of work — the transaction and the entity scoping are shared, which is the whole point
of being in-process — and the statements are here.

**Seniority is computed here, not stored.** It is the earliest `effective_from` among a
rule's versions, so a column would only duplicate what the rows already say, and could
disagree with them after an edit.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

import psycopg

from cfokit.assignment import (
    Counterpart,
    CounterpartKind,
    Field,
    Match,
    Operator,
    Outcome,
    Predicate,
    ResolvedBy,
    RuleVersion,
    Status,
)
from cfokit.assignment.candidate import Candidate, SourceKind


@dataclass(frozen=True, slots=True)
class StoredDecision:
    """A decision as it was recorded, with the facts it was taken on and what it found."""

    id: str
    transaction_id: str
    decided_at: datetime
    outcome: Outcome
    winner_id: str | None
    winner_label: str | None
    resolved_by: ResolvedBy | None
    rule_set_digest: str
    counterpart_digest: str
    evaluator_version: int
    supersedes: str | None
    chosen_by: str | None
    decided_with: str | None
    candidate: Candidate
    counterparts: tuple[Counterpart, ...]

    @property
    def declines(self) -> bool:
        """Whether this is a person answering "none of these": the rules decided after it, and
        the search is not run for the line again (ADR-0059 § 4)."""
        return self.chosen_by is not None and self.outcome in (
            Outcome.ASSIGNED,
            Outcome.UNMATCHED,
        )


__all__ = [
    "StoredDecision",
    "claimed",
    "decision_for_transaction",
    "insert_decision",
    "insert_rule_version",
    "latest_decision",
    "line_declined",
    "load_decision",
    "load_decisions",
    "load_versions",
    "moment",
    "next_version",
    "open_questions",
    "open_side",
    "open_sides",
    "precedence_taken",
    "rule_for_posting",
]


def moment(conn: psycopg.Connection[Any]) -> datetime:
    """The instant a decision is taken at, read after the entity's lock is held.

    Not `now()`, which is when the database transaction began — possibly before another
    writer to this entity committed and released the lock. Everything visible here committed
    before this instant, so "the books as they stood at `decided_at`" names exactly what the
    search saw, and every decision's moment follows the last's (ADR-0011, ADR-0059 § 5).
    """
    with conn.cursor() as cur:
        cur.execute("SELECT clock_timestamp()")
        row = cur.fetchone()
    assert row is not None  # noqa: S101 - a SELECT of a function always yields a row
    at: datetime = row[0]
    return at


def load_versions(conn: psycopg.Connection[Any], *, entity_id: str) -> tuple[RuleVersion, ...]:
    """Every version and predicate for an entity, in one pass.

    All of them, not the ones in force: which those are is a question about a moment, and
    answering it in SQL would put the temporal rule in a second place — where it would drift
    from the one `rule_set_as_of` implements and replay depends on. Rules per entity are
    dozens, and the rows are append-only, so reading them whole is cheap and cacheable.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, rule_id, version, status, label, account_id, precedence,"
            "       effective_from"
            "  FROM assignment_rule_version WHERE entity_id = %s"
            " ORDER BY rule_id, version",
            (entity_id,),
        )
        rows = cur.fetchall()

        cur.execute(
            "SELECT rule_version_id, position, field, operator, value_text, value_numeric,"
            "       value_uuid"
            "  FROM assignment_predicate WHERE entity_id = %s"
            " ORDER BY rule_version_id, position",
            (entity_id,),
        )
        predicates: dict[str, list[Predicate]] = {}
        for version_id, position, field, operator, text, numeric, uuid_value in cur.fetchall():
            value: str | Decimal = (
                numeric if numeric is not None else str(uuid_value) if uuid_value else text
            )
            predicates.setdefault(str(version_id), []).append(
                Predicate(int(position), Field(field), Operator(operator), value)
            )

    seniority: dict[str, datetime] = {}
    for _, rule_id, _, _, _, _, _, effective_from in rows:
        held = seniority.get(str(rule_id))
        if held is None or effective_from < held:
            seniority[str(rule_id)] = effective_from

    return tuple(
        RuleVersion(
            id=str(row[0]),
            rule_id=str(row[1]),
            version=int(row[2]),
            status=Status(row[3]),
            label=row[4],
            account_id=str(row[5]) if row[5] else None,
            precedence=int(row[6]),
            effective_from=row[7],
            seniority=seniority[str(row[1])],
            predicates=tuple(predicates.get(str(row[0]), ())),
        )
        for row in rows
    )


def next_version(conn: psycopg.Connection[Any], *, rule_id: str) -> int:
    """The next version number for a rule. Read under the entity's advisory lock, so the
    UNIQUE on `(rule_id, version)` is a second line rather than the only one."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COALESCE(MAX(version), 0) + 1 FROM assignment_rule_version"
            " WHERE rule_id = %s",
            (rule_id,),
        )
        row = cur.fetchone()
    return int(row[0]) if row else 1


def precedence_taken(
    conn: psycopg.Connection[Any], *, entity_id: str, precedence: int, excluding: str | None
) -> str | None:
    """The label of a live rule already at this precedence, or `None`.

    `BKP-08`'s order is stated by the operator, so two live rules sharing a precedence means
    the order does not in fact state which wins. The service refuses it. This is not a
    `UNIQUE` constraint because the condition is over the versions *in force*, which is a
    projection no constraint can express — writes for an entity serialize on its advisory
    lock (ADR-0011), so checking here is race-free, and the engine's order is total anyway.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT label FROM ("
            "  SELECT DISTINCT ON (rule_id) rule_id, label, precedence, status"
            "    FROM assignment_rule_version WHERE entity_id = %s"
            "     AND (%s::uuid IS NULL OR rule_id <> %s::uuid)"
            "   ORDER BY rule_id, effective_from DESC, version DESC"
            ") live WHERE status = 'active' AND precedence = %s LIMIT 1",
            (entity_id, excluding, excluding, precedence),
        )
        row = cur.fetchone()
    return str(row[0]) if row else None


def insert_rule_version(
    conn: psycopg.Connection[Any],
    *,
    entity_id: str,
    rule_id: str,
    version: int,
    status: Status,
    label: str,
    account_id: str | None,
    precedence: int,
    approved_by: str,
    predicates: Sequence[Predicate],
) -> str:
    """Write a version and its predicates. Never an update: an edit is the next version."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO assignment_rule_version"
            " (entity_id, rule_id, version, status, label, account_id, precedence,"
            "  approved_by)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (
                entity_id,
                rule_id,
                version,
                str(status),
                label,
                account_id,
                precedence,
                approved_by,
            ),
        )
        row = cur.fetchone()
        assert row is not None  # noqa: S101 - RETURNING on a successful insert always yields
        version_id = str(row[0])

        cur.executemany(
            "INSERT INTO assignment_predicate"
            " (entity_id, rule_version_id, position, field, operator, value_text,"
            "  value_numeric, value_uuid)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            [
                (
                    entity_id,
                    version_id,
                    predicate.position,
                    str(predicate.field),
                    str(predicate.operator),
                    *_value_columns(predicate),
                )
                for predicate in predicates
            ],
        )
    return version_id


def _value_columns(predicate: Predicate) -> tuple[str | None, Decimal | None, str | None]:
    """Text, numeric, uuid — exactly one of which is set, as the CHECK in 0012 requires."""
    if isinstance(predicate.value, Decimal):
        return (None, predicate.value, None)
    if predicate.field is Field.SOURCE_ACCOUNT_ID:
        return (None, None, predicate.value)
    return (predicate.value, None, None)


def insert_decision(
    conn: psycopg.Connection[Any],
    *,
    entity_id: str,
    transaction_id: str,
    decided_at: datetime,
    candidate: Candidate,
    outcome: Outcome,
    winner_id: str | None,
    resolved_by: ResolvedBy | None,
    matches: Iterable[Match],
    rule_set_digest: str,
    counterparts: Sequence[Counterpart],
    counterpart_digest: str,
    evaluator_version: int,
    supersedes: str | None = None,
    chosen_by: str | None = None,
    decided_with: str | None = None,
) -> str:
    """Record what was decided, the contest behind it and what the search found, in the
    caller's transaction.

    Written for a question too. `BKP-12` forbids parking a line in a holding account, and a
    decision saying what was not settled against a one-legged draft is the honest record of a
    question rather than the absence of one.
    """
    ranked = list(matches)
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO assignment_decision"
            " (entity_id, transaction_id, decided_at, outcome, winning_rule_version_id,"
            "  resolved_by, match_count, rule_set_digest, counterpart_digest,"
            "  evaluator_version, candidate_payee, candidate_payee_raw, candidate_description,"
            "  candidate_amount, candidate_commodity, candidate_source_account_id,"
            "  candidate_transaction_date, candidate_source_kind, candidate_source_ref,"
            "  supersedes_decision_id, chosen_by, decided_with_decision_id)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,"
            "         %s, %s, %s, %s, %s)"
            " RETURNING id",
            (
                entity_id,
                transaction_id,
                decided_at,
                str(outcome),
                winner_id,
                str(resolved_by) if resolved_by else None,
                len(ranked),
                rule_set_digest,
                counterpart_digest,
                evaluator_version,
                candidate.normalized_payee,
                candidate.payee,
                candidate.description,
                candidate.amount,
                candidate.commodity,
                candidate.source_account_id,
                candidate.transaction_date,
                str(candidate.source_kind),
                candidate.source_ref,
                supersedes,
                chosen_by,
                decided_with,
            ),
        )
        row = cur.fetchone()
        assert row is not None  # noqa: S101 - RETURNING on a successful insert always yields
        decision_id = str(row[0])

        cur.executemany(
            "INSERT INTO assignment_decision_match"
            " (entity_id, decision_id, rule_version_id, rank, order_key)"
            " VALUES (%s, %s, %s, %s, %s)",
            [
                (entity_id, decision_id, match.rule.id, match.rank, match.order_key)
                for match in ranked
            ],
        )
        cur.executemany(
            "INSERT INTO assignment_decision_counterpart"
            " (entity_id, decision_id, position, kind, counterpart_id, account_id, amount,"
            "  commodity, counterpart_date)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            [
                (
                    entity_id,
                    decision_id,
                    position,
                    str(found.kind),
                    found.id,
                    found.account_id,
                    found.amount,
                    found.commodity,
                    found.on,
                )
                for position, found in enumerate(counterparts, start=1)
            ],
        )
    return decision_id


def decision_for_transaction(
    conn: psycopg.Connection[Any], *, entity_id: str, transaction_id: str
) -> str | None:
    """The decision that explains a transaction, if one was recorded.

    Asked when the ledger replays a write: the transaction exists, and the only question is
    whether its decision reached the database too, since the two commit separately.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM assignment_decision WHERE entity_id = %s AND transaction_id = %s"
            " ORDER BY decided_at LIMIT 1",
            (entity_id, transaction_id),
        )
        row = cur.fetchone()
    return str(row[0]) if row else None


# Every column a `StoredDecision` is built from, the rule label joined in. The candidate comes
# back as it arrived — the payee as the bank sent it rather than as matching normalized it,
# because that is what a person recognizes and what replay re-normalizes.
_DECISION = (
    "SELECT d.id, d.transaction_id, d.decided_at, d.outcome, d.winning_rule_version_id,"
    "       v.label, d.resolved_by, d.rule_set_digest, d.counterpart_digest,"
    "       d.evaluator_version, d.supersedes_decision_id, d.chosen_by,"
    "       d.decided_with_decision_id, d.candidate_payee_raw, d.candidate_description,"
    "       d.candidate_amount, d.candidate_commodity, d.candidate_source_account_id,"
    "       d.candidate_transaction_date, d.candidate_source_kind, d.candidate_source_ref"
    "  FROM assignment_decision d"
    "  LEFT JOIN assignment_rule_version v ON v.id = d.winning_rule_version_id"
)


def _decisions(
    conn: psycopg.Connection[Any], where: str, parameters: dict[str, Any]
) -> tuple[StoredDecision, ...]:
    """Decisions matching `where`, in the order it states, each with its counterparts."""
    with conn.cursor() as cur:
        cur.execute(f"{_DECISION} {where}", parameters)
        rows = cur.fetchall()
        cur.execute(
            "SELECT decision_id, kind, counterpart_id, account_id, amount, commodity,"
            "       counterpart_date"
            "  FROM assignment_decision_counterpart"
            " WHERE entity_id = %s AND decision_id = ANY(%s::uuid[])"
            " ORDER BY decision_id, position",
            (parameters["entity_id"], [str(row[0]) for row in rows]),
        )
        found: dict[str, list[Counterpart]] = {}
        for (
            decision_id,
            kind,
            counterpart_id,
            account_id,
            amount,
            commodity,
            on,
        ) in cur.fetchall():
            found.setdefault(str(decision_id), []).append(
                Counterpart(
                    kind=CounterpartKind(kind),
                    id=str(counterpart_id),
                    account_id=str(account_id),
                    amount=Decimal(amount),
                    commodity=str(commodity),
                    on=on,
                )
            )

    return tuple(
        StoredDecision(
            id=str(row[0]),
            transaction_id=str(row[1]),
            decided_at=row[2],
            outcome=Outcome(row[3]),
            winner_id=str(row[4]) if row[4] else None,
            winner_label=str(row[5]) if row[5] is not None else None,
            resolved_by=ResolvedBy(row[6]) if row[6] else None,
            rule_set_digest=str(row[7]),
            counterpart_digest=str(row[8]),
            evaluator_version=int(row[9]),
            supersedes=str(row[10]) if row[10] else None,
            chosen_by=str(row[11]) if row[11] is not None else None,
            decided_with=str(row[12]) if row[12] else None,
            candidate=Candidate(
                payee=row[13],
                description=row[14],
                amount=row[15],
                commodity=row[16],
                source_account_id=str(row[17]),
                transaction_date=row[18],
                source_kind=SourceKind(row[19]),
                source_ref=row[20],
            ),
            counterparts=tuple(found.get(str(row[0]), ())),
        )
        for row in rows
    )


def latest_decision(
    conn: psycopg.Connection[Any], *, entity_id: str, source_ref: str
) -> StoredDecision | None:
    """What most recently became of this source line, or `None` if nothing has.

    A line's decisions follow one another — a question, then the decision that answers it,
    which names it — so the latest is the line's state: an open question, or how it was
    settled. Once settled it stays settled: a rule changed since affects future assignments only
    (`BKP-11`), so a re-run reports this rather than deciding again.
    """
    found = _decisions(
        conn,
        "WHERE d.entity_id = %(entity_id)s AND d.candidate_source_ref = %(source_ref)s"
        " ORDER BY d.decided_at DESC, d.id DESC LIMIT 1",
        {"entity_id": entity_id, "source_ref": source_ref},
    )
    return found[0] if found else None


def load_decision(
    conn: psycopg.Connection[Any], *, entity_id: str, decision_id: str
) -> StoredDecision | None:
    found = _decisions(
        conn,
        "WHERE d.entity_id = %(entity_id)s AND d.id = %(decision_id)s::uuid",
        {"entity_id": entity_id, "decision_id": decision_id},
    )
    return found[0] if found else None


def line_declined(
    conn: psycopg.Connection[Any], *, entity_id: str, source_ref: str, before: datetime
) -> bool:
    """Whether a person answered this line "none of these" before `before`.

    After that the rules decide it and the search is not run for it again: the person has
    said what it is not, and asking them the same question on every run would be a question
    nobody can close (ADR-0059 § 4).
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT EXISTS (SELECT 1 FROM assignment_decision"
            "  WHERE entity_id = %s AND candidate_source_ref = %s AND decided_at < %s"
            "    AND chosen_by IS NOT NULL AND outcome IN ('assigned', 'unmatched'))",
            (entity_id, source_ref, before),
        )
        row = cur.fetchone()
    return bool(row and row[0])


def claimed(
    conn: psycopg.Connection[Any],
    *,
    entity_id: str,
    account_id: str,
    transaction_ids: Sequence[str],
    before: datetime,
) -> frozenset[str]:
    """Which of these transactions' legs on `account_id` a line had claimed before `before`.

    **A leg is claimed by at most one line** (ADR-0059 § 1), and a claimed one is never a
    counterpart: two coffees on one statement are two lines, and the second must not find the
    first one's entry. The unique index on a decision's transaction and its line's account is
    the schema's half of the same rule.
    """
    if not transaction_ids:
        return frozenset()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT transaction_id FROM assignment_decision"
            " WHERE entity_id = %s AND candidate_source_account_id = %s"
            "   AND transaction_id = ANY(%s::uuid[]) AND decided_at < %s",
            (entity_id, account_id, list(transaction_ids), before),
        )
        return frozenset(str(row[0]) for row in cur.fetchall())


# A line's question still open at a moment: a question decided before it, with no later
# decision for the same line decided before it either.
_OPEN_AT = (
    " d.outcome IN ('unmatched', 'ambiguous', 'proposed') AND d.decided_at < %(at)s"
    " AND NOT EXISTS (SELECT 1 FROM assignment_decision a"
    "                  WHERE a.entity_id = d.entity_id"
    "                    AND a.candidate_source_ref = d.candidate_source_ref"
    "                    AND a.decided_at > d.decided_at AND a.decided_at < %(at)s)"
)


def _side(decision: StoredDecision) -> Counterpart:
    candidate = decision.candidate
    return Counterpart(
        kind=CounterpartKind.TRANSFER,
        id=decision.id,
        account_id=candidate.source_account_id,
        amount=candidate.amount,
        commodity=candidate.commodity,
        on=candidate.transaction_date,
    )


def open_sides(
    conn: psycopg.Connection[Any], *, entity_id: str, candidate: Candidate, at: datetime
) -> tuple[Counterpart, ...]:
    """Other lines' questions open at `at`, on another account, for the negated amount.

    The other side of a transfer, as the books held it (ADR-0059 § 2): the one-legged draft of
    a line nothing has answered. The window is the engine's to apply.
    """
    found = _decisions(
        conn,
        "WHERE d.entity_id = %(entity_id)s AND"
        + _OPEN_AT
        + " AND d.candidate_source_account_id <> %(account_id)s::uuid"
        " AND d.candidate_commodity = %(commodity)s"
        " AND d.candidate_amount = %(negated)s"
        " AND d.candidate_source_ref <> %(source_ref)s"
        " ORDER BY d.decided_at, d.id",
        {
            "entity_id": entity_id,
            "at": at,
            "account_id": candidate.source_account_id,
            "commodity": candidate.commodity,
            "negated": -candidate.amount,
            "source_ref": candidate.source_ref,
        },
    )
    return tuple(_side(decision) for decision in found)


def open_side(
    conn: psycopg.Connection[Any],
    *,
    entity_id: str,
    decision_id: str,
    source_ref: str,
    at: datetime,
) -> Counterpart | None:
    """One line's question, as the other side of a transfer for the line `source_ref`, if it
    was still open at `at` and is another line's."""
    found = _decisions(
        conn,
        "WHERE d.entity_id = %(entity_id)s AND d.id = %(decision_id)s::uuid"
        " AND d.candidate_source_ref <> %(source_ref)s AND" + _OPEN_AT,
        {
            "entity_id": entity_id,
            "decision_id": decision_id,
            "source_ref": source_ref,
            "at": at,
        },
    )
    return _side(found[0]) if found else None


def load_decisions(
    conn: psycopg.Connection[Any], *, entity_id: str
) -> tuple[StoredDecision, ...]:
    """Every decision for an entity, oldest first: what a replay walks.

    The candidate's facts come back as they were matched on, which is the point — a replay
    that reconstructed its inputs from the transaction it produced would be asserting that
    the code agrees with itself.
    """
    return _decisions(
        conn,
        "WHERE d.entity_id = %(entity_id)s"
        " ORDER BY d.decided_at, d.decided_with_decision_id NULLS FIRST, d.id",
        {"entity_id": entity_id},
    )


def rule_for_posting(
    conn: psycopg.Connection[Any], *, entity_id: str, posting_id: str
) -> tuple[str, str, int] | None:
    """`RPT-08`: from a posting to the rule that assigned it, in one lookup.

    The acceptance says "without composing a query", and this is the query nobody composes.
    Returns the rule's own id, its label and its version — the version, because after an
    edit a pointer to the rule would show criteria that were not the ones applied.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT v.rule_id, v.label, v.version"
            "  FROM posting p JOIN assignment_rule_version v"
            "    ON v.id = p.assigned_by_rule_version_id"
            " WHERE p.entity_id = %s AND p.id = %s",
            (entity_id, posting_id),
        )
        row = cur.fetchone()
    return (str(row[0]), str(row[1]), int(row[2])) if row else None


def open_questions(
    conn: psycopg.Connection[Any], *, entity_id: str
) -> tuple[StoredDecision, ...]:
    """`BKP-12`'s worklist: every line whose latest decision is a question.

    Unmatched, ambiguous or proposed, each with what its search found, so the person sees the
    candidates or the proposal they are being asked about (ADR-0059 § 4). In the order the
    activity happened, so the person works through it as the account did.
    """
    return _decisions(
        conn,
        "WHERE d.entity_id = %(entity_id)s"
        "  AND d.outcome IN ('unmatched', 'ambiguous', 'proposed')"
        "  AND NOT EXISTS (SELECT 1 FROM assignment_decision a"
        "                   WHERE a.entity_id = d.entity_id"
        "                     AND a.candidate_source_ref = d.candidate_source_ref"
        "                     AND a.decided_at > d.decided_at)"
        " ORDER BY d.candidate_transaction_date, d.decided_at, d.id",
        {"entity_id": entity_id},
    )
