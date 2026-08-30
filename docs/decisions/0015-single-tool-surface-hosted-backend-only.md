---
status: "accepted"
kind: "requirement-driven"
date: 2026-08-17
decision-makers: [Geoff]
---

# ADR-0015: One tool surface; skills target the hosted backend and never import ledger code

## Context

CFOKit ships two things that look like one product: a ledger service, and agent skills that do
bookkeeping against it. Because they live in one repository, the cheapest possible integration is
for a skill to import the ledger and call it directly.

That option is available, would work, and would be faster than HTTP. It is also the decision most
likely to quietly destroy the product's structure, which is why it needs a record rather than a
convention.

The pressure is real in three specific forms:

- **Local operation.** A user running the local compose stack could plausibly have the skill talk
  to a ledger library rather than a service, avoiding the network entirely.
- **Latency.** An in-process call is faster than an HTTP round trip, and a bookkeeping run touches
  many transactions.
- **Expressiveness.** The tool surface will always expose less than the internal service layer, and
  the first time a skill needs something not exposed, importing the ledger looks like the pragmatic
  answer.

## Decision

**One tool surface. Skills reach the ledger over HTTP, and by no other route.**

- Skills never import ledger code, never read its database, and never reach into its internals.
- There is exactly **one** tool surface, identical in every deployment topology. There is no
  richer local variant and no constrained hosted variant.
- The skill and the ledger are separate systems with separate dependency graphs that share only
  the tool contract.

Enforced rather than asserted: skills are not Python distributions at all (ADR-0021), so there is no
import path for them to take.

**Scope note.** This record governs **skills**, which are unambiguously separate. It does *not*
settle whether first-party in-repository packages must also use HTTP — an earlier draft extended it
to ingestion, which was over-committed. [ADR-0024](0024-tiny-ledger-modules-and-components.md)
records the criteria for classifying such a package as an in-process module or a separate component.
The existing `import-linter` contract forbidding `cfokit.connectors` from importing `cfokit.ledger`
stays in force as a safe provisional default, not as a settled answer.

## Alternatives rejected

### A skill imports the ledger as a library for local use

The strongest alternative, and the one that will keep being proposed: no network, works offline,
lower latency, and simpler local development.

Rejected because it produces **two booking paths, maintained forever**. The library path and the
HTTP path would each need the service-layer obligations — one `audit_log` row per state change,
per-entity locking, idempotency keys, grant validation (ADR-0012) — and any divergence between
them is a correctness bug in the component whose correctness is the product.

Worse, the local path would be exercised almost exclusively by people who cannot diagnose its
bugs, while the hosted path gets all the operational scrutiny. This is the same reasoning that
rejected a static bearer token for local mode in ADR-0019: a code path used only where nobody is
watching is a code path whose bugs are found by users.

### Two tool surfaces — a rich local one, a constrained hosted one

Attractive because it lets self-hosters have capabilities that are unsafe or unscalable in a shared
deployment.

Rejected because the skill's behaviour would then depend on where it is pointed, which makes CFOKit
two products with one name. Every piece of documentation, every support answer, and every bug
report acquires a "which deployment?" qualifier. Self-hosting is a promise that you get the same
software (ADR-0004), not a similar one.

### The skill embeds a subset of booking logic for offline queuing

Narrower: keep the ledger remote, but let the skill categorise and stage entries locally when the
network is unavailable, syncing later.

Rejected because categorisation is not the hard part — the hard part is that the skill would then
hold opinions about how a transaction books, and booking logic in two places is exactly the failure
the boundary exists to prevent. The legitimate version of this need is already met differently: the
draft state (ADR-0007) is where unposted work lives, and it lives in the ledger.

### The skill reads the ledger's database directly for queries, writing over HTTP

Read-only coupling, which feels safer than write coupling.

Rejected because reads are where the tenancy boundary is enforced. Row-level security and explicit
service-layer filtering on `entity_id` (ADR-0003, ADR-0012) both live above the database; a direct
reader bypasses them and sees every entity's books. For a fractional CFO holding many clients in one
deployment, that is the worst available failure.

### Expose the internal service layer as the tool surface

Would remove the expressiveness objection permanently by making the tool surface complete.

Rejected because the tool surface is a published interface with stability obligations (ADR-0016),
whereas the service layer is internal and expected to change. Publishing it would freeze internal
structure, which is the opposite of what the layering in ADR-0009 is for.

## Consequences

**Accepted costs.**
- Skills require network access to a ledger. There is no offline mode.
- HTTP latency on every operation, including in local deployments where both sides are on one
  machine.
- When a skill needs something the tool surface does not expose, the answer is a contract change
  with review (ADR-0016) rather than a local workaround. This will sometimes be slow, and that
  slowness is the point.

**Follow-on obligations.**
- The tool contract is a published interface: committed descriptions, diffed in CI, changes
  reviewed (ADR-0016).
- `import-linter` enforces the boundary. **Already in place** and observed to fail when
  deliberately violated.
- Skills live outside `packages/` so they have no dependency graph to couple through (ADR-0021).
- `skills/CLAUDE.md` states the rule where an agent working on a skill will read it.
- The local compose stack must make a working ledger trivially available, since skills cannot
  function without one (ADR-0019).

**Reversal cost. High.** Once skills are written against HTTP, adding a library path is not
additive — it is a second implementation of the service-layer obligations, plus the ongoing burden
of keeping two paths semantically identical. Removing the boundary later would also invalidate the
claim that a self-hoster can point a skill at their own deployment.

## Revisit when

- HTTP latency is a **measured** obstacle to a real workflow, not an anticipated one. The remedy
  would then be batching operations in the tool contract, not importing the ledger.
- An offline requirement appears that the draft state genuinely cannot satisfy.
