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

**Entity grants are not validated here yet.** ADR-0011 and ADR-0019 require them to be checked
server-side regardless of token contents, and there is no grant model in the schema to check
against. Until there is, this layer enforces isolation and not authorisation, and it is stated
here rather than implied.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from typing import Any

from cfokit.ledger.engine import Entry, build_reversal, check_postable
from cfokit.ledger.errors import (
    IdempotencyKeyRequired,
    TransactionAlreadyPosted,
    TransactionNotFound,
)
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.principal import Principal

__all__ = [
    "WriteContext",
    "WrittenTransaction",
    "post_transaction",
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

    `Decimal` is serialised through `str`, so `10.00` and `10.0` hash differently — which is
    correct, because they are different requests even though they are equal amounts.
    """
    canonical = json.dumps(parts, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _require_key(context: WriteContext) -> None:
    if not context.idempotency_key:
        raise IdempotencyKeyRequired("every write requires an idempotency key")


def record_transaction(
    database: Database,
    context: WriteContext,
    *,
    entry: Entry,
    post: bool,
    entry_kind: str = "ordinary",
) -> WrittenTransaction:
    """Record a transaction, as a draft or posted straight through.

    `post=False` writes a draft, which may be unbalanced and is freely editable (`LED-07`).
    `post=True` writes it and posts it in the same transaction, which is the ordinary path for
    a person entering a complete entry.

    An agent's writes are drafts by default — ADR-0007: "the agent proposes; a person's
    confirmation posts" — but that is a decision for the caller and its grant model, not
    something this function can infer from `actor_class`.
    """
    _require_key(context)

    digest = _request_hash(
        "record_transaction",
        entry.transaction_date,
        entry.description,
        entry.reverses_id,
        entry_kind,
        post,
        [(p.account_id, str(p.amount), p.commodity) for p in entry.postings],
    )

    with database.entity_write(context.entity_id) as write:
        replay = write.claim_idempotency(context.idempotency_key, digest)
        if replay is not None:
            # No work, and deliberately no audit row: a replay is not a state change.
            return WrittenTransaction(
                transaction_id=str(replay["transaction_id"]),
                status=str(replay["status"]),
                replayed=True,
            )

        if post:
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
            actor_class=context.principal.actor_class.value,
            acting_for_principal_id=context.principal.acting_for,
        )
        write.add_postings(transaction_id, entry.postings)

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

        stored = write.load_transaction(transaction_id)
        if stored is None:
            raise TransactionNotFound(f"no transaction {transaction_id}")
        if stored.status == "posted":
            raise TransactionAlreadyPosted(
                f"transaction {transaction_id} is posted; correct it with a reversal"
            )

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
    original_period_closed: bool,
    current_period_date: date,
    description: str | None = None,
) -> WrittenTransaction:
    """Reverse a posted transaction, leaving both visible (`LED-08`).

    A first-class operation rather than something a caller assembles by hand, because ADR-0007
    says a policy that is laborious to follow is one that gets worked around.

    The reversal is posted immediately. A draft reversal would leave the books stating
    something known to be wrong for as long as it sat unposted.
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
            original_period_closed=original_period_closed,
            current_period_date=current_period_date,
            description=description,
        )
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
