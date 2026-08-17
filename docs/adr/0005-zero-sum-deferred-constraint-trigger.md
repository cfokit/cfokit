# ADR-0005: Zero-sum is enforced by a deferred constraint trigger in the database

- **Status:** Accepted
- **Date:** 2026-08-17
- **Deciders:** Geoff

## Context

The defining invariant of double-entry accounting is that every transaction sums to zero per
commodity. A transaction that does not balance has created or destroyed money.

The application will of course validate this. The question is whether that is *sufficient*, and it
is not — for a reason specific to how software decays rather than how it is first written. The
validation lives on one code path. Over time there are more paths: a bulk import, a correction
routine, a migration backfill, a fixture loader, an admin repair script written during an incident.
Each is written by someone who knows the invariant matters and assumes the layer beneath enforces
it. The failure is silent, produces no error, and is discovered when a trial balance does not tie
months later — by which point the offending transaction is indistinguishable from the correct ones
around it.

A database constraint is the only check that no code path can bypass, including paths written
under pressure at 2am by someone who did not read this file.

There is a mechanical complication. Postings are inserted individually, so a transaction is
*legitimately* unbalanced between the first insert and the last. Any check that fires per-statement
would reject every valid transaction.

## Decision

Zero-sum per commodity is enforced by a **deferred constraint trigger**, checked at `COMMIT`.

- Deferred, so the intermediate states during multi-row insertion are permitted.
- A constraint trigger rather than application code, so no code path can avoid it.
- Per commodity, so a multi-currency transaction must balance in each commodity independently.
- Enforced **at posting**, not at draft creation — a draft may be unbalanced while it is still
  being worked on (ADR-0006).

Application-layer validation remains, to produce a good error message with a stable `code` before
the database produces a blunt one. The application check is for ergonomics; the trigger is for
correctness.

## Alternatives rejected

### Application-layer validation only

Simpler, portable across databases, easier to test, and produces better error messages. This is
what most systems do, and it is not unreasonable.

Rejected because it is only as reliable as the discipline of every future code path, and the
failure mode is silent money creation in a system whose entire value proposition is that this
cannot happen. ADR-0002 chose Postgres partly *for* this capability, and listed the loss of
cross-item constraints as one of five disqualifying reasons against DynamoDB. Declining to use the
capability we chose the database for would be incoherent.

### An immediate (non-deferred) constraint trigger

Stricter and simpler to reason about: the invariant holds after every statement rather than only at
commit.

Rejected because it is not implementable. Postings are inserted one row at a time, so the
transaction is unbalanced after the first insert. An immediate check would reject every valid
transaction, and working around it would mean constructing all postings in a single statement — a
constraint on how every write is written, imposed to satisfy the checking mechanism rather than the
invariant.

### A `CHECK` constraint

The natural first thought, and the cheapest mechanism if it worked.

Rejected because `CHECK` constraints operate on a single row. Zero-sum is a property of a *set* of
postings, which is outside what `CHECK` can express.

### A materialised balance column, kept consistent by the application

Store a running total per transaction and constrain it to zero.

Rejected because it denormalises state that is derivable, and correctness then depends on the
column being maintained correctly — which is the same class of problem one layer down, now with
the added possibility of the materialised value disagreeing with the postings it summarises.
ADR-0002 rejected materialised balances generally, on the grounds that they should be introduced
under profiler evidence rather than as a correctness mechanism.

### Application validation plus a periodic reconciliation job

Check continuously in code, and sweep for violations nightly.

Rejected because it detects after the fact. Money has already been created, reports may already
have been issued from the broken state, and — under ADR-0006 — the offending entry cannot be
deleted, only reversed. Prevention and detection are not interchangeable when the records are
append-only.

### `SERIALIZABLE` isolation instead of an explicit constraint

Would prevent some anomalies without a trigger.

Rejected because it addresses concurrency, not correctness of a single transaction's contents. A
single-threaded write of an unbalanced transaction is perfectly serialisable and still wrong.

## Consequences

**Accepted costs.**
- The invariant is expressed in SQL, in a migration, rather than in Python where most contributors
  will look for it. It needs a pointer from the code.
- Trigger overhead at commit on every write.
- Error messages from a constraint trigger are poor, which is why the application check stays.
- It ties CFOKit to a database with deferred constraint triggers. ADR-0002 already accepted this,
  and named it as the reason Aurora DSQL is deferred rather than chosen.

**Follow-on obligations.**
- The trigger is created in a migration and is covered by tests that attempt to insert unbalanced
  transactions through *every* write path, including any bulk or administrative one.
- The check applies per commodity, not to a summed total across commodities.
- It fires at posting. The draft/posted boundary must therefore exist in the schema before this
  trigger is meaningful (ADR-0006).
- Application-layer validation produces a stable error `code` (ADR-0015) so callers can distinguish
  an unbalanced transaction from other failures.
- Any future backfill or repair tooling runs through the same constraint. There is no bypass, and
  none should be added.

**Reversal cost. Low mechanically, high in confidence.** Dropping the trigger is one migration.
But every transaction written while it was absent would have to be re-verified, and the guarantee
that no path ever bypassed it could not be reconstructed after the fact.

## Revisit when

- The storage backend changes to one without deferred constraint triggers — Aurora DSQL is the
  named candidate (ADR-0002). The replacement would be an application-layer check plus
  `SELECT FOR UPDATE`, which is a real weakening and should be recorded as such.
- Commit-time trigger overhead is a **measured** bottleneck under profiling. Anticipated overhead
  is not a trigger for revisiting.
