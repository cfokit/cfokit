---
status: "draft"
kind: "substrate"
date: 2026-08-19
decision-makers: [Geoff]
---

# ADR-0024: The ledger is synchronous; async is permitted outside it

## Context and Problem Statement

Two things need deciding together, because the second follows from the first: whether the ledger is
synchronous, and which web framework serves REST.

`CLAUDE.md` has carried a synchronous-throughout rule citing ADR-0012, which does not contain one —
that record's non-goals are a web UI, plugin system, custom query language, caching layer, read
replicas, GraphQL, websockets/SSE, and an event bus. The rule was cited and unwritten. This is its
record, and it is narrower than the rule it replaces.

**The forcing constraint is the MCP SDK.** It is async, built on anyio. The alternative is
implementing the protocol by hand, which means tracking a spec that is actively moving — ADR-0019
records DCR being deprecated for Client ID Metadata Documents within the past year — in the component
that determines whether agents can reach the ledger at all.

**A fully async stack is achievable with the driver already chosen.** psycopg 3 ships
`AsyncConnection`, `AsyncCursor`, `AsyncTransaction` and `AsyncPipeline`, so async would give real
concurrency rather than a threadpool. The reason to decline it is the workload, not the driver:
thousands of mostly-idle entities with low per-entity write concurrency (ADR-0003). There is very
little concurrency to reclaim, and buying it costs a second execution model across every layer.

A second reason is sharper than the first. **In synchronous code, an `await` inside a transaction is
not expressible.** In async it is one line, it looks correct, and it can yield a connection
mid-transaction while an advisory lock is held (ADR-0011). Sync makes transaction and lock affinity a
property of the language; async makes it a matter of discipline.

**Keeping an event loop off the REST path entirely is not worth paying for.** A synchronous `def`
handler under Starlette runs start to finish in a single threadpool thread, never yielding, so the
connection and transaction stay on one thread exactly as they do under a threaded WSGI worker. The
affinity property is preserved either way.

The dependency arithmetic points the same direction. Because the MCP SDK already brings starlette and
pydantic:

| REST framework | Total resolved | Net new |
|---|---|---|
| `flask` + `apiflask` | 46 | 15 — apiflask, apispec, marshmallow, webargs, werkzeug, jinja2, … |
| `fastapi` | 33 | 2 — fastapi, annotated-doc |

So the rule that runtime dependencies are few and load-bearing argues **for** FastAPI, not against it.
A sanity check confirms it: psycopg is the most-used Postgres driver and FastAPI is the most-used
Python web framework. If combining a blocking driver with an ASGI framework were genuinely
problematic, that pairing would not be ubiquitous.

## Decision Drivers

* Keep `await` out of code holding a transaction and an advisory lock (ADR-0011).
* Do not own an implementation of a moving protocol in the path agents depend on.
* Runtime dependencies are few and load-bearing; a framework choice is measured in net new packages.
* The workload is mostly-idle entities with low write concurrency, so reclaimed concurrency is worth
  little.
* Whatever is decided must be machine-checkable, or the framework's idioms will erode it.

## Considered Options

* The ledger is synchronous, REST is FastAPI with `def` handlers, async permitted outside the ledger
* Async throughout
* Flask with APIFlask, to keep an event loop off the REST path entirely
* FastAPI with `async def` handlers
* Stay synchronous and implement MCP by hand
* Run MCP as a separate component talking to REST over HTTP

## Decision Outcome

Chosen option: "The ledger is synchronous, REST is FastAPI with `def` handlers, async permitted
outside the ledger", because the property worth protecting is narrow — no `await` while holding a
transaction and a lock — and scoping the rule to the ledger buys it without imposing a second
execution model on I/O-bound work that would benefit from one.

**The boundary is the ledger, not the language.**

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

### What this does not do

Synchronous code does not make the ledger single-threaded and does not eliminate concurrency. The
service scales horizontally, so two instances write the same entity concurrently as a matter of
course; sync `def` handlers run in anyio's threadpool, forty at a time by default; and database
anomalies are unaffected by the calling convention.

Concurrency safety comes from `pg_advisory_xact_lock` per entity, the deferred zero-sum trigger,
mandatory idempotency keys and row-level security (ADR-0003, ADR-0006, ADR-0011, ADR-0029) — every one
of which holds identically under `AsyncConnection`. What sync buys is narrower and worth stating
exactly: **an `await` inside a transaction is not expressible.** It removes a footgun; it does not
supply a guarantee.

### Consequences

* Good, because the one failure mode that costs correctness rather than latency is made
  inexpressible in the code that could suffer from it.
* Good, because FastAPI adds two net new packages where the alternative adds fifteen, and avoids
  running two web stacks.
* Good, because I/O-bound components are free to use the execution model their workload actually
  wants.
* Bad, because there are two execution models in one codebase. Confined to one module and
  machine-checked, but a contributor working in `mcp` is somewhere different and must know it.
* Bad, because the MCP module blocks its own event loop by design. Correct here, and it will look
  wrong to anyone who assumes async implies concurrency.
* Bad, because **sync handlers under ASGI run in anyio's threadpool, default 40 threads.** That is a
  concurrency ceiling and must be sized against the Postgres connection pool. Mis-sizing shows up as
  queuing latency rather than as an error — the one genuine operational cost of this arrangement.
* Bad, because contributors will propose `async def` handlers, since that is how FastAPI is normally
  written.
* Neutral, because `sse-starlette` arrives transitively while SSE transport is a binding non-goal
  (ADR-0012). Present is not used; *using* it would be a scope-gate decision.

### Confirmation

`scripts/check_async.py` walks the AST of the ledger package and fails on async constructs outside
`cfokit.ledger.mcp`. It runs inside `uv run task lint`, beside the import-linter contracts. Already in
place, with tests, and observed to reject async in the service layer while permitting it in `mcp`.

This matters *more* under FastAPI than it would have under Flask: the framework permits `async def`,
and the gate is what makes choosing not to use it a property rather than a preference.

## Pros and Cons of the Options

### The ledger is synchronous, REST is FastAPI with `def` handlers, async outside the ledger

* Good, because it protects the transaction-and-lock path without taxing I/O-bound components.
* Good, because it is two net new dependencies and one web stack.
* Bad, because it puts two execution models in one codebase.
* Bad, because it depends on a gate to hold, since the framework's idiom points the other way.

### Async throughout

The conventional modern Python choice, and it would remove the boundary entirely.

* Good, because it is one execution model everywhere, and psycopg 3 supports it fully — this would
  give real concurrency rather than a threadpool.
* Bad, because there is little concurrency to reclaim from mostly-idle entities, and the cost is a
  second execution model in every layer including the pure engine.
* Bad, because transaction and lock affinity becomes a discipline rather than a property: `async def`
  can yield mid-transaction in a way `def` cannot.
* Bad, because the pure engine, the migration runner, the CLI, and the Beancount oracle harness are
  all naturally synchronous. Async would be adopted for the sake of one adapter.

### Flask with APIFlask, to keep an event loop off the REST path entirely

The most defensible-sounding option: no event loop anywhere in application code, so `async def` could
not be written by accident.

* Good, because application code could not accidentally become async, with no gate required.
* Bad, because the affinity argument it rests on does not hold — a sync `def` handler under Starlette
  occupies one thread for its whole duration, so nothing yields mid-transaction either way.
* Bad, because the dependency arithmetic inverts: 15 net new packages against FastAPI's 2, since
  starlette and pydantic arrive with the MCP SDK regardless.
* Bad, because it would mean **two web stacks**, WSGI and ASGI, with two servers to configure, where
  one suffices.

### FastAPI with `async def` handlers

The idiomatic way to use the framework, and it would let the REST path await outbound calls.

* Good, because psycopg 3's `AsyncConnection` means an `async def` handler *would* genuinely await
  the database rather than hopping to a thread. This option is faster in principle.
* Bad, because it makes `await` inside a transaction expressible, which is the one failure mode that
  costs correctness rather than latency. Given a workload with little concurrency to gain, that is a
  poor trade.

### Stay synchronous and implement MCP by hand

Keeps the rule absolute and adds no dependency.

* Good, because it removes the heaviest dependency in the project and the exemption along with it.
* Bad, because it means owning an implementation of a moving protocol in the component that determines
  whether any agent can reach the ledger. Unbounded maintenance, and the failure mode is silent
  incompatibility with clients we do not control.

### Run MCP as a separate component talking to REST over HTTP

Would confine async to another process entirely.

* Good, because the ledger deployable would then contain no async at all, exemption included.
* Bad, because it contradicts ADR-0009: in-process was chosen to avoid a second authentication hop,
  doubled latency, and a service dialling its own ingress. Those reasons are unchanged.

## More Information

**Follow-on obligations.**

* `scripts/check_async.py` enforcing the boundary, inside `uv run task lint`. Already in place.
* The anyio threadpool size and the connection pool size are configured together and documented in
  `infra/README.md`.
* MCP handlers call the service layer synchronously and never `await` while a transaction or advisory
  lock is held (ADR-0011).
* If a service-layer signature would need to be `async` to satisfy an MCP handler, that is the
  boundary being violated, not the service needing to change.
* `CLAUDE.md` cites **this** record for the sync rule, not ADR-0012.

**Reversal cost. Lower than it first appears, in both directions.** psycopg 3 is dual-mode, so going
async later is `AsyncConnection` in place of `Connection` — the same library, the same SQL, the same
pooling story. No driver migration, no re-verification of query behavior. That is a genuine advantage
of the driver choice and it means this decision is cheap to defer rather than expensive to get wrong.
Retracting async after service signatures have become `async` is the harder direction, which is why
the gate exists before the code does.

## Revisit when

* The MCP SDK offers a synchronous API, which would remove the exception entirely.
* A **measured** need for real concurrency appears. The move is then `psycopg.AsyncConnection`
  throughout rather than a driver change, since psycopg 3 is already dual-mode. `asyncpg`
  (Apache-2.0) is the faster pure-async alternative if profiling ever justifies it, at the cost of
  leaving DB-API and of its prepared-statement caching needing care behind a transaction-mode pooler.
* The threadpool or connection pool becomes a diagnosed bottleneck — an execution-model question
  rather than a boundary one.
