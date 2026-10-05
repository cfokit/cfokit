"""The write path: what every state-changing call does, in what order.

Four obligations, each a bug if missed, and all of them satisfied here rather than in an
adapter so both protocol surfaces get them (ADR-0009):

1. **The entity lock**, taken before the state-changing work and in the same transaction
   (ADR-0011).
2. **The idempotency key**, mandatory, checked before the work and in the same transaction, so
   a retry cannot double-book (ADR-0029).
3. **Exactly one `audit_log` row** per state change — and none at all for a replay, because a
   replayed request is not a new state change (ADR-0029).
4. **Attribution derived from the authenticated principal**, never from a parameter
   (ADR-0033).

The order is not arbitrary. The lock comes first so the idempotency check cannot race; the
idempotency check comes before the work so a replay does no work; the audit row goes inside
the same transaction as the change so the two cannot be separated by a failure.

**Entity grants are validated here**, inside the locked transaction and before any work, which
is what ADR-0011 means by "server-side regardless of token contents". Reading them inside the
transaction is also what makes `IAM-15` true — a revocation committed a moment ago is already
in force, because the check is a query rather than something cached at the edge.

For an agent the check is over **two** principals and takes the intersection (`IAM-11`).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from cfokit.ledger.engine import Entry, build_reversal, check_postable
from cfokit.ledger.engine.periods import period_of
from cfokit.ledger.errors import (
    IdempotencyKeyRequired,
    ObligationNotFound,
    PeriodClosed,
    TransactionAlreadyPosted,
    TransactionIncomplete,
    TransactionNotFound,
)
from cfokit.ledger.repository.unit_of_work import Database, EntityWrite
from cfokit.ledger.service.authorization import Capability, authorize
from cfokit.ledger.service.principal import ActorClass, Principal

__all__ = [
    "WriteContext",
    "WrittenTransaction",
    "post_transaction",
    "record_in",
    "record_transaction",
    "reverse_transaction",
]


@dataclass(frozen=True, slots=True)
class WriteContext:
    """What every write carries besides its own parameters.

    Bundled rather than passed as four arguments, so a new write path cannot quietly omit one
    — the obligations arrive together or not at all.
    """

    entity_id: str
    principal: Principal
    request_id: str
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class Applied:
    """How much of a settlement goes against one obligation (`AR-12`).

    Stated per obligation rather than split by the ledger: a payment covering three invoices is
    applied the way the person paying meant it, and no rule the system invents would be right
    more often than being told.
    """

    obligation_id: str
    amount: Decimal


@dataclass(frozen=True, slots=True)
class Assigned:
    """Which posting a rule coded, and which version of the rule did it (`BKP-10`).

    Positional rather than carried on `Posting`, because `Posting` belongs to the pure engine
    and a rule is a module's concept the engine must not learn (ADR-0022). `rule_version_id`
    is opaque here for the same reason `decision_record_id` is: the ledger holds the
    identifier without importing what it points at.
    """

    posting_index: int
    rule_version_id: str


@dataclass(frozen=True, slots=True)
class WrittenTransaction:
    """What a write produced. Small enough to store as an idempotent replay's result."""

    transaction_id: str
    status: str
    replayed: bool = False


def _request_hash(*parts: Any) -> str:
    """A stable digest of a request's parameters.

    Content is hashed only to detect a **key reused with different parameters**, never to
    decide whether two requests are the same operation. ADR-0029 rejects content hashing for
    that: two five-dollar coffees on the same day are two transactions, and conflating them
    would lose one.

    `Decimal` is serialized through `str`, so `10.00` and `10.0` hash differently — which is
    correct, because they are different requests even though they are equal amounts.
    """
    canonical = json.dumps(parts, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _require_key(context: WriteContext) -> None:
    if not context.idempotency_key:
        raise IdempotencyKeyRequired("every write requires an idempotency key")


def _require_open(write: EntityWrite, when: date) -> None:
    """Refuse a posting into a closed period (`LED-11`, ADR-0030).

    Inside the locked transaction, so a close committed a moment ago already refuses and two
    concurrent writes cannot disagree about whether the period was open (ADR-0011).

    Drafts are not checked. `LED-11` says no *posting* enters a closed period, and a draft is
    not in the books — refusing it would stop an operator preparing the entry they are about
    to ask to have the period reopened for.
    """
    if write.close_in_force(period_of(when)) is not None:
        raise PeriodClosed(f"period {period_of(when)} is closed; reopen it to post into it")


def record_transaction(
    database: Database,
    context: WriteContext,
    *,
    entry: Entry,
    post: bool,
    entry_kind: str = "ordinary",
    raises_obligation: Decimal | None = None,
    settles: tuple[Applied, ...] = (),
    derived_from: dict[str, Any] | None = None,
    assigned: tuple[Assigned, ...] = (),
) -> WrittenTransaction:
    """Record a transaction in a transaction of its own. See `record_in` for what it does.

    The ordinary entry point: it opens the entity's locked transaction, records, and commits.
    """
    with database.entity_write(context.entity_id) as write:
        return record_in(
            write,
            context,
            entry=entry,
            post=post,
            entry_kind=entry_kind,
            raises_obligation=raises_obligation,
            settles=settles,
            derived_from=derived_from,
            assigned=assigned,
        )


def record_in(
    write: EntityWrite,
    context: WriteContext,
    *,
    entry: Entry,
    post: bool,
    entry_kind: str = "ordinary",
    raises_obligation: Decimal | None = None,
    settles: tuple[Applied, ...] = (),
    derived_from: dict[str, Any] | None = None,
    assigned: tuple[Assigned, ...] = (),
) -> WrittenTransaction:
    """Record a transaction, as a draft or posted straight through.

    **Inside a transaction the caller already holds**, so a module can commit its own record
    of why the entry was made in the same COMMIT as the entry (ADR-0022 § 3, ADR-0045 § 1).
    The caller's `EntityWrite` has already scoped row-level security and taken the entity's
    lock; everything else — the idempotency claim, the grant check, the one audit row, none on
    a replay — happens here exactly as it does for `record_transaction`. Whatever the caller
    does afterwards in the same transaction commits or rolls back with the entry, including
    the idempotency claim, so a failure there leaves a retry free to do the whole thing again.
    The ledger learns nothing about what the caller writes: it hands over nothing but the
    result.

    `post=False` writes a draft, which may be unbalanced and is freely editable (`LED-07`).
    `post=True` writes it and posts it in the same transaction, which is the ordinary path for
    a person entering a complete entry.

    An agent's writes are drafts by default — ADR-0007: "the agent proposes; a person's
    confirmation posts" — but that is a decision for the caller and its grant model, not
    something this function can infer from `actor_class`.

    **`raises_obligation` and `settles` record the link `LED-17` requires**, in the same
    transaction as the postings. ADR-0037 § 3 makes storing that link the decision's whole
    substance: inferring it later from account and transaction type is what the incumbents do,
    and a journal entry touching receivables defeats it. Recorded here it cannot be lost, and
    it cannot describe a transaction that does not exist.

    Both need the transaction posted. A draft is not in the books (`LED-07`), so an obligation
    raised by one would be owed by nobody and a settlement against one would apply to nothing.

    **`assigned` records that a rule chose a coding, and which rule version** (`BKP-10`).
    ADR-0042 § 4 reserved this: "`RULE` arrives when the rules engine does — as a value the
    write path sets on a posting whose coding a rule determined, not as a branch in
    `principal_from_claims`", because a token cannot tell you a coding was rule-assigned —
    the rule runs after authentication, and one credential carries both a rule-assigned
    posting and a judgment in the same session.

    Per posting, because `BKP-05` splits a transaction across accounts and a feed's two legs
    are decided by different things: the bank leg is the account the feed belongs to and no
    rule chose it. `RPT-08` walks back from a posting, so that is where the answer lives.

    It also sets the transaction's `actor_class` to `rule`, which is the one thing here that
    is not per posting. ADR-0033 § 3 wants that class maximized because "a rule-assigned
    coding is deterministic and re-derivable, and an auditor tests it cheaply and once"; it
    describes **why a posting was made** and is never an authority check (ADR-0042 § 3), so
    it does not widen what the caller may do. `actor_principal_id` still records who called.

    **`derived_from` says what this entry came from outside the books** — the source system and
    the record within it (`IMP-04`, `BKP-19`, `SOC1-14`). It is lineage, not content: it never
    affects what is posted, what balances, or what any statement shows, and it is written once
    at insert because the entry is append-only. It is deliberately not part of the idempotency
    digest below: two requests that differ only in where they say they came from are not the
    same operation, and a caller reusing a key across two sources should be told so.
    """
    _require_key(context)
    if write.entity_id != context.entity_id:
        # A programming error, not a request error: the lock and the scope held are another
        # entity's, so nothing here would be written where the context says it is.
        raise ValueError("the write is scoped to a different entity than the context names")

    digest = _request_hash(
        "record_transaction",
        entry.transaction_date,
        entry.description,
        entry.reverses_id,
        entry_kind,
        post,
        [(p.account_id, str(p.amount), p.commodity) for p in entry.postings],
        derived_from,
        [(a.posting_index, a.rule_version_id) for a in assigned],
    )

    replay = write.claim_idempotency(context.idempotency_key, digest)
    if replay is not None:
        # No work, and deliberately no audit row: a replay is not a state change.
        return WrittenTransaction(
            transaction_id=str(replay["transaction_id"]),
            status=str(replay["status"]),
            replayed=True,
        )

    authorize(write, Capability.POST if post else Capability.RECORD, context.principal)

    if (raises_obligation is not None or settles) and not post:
        raise TransactionIncomplete(
            "an obligation or a settlement needs the transaction posted; a draft is not "
            "in the books"
        )

    if post:
        _require_open(write, entry.transaction_date)
        # The ergonomic check, so the caller gets a stable code and a readable message
        # before the deferred trigger produces a blunt one at COMMIT (ADR-0006). Inside
        # the transaction because the functional currency it checks against is read from
        # the entity, and a refused write rolls back leaving nothing behind.
        check_postable(entry, functional_currency=write.functional_currency)

    transaction_id = write.insert_draft(
        transaction_date=entry.transaction_date,
        description=entry.description,
        reverses_id=entry.reverses_id,
        entry_kind=entry_kind,
        actor_principal_id=context.principal.id,
        # `rule` when a rule chose a coding, and the caller's own class otherwise. It
        # records why the posting was made rather than who may make it (ADR-0042 § 3),
        # so this narrows nothing and widens nothing.
        actor_class=(
            ActorClass.RULE.value if assigned else context.principal.actor_class.value
        ),
        acting_for_principal_id=context.principal.acting_for,
        derived_from=derived_from,
    )
    write.add_postings(
        transaction_id,
        entry.postings,
        assigned_by={a.posting_index: a.rule_version_id for a in assigned},
    )

    if raises_obligation is not None:
        write.raise_obligation(
            transaction_id=transaction_id,
            amount=raises_obligation,
            commodity=write.functional_currency,
        )
    for applied in settles:
        if write.outstanding(obligation_id=applied.obligation_id) == []:
            raise ObligationNotFound(f"no obligation {applied.obligation_id} in this entity")
        write.apply_settlement(
            obligation_id=applied.obligation_id,
            transaction_id=transaction_id,
            amount=applied.amount,
            commodity=write.functional_currency,
        )

    status = "draft"
    if post:
        write.mark_posted(transaction_id)
        status = "posted"

    write.record_audit(
        request_id=context.request_id,
        actor=context.principal.audit_actor,
        action="record_transaction",
        subject_type="ledger_transaction",
        subject_id=transaction_id,
        # Identifiers and counts. Never amounts, accounts or payees.
        detail={"postings": len(entry.postings), "posted": post, "kind": entry_kind},
    )
    write.store_idempotency_result(
        context.idempotency_key, {"transaction_id": transaction_id, "status": status}
    )

    return WrittenTransaction(transaction_id=transaction_id, status=status)


def post_transaction(
    database: Database,
    context: WriteContext,
    *,
    transaction_id: str,
) -> WrittenTransaction:
    """Move a draft to posted. The point of no return (`LED-07`)."""
    _require_key(context)
    digest = _request_hash("post_transaction", transaction_id)

    with database.entity_write(context.entity_id) as write:
        replay = write.claim_idempotency(context.idempotency_key, digest)
        if replay is not None:
            return WrittenTransaction(
                transaction_id=str(replay["transaction_id"]),
                status=str(replay["status"]),
                replayed=True,
            )

        authorize(write, Capability.POST, context.principal)

        stored = write.load_transaction(transaction_id)
        if stored is None:
            raise TransactionNotFound(f"no transaction {transaction_id}")
        if stored.status == "posted":
            raise TransactionAlreadyPosted(
                f"transaction {transaction_id} is posted; correct it with a reversal"
            )
        _require_open(write, stored.transaction_date)

        check_postable(
            Entry(
                transaction_date=stored.transaction_date,
                postings=stored.postings,
                description=stored.description,
                reverses_id=stored.reverses_id,
            ),
            functional_currency=write.functional_currency,
        )
        write.mark_posted(transaction_id)

        write.record_audit(
            request_id=context.request_id,
            actor=context.principal.audit_actor,
            action="post_transaction",
            subject_type="ledger_transaction",
            subject_id=transaction_id,
            detail={"postings": len(stored.postings)},
        )
        write.store_idempotency_result(
            context.idempotency_key, {"transaction_id": transaction_id, "status": "posted"}
        )

    return WrittenTransaction(transaction_id=transaction_id, status="posted")


def reverse_transaction(
    database: Database,
    context: WriteContext,
    *,
    transaction_id: str,
    current_period_date: date,
    description: str | None = None,
) -> WrittenTransaction:
    """Reverse a posted transaction, leaving both visible (`LED-08`).

    A first-class operation rather than something a caller assembles by hand, because ADR-0007
    says a policy that is laborious to follow is one that gets worked around.

    The reversal is posted immediately. A draft reversal would leave the books stating
    something known to be wrong for as long as it sat unposted.

    **Whether the original period is closed is read, not asserted.** ADR-0030 rule 4 dates the
    reversal by that state — an open original is restated in place, a closed one is corrected
    in the current period so prior reported figures stand — and a caller that supplied the
    answer could choose which rule applied to it.
    """
    _require_key(context)
    digest = _request_hash("reverse_transaction", transaction_id, str(current_period_date))

    with database.entity_write(context.entity_id) as write:
        replay = write.claim_idempotency(context.idempotency_key, digest)
        if replay is not None:
            return WrittenTransaction(
                transaction_id=str(replay["transaction_id"]),
                status=str(replay["status"]),
                replayed=True,
            )

        # A reversal posts immediately, so it needs the capability to post rather than only
        # to record (`LED-08`, ADR-0007).
        authorize(write, Capability.POST, context.principal)

        stored = write.load_transaction(transaction_id)
        if stored is None:
            raise TransactionNotFound(f"no transaction {transaction_id}")

        reversal = build_reversal(
            Entry(
                transaction_date=stored.transaction_date,
                postings=stored.postings,
                description=stored.description,
            ),
            reverses_id=transaction_id,
            original_period_closed=write.close_in_force(period_of(stored.transaction_date))
            is not None,
            current_period_date=current_period_date,
            description=description,
        )
        # Wherever rule 4 landed it, a reversal is a posting and the period it lands in has to
        # be open. A closed current period is the case where an operator must reopen first.
        _require_open(write, reversal.transaction_date)
        check_postable(reversal, functional_currency=write.functional_currency)

        reversal_id = write.insert_draft(
            transaction_date=reversal.transaction_date,
            description=reversal.description,
            reverses_id=transaction_id,
            entry_kind=stored.entry_kind,
            actor_principal_id=context.principal.id,
            actor_class=context.principal.actor_class.value,
            acting_for_principal_id=context.principal.acting_for,
        )
        write.add_postings(reversal_id, reversal.postings)
        write.mark_posted(reversal_id)

        write.record_audit(
            request_id=context.request_id,
            actor=context.principal.audit_actor,
            action="reverse_transaction",
            subject_type="ledger_transaction",
            subject_id=reversal_id,
            detail={"reverses": transaction_id, "postings": len(reversal.postings)},
        )
        write.store_idempotency_result(
            context.idempotency_key, {"transaction_id": reversal_id, "status": "posted"}
        )

    return WrittenTransaction(transaction_id=reversal_id, status="posted")
