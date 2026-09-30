---
status: "accepted"
kind: "requirement-driven"
date: 2026-08-16
decision-makers: [Geoff]
---

# ADR-0003: Use Postgres as the sole storage backend

**Requirements served:** `LED-03`, `LED-13`, `RPT-06`, `NFR-11`.

## Context and Problem Statement

CFOKit Ledger is a multi-tenant double-entry accounting engine serving an agent skill
over MCP and third parties over REST. The workload is thousands of entities, each with
hundreds to low tens of thousands of transactions, mostly idle, with low write
concurrency per entity and high parallelism across entities.

Correctness constraints that bear on storage choice:

- Zero-sum per commodity must hold for every transaction.
- FIFO lot selection is a read-modify-write against lot state, so concurrent disposals
  can consume the same lot without explicit serialization.
- Balances are derived by aggregation over postings.
- Backdated entries can invalidate the cost basis of every later disposal.
- Reporting is inherently ad-hoc: trial balance as of an arbitrary date, P&L for an
  arbitrary period, journal filtered by account, payee, or tag.

Self-hosting is a product promise, not a convenience (ADR-0004).

## Decision Drivers

* A database-level guard against silently creating money — the zero-sum invariant must not
  live only in application code.
* Aggregation and ad-hoc query support, because accounting reporting and a public REST API
  cannot have their access patterns designed in advance.
* Explicit serialization primitives for read-modify-write against lot state.
* One storage implementation, not two — a correctness-critical system maintained twice is
  maintained badly.
* Self-hostability with no cloud account (ADR-0004).

## Considered Options

* PostgreSQL as the sole backend
* Embedded per-client ledger file (SQLite)
* DynamoDB, with AWS Amplify
* Aurora DSQL

## Decision Outcome

Chosen option: **PostgreSQL as the sole storage backend.** No second store will be added,
including for local development.

### Consequences

* Good, because the zero-sum invariant can be enforced by a deferred constraint trigger
  rather than by application code alone (ADR-0006).
* Good, because `pg_advisory_xact_lock` gives per-entity write serialization directly
  (ADR-0011).
* Good, because ad-hoc reporting is `SUM()` over postings rather than a set of access
  patterns designed in advance.
* Bad, because self-hosters run a Postgres container rather than nothing.
* Bad, because always-on Postgres in the managed tier costs more at low utilization than a
  pay-per-request store would.

### Confirmation

`compose.yaml` brings up service and Postgres and is exercised in CI as gate 2 (ADR-0004).
Row-level security keyed on `entity_id` is enforced and proved from outside, as the
application role, in `tests/integration/test_entity_isolation.py`. It is the enforcing layer:
a repository read addresses a transaction by id and relies on the scope set on the session, so
isolation is a property of the database rather than of each query. The deferred constraint
trigger (ADR-0006) enforces zero-sum, and is exercised in
`tests/integration/test_schema_invariants.py`.

## Pros and Cons of the Options

### PostgreSQL

* Good, because it supplies every primitive the correctness constraints need: deferred
  constraint triggers, advisory locks, `NUMERIC` at arbitrary precision, aggregation, RLS.
* Good, because it is available everywhere, including with no cloud account at all.
* Bad, because it does not scale to zero, which is the one economic argument against it.

### Embedded per-client ledger file (SQLite)

*The original working approach, superseded by this record.*

* Good, because it mirrors one-Beancount-file-per-client and keeps the "your ledger is one
  portable file you own" promise literal.
* Bad, because it is single-writer, which stopped working once multi-tenant hosting became
  the point of the system.
* Bad, because it has no deferred constraint triggers and no decimal type — money would need
  scaled integers or TEXT plus app-layer `Decimal`.
* Bad, because keeping it alongside Postgres means maintaining two storage implementations of
  a correctness-critical system forever.

### DynamoDB, with AWS Amplify

* Good, because of scale-to-zero economics across many idle tenants.
* Good, because there is no connection-pool problem in front of Lambda.
* Good, because per-tenant partition isolation is natural.
* Good, because the Number type is genuinely suitable for money — 38 digits of exact decimal
  precision, and float-to-Decimal conversion overflows the limit and fails loudly rather than
  rounding silently.
* Bad, because **transaction size** caps out: `TransactWriteItems` allows 100 actions and
  4 MB, and no two actions may target the same item. A journal entry needs one transaction
  item, N postings, N balance updates, lot updates, and an idempotency record — a 20-line
  payroll entry lands near 60 items and a month-end batch exceeds 100. The same-item
  restriction also makes a FIFO disposal spanning one lot twice inexpressible in a single
  transaction.
* Bad, because there is **no aggregation**. There is no `SUM()`. Materialized running balances
  become mandatory from day one rather than an optimization introduced under profiler evidence.
* Bad, because **backdating becomes structural**. With materialized balances, a backdated entry
  requires rewriting every downstream balance item in 100-item non-atomic batches. The
  backdating policy stops being a choice (ADR-0013).
* Bad, because there are **no cross-item constraints**. The zero-sum invariant would live only
  in application code. For a system whose value proposition is that the books are correct,
  losing the database-level guard against silently creating money is disqualifying.
* Bad, because there are **no ad-hoc queries**. Every access pattern must be designed in
  advance, which conflicts with both accounting reporting and a public REST API third parties
  build on.

Supporting signal: AWS retired QLDB, its purpose-built ledger database, on 31 July 2025 and
directed customers to Aurora PostgreSQL.

### Aurora DSQL

The strongest serverless option — GA 27 May 2025. **Not rejected on merit, but deferred.**

* Good, because it is PostgreSQL wire compatible, scales to zero, and retains SQL and
  aggregation.
* Good, because wire compatibility makes adopting it later a configuration change plus two
  targeted code changes, not a port. That is why it is deferred rather than chosen now, and
  why no DynamoDB path is kept open.
* Bad, because it supports neither triggers (breaking the deferred zero-sum constraint) nor
  advisory locks (breaking the entity write lock in ADR-0011).
* Bad, because it fixes isolation at Repeatable Read and uses optimistic concurrency requiring
  commit-time retry logic.
* Neutral, because RLS support is unverified.

## More Information

**Follow-on obligations.**

- Deferred constraint trigger for zero-sum (ADR-0006).
- `pg_advisory_xact_lock` per entity on all writes (ADR-0011).
- Row-level security keyed on `entity_id`, plus explicit service-layer filtering.
- `compose.yaml` bringing up service and Postgres, exercised in CI (ADR-0004).

**Reversal cost.** Moving to DSQL is low: replace the trigger with an application-layer check
and the advisory lock with `SELECT FOR UPDATE` plus retry. Moving to DynamoDB is a rewrite of
the store and service layers and a redesign of the reporting surface.

## Revisit when

- Managed-tier database cost at low utilization exceeds compute cost, **and** DSQL has
  confirmed RLS support. At that point evaluate DSQL specifically, not DynamoDB.
- A single entity's write concurrency makes per-entity serialization a measured bottleneck.
