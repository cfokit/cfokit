---
status: "draft"
kind: "requirement-driven"
date: 2026-08-17
decision-makers: [Geoff]
---

# ADR-0029: Idempotency keys are mandatory on every write

**Requirements served:** `NFR-03`, `PLT-20`.

## Context and Problem Statement

Writes arrive from agents over HTTP, across networks that fail in the ambiguous direction: the caller
does not learn whether a request that timed out was applied. The correct client behaviour is to
retry, and agents will retry — reliably and without judgement.

In an append-only ledger a duplicated write cannot be deleted, only reversed (ADR-0007), so a
double-book is a permanent scar on the audit trail rather than a cleanup task. `NFR-03` obliges a
retried operation to produce the same result and create no duplicate record.

Serialisation is a separate problem with a separate mechanism, held in
[ADR-0011](0011-entity-advisory-lock.md). A lock orders concurrent writes; it does nothing about a
retry arriving a minute later. Neither mechanism solves the other's problem.

## Decision Drivers

* A duplicated write is permanent under append-only semantics (ADR-0007), so prevention must not
  depend on caller judgement.
* A legitimately repeated transaction must remain distinguishable from a retry.
* Both protocol surfaces must be protected, including MCP, which never passes through HTTP
  (ADR-0009).
* Whatever records the keys needs a retention policy, since it accumulates indefinitely otherwise
  (`PLT-20`).

## Considered Options

* Mandatory idempotency keys, enforced in the service layer
* Optional idempotency keys, applied where callers choose
* Deduplicating by content hash instead of an explicit key
* Idempotency at the HTTP layer only, via `Idempotency-Key`

## Decision Outcome

Chosen option: "Mandatory idempotency keys, enforced in the service layer", because the write that
omits a key is the write that double-books, and making the key mandatory moves the decision from
runtime judgement to schema requirement.

> Every write carries an idempotency key. A write without one is rejected. A repeated key returns the
> original result rather than applying the operation again.

The check happens in the **service layer**, before the state-changing work and in the same
transaction as the write, so both adapters reach it.

### Consequences

* Good, because every write path can assume the key exists, removing a whole branch of conditional
  logic.
* Good, because a retry is distinguishable from a genuinely repeated transaction — two five-dollar
  coffees on the same day stay two transactions.
* Good, because it protects MCP as well as REST, which an HTTP-layer implementation would not.
* Bad, because callers must generate and manage idempotency keys, and this must be documented on both
  published surfaces (ADR-0015).
* Bad, because idempotency records need storage and a retention policy of their own — long enough to
  outlive any plausible retry, short enough not to accumulate indefinitely (`PLT-20`).
* Bad, because it is friction on every single write, including the ones nobody would ever retry.

### Confirmation

Enforced at the service boundary: a write without a key is rejected with a stable error `code`
(ADR-0015), which makes it testable from either adapter.

**The retention policy is not yet written**, so nothing currently prunes idempotency records.
`PLT-20` sets the retention schedule per record class at deployment scope, and this record class needs
an entry before the first production deployment rather than before the first release.

## Pros and Cons of the Options

### Mandatory idempotency keys, enforced in the service layer

* Good, because the protection cannot be omitted by the caller who did not think about failure.
* Good, because both adapters are covered by one implementation.
* Bad, because it adds a required parameter to every write, including trivially safe ones.
* Bad, because it introduces a record class that needs a retention policy.

### Optional idempotency keys, applied where callers choose

* Good, because there is less friction, and most operations are not obviously dangerous to repeat.
* Bad, because the one write that omits the key is the one that double-books, and the caller who omits
  it is the caller who did not think about failure. Making it mandatory moves the decision from
  runtime judgement to schema requirement.

### Deduplicating by content hash instead of an explicit key

* Good, because it requires nothing from the caller: hash the transaction and reject duplicates.
* Bad, because legitimately identical transactions exist. Two five-dollar coffees on the same day from
  the same merchant are two transactions, not a duplicate, and a content hash cannot tell them apart
  from a retry. Suppressing the second one silently loses a real transaction, which is worse than
  double-booking because nothing indicates it happened.

### Idempotency at the HTTP layer only, via `Idempotency-Key`

* Good, because it is standard, and it is where the header belongs.
* Bad, as *sufficient* rather than as a mechanism. MCP calls the service layer in-process and never
  passes through HTTP (ADR-0009), so an HTTP-layer implementation would leave the primary consumer
  surface unprotected. The requirement belongs in the service layer, where both adapters reach it.

## More Information

**Follow-on obligations.**

- The idempotency check happens in the service layer, before the state-changing work, in the same
  transaction as the write.
- A replayed key returns the original result, and must not silently succeed with a different one — a
  key reused with different parameters is a client error and gets a stable error `code` (ADR-0015).
- The audit trail records one row per state-changing call; a replayed idempotent request is not a new
  state change and must not write a second row.
- A retention policy for idempotency records, under `PLT-20`.
- Key generation is documented on both published surfaces (ADR-0015).

**Reversal cost. Moderate.** Making idempotency optional after callers have relied on it being
mandatory is a contract change on a published interface.

Related: [ADR-0011](0011-entity-advisory-lock.md) solves serialisation, which this record deliberately
does not.

## Revisit when

- Idempotency record storage becomes significant, which is a retention-policy question rather than a
  mechanism question.
- A write path appears where a caller genuinely cannot generate a key, which would be a signal that
  the surface is wrong rather than that the rule should relax.
