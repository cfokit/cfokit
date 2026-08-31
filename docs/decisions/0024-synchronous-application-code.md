---
status: "draft"
kind: "substrate"
date: 2026-08-19
decision-makers: [Geoff]
---

# ADR-0024: The ledger is synchronous; async is permitted outside it

> **This record also fixes a gap.** `CLAUDE.md` has carried "Synchronous throughout — do not
> introduce async without an ADR" citing ADR-0012, but ADR-0012 never mentions async: its non-goals
> are a web UI, plugin system, custom query language, caching layer, read replicas, GraphQL,
> websockets/SSE, and an event bus. The sync rule was cited and unwritten. This is its record.

## Context

Two things need deciding together, because the second follows from the first: whether the codebase is
synchronous, and which web framework serves REST.

**The forcing constraint is the MCP SDK.** It is async, built on anyio. The alternative is
implementing the protocol by hand, which means tracking a spec that is actively moving — ADR-0019
records DCR being deprecated for Client ID Metadata Documents within the past year — in the component
that determines whether agents can reach the ledger at all.

**What async would buy elsewhere is little, though not nothing — and an earlier draft of this record
got the reason wrong.** It claimed psycopg is a blocking driver. That is true of psycopg2 and false
of psycopg 3, which ships `AsyncConnection`, `AsyncCursor`, `AsyncTransaction` and `AsyncPipeline`.
A fully async stack is therefore achievable with the driver already chosen, and would give real
concurrency rather than a threadpool.

The honest reason to decline it is the workload, not the driver: thousands of mostly-idle entities
with low per-entity write concurrency (ADR-0003). There is very little concurrency to reclaim, and
buying it costs a second execution model across every layer.

A second reason is sharper than the first. **In synchronous code, an `await` inside a transaction is
not expressible.** In async it is one line, it looks correct, and it can yield a connection
mid-transaction while an advisory lock is held (ADR-0011). Sync makes transaction and lock affinity a
property of the language; async makes it a matter of discipline.

**But "no event loop anywhere" turns out not to be worth paying for.** An earlier draft of this record
chose Flask specifically to keep an event loop off the REST path, on the grounds that
connection-and-transaction affinity matters for advisory locking (ADR-0011). On inspection that does
not hold: a synchronous `def` handler under Starlette runs start to finish in a single threadpool
thread, never yielding, so the connection and transaction stay on one thread exactly as they do under
a threaded WSGI worker. The property is preserved either way.

The supporting dependency argument also inverted when measured. Because the MCP SDK already brings
starlette and pydantic:

| REST framework | Total resolved | Net new |
|---|---|---|
| `flask` + `apiflask` | 46 | 15 — apiflask, apispec, marshmallow, webargs, werkzeug, jinja2, … |
| `fastapi` | 33 | 2 — fastapi, annotated-doc |

So the rule that runtime dependencies are few and load-bearing argues **for** FastAPI, not against it.

A sanity check that ought to have been applied earlier: psycopg is the most-used Postgres driver and
FastAPI is the most-used Python web framework. If combining a blocking driver with an ASGI framework
were genuinely problematic, that pairing would not be ubiquitous.

## Decision

**The ledger's write path is synchronous. Everything else may choose.**

The boundary is the ledger, not the language. What the argument below actually supports is keeping
`await` out of code that holds a transaction and an advisory lock — which is the ledger, and nothing
else.

- **No `async def`, no `await`, no `asyncio`/`anyio`/`trio` import** in the ledger's `engine`,
  `repository`, `service`, or `api` adapter.
- **`cfokit.ledger.mcp` is exempt**, because the SDK requires it. That module owns its own event loop
  and may block it calling synchronous service code; the loop serves only MCP and the work is short.
- **Modules and components are unconstrained.** Ingestion, invoice delivery, notifications and email
  are I/O-bound against third parties, which is the workload async exists for. A component is a
  separate runtime reaching the ledger over HTTP (ADR-0022, ADR-0023), so its execution model costs
  the write path nothing. An in-process module sharing the ledger's transaction is bound by the first
  rule for that work, and free otherwise.
- **REST is FastAPI**, with **synchronous `def` handlers only**. The event loop lives in the server,
  not in our code. OpenAPI generation is native, which CI gate 5 requires as a committed, diffed
  artifact (ADR-0015).
- **Nothing async crosses into the service layer.** Coroutines, tasks, and async context managers do
  not reach it. What it receives and returns is ordinary synchronous Python.
- ADR-0009 is preserved: MCP still calls the service layer **in-process**, which meant *not looping
  back through HTTP*, and still does.

**What this does not do.** Synchronous code does not make the ledger single-threaded and does not
eliminate concurrency. The service scales horizontally, so two instances write the same entity
concurrently as a matter of course; sync `def` handlers run in anyio's threadpool, forty at a time by
default; and database anomalies are unaffected by the calling convention. Concurrency safety comes
from `pg_advisory_xact_lock` per entity, the deferred zero-sum trigger, mandatory idempotency keys
and row-level security (ADR-0003, ADR-0006, ADR-0011) — every one of which holds identically under
`AsyncConnection`. What sync buys is narrower and worth stating exactly: **an `await` inside a
transaction is not expressible.** It removes a footgun; it does not supply a guarantee.

**Enforced, not asserted.** `scripts/check_async.py` walks the AST of the ledger package and fails on
async constructs outside `cfokit.ledger.mcp`. It runs inside `uv run task lint`, beside the
import-linter contracts. This matters *more* under FastAPI than it would have under Flask: the
framework now permits `async def`, and the gate is what makes choosing not to use it a property
rather than a preference.

## Alternatives rejected

### Async throughout

The conventional modern Python choice, and it would remove the boundary entirely.

Rejected on the workload rather than on the driver — psycopg 3 supports async perfectly well, and an
earlier draft of this record wrongly said otherwise. There is little concurrency to reclaim from
mostly-idle entities, and the cost is a second execution model in every layer including the pure
engine, plus transaction and lock affinity becoming a discipline rather than a property: `async def`
can yield mid-transaction in a way `def` cannot.

The pure engine, the migration runner, the CLI, and the Beancount oracle harness are all naturally
synchronous. Async would be adopted for the sake of one adapter.

### Flask with APIFlask, to keep an event loop off the REST path entirely

This record's earlier decision, now reversed. It is the most defensible-sounding option and it fails
on measurement.

Rejected on three counts. The affinity argument does not hold — a sync `def` handler under Starlette
occupies one thread for its whole duration, so nothing yields mid-transaction. The dependency argument
inverts: 15 net new packages against FastAPI's 2, because starlette and pydantic arrive with the MCP
SDK regardless. And it would mean **two web stacks**, WSGI and ASGI, with two servers to configure,
where one suffices.

Its remaining merit was that application code could not accidentally become async. The gate provides
that directly, without the other costs.

### FastAPI with `async def` handlers

The idiomatic way to use the framework, and it would let the REST path await outbound calls.

Rejected on the hazard, not on performance. psycopg 3's `AsyncConnection` means an `async def` handler
*would* genuinely await the database rather than hopping to a thread — so this option is faster in
principle, and that should be stated plainly. What it also does is make `await` inside a transaction
expressible, which is the one failure mode that costs correctness rather than latency. Given a
workload with little concurrency to gain, that is a poor trade.

### Stay synchronous and implement MCP by hand

Keeps the rule absolute and adds no dependency.

Rejected because it means owning an implementation of a moving protocol in the component that
determines whether any agent can reach the ledger. Unbounded maintenance, and the failure mode is
silent incompatibility with clients we do not control.

### Run MCP as a separate component talking to REST over HTTP

Would confine async to another process entirely.

Rejected because it contradicts ADR-0009: in-process was chosen to avoid a second authentication hop,
doubled latency, and a service dialling its own ingress. Those reasons are unchanged.

## Consequences

**Accepted costs.**
- Two execution models in one codebase. Confined to one module and machine-checked, but a contributor
  working in `mcp` is somewhere different and must know it.
- The MCP module blocks its own event loop by design. Correct here, and it will look wrong to anyone
  who assumes async implies concurrency.
- **Sync handlers under ASGI run in anyio's threadpool, default 40 threads.** That is a concurrency
  ceiling, and it must be sized against the Postgres connection pool. Mis-sizing shows up as queuing
  latency rather than as an error — the one genuine operational cost of this arrangement.
- Contributors will propose `async def` handlers, because that is how FastAPI is normally written.
  That is what the gate and this record are for.
- The MCP SDK remains the heaviest dependency, bringing roughly twenty transitive packages.
- `sse-starlette` arrives transitively while SSE transport is a binding non-goal (ADR-0012). Present
  is not used; *using* it would be a scope-gate decision.

**Follow-on obligations.**
- `scripts/check_async.py` enforcing the boundary, inside `uv run task lint`. **Already in place**,
  with tests, and observed to reject async in the service layer while permitting it in `mcp`.
- The anyio threadpool size and the connection pool size are configured together and documented in
  `infra/README.md`.
- MCP handlers call the service layer synchronously and never `await` while a transaction or advisory
  lock is held (ADR-0011).
- If a service-layer signature would need to be `async` to satisfy an MCP handler, that is the
  boundary being violated, not the service needing to change.
- `CLAUDE.md` cites **this** record for the sync rule, not ADR-0012.

**Reversal cost. Lower than it first appears, in both directions.** psycopg 3 is dual-mode, so going
async later is `AsyncConnection` in place of `Connection` — the same library, the same SQL, the same
pooling story. No driver migration, no re-verification of query behaviour. That is a genuine
advantage of the driver choice and it means this decision is cheap to defer rather than expensive to
get wrong. Retracting async after service signatures have become `async` is the harder direction,
which is why the gate exists before the code does.

## Revisit when

- The MCP SDK offers a synchronous API, which would remove the exception entirely.
- A **measured** need for real concurrency appears. The move is then `psycopg.AsyncConnection`
  throughout rather than a driver change, since psycopg 3 is already dual-mode. `asyncpg`
  (Apache-2.0) is the faster pure-async alternative if profiling ever justifies it, at the cost of
  leaving DB-API and of its prepared-statement caching needing care behind a transaction-mode
  pooler.
- The threadpool or connection pool becomes a diagnosed bottleneck — an execution-model question
  rather than a boundary one.
