---
status: "accepted"
kind: "requirement-driven"
date: 2026-08-17
decision-makers: [Geoff]
---

# ADR-0012: Per-entity advisory lock on writes, and mandatory idempotency keys

## Context and Problem Statement

Two concurrency problems, with different shapes.

**Serialisation.** The workload is thousands of entities, mostly idle, with low write concurrency
*per entity* and high parallelism *across* entities (ADR-0003). Writes within one entity must not
interleave in ways that corrupt derived state; writes across entities must not block each other at
all, because that would destroy the property that makes multi-tenant hosting viable.

**Retries.** Writes arrive from agents over HTTP, across networks that fail in the ambiguous
direction: the caller does not learn whether a request that timed out was applied. The correct
client behaviour is to retry, and agents will retry — reliably and without judgement. In an
append-only ledger a duplicated write cannot be deleted, only reversed (ADR-0007), so a double-book
is a permanent scar on the audit trail rather than a cleanup task.

These are separate problems and neither solves the other. Serialisation does not make a retry safe;
idempotency does not order concurrent writes.

## Decision Drivers

* Writes across entities must never contend, or multi-tenant hosting stops being viable (REQ-A2).
* A duplicated write is permanent under append-only semantics (ADR-0007), so prevention must not
  depend on caller judgement.
* Retry logic must not proliferate into every write path.
* Both protocol surfaces must be protected, including MCP, which never passes through HTTP
  (ADR-0009).

## Considered Options

* Per-entity `pg_advisory_xact_lock` plus mandatory idempotency keys
* Optimistic concurrency with retry on conflict
* `SELECT ... FOR UPDATE` on the entity row
* Table-level or global locking
* `SERIALIZABLE` isolation instead of explicit locking
* Optional idempotency keys, applied where callers choose
* Deduplicating by content hash instead of an explicit key
* Idempotency at the HTTP layer only, via `Idempotency-Key`

## Decision Outcome

Chosen option: **every write takes `pg_advisory_xact_lock` keyed on the entity, and carries a
mandatory idempotency key.**

- The lock is transaction-scoped, so it releases at commit or rollback with no explicit unlock and
  no leak on failure.
- It is keyed on `entity_id`, so writes to different entities never contend.
- Idempotency keys are **mandatory, not optional**. A write without one is rejected.
- A repeated key returns the original result rather than applying the operation again.

Entity grants are validated server-side on every request regardless of token contents, and this is
independent of both mechanisms — it is authorisation, not concurrency, and is noted here because
`CLAUDE.md` groups them.

### Consequences

* Good, because contention is deterministic and local to one entity, which is far easier to reason
  about and to test than conflict-abort-retry.
* Good, because every write path can assume the idempotency key exists, removing a whole branch of
  conditional logic.
* Good, because the lock is transaction-scoped, so no failure path leaks it.
* Bad, because writes to one entity serialise, so a long-running write blocks others for that
  entity. Acceptable given per-entity write concurrency is low by workload assumption, and it is
  the reason any long-running operation belongs on a non-request path (ADR-0018).
* Bad, because callers must generate and manage idempotency keys, and this must be documented on
  both published surfaces (ADR-0016).
* Bad, because idempotency records need storage and a retention policy of their own — long enough
  to outlive any plausible retry, short enough not to accumulate indefinitely (REQ-E7).

### Confirmation

Tests must prove serialisation by actually running concurrent writes, not by inspection. This is an
M3 exit criterion.

## Pros and Cons of the Options

### Per-entity advisory lock plus mandatory idempotency keys

* Good, because the two mechanisms address the two distinct problems without either pretending to
  solve the other.
* Good, because an advisory lock says what it is, rather than overloading a data row.
* Bad, because advisory lock keys must be derived from `entity_id` by a documented, collision-free
  scheme, since the advisory namespace is global and shared across the database.

### Optimistic concurrency with retry on conflict

* Good, because it costs nothing in the uncontended case, which is nearly all cases here given how
  idle most entities are.
* Good, because it is what a distributed SQL backend would force anyway (ADR-0003).
* Bad, because it moves retry logic into every write path, and retry-on-conflict interacts badly
  with the retries already arriving from agents — a client retry of a transaction that itself
  retried internally is difficult to reason about, and the ambiguity compounds.
* Bad, because it would be insufficient on its own for read-modify-write against lot state, which
  ADR-0003 explicitly cited as a serialisation requirement, so it would need supplementing anyway.

### `SELECT ... FOR UPDATE` on the entity row

The conventional approach, and genuinely close in effect. **This is the alternative most likely to
be re-proposed, and it is a reasonable choice** — it is simply less explicit, and it is the
documented fallback should the backend change.

* Good, because it works, requires no advisory-lock namespace, and is portable to any SQL database.
* Bad, because it requires a lockable row to exist for every entity and couples the lock to that
  row's lifecycle, so deleting or replacing the row has concurrency consequences that are not
  obvious from reading it.
* Bad, because it conflates data with a control mechanism: a reader of the schema cannot tell the
  row is load-bearing for serialisation.

### Table-level or global locking

* Good, because it is simplest to reason about and trivially correct.
* Bad, because it serialises writes across all entities, which destroys the high-parallelism
  property that makes one deployment viable for a fractional CFO with many clients (REQ-A2). It
  would turn an idle-heavy multi-tenant workload into a single-writer system.

### `SERIALIZABLE` isolation instead of explicit locking

* Good, because Postgres would detect conflicting interleavings and abort one transaction.
* Bad, because it produces serialisation failures under contention that every caller must handle,
  which is retry logic again, now triggered by conditions that are hard to reproduce in tests.

### Optional idempotency keys, applied where callers choose

* Good, because there is less friction, and most operations are not obviously dangerous to repeat.
* Bad, because the one write that omits the key is the one that double-books, and the caller who
  omits it is the caller who did not think about failure. Making it mandatory moves the decision
  from runtime judgement to schema requirement.

### Deduplicating by content hash instead of an explicit key

* Good, because it requires nothing from the caller: hash the transaction and reject duplicates.
* Bad, because legitimately identical transactions exist. Two five-dollar coffees on the same day
  from the same merchant are two transactions, not a duplicate, and a content hash cannot tell them
  apart from a retry. Suppressing the second one silently loses a real transaction, which is worse
  than double-booking because nothing indicates it happened.

### Idempotency at the HTTP layer only, via `Idempotency-Key`

* Good, because it is standard, and it is where the header belongs.
* Bad, as *sufficient* rather than as a mechanism. MCP calls the service layer in-process and never
  passes through HTTP (ADR-0009), so an HTTP-layer implementation would leave the primary consumer
  surface unprotected. The requirement belongs in the service layer, where both adapters reach it.

## More Information

**Follow-on obligations.**

- The advisory lock is taken in the service layer, not in adapters or in the repository, so it
  applies uniformly across both protocol surfaces.
- Lock acquisition and idempotency check happen before the state-changing work, in the same
  transaction as the write.
- A replayed idempotency key returns the original result, and must not silently succeed with a
  different one — a key reused with different parameters is a client error and gets a stable error
  `code` (ADR-0016).
- The audit trail records one row per state-changing call; a replayed idempotent request is not a
  new state change and must not write a second row.
- Advisory lock keys are derived from `entity_id` by a documented, collision-free scheme.

**Reversal cost. Moderate.** Swapping the lock mechanism is a contained change in the service layer
— ADR-0003 already names `SELECT FOR UPDATE` plus retry as the replacement if the backend changes.
Making idempotency optional after callers have relied on it is a contract change on a published
interface.

## Revisit when

- A single entity's write concurrency makes per-entity serialisation a **measured** bottleneck.
  ADR-0003 names this as a revisit trigger for the storage decision too.
- The storage backend changes to one without advisory locks, which is the documented DSQL scenario.
- Idempotency record storage becomes significant, which is a retention-policy question rather than
  a mechanism question.
