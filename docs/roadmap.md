# CFOKit — Work Plan

- **Status:** Current
- **Date:** 2026-08-17
- **Owner:** Geoff

Sequenced work toward the capabilities in [`product/requirements.md`](product/requirements.md).
Ordered so that each milestone is verifiable by a CI gate before the next begins.

## How this is used

- **Milestones are ordered by dependency, not by preference.** A milestone's exit criteria
  must be machine-verifiable — "reviewed and looks right" is not an exit criterion.
- **Work items cite `REQ-` ids.** An item that cites none is either infrastructure or scope
  creep; say which.
- **Nothing gets built before the decision it depends on is written.** The ADR backlog is
  therefore on the critical path, not adjacent to it.

## Toolchain versions

| Tool | Version | Why pinned here |
|---|---|---|
| Spec Kit | `v0.16.4` | Install: `uv tool install specify-cli --from git+https://github.com/github/spec-kit.git@v0.16.4`. Pinned because it regenerates templates on upgrade and we override two of them. |
| Python | `>=3.12` | `pyproject.toml` |

---

## M0 — Repository ready for agentic development — **complete**

**Goal:** every rule in `CLAUDE.md` is executable, and the product intent is written down.

Done: git repository with MIT licence; ADR index relocated; structure and naming settled
(ADR-0020); uv workspace with the documented task names; ruff, `mypy --strict`, import-linter
contracts, and the async boundary gate — each observed to fail when deliberately violated;
CI gate 4 implemented and unit-tested; vision, requirements, accounting policy and this plan
written; Spec Kit installed and pinned with local template overrides; `compose.yaml` plus dev
overlay; CI workflow; Dockerfile with the ADR-0024 entrypoints; the core schema migration with
its invariants verified against a real Postgres; `/healthz` and `/readyz`.

**Verified end to end:** `docker compose up` from a clean volume brings the stack healthy,
`/readyz` reports 503 with migrations pending, the explicit migrate job applies them, and
`/readyz` returns 200. Liveness stays 200 throughout, which is what proves migrations never run
at startup (ADR-0003).


---

## M1 — Decisions of record — **complete**

**Goal:** no rule in `CLAUDE.md` cites an ADR that does not exist.

**All 25 records are written and Accepted** (0001–0026; 0007 is deferred, not pending). Every
`CLAUDE.md` rule cites a record that says what the rule claims, checked semantically rather than
just for existence. Immutability now binds: a changed mind is a superseding ADR, not an edit.

Written during this milestone beyond the original backlog: **0020** repository layout, **0021**
Spec Kit workflow, **0022** Slack surface, **0023** ledger/module/component topology, **0024**
component deployment and authentication, **0025** synchronous application code, **0026** rounding
and allocation.

**Deferred, with an activation trigger rather than a date:** **0007** (STRICT and FIFO booking)
waits on REQ-A6 activating — an entity acquiring inventory or holding investments.

**Known open questions**, none blocking M2: rendered report output needs an ADR through the
ADR-0012 scope gate; the licence question is deliberately open (ADR-0001); the agent runtime is
undecided (ADR-0022 § 6); `packages/connectors` is named wrongly on purpose and awaits its
classification (ADR-0023).


---

## M2 — Booking engine

**Goal:** correct double-entry booking, provable against an independent implementation.
**Requirements:** REQ-A1, REQ-A3, REQ-A4, REQ-A5. **Not** REQ-A6 — see below.
**Depends on:** M1 through ADR-0013.

Pure engine first, with no persistence: transaction and posting model on `Decimal`,
zero-sum validation, and the Beancount differential harness. The engine layer takes no
configuration and performs no I/O, so all of this is testable without a database.

**Lot tracking and FIFO disposal are deferred** (REQ-A6). No entity holds inventory or
investments, and checking-account interest needs no basis tracking. This removes the hardest
part of three decisions: ADR-0013 backdating no longer cascades through a FIFO queue, `rebook`
is not needed, and ADR-0017's long-running compute path relaxes with it.

**Reserve the shape anyway:** a posting must carry an optional cost and lot reference from the
first schema version. ADR-0002 already presumes lot state, and retrofitting it later is a
migration on the most-written table.

**Rounding is decided** (ADR-0026): the ledger never rounds, zero-sum is exact with no tolerance,
presentation rounds half-up, and allocation uses largest remainder. The exact-versus-tolerance
difference is a known divergence from Beancount and belongs in the divergence register from its
first run rather than being treated as a defect.

**Known limitation to design around:** zero-sum is enforced per commodity, so a transaction cannot
yet express an FX trade — `USD -100, EUR +90` fails both. Balancing that needs price annotation,
which is the `cost_amount`/`cost_commodity` pair reserved but deferred with lots (REQ-A6). Fine for
a USD cash-basis entity; it surfaces the moment multi-currency does.

**Exit criteria:** CI gate 3 passes with every divergence from the oracle documented.
**Human review required** before merge — booking semantics.

---

## M3 — Persistence and service layer

**Goal:** durable multi-tenant books with a complete audit trail.
**Requirements:** REQ-A2, REQ-A4, REQ-A7, REQ-C4, REQ-E4.
**Depends on:** M2; ADR-0005, ADR-0011.

Schema and hand-written SQL, the deferred zero-sum constraint trigger, row-level security
on `entity_id`, per-entity advisory locking, idempotency keys, and `audit_log`. A Postgres
driver is the first runtime dependency and needs explicit approval before it is added.

**Exit criteria:** CI gate 4 passes against a real schema; concurrent writes to the same entity
are proven serialized by test; every state-changing call is shown to write exactly one
`audit_log` row; a posting can carry an optional cost and lot reference even though nothing
populates it yet (REQ-A6).
**Human review required** — the write path.

---

## M4 — Interfaces

**Goal:** the ledger is reachable by MCP clients and by HTTP.
**Requirements:** REQ-D2, REQ-D3, REQ-D4.
**Depends on:** M3; ADR-0009, ADR-0015, ADR-0019.

One service layer, two adapters; MCP calls the service in-process. Resource server with
mandatory audience validation, the issuer conformance suite that makes the swap claim true,
`/healthz` and `/readyz`, and committed OpenAPI plus MCP tool descriptions.

**Exit criteria:** CI gates 1, 2, and 5 pass; the conformance suite passes against the
default issuer; the local stack completes discovery from a real MCP client.
**Human review required** — auth.

---

## M5 — Ingestion

**Goal:** transactions arrive without manual entry.
**Requirements:** REQ-C1, REQ-C2, REQ-C3.
**Depends on:** M4 (connectors use the public API, so it must exist first).

The `TransactionSource` protocol, the credential-free local default provider, then a real
institution provider behind the same protocol.

**Exit criteria:** the portability gate passes with no provider credentials present, using
the local default; re-running a sync books nothing new.

---

## M6 — Bookkeeper skill

**Goal:** an agent that does the bookkeeping.
**Requirements:** REQ-B1.
**Depends on:** M4.

Talks to the ledger over HTTP only, never importing ledger code.

**Exit criteria:** the skill books a month of realistic transactions with no manual
correction and no silent suspense-account postings.
**Human review required** — booking semantics.

---

## M7 — Delivery surface

**Goal:** per-client Slack channels.
**Requirements:** REQ-D1.
**Blocked by:** ADR-0022.

**Exit criteria:** two entities operated from two channels, with a test proving a request
in one channel cannot read the other's books.

---

## Beyond

Reporting and cash flow (REQ-B2, REQ-B3), export (REQ-E5), managed deployment (REQ-E2),
retention schedule (REQ-E7), then the blocked-by-decision items: tax preparation (REQ-B4),
compliance tracking (REQ-B5), agent role split (REQ-B6), billing (REQ-E6). Each needs its open
question resolved before it can be specified.

### Deferred until a real need appears

| Item | Activation trigger |
|---|---|
| Cost basis and lot tracking, FIFO disposal (REQ-A6), ADR-0007 | An entity acquires inventory, or holds investments in a brokerage account |
| `rebook` and a long-running compute path | Lot tracking activates |

Neither is speculative-abstraction bait: the schema reserves an optional cost and lot reference
from day one, so activating them is additive rather than a migration.

## Standing rules for every milestone

1. Tests are written alongside the code, not after.
2. `uv run task lint` and the relevant tests pass before work is reported complete. Never
   report completion on a red suite.
3. Anything touching booking semantics, auth, or the write path stops for human review.
4. A decision future work should be bound by becomes an ADR, not a code comment.
5. Adding a runtime dependency requires asking first.
