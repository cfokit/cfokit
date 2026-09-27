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
    """A decision as it was recorded, with the facts it was taken on."""

    id: str
    decided_at: datetime
    outcome: Outcome
    winner_id: str | None
    resolved_by: ResolvedBy | None
    rule_set_digest: str
    evaluator_version: int
    candidate: Candidate


__all__ = [
    "insert_decision",
    "insert_rule_version",
    "load_decisions",
    "load_versions",
    "next_version",
    "precedence_taken",
    "rule_for_posting",
]


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
    projection no constraint can express — writes for an entity serialise on its advisory
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
    candidate: Candidate,
    fingerprint: str,
    outcome: Outcome,
    winner_id: str | None,
    resolved_by: ResolvedBy | None,
    matches: Iterable[Match],
    rule_set_digest: str,
    evaluator_version: int,
) -> str:
    """Record what was decided and the contest behind it, in the caller's transaction.

    Written for an unmatched candidate too. `BKP-12` forbids parking one in a holding
    account, and a decision saying "nothing matched" against a one-legged draft is the
    honest record of a question rather than the absence of one.
    """
    ranked = list(matches)
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO assignment_decision"
            " (entity_id, transaction_id, outcome, winning_rule_version_id, resolved_by,"
            "  match_count, rule_set_digest, evaluator_version, candidate_payee,"
            "  candidate_payee_raw, candidate_description, candidate_amount,"
            "  candidate_commodity, candidate_source_account_id, candidate_transaction_date,"
            "  candidate_source_kind, candidate_fingerprint)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
            " RETURNING id",
            (
                entity_id,
                transaction_id,
                str(outcome),
                winner_id,
                str(resolved_by) if resolved_by else None,
                len(ranked),
                rule_set_digest,
                evaluator_version,
                candidate.normalised_payee,
                candidate.payee,
                candidate.description,
                candidate.amount,
                candidate.commodity,
                candidate.source_account_id,
                candidate.transaction_date,
                str(candidate.source_kind),
                fingerprint,
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
    return decision_id


def load_decisions(
    conn: psycopg.Connection[Any], *, entity_id: str
) -> tuple[StoredDecision, ...]:
    """Every decision for an entity, oldest first: what a replay walks.

    The candidate's facts come back as they were matched on, which is the point — a replay
    that reconstructed its inputs from the transaction it produced would be asserting that
    the code agrees with itself.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, decided_at, outcome, winning_rule_version_id, resolved_by,"
            "       rule_set_digest, evaluator_version, candidate_payee_raw,"
            "       candidate_description, candidate_amount, candidate_commodity,"
            "       candidate_source_account_id, candidate_transaction_date,"
            "       candidate_source_kind"
            "  FROM assignment_decision WHERE entity_id = %s ORDER BY decided_at, id",
            (entity_id,),
        )
        rows = cur.fetchall()

    return tuple(
        StoredDecision(
            id=str(row[0]),
            decided_at=row[1],
            outcome=Outcome(row[2]),
            winner_id=str(row[3]) if row[3] else None,
            resolved_by=ResolvedBy(row[4]) if row[4] else None,
            rule_set_digest=str(row[5]),
            evaluator_version=int(row[6]),
            candidate=Candidate(
                payee=row[7],
                description=row[8],
                amount=row[9],
                commodity=row[10],
                source_account_id=str(row[11]),
                transaction_date=row[12],
                source_kind=SourceKind(row[13]),
            ),
        )
        for row in rows
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
