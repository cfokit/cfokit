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
true across every capability; `src/cfokit/*/CLAUDE.md` carries capability-specific rules and
loads only when working in that directory. Both cite record numbers. Read the cited record before
proposing a change to a rule.

Records live at the repository root rather than beside a capability, because decisions frequently
bind more than one — the tool contract, the storage choice, and the skill/ledger boundary all span
capabilities.

**These files are not auto-loaded.** Claude Code loads `CLAUDE.md` at session start; records are read
on demand. Do not `@`-import this directory into `CLAUDE.md` — imports are pulled in at load time and
cost the same context as inlining, while diluting adherence to the rules that matter every session.

## Rules

**Nothing here is final.** Records are corrected in place when they turn out to be wrong, and
deleted when they describe a problem the system does not have. Immutability, supersession and
never reusing a number are rules for a corpus that outside things cite; nothing is released and
nothing cites these but this repository. They are added when something breaks without them.

1. **One decision per file, tested by supersession.** A record may state a decision in several
   clauses when they stand or fall together. The test: *could one clause be superseded without
   reopening the others?* If it could, they are two decisions — split them. A title containing
   "and" is a signal to apply the test, not a violation by itself. (ADR-0001)
2. **Written when the decision is made,** not reconstructed later.
3. **Rejected alternatives are mandatory.** A record without them does not prevent re-litigation.
4. **State what is,** not the history of how the decision was reached. The reasoning belongs in the
   record; the story of how the thinking evolved belongs nowhere.

## Index

| ADR | Title | Status |
|---|---|---|
| [0001](0001-documentation-structure.md) | Documentation structure | Draft |
| [0002](0002-build-the-ledger-rather-than-adopt-one.md) | Build the ledger rather than adopt an existing accounting system | Draft |
| [0003](0003-postgres-as-sole-storage-backend.md) | Use Postgres as the sole storage backend | Accepted |
| [0004](0004-portability-as-a-build-gate.md) | Portability is a build gate; configuration is env vars only | Draft |
| [0005](0005-decimal-throughout-numeric-28-10.md) | `Decimal` in the app, `NUMERIC(28,10)` in the database, floats nowhere | Accepted |
| [0006](0006-zero-sum-deferred-constraint-trigger.md) | Zero-sum enforced by a deferred constraint trigger | Accepted |
| [0007](0007-append-only-from-posting-reversing-corrections.md) | Records become immutable at posting; corrections are reversing entries | Accepted |
| [0008](0008-layered-architecture-pure-engine.md) | Four layers, with a pure booking engine at the bottom | Draft |
| [0009](0009-one-app-two-protocol-adapters.md) | One application, two protocol adapters; MCP calls the service in-process | Draft |
| [0010](0010-beancount-as-test-oracle.md) | Beancount is a differential test oracle, never a runtime dependency | Draft |
| [0011](0011-entity-advisory-lock.md) | Writes serialize on a per-entity advisory lock | Draft |
| [0012](0012-binding-non-goals-and-scope-discipline.md) | Binding non-goals, enforced as a gate rather than a ban | Draft |
| [0013](0013-two-dates-bitemporality.md) | Two dates per transaction, and bitemporality for free | Accepted |
| [0014](0014-single-tool-surface-hosted-backend-only.md) | One tool surface; skills target the hosted backend only | Draft |
| [0015](0015-three-published-interfaces-stability-obligations.md) | Three published interfaces, each with a committed artifact and diff gate | Draft |
| [0016](0016-opentofu-single-cloud-target-iac.md) | OpenTofu, one cloud target, written deployment contract | Draft |
| [0017](0017-gcp-initial-cloud-target.md) | GCP (Cloud Run + Cloud SQL) as the initial cloud target | Draft |
| [0018](0018-local-compose-dev-and-production.md) | One compose stack for local development and local production | Draft |
| [0019](0019-identity-provider-conformance-contract.md) | Identity provider as a swappable dependency behind a conformance contract | Accepted |
| [0020](0020-repository-layout-artifact-kinds.md) | Repository directories are organized by artifact kind | Draft |
| [0021](0021-slack-as-a-delivery-surface.md) | Slack is a delivery surface, built as a separate component over HTTP events | Draft |
| [0022](0022-tiny-ledger-modules-and-components.md) | The ledger stays tiny; everything else is an in-process module or a separate component | Draft |
| [0023](0023-one-image-many-entrypoints.md) | Components ship as one image with many entrypoints | Draft |
| [0024](0024-synchronous-application-code.md) | The ledger is synchronous; async is permitted outside it | Draft |
| [0025](0025-rounding-and-allocation.md) | The ledger never rounds; presentation rounds half-up, allocation uses largest remainder | Draft |
| [0026](0026-apache-2-0-as-the-project-license.md) | Apache 2.0 is the project license | Draft |
| [0027](0027-reopening-does-not-cascade.md) | Reopening does not cascade; a stale year-end close is re-run | Draft |
| [0028](0028-hand-written-sql-no-orm.md) | Hand-written SQL in the repository layer, rather than an ORM | Draft |
| [0029](0029-mandatory-idempotency-keys.md) | Idempotency keys are mandatory on every write | Accepted |
| [0030](0030-closed-period-reopen.md) | A closed period is reopened, never overridden | Draft |
| [0031](0031-packages-named-for-capabilities.md) | Packages are named for the capability they provide | Draft |
| [0032](0032-component-authentication-and-configuration.md) | Components authenticate as OAuth clients | Draft |
| [0033](0033-provenance-captured-at-the-tool-boundary.md) | Provenance is captured at the tool boundary, never self-reported by the agent | Accepted |
| [0034](0034-cfokit-operated-agent-runtime.md) | CFOKit ships an agent runtime, and the SOC 1 boundary is drawn at it | Draft |
| [0035](0035-inference-for-the-attested-runtime.md) | CFOKit holds the inference relationship for the attested runtime | Draft |
| [0036](0036-correctness-is-tested-in-four-layers.md) | Correctness is tested in four layers, and only the top one needs a model | Draft |
| [0037](0037-accounting-basis-is-a-presentation-property.md) | The ledger records obligation and settlement; accounting basis is a presentation property | Accepted |
| [0038](0038-an-entity-is-held-by-its-owners.md) | An entity is held by one or more mutually equivalent owners | Proposed |
| [0039](0039-roles-are-rows-privileges-are-code.md) | Roles are rows, privileges are code, and only `owner` exists yet | Proposed |
| [0040](0040-import-is-the-first-module.md) | Import is the first in-process module, and the file never passes through a model | Proposed |
| [0041](0041-import-is-parsed-where-the-file-is.md) | An import is parsed where the file is, and the books arrive as a neutral shape | Proposed |
| [0042](0042-person-only-acts-are-a-capability.md) | A person-only act is gated by a capability, and `actor_class` describes provenance rather than authority | Proposed |
| [0043](0043-conformance-is-claimed-in-three-bands.md) | Conformance is claimed in three bands, and accounting policy is not one of them | Proposed |
| [0044](0044-an-expected-value-comes-from-a-redistributable-source.md) | An expected value comes only from a source we can redistribute | Proposed |
| [0045](0045-assignment-is-stored-rules.md) | Assignment is stored rules in a module of their own, matched by a closed predicate set | Proposed |
| [0046](0046-a-statement-proves-itself.md) | Account activity is a module, and a statement is recorded only if it accounts for its own balances | Proposed |
| [0047](0047-an-uploaded-line-is-drafted.md) | A transaction read from an uploaded document is drafted, never posted by a rule | Proposed |
| [0048](0048-merge-eligibility-is-policy.md) | A deterministic policy decides whether a pull request may merge; a reviewing model can only withhold it | Proposed |
| [0049](0049-cfokit-has-a-web-client.md) | CFOKit has a web client, served by the API and signed in through the issuer | Proposed |
| [0050](0050-the-import-oracle-is-basis-free.md) | An import is checked against the journal's own total, and a basis difference must net to zero | Proposed |
| [0051](0051-books-are-imported-through-the-web-client.md) | Books are imported through the web client, which reads the export, not through a model | Superseded by ADR-0058 |
| [0052](0052-notifications-are-records-delivered-after-commit.md) | Notifications are records, delivered after their commit through CFOKit's own channels | Proposed |
| [0053](0053-an-invoice-is-a-page-delivered-by-public-address.md) | An issued invoice is a page, and what is delivered depends on the deployment's public address | Proposed |
| [0054](0054-the-web-client-lives-in-web.md) | The web client lives in a top-level `web/` directory, with its toolchain | Proposed |
| [0055](0055-on-gcp-the-web-client-is-served-from-a-cdn.md) | On GCP the web client is served from a bucket behind Cloud CDN, on the API's origin | Proposed |
| [0056](0056-a-notification-is-open-until-answered-or-dismissed.md) | A notification is open until its question is answered or its recipient dismisses it, and open notifications are read through the published interface | Proposed |
| [0057](0057-push-is-web-push-sent-by-cfokit.md) | Push notifications are Web Push to the installed web client, sent by CFOKit's own process | Proposed |
| [0058](0058-getting-started-is-one-path-on-the-web.md) | Getting started is one path: web pages until the agent is connected, then the conversation | Proposed |
| [0059](0059-a-line-is-matched-before-it-is-coded.md) | An incoming transaction is matched to what the books already hold before any rule codes it, and only a sole exact counterpart is acted on | Accepted |
| [0060](0060-production-is-one-gcp-project-deployed-on-merge.md) | Production is one GCP project behind one load balancer, deployed on every merge | Accepted |
| [0061](0061-unattended-work-is-a-queue-in-postgres.md) | Unattended work is a queue in Postgres, filled from stored schedules and drained a pass at a time, on a tick and when a person waits | Accepted |
| [0062](0062-a-bank-feed-is-synchronized-by-cfokit-itself.md) | A bank feed is synchronized by CFOKit's own process into account activity, through a provider protocol, and only a posted transaction becomes a line | Accepted |
| [0063](0063-a-feed-provider-webhook-only-marks-a-connection-due.md) | A feed provider's webhook is a signed way in that only marks one connection's sync as due | Accepted |
| [0064](0064-a-registered-client-redirects-only-to-a-known-host.md) | A client that registers itself may send a sign-in only to a known redirect | Accepted |
| [0065](0065-database-connections-are-encrypted-not-certificate-verified.md) | Database connections are encrypted, and the server's certificate is not verified | Accepted |
| [0068](0068-cfokit-optimizes-for-the-persons-own-agent.md) | Where the person's own agent and the browser trade off, CFOKit optimizes for the agent | Proposed |

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
| Whether CFOKit uses a specification workflow, and which one | ADR-0001 leaves this open; Spec Kit was adopted and removed, and its record is deleted |
| How rendered report output works | RPT-13 — needs a record through the ADR-0012 scope gate, as ADR-0021 took for Slack |

## Substrate records

These settle choices the product does not force — they would be the same for a different product of
this shape, and they cite no requirement (ADR-0001).

| ADR | Choice |
|---|---|
| 0001 | Documentation structure |
| 0012 | Binding non-goals as a gate |
| 0016 | OpenTofu, one cloud target |
| 0017 | GCP as the initial target |
| 0020 | Repository layout by artifact kind |
| 0024 | The ledger is synchronous |
| 0031 | Packages named for capabilities |
| 0048 | Merge eligibility is decided by policy, not by a reviewer |
| 0054 | The web client lives in `web/` |
| 0055 | On GCP the web client is served from a CDN |

Every other record is `kind: requirement-driven` and must cite at least one requirement id.

## Status of this corpus

**Nine records are `accepted`; the rest are `draft`.**

Acceptance is not a claim of confidence. It means changes from here leave a trail: a changed mind
becomes a superseding record, and the superseded one stays in place with its reasoning intact. The
cost of accepting a record that later proves wrong is one more record. The cost of leaving it
`draft` is that a rewrite leaves nothing behind at all.

So the trigger is not "reviewed enough" — it is **about to become irreversible**. Eight of the nine
are the ones the first migration and the booking engine embody in something that cannot be taken
back: `ADR-0003` Postgres-specific mechanisms in the schema, `ADR-0005` `NUMERIC(28,10)`, `ADR-0006`
the deferred zero-sum trigger, `ADR-0007` append-only enforcement and every row written under it,
`ADR-0013` `recorded_at`, `ADR-0029` the idempotency key in schema and published contract, `ADR-0033`
the attribution columns, and `ADR-0037` obligation and settlement as linked postings. Each was read
for staleness before acceptance rather than accepted in a batch.

The ninth, `ADR-0019`, rests on a different footing: its reversal cost is low by construction, but
its conformance contract is written, verified by a test, and depended on by every deployment's
issuer configuration.

Everything else stays `draft` because building the ledger does not embody it. Records move to
`accepted` deliberately, one at a time, and not before.

**Every record follows the template**, and `uv run task check-decisions` fails the build if one
does not. The thirteen records that carried the earlier section structure — no `Decision Drivers`,
no flat `Considered Options` list, no `Confirmation` — were re-derived rather than reformatted:
their `Alternatives rejected` subsections already held the substance of `Pros and Cons of the
Options`, and the drivers were recovered from reasoning each record already stated rather than
Five records stated two decisions each and were split under the one-decision-per-file rule: ADR-0028 (no ORM) out of
ADR-0008, ADR-0029 (idempotency keys) out of ADR-0011, ADR-0030 (closed-period reopen) out of
ADR-0013, ADR-0031 (capability naming) out of ADR-0020, and ADR-0032 (component authentication)
out of ADR-0023. Each half could have been superseded without reopening the other, which is the
test.

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
and the guarantees come from ADR-0006, ADR-0011 and ADR-0029.

**Resolved.** The period-close contradiction between ADR-0007, ADR-0030 and `LED-11` is settled in
favor of `LED-11`: a closed period is reopened, never overridden. The license is settled in
ADR-0026.

### The SOC 1 and SOC 2 sections were never swept

Sections 7 and 8 of `requirements.md` carry about seventy `Must` requirements, and **no decision
record cites one of them**. That disconnection is how the reopen model came to specify an acknowledgement
parameter while `SOC1-17` already required an administrative reopen with no privileged path around
it — neither document was wrong on its own terms, and nothing compared them.

A sweep found five conflicts and eight unserved requirements. None is fixed.

**Conflicts.**

| Conflict | Where |
|---|---|
| `SOC1-25` requires the acting principal's own credential to flow through, "never against a shared credential with the real actor passed as a parameter". Components authenticate by client credentials and assert which user is acting — the intersection of grants mitigates this but does not satisfy it. The fix is OAuth token exchange (RFC 8693), which ADR-0019's conformance contract also does not require | ADR-0021, ADR-0032, ADR-0019 |
| `SOC1-15` puts actor class on the entry "in the data itself, not only in an audit record", and `SOC1-06`, `SOC1-34` and `SOC1-35` add model and skill versions against it. ADR-0022 says the ledger knows nothing about agents. Its boundary test has no answer for this | ADR-0022 |
| `SOC2-20` requires central session revocation reaching skills. ADR-0019's conformance contract does not enumerate it, so a conforming issuer does not satisfy it | ADR-0019 |
| `SOC1-22` requires audit records in storage the application cannot modify or delete by any code path, administrative ones included. ADR-0003 permits only Postgres and does not address how | ADR-0003 |
| `SOC2-03` requires an agent turn reading untrusted content to hold a reduced capability set, enforced at the interface, so reading a document and writing to the ledger are not simultaneously available. The published tool surface has no notion of a reduced capability set | ADR-0015, ADR-0009 |

**`Must` requirements no record serves.**

| Requirement | What it needs decided |
|---|---|
| `SOC1-08` | Gapless verifiable sequencing — sequence numbers, a hash chain, or both, with different failure modes |
| `SOC1-04`, `SOC1-33` | Per-entity versioned configuration of what an agent may complete without a person |
| `SOC1-28`–`SOC1-32` | The exception queue: durable, dispositioned, reportable. A subsystem, not a field |
| `SOC1-27`, `SOC2-23` | Break-glass operator access — time-bounded, individually authorized, visible to the customer |
| `SOC2-09`, `SOC2-10` | A provider registry the system maintains, enforcing zero-retention terms as configuration validation |
| `SOC2-16` | Entity isolation across derived artifacts — embeddings, conversation memory, indexes |
| `SOC2-18` | Deletion reaching derived artifacts and representations held by a provider |
| `SOC2-14` | Key custody, rotation, and revoking access to encrypted data as deployment properties |

**Not every one of these wants an ADR.** Several are foreclosed by the requirement that states them —
`SOC1-25` has no live alternative, and a record would add ceremony rather than reasoning. Sections 7
and 8 already annotate their own architectural consequences in place, which is most of what a record
would say. What earns a record is where the requirement leaves genuine latitude: `SOC1-08` is a real
choice between mechanisms with different failure modes, and `SOC1-28`–`32` is a subsystem whose shape
is not implied by anything.
