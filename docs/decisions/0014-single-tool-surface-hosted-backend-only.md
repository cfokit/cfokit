---
status: "draft"
kind: "requirement-driven"
date: 2026-08-17
decision-makers: [Geoff]
---

# ADR-0014: One tool surface; skills target the hosted backend and never import ledger code

**Requirements served:** `PLT-01`, `PLT-02`, `NFR-17`.

## Context and Problem Statement

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

## Decision Drivers

* One booking path. The service-layer obligations — one `audit_log` row per state change,
  per-entity locking, idempotency keys, grant validation (ADR-0011, ADR-0029) — must have exactly one
  implementation.
* A skill behaves identically wherever it is pointed. Self-hosting is a promise of the same
  software, not similar software (ADR-0004).
* The tenancy boundary is enforced above the database, so anything reaching beneath it sees every
  entity's books.
* A published interface carries stability obligations that internal structure must not inherit
  (ADR-0015).

## Considered Options

* One tool surface, reached only over HTTP
* A skill imports the ledger as a library for local use
* Two tool surfaces — a rich local one, a constrained hosted one
* The skill embeds a subset of booking logic for offline queuing
* The skill reads the ledger's database directly for queries, writing over HTTP
* Expose the internal service layer as the tool surface

## Decision Outcome

Chosen option: "One tool surface, reached only over HTTP", because every alternative produces a
second path through the booking obligations, and the component whose correctness is the product
cannot have two implementations.

> One tool surface. Skills reach the ledger over HTTP, and by no other route.

- Skills never import ledger code, never read its database, and never reach into its internals.
- There is exactly **one** tool surface, identical in every deployment topology. There is no richer
  local variant and no constrained hosted variant.
- The skill and the ledger are separate systems with separate dependency graphs that share only the
  tool contract.

### Scope: this record governs skills

Skills are unambiguously separate, and this record binds them. It does **not** settle whether
first-party in-repository packages must also use HTTP.
[ADR-0022](0022-tiny-ledger-modules-and-components.md) holds the criteria for classifying such a
package as an in-process module or a separate component. There was an `import-linter` contract
standing as a provisional default for ingestion; the package it guarded held no code and has been
removed, so the question is open with nothing pre-empting it.

### Consequences

* Good, because there is one implementation of the booking obligations, exercised by every caller
  in every topology.
* Good, because a self-hoster pointing a skill at their own deployment gets identical behaviour, so
  documentation and support answers need no "which deployment?" qualifier.
* Good, because the boundary is structural rather than conventional: skills are not Python
  distributions at all (ADR-0020), so there is no import path to take.
* Bad, because skills require network access to a ledger. There is no offline mode.
* Bad, because HTTP latency applies to every operation, including local deployments where both
  sides are on one machine.
* Bad, because when a skill needs something the tool surface does not expose, the answer is a
  contract change with review (ADR-0015) rather than a local workaround. This will sometimes be
  slow, and that slowness is the point.

### Confirmation

Enforced, and observed to fail when deliberately violated. `import-linter` contracts in
`pyproject.toml` fail `uv run task lint` on a layer violation. Structurally, skills live outside
`packages/` and are not distributions (ADR-0020), so a skill has no dependency graph through which
to couple — the lint contract is a second line rather than the only one.

## Pros and Cons of the Options

### One tool surface, reached only over HTTP

* Good, because the service-layer obligations have exactly one implementation.
* Good, because the boundary is enforced by packaging and by lint, not by discipline.
* Bad, because it costs a network round trip even when both sides are on one machine.
* Bad, because expanding what a skill can do requires a reviewed contract change.

### A skill imports the ledger as a library for local use

The strongest alternative, and the one that will keep being proposed: no network, works offline,
lower latency, and simpler local development.

* Good, because it is faster, simpler to run, and removes the network from the local story
  entirely.
* Bad, because it produces **two booking paths, maintained forever**. The library path and the HTTP
  path would each need the service-layer obligations, and any divergence between them is a
  correctness bug in the component whose correctness is the product.
* Bad, because the local path would be exercised almost exclusively by people who cannot diagnose
  its bugs, while the hosted path gets all the operational scrutiny. This is the same reasoning that
  rejected a static bearer token for local mode in ADR-0018: a code path used only where nobody is
  watching is a code path whose bugs are found by users.

### Two tool surfaces — a rich local one, a constrained hosted one

Attractive because it lets self-hosters have capabilities that are unsafe or unscalable in a shared
deployment.

* Good, because it would let a single-user local deployment skip limits that only exist for shared
  tenancy.
* Bad, because the skill's behaviour would then depend on where it is pointed, which makes CFOKit
  two products with one name. Every piece of documentation, every support answer, and every bug
  report acquires a "which deployment?" qualifier.

### The skill embeds a subset of booking logic for offline queuing

Narrower: keep the ledger remote, but let the skill categorise and stage entries locally when the
network is unavailable, syncing later.

* Good, because it would make a skill useful on a plane, and categorisation genuinely does not need
  the ledger.
* Bad, because categorisation is not the hard part — the hard part is that the skill would then hold
  opinions about how a transaction books, and booking logic in two places is exactly the failure the
  boundary exists to prevent.
* Bad, because the legitimate version of this need is already met differently: the draft state
  (ADR-0007) is where unposted work lives, and it lives in the ledger.

### The skill reads the ledger's database directly for queries, writing over HTTP

Read-only coupling, which feels safer than write coupling.

* Good, because reads are the bulk of the traffic and this would remove most of the latency cost
  without touching the write path.
* Bad, because reads are where the tenancy boundary is enforced. Row-level security and explicit
  service-layer filtering on `entity_id` (ADR-0003, ADR-0011) both live above the database; a direct
  reader bypasses them and sees every entity's books. For a fractional CFO holding many clients in
  one deployment, that is the worst available failure.

### Expose the internal service layer as the tool surface

Would remove the expressiveness objection permanently by making the tool surface complete.

* Good, because no skill would ever be blocked by a missing tool.
* Bad, because the tool surface is a published interface with stability obligations (ADR-0015),
  whereas the service layer is internal and expected to change. Publishing it would freeze internal
  structure, which is the opposite of what the layering in ADR-0008 is for.

## More Information

**Follow-on obligations.**

* The tool contract is a published interface: committed descriptions, diffed in CI, changes reviewed
  (ADR-0015).
* `import-linter` enforces the boundary. Already in place.
* Skills live outside `packages/` so they have no dependency graph to couple through (ADR-0020).
* `skills/CLAUDE.md` states the rule where an agent working on a skill will read it.
* The local compose stack must make a working ledger trivially available, since skills cannot
  function without one (ADR-0018).

**Reversal cost. High.** Once skills are written against HTTP, adding a library path is not additive
— it is a second implementation of the service-layer obligations, plus the ongoing burden of keeping
two paths semantically identical. Removing the boundary later would also invalidate the claim that a
self-hoster can point a skill at their own deployment.

## Revisit when

* HTTP latency is a **measured** obstacle to a real workflow, not an anticipated one. The remedy
  would then be batching operations in the tool contract, not importing the ledger.
* An offline requirement appears that the draft state genuinely cannot satisfy.
