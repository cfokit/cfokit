# Decision records

Decisions that bind future work. If a choice would be expensive to reverse, or if someone might
reasonably re-propose the alternative in six months, it belongs here.

Format is [MADR 4.0.0](https://adr.github.io/madr/), with two local rules. `Considered Options` and
`Pros and Cons of the Options` are **mandatory** — MADR marks the second optional, and a record that
names alternatives without refuting each one does not prevent re-litigation, which is the main thing
a record is for. `Revisit when` is an added section naming concrete triggers. ADR-0001 holds the
reasoning; `adr-template.md` is the starting point.

## How these are used

`CLAUDE.md` files hold the rules; these files hold the reasoning. Root `CLAUDE.md` carries what is
true across every package; `packages/*/CLAUDE.md` carries package-specific rules and loads only when
working in that directory. Both cite record numbers. Read the cited record before proposing a change
to a rule.

Records live at the repository root rather than per package, because decisions frequently bind more
than one package — the tool contract, the storage choice, and the skill/ledger boundary all span
packages.

**These files are not auto-loaded.** Claude Code loads `CLAUDE.md` at session start; records are read
on demand. Do not `@`-import this directory into `CLAUDE.md` — imports are pulled in at load time and
cost the same context as inlining, while diluting adherence to the rules that matter every session.

## Rules

1. **Immutable once accepted.** Fix typos; never rewrite the reasoning. A changed mind is a new
   record that supersedes the old one.
2. **Supersede, don't delete.** Set the old record's `status` to `superseded by ADR-NNNN` and leave
   it in place. The rejected-alternatives history is most of the value.
3. **One decision per file.** If the title needs "and", split it.
4. **Number sequentially, never reuse.** Gaps are fine. Numbers are identifiers, not chronology —
   the `date` field is authoritative for sequence.
5. **Written when the decision is made,** not reconstructed later.
6. **Rejected alternatives are mandatory.** A record without them does not prevent re-litigation.
7. **State what is,** not the history of how the decision was reached. The reasoning belongs in the
   record; the story of how the thinking evolved belongs nowhere.

## Index

| ADR | Title | Status |
|---|---|---|
| [0001](0001-documentation-structure.md) | Documentation structure | Draft |
| [0002](0002-build-the-ledger-rather-than-adopt-one.md) | Build the ledger rather than adopt an existing accounting system | Draft |
| [0003](0003-postgres-as-sole-storage-backend.md) | Use Postgres as the sole storage backend | Draft |
| [0004](0004-portability-as-a-build-gate.md) | Portability is a build gate; configuration is env vars only | Draft |
| [0005](0005-decimal-throughout-numeric-28-10.md) | `Decimal` in the app, `NUMERIC(28,10)` in the database, floats nowhere | Draft |
| [0006](0006-zero-sum-deferred-constraint-trigger.md) | Zero-sum enforced by a deferred constraint trigger | Draft |
| [0007](0007-append-only-from-posting-reversing-corrections.md) | Records become immutable at posting; corrections are reversing entries | Draft |
| [0008](0008-layered-architecture-pure-engine-no-orm.md) | Four layers with a pure booking engine; hand-written SQL, no ORM | Draft |
| [0009](0009-one-app-two-protocol-adapters.md) | One application, two protocol adapters; MCP calls the service in-process | Draft |
| [0010](0010-beancount-as-test-oracle.md) | Beancount is a differential test oracle, never a runtime dependency | Draft |
| [0011](0011-entity-advisory-lock-idempotency-keys.md) | Per-entity advisory lock on writes; mandatory idempotency keys | Draft |
| [0012](0012-binding-non-goals-and-scope-discipline.md) | Binding non-goals, enforced as a gate rather than a ban | Draft |
| [0013](0013-two-dates-and-period-reopen.md) | Two dates per transaction; a closed period is reopened, never overridden | Draft |
| [0014](0014-single-tool-surface-hosted-backend-only.md) | One tool surface; skills target the hosted backend only | Draft |
| [0015](0015-three-published-interfaces-stability-obligations.md) | Three published interfaces, each with a committed artifact and diff gate | Draft |
| [0016](0016-opentofu-single-cloud-target-iac.md) | OpenTofu, one cloud target, written deployment contract | Draft |
| [0017](0017-gcp-initial-cloud-target.md) | GCP (Cloud Run + Cloud SQL) as the initial cloud target | Draft |
| [0018](0018-local-compose-dev-and-production.md) | One compose stack for local development and local production | Draft |
| [0019](0019-identity-provider-conformance-contract.md) | Identity provider as a swappable dependency behind a conformance contract | Draft |
| [0020](0020-repository-layout-and-artifact-taxonomy.md) | Repository layout separates artifact kinds; packages named for capabilities | Draft |
| [0021](0021-slack-as-a-delivery-surface.md) | Slack is a delivery surface, built as a separate component over HTTP events | Draft |
| [0022](0022-tiny-ledger-modules-and-components.md) | The ledger stays tiny; everything else is an in-process module or a separate component | Draft |
| [0023](0023-component-deployment-and-authentication.md) | Components ship as one image with many entrypoints; authenticate as OAuth clients | Draft |
| [0024](0024-synchronous-application-code.md) | The ledger is synchronous; async is permitted outside it | Draft |
| [0025](0025-rounding-and-allocation.md) | The ledger never rounds; presentation rounds half-up, allocation uses largest remainder | Draft |
| [0026](0026-apache-2-0-as-the-project-licence.md) | Apache 2.0 is the project licence | Draft |

## Deferred — decided in principle, waiting on a need

| Title | Activation trigger |
|---|---|
| STRICT and FIFO booking only | An entity acquires inventory, or holds investments in a brokerage account (LED-18, LED-19) |

It takes the next free number when it is written. Reserving one now would leave a gap in the
sequence for a record that may never be needed, and writing it before the need exists would be
designing a boundary around a guess (ADR-0012).

## Open questions these records leave

| Question | Where |
|---|---|
| Whether reopening a closed period reopens the ones after it, given `LED-12` closes income and expense to retained earnings at year end | ADR-0013 |
| Whether CFOKit uses a specification workflow, and which one | ADR-0001 leaves this open; Spec Kit was adopted and removed, and its record is deleted |
| How rendered report output works | RPT-13 — needs a record through the ADR-0012 scope gate, as ADR-0021 took for Slack |

## Substrate records

These settle choices the product does not force — they would be the same for a different product of
this shape, and they cite no requirement (ADR-0001).

| ADR | Choice |
|---|---|
| 0001 | Documentation structure |
| 0013 | Binding non-goals as a gate |
| 0017 | OpenTofu, one cloud target |
| 0018 | GCP as the initial target |
| 0021 | Repository layout |

Every other record is `kind: requirement-driven` and must cite at least one requirement id.

## Status of this corpus

**Every record is `draft`.** This corpus is a first pass and has not been reviewed to a standard
that would justify accepting any of it. `draft` is the template's own word for pre-acceptance:
still being written, freely editable, and the immutability rule does not bind. Records move to
`accepted` deliberately, one at a time, and not before.

ADR-0001 is the only record written to the current standard. Records 0002 to 0013 carry their
original reasoning in MADR form; 0014 to 0027 have MADR frontmatter but the previous section
structure — no `Decision Drivers`, no flat `Considered Options` list, and no `Confirmation`.
Their `Alternatives rejected` sections do give each rejected option its own subsection, which
carries the substance of `Pros and Cons of the Options` without the heading.

**Bringing those fourteen to the template means writing reasoning that was never written**, which
rule 1 forbids. Either the template applies prospectively and this stays documented, or the
records are re-derived rather than reformatted. That is undecided.

**Every requirement-driven record now traces.** Each carries a `Requirements served:` line naming
live domain-prefixed ids, and the retired `REQ-` scheme is gone from the repository entirely —
records, rules, skills, infrastructure notes, migration SQL and tests. `tests/test_documentation.py`
holds both halves: every cited requirement id must resolve to one in `requirements.md`, and a
record declaring `kind: requirement-driven` must name at least one.

The traces are a first mapping and are part of what re-derivation checks. Two things they do not
yet establish: whether each record still serves the requirement it names, and whether any
requirement needing a record lacks one. `RPT-13` is the known instance of the second.

ADR-0024 is reclassified `substrate`. Nothing in the requirements forces the synchronous choice;
its reasoning rests on workload and on the MCP SDK, and a different product of this shape would
face the same question. Its scope has been corrected: the boundary is the ledger, not the MCP
module, so ingestion, delivery and AR are free to be async. The record also no longer implies
that synchronous code makes the ledger concurrency-safe — it removes an `await` mid-transaction,
and the guarantees come from ADR-0006 and ADR-0011.

**Known conflicts, not yet resolved.** None. The period-close contradiction between ADR-0007,
ADR-0013 and `LED-11` is settled in favour of `LED-11`: a closed period is reopened, never
overridden. The licence is settled in ADR-0026.
