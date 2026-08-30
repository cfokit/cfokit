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
| [0001](0001-documentation-structure.md) | Documentation structure | Accepted |
| [0002](0002-build-the-ledger-rather-than-adopt-one.md) | Build the ledger rather than adopt an existing accounting system | Accepted |
| [0003](0003-postgres-as-sole-storage-backend.md) | Use Postgres as the sole storage backend | Accepted |
| [0004](0004-portability-as-a-build-gate.md) | Portability is a build gate; configuration is env vars only | Accepted |
| [0005](0005-decimal-throughout-numeric-28-10.md) | `Decimal` in the app, `NUMERIC(28,10)` in the database, floats nowhere | Accepted |
| [0006](0006-zero-sum-deferred-constraint-trigger.md) | Zero-sum enforced by a deferred constraint trigger | Accepted |
| [0007](0007-append-only-from-posting-reversing-corrections.md) | Records become immutable at posting; corrections are reversing entries | Accepted |
| [0009](0009-layered-architecture-pure-engine-no-orm.md) | Four layers with a pure booking engine; hand-written SQL, no ORM | Accepted |
| [0010](0010-one-app-two-protocol-adapters.md) | One application, two protocol adapters; MCP calls the service in-process | Accepted |
| [0011](0011-beancount-as-test-oracle.md) | Beancount is a differential test oracle, never a runtime dependency | Accepted |
| [0012](0012-entity-advisory-lock-idempotency-keys.md) | Per-entity advisory lock on writes; mandatory idempotency keys | Accepted |
| [0013](0013-binding-non-goals-and-scope-discipline.md) | Binding non-goals, enforced as a gate rather than a ban | Accepted |
| [0014](0014-backdating-two-dates-and-close-crossing.md) | Two dates per transaction; backdating permitted but never silent | Accepted |
| [0015](0015-single-tool-surface-hosted-backend-only.md) | One tool surface; skills target the hosted backend only | Accepted |
| [0016](0016-three-published-interfaces-stability-obligations.md) | Three published interfaces, each with a committed artifact and diff gate | Accepted |
| [0017](0017-opentofu-single-cloud-target-iac.md) | OpenTofu, one cloud target, written deployment contract | Accepted |
| [0018](0018-gcp-initial-cloud-target.md) | GCP (Cloud Run + Cloud SQL) as the initial cloud target | Accepted |
| [0019](0019-local-compose-dev-and-production.md) | One compose stack for local development and local production | Accepted |
| [0020](0020-identity-provider-conformance-contract.md) | Identity provider as a swappable dependency behind a conformance contract | Accepted |
| [0021](0021-repository-layout-and-artifact-taxonomy.md) | Repository layout separates artifact kinds; packages named for capabilities | Accepted |
| [0022](0022-spec-kit-workflow-claude-md-constitution.md) | Spec Kit as the specification workflow; CLAUDE.md the sole constitution | **Deprecated** |
| [0023](0023-slack-as-a-delivery-surface.md) | Slack is a delivery surface, built as a separate component over HTTP events | Accepted |
| [0024](0024-tiny-ledger-modules-and-components.md) | The ledger stays tiny; everything else is an in-process module or a separate component | Accepted |
| [0025](0025-component-deployment-and-authentication.md) | Components ship as one image with many entrypoints; authenticate as OAuth clients | Accepted |
| [0026](0026-synchronous-application-code.md) | Application code is synchronous; async confined to the MCP module | Accepted |
| [0027](0027-rounding-and-allocation.md) | The ledger never rounds; presentation rounds half-up, allocation uses largest remainder | Accepted |

## Deferred — decided in principle, waiting on a need

| ADR | Title | Activation trigger |
|---|---|---|
| 0008 | STRICT and FIFO booking only | An entity acquires inventory, or holds investments in a brokerage account (REQ-A6) |

This is the only unwritten number, and it waits on a real need rather than on a decision. Writing it
before then would be designing a boundary around a guess (ADR-0013).

## Open questions these records leave

| Question | Where |
|---|---|
| Whether CFOKit uses a specification workflow, and which one | ADR-0001 leaves this open; ADR-0022 predates that record and is due for re-derivation |
| How rendered report output works | REQ-B3 — needs a record through the ADR-0013 scope gate, as ADR-0023 took for Slack |
| Project licence | ADR-0002, deliberately left open and not load-bearing there |

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
| 0022 | Spec Kit *(deprecated)* |

Every other record is `kind: requirement-driven` and must cite at least one requirement id.

## Status of this corpus

ADR-0001 is the only record written to the current standard. Records 0002 to 0013 carry their
original reasoning in MADR form; 0014 to 0027 have MADR frontmatter but the previous section
structure — no `Decision Drivers`, no flat `Considered Options` list, and no `Confirmation`.
Their `Alternatives rejected` sections do give each rejected option its own subsection, which
carries the substance of `Pros and Cons of the Options` without the heading.

**No requirement-driven record currently has a valid trace.** Two separate faults:

* Eleven cite no requirement at all — 0003, 0005, 0006, 0009, 0010, 0011, 0015, 0016, 0019, 0020
  and 0026.
* The other nine cite ids from a retired scheme. `docs/product/requirements.md` uses domain
  prefixes — `LED-`, `BKP-`, `IAM-`, `PLT-`, `RPT-`, `MIG-`, `AR-`, `NFR-`, `SOC1-`, `SOC2-` — and
  contains no `REQ-` id at all. Every `REQ-` citation in the corpus is dangling: `REQ-A1`, `A2`,
  `A3`, `A6`, `A8`, `A9`, `B1`, `B3`, `B7`, `C1`, `C2`, `C4`, `D1`, `E1`, `E3`, `E7`.

Two substrate records — 0013 and 0021 — also carry dangling `REQ-` ids in prose. They are not
required to cite a requirement, but the links are broken all the same. ADR-0013's gate still
instructs a proposer to name "the `REQ-` id it serves", which is a live rule pointing at a dead
scheme.

Re-tracing every record to live requirement ids is part of the re-derivation.

None of 0002 to 0027 has been re-derived against the current vision and requirements, and none is
presumed correct until it has been. `kind` values are a first classification and are part of what
the re-derivation checks — 0026 in particular reads as substrate rather than requirement-driven.

**Renumbering debris: resolved.** An earlier renumbering shifted every record up by one and left
citations behind in files the documentation test does not read. `compose.yaml`, `compose.dev.yaml`,
`.github/workflows/ci.yml`, the first migration and its `sql/.gitkeep` have been corrected, as has
a mislabelled link in the root `README.md`. Three records cited each other wrongly and are fixed:
0012 cited ADR-0009 twice for ADR-0010's in-process rule, 0014 cited ADR-0015 for ADR-0016's error
codes, and 0021 carried five bare backlog numbers in the pre-renumbering scheme. `CLAUDE.md`,
`CONTRIBUTING.md`, `infra/README.md`, `pyproject.toml`, the package `CLAUDE.md` and `README.md`
files, `scripts/` and `packages/ledger/src/` were already correct.

`tests/test_documentation.py` checks that a cited number **exists**, not that it is the **right**
one, and it reads only markdown outside this directory — which is why the drift survived. Both
gaps are worth closing.

**Known conflicts, not yet resolved.**

| Conflict | Where |
|---|---|
| Period close is advisory and backdating into a closed period needs only acknowledgement — but `LED-11` now requires a recorded reopening, which is the alternative ADR-0014 rejected by name | ADR-0007, ADR-0014 |
| Licence is "deliberately left open", yet `LICENSE`, `pyproject.toml`, `README.md` and ADR-0017's rejection of Terraform all rely on MIT, and `NFR-14` makes permissive licensing a Must | ADR-0002, ADR-0017 |
| Prescribes `specs/`, `REQ-` ids and an accounting-policy artifact kind, all three since retired | ADR-0021 |
| Status is `deprecated`; ADR-0001 replaced its decision, so `superseded by ADR-0001` is the accurate status under rule 2 | ADR-0022 |
