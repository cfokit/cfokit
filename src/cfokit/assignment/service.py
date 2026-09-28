"""Proposing a rule, approving it, and applying it (`BKP-06` to `BKP-12`).

Three calls, each doing one thing.

`propose` evaluates a rule that does not exist yet and **writes nothing**. It answers
`BKP-08`'s acceptance — "the operator can see which rule won and why *before* approving
either" — by showing what the rule would book and which live rules it would contend with.

`approve` is a person's act (`BKP-09`, ADR-0042) and writes the version. Editing a rule and
retiring one are the same call: both append a version, because both change the rule set from
a moment onward and one mechanism is fewer than two (`BKP-11`).

`apply` books what the approved rules resolve and returns what they do not. An unresolved
candidate produces no posting at all — `BKP-12` and `NFR-16` forbid a guess and forbid a
holding account, so the caller asks the operator.

**Nothing here stores a candidate.** The caller supplies them; a decision and the draft it
coded are what persist. Letting this module hold a queue of unassigned activity is how
`connectors` would have gone wrong (ADR-0031).
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from cfokit.assignment import (
    Outcome,
    Predicate,
    Resolution,
    RuleSet,
    RuleVersion,
    Status,
)
from cfokit.assignment.candidate import Candidate
from cfokit.assignment.engine import (
    EVALUATOR_VERSION,
    digest,
    evaluate,
    matches,
    rule_set_as_of,
)
from cfokit.assignment.errors import PrecedenceTaken, RuleNotFound
from cfokit.assignment.repository import (
    insert_decision,
    insert_rule_version,
    load_decisions,
    load_versions,
    next_version,
    precedence_taken,
)
from cfokit.ledger.engine import Entry, Posting
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.authorisation import authorise_own_act
from cfokit.ledger.service.principal import Principal
from cfokit.ledger.service.write import Assigned, WriteContext, record_transaction

__all__ = [
    "Applied",
    "Booked",
    "Proposal",
    "Replay",
    "apply_rules",
    "approve",
    "propose",
    "replay",
]


@dataclass(frozen=True, slots=True)
class Proposal:
    """What a rule would do, before it exists. Nothing has been written."""

    would_book: tuple[tuple[Candidate, str], ...]
    would_contend_with: tuple[tuple[Candidate, str], ...]
    unaffected: tuple[Candidate, ...]


@dataclass(frozen=True, slots=True)
class Booked:
    """One candidate, and what became of it."""

    candidate: Candidate
    transaction_id: str
    decision_id: str
    outcome: Outcome
    rule_label: str | None


@dataclass(frozen=True, slots=True)
class Applied:
    """What a run of `apply_rules` did. `unresolved` is the operator's worklist."""

    booked: tuple[Booked, ...]
    unresolved: tuple[Booked, ...]


def propose(
    database: Database,
    *,
    entity_id: str,
    principal: Principal,
    label: str,
    precedence: int,
    account_id: str,
    predicates: Sequence[Predicate],
    candidates: Sequence[Candidate],
) -> Proposal:
    """What this rule would do to these candidates, and what it would contend with.

    A read, so a delegated agent may do it: proposing is not the reserved act, approving is
    (ADR-0042). `would_contend_with` is the part `BKP-08`'s acceptance asks for — a
    candidate a live rule already claims, named, so the operator sees the conflict before
    creating it rather than discovering it in the books afterwards.
    """
    with database.entity_write(entity_id) as write:
        in_force = rule_set_as_of(load_versions(write.connection, entity_id=entity_id), _now())

    candidate_rule = _draft_version(label, precedence, account_id, predicates)
    books: list[tuple[Candidate, str]] = []
    contends: list[tuple[Candidate, str]] = []
    untouched: list[Candidate] = []

    for candidate in candidates:
        if not matches(candidate, candidate_rule):
            untouched.append(candidate)
            continue
        incumbent = evaluate(candidate, in_force)
        if incumbent.outcome is Outcome.ASSIGNED and incumbent.winner is not None:
            contends.append((candidate, incumbent.winner.label))
        else:
            books.append((candidate, account_id))

    return Proposal(
        would_book=tuple(books),
        would_contend_with=tuple(contends),
        unaffected=tuple(untouched),
    )


def approve(
    database: Database,
    *,
    entity_id: str,
    principal: Principal,
    label: str,
    precedence: int,
    account_id: str | None,
    predicates: Sequence[Predicate],
    rule_id: str | None = None,
    retire: bool = False,
) -> str:
    """Approve a rule, an edit to one, or its retirement. Returns the version's id.

    **A person's own act** (ADR-0042). `BKP-09` makes approval what licenses unattended
    booking thereafter, which is the same shape as reopening a period and importing books —
    the two acts the record already reserves. A delegated agent proposes; it does not
    approve.

    An edit passes the `rule_id` it supersedes. Nothing is updated: the prior version stays,
    unchanged, which is why `BKP-11`'s "existing postings are untouched" needs no code to
    enforce it.
    """
    with database.entity_write(entity_id) as write:
        authorise_own_act(write, principal)
        conn = write.connection

        if rule_id is None:
            rule_id = str(uuid.uuid4())
        elif not any(v.rule_id == rule_id for v in load_versions(conn, entity_id=entity_id)):
            raise RuleNotFound(f"no rule {rule_id} in this entity")

        if not retire:
            clash = precedence_taken(
                conn, entity_id=entity_id, precedence=precedence, excluding=rule_id
            )
            if clash is not None:
                raise PrecedenceTaken(
                    f"precedence {precedence} is held by {clash!r}; "
                    "two live rules at one precedence leave the order unstated (BKP-08)"
                )

        version_id = insert_rule_version(
            conn,
            entity_id=entity_id,
            rule_id=rule_id,
            version=next_version(conn, rule_id=rule_id),
            status=Status.RETIRED if retire else Status.ACTIVE,
            label=label,
            account_id=None if retire else account_id,
            precedence=precedence,
            approved_by=principal.id,
            predicates=() if retire else predicates,
        )
        write.record_audit(
            request_id=f"assignment-{uuid.uuid4().hex}",
            actor=principal.audit_actor,
            action="retire_rule" if retire else "approve_rule",
            subject_type="assignment_rule_version",
            subject_id=version_id,
            detail={"rule_id": rule_id, "precedence": precedence},
        )
    return version_id


def apply_rules(
    database: Database,
    *,
    entity_id: str,
    principal: Principal,
    request_id: str,
    candidates: Sequence[Candidate],
) -> Applied:
    """Book what the rules resolve. Return what they do not.

    Each candidate is its own write through the ledger's ordinary path, as an import's
    entries are: its own audit row, its own idempotency claim, its own advisory lock.

    A resolved candidate posts straight through, because the person already approved the
    pattern — `BKP-09`'s "an approved pattern is never asked about again". An unresolved one
    becomes a one-legged draft: it cannot be posted, because the engine requires two
    postings, so the ledger itself refuses to let an unanswered question reach the books.
    """
    booked: list[Booked] = []
    unresolved: list[Booked] = []

    for index, candidate in enumerate(candidates):
        with database.entity_write(entity_id) as write:
            in_force = rule_set_as_of(
                load_versions(write.connection, entity_id=entity_id), _now()
            )
        resolution = evaluate(candidate, in_force)
        outcome = _book(
            database,
            entity_id=entity_id,
            principal=principal,
            request_id=f"{request_id}-{index}",
            candidate=candidate,
            resolution=resolution,
            rule_set=in_force,
        )
        (booked if resolution.outcome is Outcome.ASSIGNED else unresolved).append(outcome)

    return Applied(booked=tuple(booked), unresolved=tuple(unresolved))


def _book(
    database: Database,
    *,
    entity_id: str,
    principal: Principal,
    request_id: str,
    candidate: Candidate,
    resolution: Resolution,
    rule_set: RuleSet,
) -> Booked:
    """One candidate's transaction and its decision, in one `COMMIT`.

    That they land together is the whole reason assignment is in-process rather than a
    separate component (ADR-0022 § 3): a decision naming a transaction that rolled back, or
    a coding no record explains, is the gap `RPT-08` exists to close.
    """
    assigned_leg = (
        Posting(
            account_id=resolution.winner.account_id or "",
            amount=-candidate.amount,
            commodity=candidate.commodity,
        )
        if resolution.winner is not None
        else None
    )
    postings = (
        Posting(
            account_id=candidate.source_account_id,
            amount=candidate.amount,
            commodity=candidate.commodity,
        ),
        *(() if assigned_leg is None else (assigned_leg,)),
    )

    written = record_transaction(
        database,
        WriteContext(
            entity_id=entity_id,
            principal=principal,
            request_id=request_id,
            idempotency_key=_key(candidate),
        ),
        entry=Entry(
            transaction_date=candidate.transaction_date,
            postings=postings,
            description=candidate.description or candidate.payee,
        ),
        post=resolution.outcome is Outcome.ASSIGNED,
        derived_from={"source_kind": str(candidate.source_kind), "payee": candidate.payee},
        assigned=(
            ()
            if resolution.winner is None
            # Index 1: the coded leg. The source leg is the account the candidate arrived
            # on, and no rule chose it.
            else (Assigned(posting_index=1, rule_version_id=resolution.winner.id),)
        ),
    )

    with database.entity_write(entity_id) as write:
        decision_id = insert_decision(
            write.connection,
            entity_id=entity_id,
            transaction_id=written.transaction_id,
            candidate=candidate,
            fingerprint=fingerprint(candidate),
            outcome=resolution.outcome,
            winner_id=resolution.winner.id if resolution.winner else None,
            resolved_by=resolution.resolved_by,
            matches=resolution.matches,
            rule_set_digest=digest(rule_set),
            evaluator_version=EVALUATOR_VERSION,
        )

    return Booked(
        candidate=candidate,
        transaction_id=written.transaction_id,
        decision_id=decision_id,
        outcome=resolution.outcome,
        rule_label=resolution.winner.label if resolution.winner else None,
    )


def fingerprint(candidate: Candidate) -> str:
    """A digest of the normalised facts.

    `BKP-13` is "match an incoming transaction to a record the books already hold", and the
    cheapest form of that question — the identical line arriving twice — is this compared
    with itself. Written now because the facts to hash are here now; nothing reads it until
    `BKP-13` lands.
    """
    parts = (
        candidate.normalised_payee,
        str(candidate.amount),
        candidate.commodity,
        candidate.source_account_id,
        candidate.transaction_date.isoformat(),
    )
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _key(candidate: Candidate) -> str:
    """Derived from the candidate, not minted, so a re-run of the same statement replays
    rather than double-booking — the device `imports` uses for the same reason."""
    return f"assignment:{fingerprint(candidate)[:48]}"


def _draft_version(
    label: str, precedence: int, account_id: str, predicates: Sequence[Predicate]
) -> RuleVersion:
    """A rule that does not exist, for `propose` to evaluate. Never written."""
    now = _now()
    return RuleVersion(
        id="",
        rule_id="",
        version=0,
        status=Status.ACTIVE,
        label=label,
        account_id=account_id,
        precedence=precedence,
        effective_from=now,
        seniority=now,
        predicates=tuple(predicates),
    )


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class Replay:
    """What a replay found. `BKP-06`'s acceptance is `reproduced == compared`.

    `rule_set_changed` and `semantics_changed` are the decisions a replay declined to judge
    rather than ones it failed. Without separating them the acceptance criterion would be
    unfalsifiable: a disagreement would have three possible causes and the test could not
    say which, so it would either fail constantly or assert nothing.
    """

    total: int
    compared: int
    reproduced: int
    rule_set_changed: int
    semantics_changed: int
    diverged: tuple[str, ...]


def replay(database: Database, *, entity_id: str) -> Replay:
    """Re-decide every recorded decision against the rule set that was in force.

    **`BKP-06`'s acceptance, executable**: "replaying an entity's full transaction history
    against an unchanged rule set reproduces every assignment identically".

    Writes nothing — a read and a pure function — so it is safe to run against real books.

    A decision whose stored digest no longer matches the reconstructed set is *not* a
    failure: `BKP-11` permits a rule to change, and the digest is exactly what tells the two
    apart. One taken under different evaluator semantics is not compared either, which is
    the honest limit of this check and the reason bumping `EVALUATOR_VERSION` needs a record.
    """
    with database.entity_write(entity_id) as write:
        versions = load_versions(write.connection, entity_id=entity_id)
        decisions = load_decisions(write.connection, entity_id=entity_id)

    compared = reproduced = rule_set_changed = semantics_changed = 0
    diverged: list[str] = []

    for decision in decisions:
        if decision.evaluator_version != EVALUATOR_VERSION:
            semantics_changed += 1
            continue

        in_force = rule_set_as_of(versions, decision.decided_at)
        if digest(in_force) != decision.rule_set_digest:
            rule_set_changed += 1
            continue

        compared += 1
        again = evaluate(decision.candidate, in_force)
        same = (
            again.outcome is decision.outcome
            and (again.winner.id if again.winner else None) == decision.winner_id
            and again.resolved_by is decision.resolved_by
        )
        if same:
            reproduced += 1
        else:
            diverged.append(decision.id)

    return Replay(
        total=len(decisions),
        compared=compared,
        reproduced=reproduced,
        rule_set_changed=rule_set_changed,
        semantics_changed=semantics_changed,
        diverged=tuple(diverged),
    )
