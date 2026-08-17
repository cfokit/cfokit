# ADR-0002: Use Postgres as the sole storage backend

- **Status:** Accepted
- **Date:** 2026-08-16
- **Deciders:** Geoff

## Context

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

Self-hosting is a product promise, not a convenience (ADR-0003).

## Decision

We will use PostgreSQL as the sole storage backend. No second store will be added,
including for local development.

## Alternatives rejected

### Embedded per-client ledger file (SQLite)

*The original working approach, superseded by this record.*

Attractive because it mirrors one-Beancount-file-per-client and keeps the "your ledger
is one portable file you own" promise literal. Rejected once multi-tenant hosting
became the point of the system: single-writer concurrency, no deferred constraint
triggers, and no decimal type (requiring scaled integers or TEXT plus app-layer
`Decimal`). Keeping it as a second backend alongside Postgres would mean maintaining
two storage implementations of a correctness-critical system forever.

### DynamoDB (with AWS Amplify)

Attractive for scale-to-zero economics across many idle tenants, no connection-pool
problem in front of Lambda, and natural per-tenant partition isolation. The Number type
is also genuinely suitable for money — 38 digits of exact decimal precision, and
float-to-Decimal conversion overflows the limit and fails loudly rather than rounding
silently.

Rejected on five counts:

1. **Transaction size.** `TransactWriteItems` caps at 100 actions and 4 MB, and no two
   actions may target the same item. A journal entry needs one transaction item, N
   postings, N balance updates, lot updates, and an idempotency record — a 20-line
   payroll entry lands near 60 items and a month-end batch exceeds 100. The same-item
   restriction also makes a FIFO disposal spanning one lot twice inexpressible in a
   single transaction.
2. **No aggregation.** There is no `SUM()`. Materialized running balances become
   mandatory from day one rather than an optimization introduced under profiler
   evidence.
3. **Backdating becomes structural.** With materialized balances, a backdated entry
   requires rewriting every downstream balance item in 100-item non-atomic batches.
   The backdating policy stops being a choice (ADR-0013).
4. **No cross-item constraints.** The zero-sum invariant would live only in
   application code. For a system whose value proposition is that the books are
   correct, losing the database-level guard against silently creating money is
   disqualifying.
5. **No ad-hoc queries.** Every access pattern must be designed in advance, which
   conflicts with both accounting reporting and a public REST API third parties build
   on.

Supporting signal: AWS retired QLDB, its purpose-built ledger database, on 31 July 2025
and directed customers to Aurora PostgreSQL.

### Aurora DSQL

The strongest serverless option — GA 27 May 2025, PostgreSQL wire compatible, scales to
zero, retains SQL and aggregation. Not rejected on merit, but deferred: it supports
neither triggers (breaking the deferred zero-sum constraint) nor advisory locks
(breaking the entity write lock in ADR-0011), fixes isolation at Repeatable Read, and
uses optimistic concurrency requiring commit-time retry logic. RLS support is
unverified.

Because DSQL speaks the Postgres wire protocol, adopting it later is a configuration
change plus two targeted code changes, not a port. That is the reason it is deferred
rather than chosen now, and the reason no DynamoDB path is kept open.

## Consequences

**Accepted costs.** Self-hosters run a Postgres container rather than nothing.
Always-on Postgres in the managed tier costs more at low utilization than a
pay-per-request store would.

**Follow-on obligations.**
- Deferred constraint trigger for zero-sum (ADR-0005).
- `pg_advisory_xact_lock` per entity on all writes (ADR-0011).
- Row-level security keyed on `entity_id`, plus explicit service-layer filtering.
- `compose.yaml` bringing up service and Postgres, exercised in CI (ADR-0003).

**Reversal cost.** Moving to DSQL is low: replace the trigger with an application-layer
check and the advisory lock with `SELECT FOR UPDATE` plus retry. Moving to DynamoDB is
a rewrite of the store and service layers and a redesign of the reporting surface.

## Revisit when

- Managed-tier database cost at low utilization exceeds compute cost, **and** DSQL has
  confirmed RLS support. At that point evaluate DSQL specifically, not DynamoDB.
- A single entity's write concurrency makes per-entity serialization a measured
  bottleneck.
