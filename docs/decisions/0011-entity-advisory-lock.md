---
status: "draft"
kind: "requirement-driven"
date: 2026-08-17
decision-makers: [Geoff]
---

# ADR-0011: Writes serialize on a per-entity advisory lock

**Requirements served:** `LED-13`, `NFR-02`.

## Context and Problem Statement

The workload is thousands of entities, mostly idle, with low write concurrency *per entity* and high
parallelism *across* entities (ADR-0003).

Writes within one entity must not interleave in ways that corrupt derived state. Read-modify-write
against lot state is the concrete case ADR-0003 cited: two concurrent writes that each read the same
starting state and then both write produce a result neither would have produced alone.

Writes across entities must not block each other at all. That property is what makes one deployment
viable for a fractional CFO holding many clients (`LED-13`), and losing it would turn an idle-heavy
multi-tenant workload into a single-writer system.

Retry safety is a separate problem with a separate mechanism, held in
[ADR-0029](0029-mandatory-idempotency-keys.md). Serialization does not make a retry safe, and
idempotency does not order concurrent writes; conflating them produces a design that does neither
well.

## Decision Drivers

* Writes across entities must never contend, or multi-tenant hosting stops being viable (`LED-13`).
* Serialization must be deterministic and testable, rather than dependent on conflict detection that
  is hard to reproduce.
* No failure path may leak a held lock.
* The mechanism must protect both protocol surfaces, including MCP, which never passes through HTTP
  (ADR-0009).

## Considered Options

* Per-entity `pg_advisory_xact_lock`, taken in the service layer
* Optimistic concurrency with retry on conflict
* `SELECT ... FOR UPDATE` on the entity row
* Table-level or global locking
* `SERIALIZABLE` isolation instead of explicit locking

## Decision Outcome

Chosen option: "Per-entity `pg_advisory_xact_lock`, taken in the service layer", because it gives
deterministic serialization scoped exactly to the entity, with no lock to leak and no retry logic
pushed onto callers.

> Every write takes `pg_advisory_xact_lock` keyed on the entity, in the service layer, before the
> state-changing work and in the same transaction as it.

- The lock is transaction-scoped, so it releases at commit or rollback with no explicit unlock and no
  leak on failure.
- It is keyed on `entity_id`, so writes to different entities never contend.
- It is taken in the **service layer**, not in adapters or in the repository, so it applies uniformly
  across both protocol surfaces.

Entity grants are validated server-side on every request regardless of token contents. That is
authorization rather than concurrency, and is noted here only because `CLAUDE.md` groups them.

### Consequences

* Good, because contention is deterministic and local to one entity, which is far easier to reason
  about and to test than conflict-abort-retry.
* Good, because the lock is transaction-scoped, so no failure path leaks it.
* Good, because an advisory lock says what it is, rather than overloading a data row with a control
  meaning.
* Bad, because writes to one entity serialize, so a long-running write blocks others for that entity.
  Acceptable given per-entity write concurrency is low by workload assumption, and it is the reason
  any long-running operation belongs on a non-request path (ADR-0017).
* Bad, because advisory lock keys must be derived from `entity_id` by a documented, collision-free
  scheme, since the advisory namespace is global and shared across the database.

### Confirmation

Serialization is proved by actually running concurrent writes rather than by inspection.
`tests/integration/test_write_path.py::test_writes_to_one_entity_serialize` holds the entity's
advisory lock on one connection and starts a service write on another: the write must block, which
it would not do had it failed to take the same lock, and must complete once the lock is released.

`scripts/check_async.py` protects the property the lock depends on: no `await` can appear in code
holding the lock, because async constructs are rejected throughout the ledger's service layer
(ADR-0024). Without that, a yield mid-transaction would hold the lock across a suspension point.

## Pros and Cons of the Options

### Per-entity `pg_advisory_xact_lock`, taken in the service layer

* Good, because it is deterministic, scoped to the entity, and self-releasing.
* Good, because it names itself: a reader sees a lock, not a row that happens to be load-bearing.
* Bad, because the advisory namespace is global, so key derivation must be documented and
  collision-free.
* Bad, because it is Postgres-specific, which ADR-0003 already accepts as a general condition.

### Optimistic concurrency with retry on conflict

* Good, because it costs nothing in the uncontended case, which is nearly all cases here given how
  idle most entities are.
* Good, because it is what a distributed SQL backend would force anyway (ADR-0003).
* Bad, because it moves retry logic into every write path, and retry-on-conflict interacts badly with
  the retries already arriving from agents — a client retry of a transaction that itself retried
  internally is difficult to reason about, and the ambiguity compounds.
* Bad, because it would be insufficient on its own for read-modify-write against lot state, which
  ADR-0003 explicitly cited as a serialization requirement, so it would need supplementing anyway.

### `SELECT ... FOR UPDATE` on the entity row

The conventional approach, and genuinely close in effect. **This is the alternative most likely to be
re-proposed, and it is a reasonable choice** — it is simply less explicit, and it is the documented
fallback should the backend change.

* Good, because it works, requires no advisory-lock namespace, and is portable to any SQL database.
* Bad, because it requires a lockable row to exist for every entity and couples the lock to that
  row's lifecycle, so deleting or replacing the row has concurrency consequences that are not obvious
  from reading it.
* Bad, because it conflates data with a control mechanism: a reader of the schema cannot tell the row
  is load-bearing for serialization.

### Table-level or global locking

* Good, because it is simplest to reason about and trivially correct.
* Bad, because it serializes writes across all entities, which destroys the high-parallelism property
  that makes one deployment viable for a fractional CFO with many clients (`LED-13`).

### `SERIALIZABLE` isolation instead of explicit locking

* Good, because Postgres would detect conflicting interleavings and abort one transaction, with no
  lock discipline required of application code.
* Bad, because it produces serialization failures under contention that every caller must handle,
  which is retry logic again, now triggered by conditions that are hard to reproduce in tests.

## More Information

**Follow-on obligations.**

- The advisory lock is taken in the service layer, not in adapters or in the repository.
- Lock acquisition happens before the state-changing work, in the same transaction as the write.
- Advisory lock keys are derived from `entity_id` by a documented, collision-free scheme.
- Nothing `await`s while the lock is held (ADR-0024).
- Long-running operations that hold the lock — `rebook` in particular — run on a compute path with no
  request timeout (ADR-0017).

**Reversal cost. Moderate.** Swapping the lock mechanism is a contained change in the service layer —
ADR-0003 already names `SELECT FOR UPDATE` plus retry as the replacement if the backend changes.

Related: [ADR-0029](0029-mandatory-idempotency-keys.md) solves retry safety, which this record
deliberately does not.

## Revisit when

- A single entity's write concurrency makes per-entity serialization a **measured** bottleneck.
  ADR-0003 names this as a revisit trigger for the storage decision too.
- The storage backend changes to one without advisory locks, which is the documented DSQL scenario.
