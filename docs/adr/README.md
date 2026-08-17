# Architecture Decision Records

Decisions that bind future work. If a choice would be expensive to reverse, or if
someone might reasonably re-propose the alternative in six months, it belongs here.

## How these are used

`CLAUDE.md` files hold the rules; these files hold the reasoning. Root `CLAUDE.md`
carries what is true across every package; `packages/*/CLAUDE.md` carries
package-specific rules and loads only when working in that directory. Both cite ADR
numbers. Read the cited ADR before proposing a change to a rule.

ADRs live at the repo root, not per package, because decisions frequently bind more
than one package — the tool contract, the storage choice, and the skill/ledger boundary
all span packages.

**These files are not auto-loaded.** Claude Code loads `CLAUDE.md` at session start;
ADRs are read on demand. Do not `@`-import this directory into `CLAUDE.md` — imports
are pulled in at load time and cost the same context as inlining, while diluting
adherence to the rules that matter every session.

## Rules

1. **Immutable once Accepted.** Fix typos; never rewrite the reasoning. A changed mind
   is a new ADR that supersedes the old one.
2. **Supersede, don't delete.** Set the old ADR's status to `Superseded by ADR-NNNN`
   and leave it in place. The rejected-alternatives history is most of the value.
3. **One decision per file.** If the title needs "and", split it.
4. **Number sequentially, never reuse.** Gaps are fine.
5. **Written when the decision is made,** not reconstructed later.
6. **Rejected alternatives are mandatory.** An ADR without them does not prevent
   re-litigation, which is the main thing an ADR is for.

## Index

| ADR | Title | Status |
|---|---|---|
| [0001](0001-build-the-ledger-rather-than-adopt-one.md) | Build the ledger rather than adopt an existing accounting system | Accepted |
| [0002](0002-postgres-as-sole-storage-backend.md) | Use Postgres as the sole storage backend | Accepted |
| [0003](0003-portability-as-a-build-gate.md) | Portability is a build gate; configuration is env vars only | Accepted |
| [0004](0004-decimal-throughout-numeric-28-10.md) | `Decimal` in the app, `NUMERIC(28,10)` in the database, floats nowhere | Accepted |
| [0005](0005-zero-sum-deferred-constraint-trigger.md) | Zero-sum enforced by a deferred constraint trigger | Accepted |
| [0006](0006-append-only-from-posting-reversing-corrections.md) | Records become immutable at posting; corrections are reversing entries | Accepted |
| [0008](0008-layered-architecture-pure-engine-no-orm.md) | Four layers with a pure booking engine; hand-written SQL, no ORM | Accepted |
| [0009](0009-one-app-two-protocol-adapters.md) | One application, two protocol adapters; MCP calls the service in-process | Accepted |
| [0010](0010-beancount-as-test-oracle.md) | Beancount is a differential test oracle, never a runtime dependency | Accepted |
| [0011](0011-entity-advisory-lock-idempotency-keys.md) | Per-entity advisory lock on writes; mandatory idempotency keys | Accepted |
| [0012](0012-binding-non-goals-and-scope-discipline.md) | Binding non-goals, enforced as a gate rather than a ban | Accepted |
| [0013](0013-backdating-two-dates-and-close-crossing.md) | Two dates per transaction; backdating permitted but never silent | Accepted |
| [0014](0014-single-tool-surface-hosted-backend-only.md) | One tool surface; skills target the hosted backend only | Accepted |
| [0015](0015-three-published-interfaces-stability-obligations.md) | Three published interfaces, each with a committed artifact and diff gate | Accepted |
| [0016](0016-opentofu-single-cloud-target-iac.md) | OpenTofu, one cloud target, written deployment contract | Accepted |
| [0017](0017-gcp-initial-cloud-target.md) | GCP (Cloud Run + Cloud SQL) as the initial cloud target | Accepted |
| [0018](0018-local-compose-dev-and-production.md) | One compose stack for local development and local production | Accepted |
| [0019](0019-identity-provider-conformance-contract.md) | Identity provider as a swappable dependency behind a conformance contract | Accepted |
| [0020](0020-repository-layout-and-artifact-taxonomy.md) | Repository layout separates artifact kinds; packages named for capabilities | Accepted |
| [0021](0021-spec-kit-workflow-claude-md-constitution.md) | Spec Kit as the specification workflow; CLAUDE.md the sole constitution | Accepted |
| [0022](0022-slack-as-a-delivery-surface.md) | Slack is a delivery surface, built as a separate component over HTTP events | Accepted |
| [0023](0023-tiny-ledger-modules-and-components.md) | The ledger stays tiny; everything else is an in-process module or a separate component | Accepted |
| [0024](0024-component-deployment-and-authentication.md) | Components ship as one image with many entrypoints; authenticate as OAuth clients | Accepted |
| [0025](0025-synchronous-application-code.md) | Application code is synchronous; async confined to the MCP module | Accepted |
| [0026](0026-rounding-and-allocation.md) | The ledger never rounds; presentation rounds half-up, allocation uses largest remainder | Accepted |

## Deferred — decided in principle, waiting on a need

| ADR | Title | Activation trigger |
|---|---|---|
| 0007 | STRICT and FIFO booking only | An entity acquires inventory, or holds investments in a brokerage account (REQ-A6) |

This is the only unwritten number, and it waits on a real need rather than on a decision. Writing it
before then would be designing a boundary around a guess (ADR-0012).

## Open questions these records leave

None block the booking engine. Each is named inside the record that leaves it open:

| Question | Where |
|---|---|
| How rendered report output works | REQ-B3 — needs an ADR through the ADR-0012 scope gate, as ADR-0022 took for Slack |
| Project licence | ADR-0001, deliberately left open and not load-bearing there |
| Agent runtime — where a skill executes | ADR-0022 § 6 |
| Whether `connectors` is a module or a component, and its rename | ADR-0023 § 5 |
| Deprecation policy for published interfaces | ADR-0015, needed before the first removal |
| Display scale per commodity | ADR-0026 |


## Immutability now applies

Every record above is **Accepted** as of the initial commit. Rules 1 and 2 bind from here: fix typos,
never rewrite reasoning, and a changed mind is a new ADR that supersedes the old one.

The drafting period — during which these were edited in place rather than superseded — is over. It
was legitimate while nothing had been relied on; it is not legitimate now.

## On the format

The template is a variant of [MADR](https://adr.github.io/madr/), not a local invention: the
same frontmatter, and mandatory rejected alternatives, which is MADR's main improvement over
Nygard's original five sections. The additions are **reversal cost** and **revisit when**.
Specifications are a separate artifact and live in [`specs/`](../../specs/) — see
[ADR-0021](0021-spec-kit-workflow-claude-md-constitution.md).
