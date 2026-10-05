"""Proposing a rule, approving it, applying it, and answering a line's question (`BKP-06` to
`BKP-14`).

`propose` evaluates a rule that does not exist yet and **writes nothing**. It answers
`BKP-08`'s acceptance — "the operator can see which rule won and why *before* approving
either" — by showing what the rule would book and which live rules it would contend with.

`approve` is a person's act (`BKP-09`, ADR-0042) and writes the version. Editing a rule and
retiring one are the same call: both append a version, because both change the rule set from
a moment onward and one mechanism is fewer than two (`BKP-11`).

`apply_rules` decides each line's fate. **The books are searched first** (ADR-0059): a line the
books already explain — a payment of an open obligation, an entry made ahead of the feed, the
other side of a transfer — is matched to that record and no rule is consulted. Two or more such
records and the line is a question. None, and the rules decide, as before: a resolved line is
booked and an unresolved one produces no posting at all — `BKP-12` and `NFR-16` forbid a guess
and forbid a holding account, so the caller asks the operator.

`answer_question` is a person naming what a line is: one counterpart, or none of those it was
asked about, after which the rules decide. Their own act (ADR-0042), as approving a rule is.

**An uploaded candidate is never posted by the session that read it.** Its figures were read out
of a document the organization did not author, by a model, in the session that is now asking to
post them (`PLT-23`, ADR-0047). A rule decides where it belongs and a person decides that it
happened — so its transaction is a draft, and an uploaded payment of an open obligation is a
question a person confirms, because a settlement needs its transaction posted.

**A question is a notification, and the person is told** (`PLT-07`, ADR-0052). The decision that
records one raises a notification to everyone who could answer it, and the decision that later
settles the line closes it, in the same transaction each time (ADR-0056 § 1). The notification
carries the line's reference and nothing from the statement.

**Nothing here stores a candidate.** The caller supplies them; a decision and the draft it
coded are what persist. Letting this module hold a queue of unassigned activity is how
`connectors` would have gone wrong (ADR-0031).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from cfokit.assignment import (
    Counterpart,
    CounterpartKind,
    Fate,
    Outcome,
    Predicate,
    Resolution,
    RuleSet,
    RuleVersion,
    Status,
)
from cfokit.assignment.candidate import Candidate, SourceKind
from cfokit.assignment.engine import (
    EVALUATOR_VERSION,
    counterpart_digest,
    decide,
    digest,
    evaluate,
    fits,
    matches,
    rule_set_as_of,
    search,
)
from cfokit.assignment.errors import (
    NotACounterpart,
    NothingToDecline,
    PrecedenceTaken,
    QuestionNotFound,
    RuleNotFound,
)
from cfokit.assignment.repository import (
    StoredDecision,
    claimed,
    decision_for_transaction,
    insert_decision,
    insert_rule_version,
    latest_decision,
    line_declined,
    load_decision,
    load_decisions,
    load_versions,
    moment,
    next_version,
    open_side,
    open_sides,
    precedence_taken,
)
from cfokit.assignment.repository import open_questions as stored_questions
from cfokit.ledger.engine import Entry, Posting
from cfokit.ledger.errors import IdempotencyKeyRequired
from cfokit.ledger.repository.unit_of_work import Database, EntityWrite
from cfokit.ledger.service.authorization import Capability, authorize, authorize_own_act
from cfokit.ledger.service.notifications import answer, notify_holders
from cfokit.ledger.service.principal import Principal
from cfokit.ledger.service.write import Applied as Settles
from cfokit.ledger.service.write import Assigned, WriteContext, record_in

__all__ = [
    "UNRESOLVED_TRANSACTION",
    "Answered",
    "Applied",
    "Booked",
    "Proposal",
    "Replay",
    "answer_question",
    "apply_rules",
    "approve",
    "counterpart_pool",
    "open_questions",
    "propose",
    "replay",
]


# The notification class for a line waiting on a person — no rule resolved it, two records fit
# it, or an uploaded payment waits to be confirmed. To the person it is one question: what is
# this line? Answered by the decision that settles it.
UNRESOLVED_TRANSACTION = "unresolved_transaction"

# What the rules say about a line they were not asked about: the search settled it.
_NOTHING = Resolution(outcome=Outcome.UNMATCHED, winner=None, resolved_by=None, matches=())


@dataclass(frozen=True, slots=True)
class Proposal:
    """What a rule would do, before it exists. Nothing has been written."""

    would_book: tuple[tuple[Candidate, str], ...]
    would_contend_with: tuple[tuple[Candidate, str], ...]
    unaffected: tuple[Candidate, ...]


@dataclass(frozen=True, slots=True)
class Booked:
    """One candidate, and what became of it.

    `counterparts` is what its search found: the one it was matched to or is proposed for, or
    every one an ambiguous line is asked about.
    """

    candidate: Candidate
    transaction_id: str
    decision_id: str
    outcome: Outcome
    rule_label: str | None
    counterparts: tuple[Counterpart, ...] = ()


@dataclass(frozen=True, slots=True)
class Applied:
    """What a run of `apply_rules` did. `unresolved` is the operator's worklist."""

    booked: tuple[Booked, ...]
    unresolved: tuple[Booked, ...]


@dataclass(frozen=True, slots=True)
class Answered:
    """What a person's answer did. `replayed` when the key was seen before."""

    decision_id: str
    outcome: Outcome
    transaction_id: str
    replayed: bool = False


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
        authorize(write, Capability.READ, principal)
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
        authorize_own_act(write, principal)
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
    """Decide each line's fate: the search, then the rules. Return what waits on a person.

    Each candidate is its own write through the ledger's ordinary path, as an import's
    entries are: its own audit row, its own idempotency claim, its own advisory lock. **The
    search and the write are one transaction under that lock** (ADR-0059 § 1), so two runs
    cannot claim one counterpart, and a line cannot reach the rules without the search having
    run.

    A line matched to a counterpart writes what the match means: a posted settlement for an
    open obligation, nothing for a recorded transaction, and one transaction for both sides of
    a transfer. A resolved line posts straight through, because the person already approved
    the pattern — `BKP-09`'s "an approved pattern is never asked about again" — **unless it was
    uploaded**, in which case it is a complete draft a person posts (ADR-0047). A question
    becomes a one-legged draft: it cannot be posted, because the engine requires two postings,
    so the ledger itself refuses to let an unanswered question reach the books.

    Running a candidate again is safe. A settled line is reported as it was settled; a line
    still a question stays the one question; a question now answered — a rule approved, a
    counterpart recorded, the other side of a transfer arrived — is a new decision that names
    the one it supersedes.
    """
    booked: list[Booked] = []
    unresolved: list[Booked] = []

    for index, candidate in enumerate(candidates):
        with database.entity_write(entity_id) as write:
            # Before anything is read. A line already settled is reported from this
            # transaction without reaching the write path, whose own check would otherwise
            # be the first: its transaction and rule are the entity's data (`IAM-01`).
            authorize(write, Capability.RECORD, principal)
            conn = write.connection
            at = moment(conn)
            latest = latest_decision(conn, entity_id=entity_id, source_ref=candidate.source_ref)
            if latest is not None and not latest.outcome.is_question:
                # Already settled. `BKP-11`: a rule changed since affects future assignments
                # only, so a line booked once is reported as it was booked, not re-decided.
                booked.append(_reported(candidate, latest))
                continue

            in_force = rule_set_as_of(load_versions(conn, entity_id=entity_id), at)
            declined = line_declined(
                conn, entity_id=entity_id, source_ref=candidate.source_ref, before=at
            )
            found = (
                () if declined else search(candidate, counterpart_pool(write, candidate, at=at))
            )
            fate = decide(candidate, found, in_force)
            if latest is not None and fate.outcome.is_question:
                # Asked already, and not answered since: one question per line, however often
                # the statement is run.
                unresolved.append(_reported(candidate, latest))
                continue

            outcome = _record(
                write,
                principal=principal,
                request_id=f"{request_id}-{index}",
                candidate=candidate,
                fate=fate,
                rule_set=in_force,
                at=at,
                supersedes=latest,
                chosen_by=None,
            )
        (unresolved if outcome.outcome.is_question else booked).append(outcome)

    return Applied(booked=tuple(booked), unresolved=tuple(unresolved))


def answer_question(
    database: Database,
    context: WriteContext,
    *,
    source_ref: str,
    counterpart: tuple[CounterpartKind, str] | None,
) -> Answered:
    """A person answers a line's question: it is this counterpart, or none of those it was
    asked about (ADR-0059 § 4).

    **A person's own act** (ADR-0042), as approving a rule is, because nothing but the person
    stands behind it — and refused for a delegated session, so the agent that read a document
    cannot confirm that a payment it read happened (`PLT-23`).

    The counterpart is held to the same exact facts as the search, not to its windows: a check
    that cleared after six weeks is answered by choosing the entry. Naming none is for a line
    with candidates — ambiguous or proposed — and the rules then decide it, and the search is
    not run for the line again. What it writes is posted, unless it pairs a transfer with an
    uploaded line, or the rules code an uploaded one, either of which is a draft (ADR-0047).

    The decision supersedes the question and closes its notification in the same transaction
    (ADR-0056 § 1), unless the rules leave the line unresolved, when the question stands.
    """
    if not context.idempotency_key:
        raise IdempotencyKeyRequired("every write requires an idempotency key")
    request = _request_hash(
        "answer_question",
        source_ref,
        str(counterpart[0]) if counterpart else None,
        counterpart[1] if counterpart else None,
    )

    with database.entity_write(context.entity_id) as write:
        authorize_own_act(write, context.principal)
        replayed = write.claim_idempotency(context.idempotency_key, request)
        if replayed is not None:
            return Answered(
                decision_id=str(replayed["decision_id"]),
                outcome=Outcome(str(replayed["outcome"])),
                transaction_id=str(replayed["transaction_id"]),
                replayed=True,
            )

        conn = write.connection
        at = moment(conn)
        latest = latest_decision(conn, entity_id=context.entity_id, source_ref=source_ref)
        if latest is None or not latest.outcome.is_question:
            raise QuestionNotFound(f"no open question about line {source_ref}")
        line = latest.candidate
        in_force = rule_set_as_of(load_versions(conn, entity_id=context.entity_id), at)

        if counterpart is None:
            if latest.outcome not in (Outcome.AMBIGUOUS, Outcome.PROPOSED):
                raise NothingToDecline(
                    "only a line with candidates can be answered with none of them; name the "
                    "record this one is, or approve a rule that covers it"
                )
            resolution = evaluate(line, in_force)
            fate = Fate(outcome=resolution.outcome, counterparts=(), resolution=resolution)
        else:
            kind, named = counterpart
            found = _reconstruct(write, kind, named, line=line, at=at, excluding=None)
            if found is None or not fits(line, found, windowed=False):
                raise NotACounterpart(
                    f"that {kind} is not one this line could be: it must be unclaimed and "
                    "open, in the line's commodity, for exactly the line's amount — on the "
                    "line's account for a transaction, the negated amount on another for a "
                    "transfer"
                )
            fate = Fate(outcome=Outcome.MATCHED, counterparts=(found,), resolution=_NOTHING)

        settled = _record(
            write,
            principal=context.principal,
            request_id=context.request_id,
            candidate=line,
            fate=fate,
            rule_set=in_force,
            at=at,
            supersedes=latest,
            chosen_by=context.principal.id,
        )
        write.store_idempotency_result(
            context.idempotency_key,
            {
                "decision_id": settled.decision_id,
                "outcome": str(settled.outcome),
                "transaction_id": settled.transaction_id,
            },
        )

    return Answered(
        decision_id=settled.decision_id,
        outcome=settled.outcome,
        transaction_id=settled.transaction_id,
    )


def _record(
    write: EntityWrite,
    *,
    principal: Principal,
    request_id: str,
    candidate: Candidate,
    fate: Fate,
    rule_set: RuleSet,
    at: datetime,
    supersedes: StoredDecision | None,
    chosen_by: str | None,
) -> Booked:
    """Write one line's fate: what it puts in the books, its decision, and its notification.

    That they land together is the whole reason assignment is in-process rather than a
    separate component (ADR-0022 § 3): a decision naming a transaction that rolled back, or
    a coding no record explains, is the gap `RPT-08` exists to close. So the entry, the
    decision and the notification it raises or answers are one transaction: the ledger's
    write path runs inside it (`record_in`), and a failure anywhere rolls back all of them.

    A replayed write gets no second decision. The first one already explains the
    transaction, and a decision per retry would make a replay's count of decisions a count
    of how often a client retried.
    """
    conn = write.connection
    entity_id = write.entity_id
    resolved = not fate.outcome.is_question
    found = fate.counterparts[0] if fate.outcome is Outcome.MATCHED else None
    other = (
        load_decision(conn, entity_id=entity_id, decision_id=found.id)
        if found is not None and found.kind is CounterpartKind.TRANSFER
        else None
    )
    winner = fate.resolution.winner

    if found is not None and found.kind is CounterpartKind.TRANSACTION:
        # The books already hold it. Nothing new is written, and the entry is not altered —
        # not even its `derived_from`, because it was not derived from this line. The
        # decision naming it is the line's link to it (ADR-0059 § 3).
        transaction_id = found.id
    else:
        legs, post, settles, assigned = _entry(candidate, fate, other)
        written = record_in(
            write,
            WriteContext(
                entity_id=entity_id,
                principal=principal,
                request_id=request_id,
                idempotency_key=_key(
                    candidate,
                    resolved=resolved,
                    asked_again=None if resolved or supersedes is None else supersedes.id,
                ),
            ),
            entry=Entry(
                transaction_date=candidate.transaction_date,
                postings=legs,
                description=candidate.description or candidate.payee,
            ),
            post=post,
            settles=settles,
            derived_from=_derived(candidate, other),
            assigned=assigned,
            # A match is deterministic and re-derivable, which is what `rule` records, though
            # no rule chose either leg. A person's choice is the person's.
            by_rule=fate.outcome is Outcome.MATCHED and chosen_by is None,
        )
        transaction_id = written.transaction_id
        if written.replayed:
            existing = decision_for_transaction(
                conn, entity_id=entity_id, transaction_id=transaction_id
            )
            if existing is not None:
                return Booked(
                    candidate=candidate,
                    transaction_id=transaction_id,
                    decision_id=existing,
                    outcome=fate.outcome,
                    rule_label=winner.label if winner else None,
                    counterparts=fate.counterparts,
                )

    rule_set_digest = digest(rule_set)
    decision_id = insert_decision(
        conn,
        entity_id=entity_id,
        transaction_id=transaction_id,
        decided_at=at,
        candidate=candidate,
        outcome=fate.outcome,
        winner_id=winner.id if winner else None,
        resolved_by=fate.resolution.resolved_by,
        matches=fate.resolution.matches,
        rule_set_digest=rule_set_digest,
        counterparts=fate.counterparts,
        counterpart_digest=counterpart_digest(fate.counterparts),
        evaluator_version=EVALUATOR_VERSION,
        # An answer names the question it answers, and so does a person's "none" the rules
        # leave unresolved: the line's question is now that one.
        supersedes=supersedes.id if supersedes is not None else None,
        chosen_by=chosen_by,
    )

    if found is not None and found.kind is CounterpartKind.TRANSACTION:
        # No ledger write, so no audit row from the write path: this call's one row is here.
        write.record_audit(
            request_id=request_id,
            actor=principal.audit_actor,
            action="answer_question" if chosen_by else "match_line",
            subject_type="assignment_decision",
            subject_id=decision_id,
            detail={"counterpart": str(found.kind)},
        )

    if other is not None:
        # The earlier side of the transfer is answered by this one: its own decision,
        # superseding its question and naming this line's as what decided it (ADR-0059 § 3).
        mine = Counterpart(
            kind=CounterpartKind.TRANSFER,
            id=decision_id,
            account_id=candidate.source_account_id,
            amount=candidate.amount,
            commodity=candidate.commodity,
            on=candidate.transaction_date,
        )
        paired = insert_decision(
            conn,
            entity_id=entity_id,
            transaction_id=transaction_id,
            decided_at=at,
            candidate=other.candidate,
            outcome=Outcome.MATCHED,
            winner_id=None,
            resolved_by=None,
            matches=(),
            rule_set_digest=rule_set_digest,
            counterparts=(mine,),
            counterpart_digest=counterpart_digest((mine,)),
            evaluator_version=EVALUATOR_VERSION,
            supersedes=other.id,
            chosen_by=chosen_by,
            decided_with=decision_id,
        )
        answer(
            write,
            notification_class=UNRESOLVED_TRANSACTION,
            subject_ref=other.candidate.source_ref,
            principal=principal,
            act_ref=paired,
        )

    if resolved:
        # Closes the question if one was asked; a line settled first time closes nothing.
        answer(
            write,
            notification_class=UNRESOLVED_TRANSACTION,
            subject_ref=candidate.source_ref,
            principal=principal,
            act_ref=decision_id,
        )
    elif supersedes is None:
        # Whoever may approve a rule is whoever can answer it (`BKP-09`, ADR-0042). A
        # question restated — a person's "none" the rules leave open — was asked already.
        notify_holders(
            write,
            Capability.ACT_AS_PRINCIPAL,
            notification_class=UNRESOLVED_TRANSACTION,
            subject_ref=candidate.source_ref,
            link=f"/app/companies/{entity_id}/questions",
        )

    return Booked(
        candidate=candidate,
        transaction_id=transaction_id,
        decision_id=decision_id,
        outcome=fate.outcome,
        rule_label=winner.label if winner else None,
        counterparts=fate.counterparts,
    )


def _entry(
    candidate: Candidate, fate: Fate, other: StoredDecision | None
) -> tuple[tuple[Posting, ...], bool, tuple[Settles, ...], tuple[Assigned, ...]]:
    """The postings a fate writes, whether they post, what they settle, and which leg a rule
    chose.

    The source leg is always the account the line arrived on, as it arrived; no rule chose it.
    """
    source = Posting(
        account_id=candidate.source_account_id,
        amount=candidate.amount,
        commodity=candidate.commodity,
    )
    uploaded = candidate.source_kind is SourceKind.UPLOAD
    winner = fate.resolution.winner

    if fate.outcome is Outcome.ASSIGNED and winner is not None:
        coded = Posting(
            account_id=winner.account_id or "",
            amount=-candidate.amount,
            commodity=candidate.commodity,
        )
        # Index 1: the coded leg.
        return (source, coded), not uploaded, (), (Assigned(1, winner.id),)

    if fate.outcome is Outcome.MATCHED and other is not None:
        # Both sides of a transfer in one transaction. A draft if either line was uploaded
        # (ADR-0047): a two-legged draft needs nothing the ledger lacks.
        side = other.candidate
        legs = (
            source,
            Posting(
                account_id=side.source_account_id, amount=side.amount, commodity=side.commodity
            ),
        )
        return legs, not (uploaded or side.source_kind is SourceKind.UPLOAD), (), ()

    if fate.outcome is Outcome.MATCHED:
        # An open obligation, settled for the line's amount against the account that carries
        # it: the stored link `AR-13` and ADR-0037 § 3 require, recorded where the payment is.
        owed = fate.counterparts[0]
        legs = (
            source,
            Posting(
                account_id=owed.account_id, amount=-candidate.amount, commodity=owed.commodity
            ),
        )
        return legs, True, (Settles(obligation_id=owed.id, amount=candidate.amount),), ()

    # A question: the honest representation of "we do not know the other side" is a draft
    # that does not have one.
    return (source,), False, (), ()


def _derived(candidate: Candidate, other: StoredDecision | None) -> dict[str, str]:
    """`BKP-19`: what the entry came from outside the books."""
    derived = {
        "source_kind": str(candidate.source_kind),
        "source_ref": candidate.source_ref,
        "payee": candidate.payee,
    }
    if other is not None:
        derived["transfer_with"] = other.candidate.source_ref
    return derived


def _reported(candidate: Candidate, stored: StoredDecision) -> Booked:
    """A line as an earlier decision left it, reported rather than decided again."""
    return Booked(
        candidate=candidate,
        transaction_id=stored.transaction_id,
        decision_id=stored.id,
        outcome=stored.outcome,
        rule_label=stored.winner_label,
        counterparts=stored.counterparts,
    )


def counterpart_pool(
    write: EntityWrite, candidate: Candidate, *, at: datetime, excluding: str | None = None
) -> tuple[Counterpart, ...]:
    """What the books held at `at` that this line could be: what the search sees.

    Open obligations, unreversed entries on the line's account for its amount that no line has
    claimed, and other lines' open questions for the negated amount. The ledger supplies its
    reads and learns nothing about what a line is (ADR-0022); this module adds what only it
    knows — which legs lines have claimed, and which questions are open. The exact facts and the
    windows are the engine's to apply.

    `excluding` is a transaction to leave out: the one a decision itself wrote, when replay
    rebuilds the books as they stood the moment before it.
    """
    conn = write.connection
    owed = tuple(
        Counterpart(
            kind=CounterpartKind.OBLIGATION,
            id=held.obligation_id,
            account_id=held.account_id,
            amount=held.outstanding,
            commodity=held.commodity,
            on=held.transaction_date,
        )
        for held in write.obligations_as_of(at=at, excluding_transaction=excluding)
        if held.outstanding != 0
    )
    moved = write.movements_as_of(
        account_id=candidate.source_account_id,
        commodity=candidate.commodity,
        at=at,
        amount=candidate.amount,
        excluding_transaction=excluding,
    )
    taken = claimed(
        conn,
        entity_id=write.entity_id,
        account_id=candidate.source_account_id,
        transaction_ids=[movement.transaction_id for movement in moved],
        before=at,
    )
    recorded = tuple(
        Counterpart(
            kind=CounterpartKind.TRANSACTION,
            id=movement.transaction_id,
            account_id=candidate.source_account_id,
            amount=movement.amount,
            commodity=candidate.commodity,
            on=movement.transaction_date,
        )
        for movement in moved
        if movement.transaction_id not in taken
    )
    sides = open_sides(conn, entity_id=write.entity_id, candidate=candidate, at=at)
    return (*owed, *recorded, *sides)


def _reconstruct(
    write: EntityWrite,
    kind: CounterpartKind,
    named: str,
    *,
    line: Candidate,
    at: datetime,
    excluding: str | None,
) -> Counterpart | None:
    """One named counterpart as the books held it at `at`, or `None` if they did not.

    Read by its id rather than through the search, so replay rebuilds what a decision stored
    independently of what the search sees — and a person's choice is checked against the
    record as it stands, whatever the windows would have said.
    """
    try:
        uuid.UUID(named)
    except ValueError:
        return None
    conn = write.connection
    match kind:
        case CounterpartKind.OBLIGATION:
            held = write.obligations_as_of(
                at=at, excluding_transaction=excluding, obligation_id=named
            )
            if not held or held[0].outstanding == 0:
                return None
            return Counterpart(
                kind=kind,
                id=named,
                account_id=held[0].account_id,
                amount=held[0].outstanding,
                commodity=held[0].commodity,
                on=held[0].transaction_date,
            )
        case CounterpartKind.TRANSACTION:
            moved = write.movements_as_of(
                account_id=line.source_account_id,
                commodity=line.commodity,
                at=at,
                excluding_transaction=excluding,
                transaction_id=named,
            )
            taken = claimed(
                conn,
                entity_id=write.entity_id,
                account_id=line.source_account_id,
                transaction_ids=[named],
                before=at,
            )
            if not moved or named in taken:
                return None
            return Counterpart(
                kind=kind,
                id=named,
                account_id=line.source_account_id,
                amount=moved[0].amount,
                commodity=line.commodity,
                on=moved[0].transaction_date,
            )
        case CounterpartKind.TRANSFER:
            return open_side(
                conn,
                entity_id=write.entity_id,
                decision_id=named,
                source_ref=line.source_ref,
                at=at,
            )


def open_questions(
    database: Database, *, entity_id: str, principal: Principal
) -> tuple[StoredDecision, ...]:
    """Every line waiting on a person, with what it is asked about (`BKP-12`, ADR-0059 § 4).

    A read, so a delegated agent may do it: this is what it shows the person before asking.
    An unmatched line is answered by approving a rule that covers it and running the line
    again (`BKP-09`), or by naming the record it is; an ambiguous or proposed one by naming a
    counterpart, or none of them.
    """
    with database.entity_write(entity_id) as write:
        authorize(write, Capability.READ, principal)
        return stored_questions(write.connection, entity_id=entity_id)


def _key(candidate: Candidate, *, resolved: bool, asked_again: str | None = None) -> str:
    """Derived from the source's reference, not minted, so a re-run of the same statement
    replays rather than double-booking — the device `imports` uses for the same reason.

    **Never from the content.** Two identical coffees on one statement share every fact and
    differ only in which line they are; a key built from their content gave them one key,
    and the second was replayed as the first and lost (ADR-0029).

    **An unanswered candidate has a key of its own.** Its write is a question — a one-legged
    draft — and the operator answering it makes the next write a different one. Under one key
    that would be a key reused with different parameters, which the ledger rightly refuses;
    under two, the answer is its own transaction and its decision names the question it
    supersedes. A question asked again — a person's "none" the rules leave open — is keyed by
    the question it restates, since its draft is a new one.
    """
    reference = hashlib.sha256(candidate.source_ref.encode("utf-8")).hexdigest()[:48]
    if resolved:
        return f"assignment:{reference}"
    if asked_again is not None:
        return f"assignment:{reference}:unresolved:{asked_again}"
    return f"assignment:{reference}:unresolved"


def _request_hash(*parts: object) -> str:
    """A digest of the parameters, to detect a key reused for a different request (ADR-0029).

    Duplicated from the write path rather than shared, which is the default between files that
    happen to need the same few lines.
    """
    canonical = json.dumps(parts, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


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

    `rule_set_changed`, `semantics_changed` and `books_changed` are the decisions a replay
    declined to judge rather than ones it failed: a rule changed since (`BKP-11` permits it),
    the evaluator's semantics changed, or what the search saw cannot be rebuilt as it was.
    `chosen` are a person's choices, which are not a function of the inputs and so are counted
    rather than re-decided (ADR-0059 § 5). Without separating them the acceptance criterion
    would be unfalsifiable: a disagreement would have several possible causes and the test
    could not say which, so it would either fail constantly or assert nothing.
    """

    total: int
    compared: int
    reproduced: int
    rule_set_changed: int
    semantics_changed: int
    books_changed: int
    chosen: int
    diverged: tuple[str, ...]


_REPRODUCED = "reproduced"
_DIVERGED = "diverged"
_RULES = "rule_set_changed"
_SEMANTICS = "semantics_changed"
_BOOKS = "books_changed"
_CHOSEN = "chosen"


def replay(database: Database, *, entity_id: str, principal: Principal) -> Replay:
    """Re-decide every recorded decision — search, then rules — as the books and the rule set
    stood when it was taken.

    **`BKP-06`'s acceptance, executable**: "replaying an entity's full transaction history
    against an unchanged rule set reproduces every assignment identically". It covers the
    search too, so a line booked by a rule while a counterpart sat in the books is a divergence
    rather than an invisible figure (ADR-0059 § 5).

    Writes nothing, so it is safe to run against real books. It is still a read of the
    entity's decisions, so it needs a grant like any other read (`IAM-01`).

    A decision whose stored digests no longer match what is rebuilt is *not* a failure:
    `BKP-11` permits a rule to change, and the digests are exactly what tell the two apart. One
    taken under different evaluator semantics is not compared either, which is the honest limit
    of this check and the reason bumping `EVALUATOR_VERSION` needs a record. The earlier side of
    a transfer is judged with the line whose search decided it.
    """
    verdicts: dict[str, str] = {}
    with database.entity_write(entity_id) as write:
        authorize(write, Capability.READ, principal)
        versions = load_versions(write.connection, entity_id=entity_id)
        decisions = load_decisions(write.connection, entity_id=entity_id)
        for decision in decisions:
            if decision.chosen_by is not None:
                verdicts[decision.id] = _CHOSEN
            elif decision.decided_with is None:
                verdicts[decision.id] = _rejudge(write, decision, versions)

    for decision in decisions:
        if decision.id not in verdicts:
            verdicts[decision.id] = verdicts.get(decision.decided_with or "", _BOOKS)

    def counted(verdict: str) -> int:
        return sum(1 for d in decisions if verdicts[d.id] == verdict)

    diverged = tuple(d.id for d in decisions if verdicts[d.id] == _DIVERGED)
    reproduced = counted(_REPRODUCED)
    return Replay(
        total=len(decisions),
        compared=reproduced + len(diverged),
        reproduced=reproduced,
        rule_set_changed=counted(_RULES),
        semantics_changed=counted(_SEMANTICS),
        books_changed=counted(_BOOKS),
        chosen=counted(_CHOSEN),
        diverged=diverged,
    )


def _rejudge(
    write: EntityWrite, decision: StoredDecision, versions: Sequence[RuleVersion]
) -> str:
    """One decision, re-decided as at the moment it was taken."""
    if decision.evaluator_version != EVALUATOR_VERSION:
        return _SEMANTICS

    in_force = rule_set_as_of(versions, decision.decided_at)
    if digest(in_force) != decision.rule_set_digest:
        return _RULES

    line = decision.candidate
    # The transaction the decision itself wrote, which the books as they stood the moment
    # before it did not hold. A match to a recorded transaction wrote none: that one was there.
    wrote = not (
        decision.outcome is Outcome.MATCHED
        and decision.counterparts
        and decision.counterparts[0].kind is CounterpartKind.TRANSACTION
    )
    own = decision.transaction_id if wrote else None
    rebuilt = [
        _reconstruct(write, c.kind, c.id, line=line, at=decision.decided_at, excluding=own)
        for c in decision.counterparts
    ]
    present = [c for c in rebuilt if c is not None]
    if (
        len(present) != len(rebuilt)
        or counterpart_digest(present) != decision.counterpart_digest
    ):
        return _BOOKS

    declined = line_declined(
        write.connection,
        entity_id=write.entity_id,
        source_ref=line.source_ref,
        before=decision.decided_at,
    )
    found = (
        ()
        if declined
        else search(line, counterpart_pool(write, line, at=decision.decided_at, excluding=own))
    )
    again = decide(line, found, in_force)
    same = (
        again.outcome is decision.outcome
        and [(c.kind, c.id) for c in again.counterparts]
        == [(c.kind, c.id) for c in decision.counterparts]
        and (again.resolution.winner.id if again.resolution.winner else None)
        == decision.winner_id
        and again.resolution.resolved_by is decision.resolved_by
    )
    return _REPRODUCED if same else _DIVERGED
