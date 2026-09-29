---
status: "accepted"
kind: "requirement-driven"
date: 2026-08-31
decision-makers: [Geoff]
---

# ADR-0033: Provenance is captured at the tool boundary, never self-reported by the agent

**Requirements served:** `LED-20`, `NFR-23`, `SOC1-06`, `SOC1-15`, `SOC1-34`, `SOC1-35`.

> `LED-20` and `NFR-23` carry this record's basis. They were promoted out of section 7 because attribution and tamper-detectability are irreversible under append-only storage, which is true whether or not an examination ever happens. The `SOC1-` citations remain because the record also serves them, but it does not depend on them surviving review.

## Context and Problem Statement

`SOC1-15` requires that a coding decision made by an agent be distinguishable from one made by a
person **in the data itself**, for the life of the entry. `SOC1-06` requires a posted entry to be
explainable after the fact without re-running a model. `SOC1-34` and `SOC1-35` require the skill,
prompt and model versions in force to be recorded, and entries either side of a model change to be
distinguishable.

Today none of this exists. `ledger_transaction` carries no actor column at all; attribution lives
only in `audit_log.actor`, which is subject to a retention schedule (`PLT-20`) while the entry it
describes is permanent (ADR-0007). An entry outliving its audit record becomes unattributable, which
is the same failure ADR-0013 rejected when it declined to infer backdating from an audit-log
timestamp: a retention policy must never change what a report says.

**The obvious implementation does not work.** The natural move is to have the skill report its own
provenance — model, versions, context, rationale — as parameters on the write. A language model is
non-deterministic and handles untrusted input; a skill instructed to record its own session
faithfully will do so most of the time, and there is no guarantee for any particular run. "Most of
the time" is not a control. An examination tests whether a control operated *throughout* the period,
so a single unrecorded entry is a control failure rather than a rounding error.

`SOC1-02` already settles the principle for authority — *"no prompt or instruction participates in
the enforcement"*. This record applies the same principle to evidence.

Whether CFOKit is positioned to observe everything `SOC1-06` asks for is a different question, and it
depends on who operates the agent runtime. That is [ADR-0034](0034-cfokit-operated-agent-runtime.md).
This record decides the mechanism, which holds whatever the answer there is.

## Decision Drivers

* No prompt or instruction may participate in producing evidence, for the same reason `SOC1-02`
  excludes them from producing authorisation.
* Attribution must survive audit-log retention, because the entry does (`PLT-20`, ADR-0007).
* The set of provenance dimensions is open-ended, and append-only forbids backfilling a column added
  later (ADR-0013's `recorded_at` lesson, inverted).
* The ledger stays tiny; it may not learn what a skill or a model is (ADR-0022).
* Evidence must be tamper-evident. An editable record is a document somebody could have changed, and
  an examiner treats it as one.

## Considered Options

* Capture at the tool boundary: narrow attribution on the entry, versions verified against a
  registry, and a decision record holding the rest
* Provenance columns on the entry, including model and version
* The skill self-reports provenance as parameters on the write
* Attribution in the audit log only
* An event-sourced attestation log outside the ledger, joined by time

## Decision Outcome

Chosen option: "Capture at the tool boundary", because the API *is* the tool surface, so what the
server observes needs no cooperation from the model — and everything the server cannot observe is
labeled as an assertion rather than presented as fact.

### 1. Three classes of provenance, distinguished in the schema

The distinction is not cosmetic. An examiner asking "how do you know?" gets a different answer for
each, and conflating them is how a report overclaims.

| Class | How established | Examples |
|---|---|---|
| **Observed** | The server sees it directly. Cannot be misreported. | Acting principal, principal acted for, every tool call and its arguments and result, server timestamps (`SOC1-18`), what was written |
| **Verified** | Supplied by the caller and checked against a registry. A lie is detectable, not impossible. | Skill version, prompt version, tool-definition version (§ 4) |
| **Asserted** | Supplied by the agent. Evidence of what it claimed, not of why it acted | Stated basis, alternatives considered (`SOC1-05`, `SOC1-06`) |

**Verified is a real class and not a softer word for observed.** A compromised or defective runtime
can present a different *registered* version of its own skill. What it cannot do is invent a version
that was never registered, or borrow one belonging to another skill — and fabrication is the failure
that matters for `SOC1-34`. Recording this as observed would overstate it by exactly the amount an
examiner would find.

**Asserted content is stored as an assertion and rendered as one.** A model's stated rationale is not
necessarily its operative reason. Presented to an examiner as *the explanation* for a coding
decision, it is an overclaim, and an overclaim discovered in one place discredits the rest of the
report. Presented as *what the agent said when asked*, it is honest evidence and still useful.

### 2. What sits on the entry

Four columns, and no more:

- `actor_principal_id` — who wrote it
- `actor_class` — see § 3
- `acting_for_principal_id` — the person the agent acted for, nullable (`IAM-11`, `SOC1-15`)
- `decision_record_id` — lineage pointer, nullable

The ledger has learned that **principals have a class and one may act on behalf of another**. That is
an identity concept — it is the delegation `act` claim, the same machinery `SOC1-25` already wants —
not knowledge of what a skill is. "Which skill acted" resolves through the principal registry, which
lives outside the ledger, exactly as `entity_id` resolves without the ledger knowing what a company
is. ADR-0022's boundary test survives: the ledger still does not know what a customer, an invoice, or
a model is.

`decision_record_id` is the same shape of pointer `SOC1-14` already forces for feed lineage.

### 3. `actor_class` has three values, not two

`person`, `rule`, `agent`.

Collapsing `rule` into "non-human" discards the distinction that most reduces examination cost. A
rule-assigned coding is deterministic and re-derivable — a conventional automated control an auditor
tests cheaply and once. An agent judgment is neither. `SOC1-04` already splits on exactly this line
when it permits an agent to complete a transaction assigned by an approved rule while requiring human
authorisation for anything derived from untrusted content.

The rule path is the one to maximize. Making it invisible in the data removes the incentive to.

### 4. Versions are verified against a registry, never accepted as free text

The runtime presents the **digest of the prompt and tool-definition bundle it actually loaded**, and
CFOKit refuses the write unless that digest is registered and belongs to the acting principal.

Two weaker mechanisms were considered and both are stale by construction. Encoding the version in the
credential means a process that hot-reloads its artifacts keeps writing under the hour-old token it
already holds. Looking the version up in the registry at write time is worse: a deploy moves the
registry forward, and a process still running the previous bundle has its entries attributed to a
version it never loaded — confidently wrong about a control artifact, which is the one thing worse
than silent.

Reporting what was loaded is the only mechanism that survives a mid-session deploy, and it is why this
is a caller-supplied value rather than an observed one. It stays trustworthy because the check is not
on the value's plausibility but on its existence: an unregistered digest is refused.

Authentication is unaffected by any of this. A runtime obtains one token per session under the client
credentials grant (ADR-0032), and each tool call carries it for local signature and audience
validation against cached JWKS — which ADR-0019 already requires on every request. Nothing here adds
an issuer round trip, and nothing happens per message.

`SOC1-34`'s gate is that **registration precedes rollout**: an edited prompt must be registered before
any runtime loading it can write, and that registration is the moment the change becomes reviewable as
a change to a financial control.

### 5. The decision record is an in-process module

Everything not on the entry — versions in force, tool calls, inputs and context where available,
asserted basis, provider and endpoint (`SOC1-36`) — lives in one immutable decision record per agent
run, written in the same transaction as the postings it produced.

ADR-0022 § 3 classifies it on the first criterion: it must commit atomically with a ledger write. An
entry with a dangling `decision_record_id`, or a decision record with no entry, is precisely the gap
an examiner looks for. So it is a **module**, not a component, and the ledger holds an opaque
identifier without importing it.

One record per run rather than per entry, because versions and context are constant across a run and
duplicating them onto every posting denormalises a per-run value onto the most-written table in the
system.

### 6. Decision records are hash-chained

Each record carries the hash of its predecessor within the entity. This is the tamper-evidence the
practitioner consensus now expects, and it is the same mechanism `SOC1-08` needs for gapless
verifiable sequencing and `SOC1-22` needs for audit records the application cannot silently alter.
One construct, three requirements.

### Consequences

* Good, because the parts an examiner leans on hardest — who acted, on whose behalf, what tools were
  called — need no cooperation from a non-deterministic system.
* Good, because a prompt edit cannot reach production without being registered first, which makes
  `SOC1-34` a gate rather than a habit, and because reporting the loaded digest stays correct across a
  mid-session deploy.
* Good, because the open-ended set of provenance dimensions costs nothing to extend: a new dimension
  is a field on the decision record, not a migration on `posting`.
* Good, because `actor_class` distinguishes the cheap-to-audit rule path from agent judgment, so
  there is an incentive to widen it.
* Good, because hash chaining serves `SOC1-08`, `SOC1-22` and the tamper-evidence expectation at once.
* Bad, because per-run context and tool calls are meaningful storage and a real write-path burden,
  realized at examination time rather than in daily use. `requirements.md` already names this cost.
* Bad, because registering a bundle before it can be used makes deploying a prompt change a release
  operation, which is more ceremony than editing a file and will be felt on every iteration.
* Bad, because the asserted class is irreducibly weaker evidence than the other two, and no mechanism
  here improves it. Labeling is the whole of the remedy.
* Bad, because the verified class is weaker than observed, and a compromised runtime can still name
  another registered version of its own skill. The record says so rather than rounding it up.
* Neutral, because the ledger gains three attribution columns and a pointer. That is a boundary
  clarification rather than a boundary move, but ADR-0022's phrasing needs amending to say so.

### Confirmation

Structural where it can be. `actor_principal_id` and `actor_class` are `NOT NULL` on
`ledger_transaction`, and the service layer derives both from the authenticated principal rather than
from any request parameter — a caller cannot supply them because no write path accepts them. That is
the same device ADR-0013 used for `recorded_at`.

Atomicity is enforced by writing the decision record in the transaction that writes the postings,
under the advisory lock already held (ADR-0011). A test will assert that no posting produced by an
`agent`-class principal exists without a resolvable `decision_record_id`, and that no decision record
is orphaned. **Neither the decision-record module nor that test exists yet**; the four columns ship
ahead of both because append-only forbids adding them afterwards.

An unregistered artifact digest is refused at the write path with a stable error `code` (ADR-0015),
so a runtime carrying an unreleased prompt cannot post at all.

The hash chain is verified by a periodic integrity job, persisted as a durable dated artifact rather
than displayed and discarded (`SOC1-10`).

**Not enforced:** nothing verifies that an asserted basis is truthful, and nothing can. That is the
reason for the labeling rule rather than a gap in it.

## Pros and Cons of the Options

### Capture at the tool boundary

* Good, because the reliable classes need no cooperation from the model.
* Good, because it keeps the ledger's new knowledge to identity and lineage.
* Bad, because it needs a module, a credential-binding scheme, and a hash chain before the first
  agent-posted entry.
* Bad, because it does not close the context gap on its own — only ADR-0034 can.

### Provenance columns on the entry, including model and version

The straightforward reading of the sweep that raised this, and the fastest thing to build.

* Good, because every provenance question becomes a single-table query with no join, which is exactly
  what population stratification and `AU-C 240` journal entry testing want.
* Bad, because the dimensions are open-ended — retrieval index, guardrail config, sampling
  parameters, provider endpoint — and each new one is a migration on `posting`, with every historical
  row `NULL` forever because append-only forbids backfill.
* Bad, because versions are constant across a run, so this duplicates a per-run value onto the
  most-written table.
* Bad, because it cannot hold what `SOC1-06` actually asks for. Nobody puts a context window on a
  posting row, so a separate artifact is needed regardless — and once it exists the versions belong
  on it.
* Bad, because it does move ADR-0022's boundary: `model_version` on a posting is the ledger knowing
  what a model is.

### The skill self-reports provenance as parameters on the write

* Good, because it requires no new infrastructure and captures context the server cannot otherwise
  see, which is the one thing the chosen option cannot do alone.
* Bad, because it is a prompt-based control, which `SOC1-02` excludes by name for authority and which
  fails here for the identical reason. A non-deterministic system asked to record itself faithfully
  will do so most of the time, and an examination does not grade on most.
* Bad, because it is unfalsifiable from inside the system: a run that omitted its own provenance
  leaves nothing indicating that it did.

The verified class in § 4 is not this option. A digest checked for existence against a registry is
refused when wrong; a free-text version, a context blob, or a rationale is accepted whatever it says.
The difference is whether the server can tell.

### Attribution in the audit log only

The status quo, and the least work.

* Good, because `audit_log` already exists, is append-only by trigger, and carries an actor.
* Bad, because it fails `SOC1-15` on its face — the requirement says "in the data itself, **not only
  in an audit record**".
* Bad, because the audit log has a retention schedule (`PLT-20`) and the entry does not, so
  attribution expires while the entry it describes remains. A retention policy would then determine
  what a report can say.
* Bad, because stratifying a population for sampling by joining to a log makes population
  completeness — the thing under test — depend on the join.

### An event-sourced attestation log outside the ledger, joined by time

Keeps the ledger entirely untouched, which is its attraction.

* Good, because it needs no schema change to `ledger_transaction` at all, and would let provenance
  evolve on its own cadence.
* Bad, because a join by time is not an attribution. Two agent runs overlapping on one entity make
  the mapping ambiguous, and ambiguity at exactly the point an examiner is testing is worse than
  absence.
* Bad, because nothing makes the log and the ledger commit together, so a failure between them
  produces entries with no attestation and no way to detect which.

## More Information

**Follow-on obligations.**

* ADR-0022's phrasing — "the ledger knows nothing about ... agents" — is amended to permit principal
  class and delegation, which are identity concepts. The boundary test is unchanged.
* A principal registry outside the ledger resolving `actor_principal_id` to a skill, its versions, and
  its owner.
* An artifact registry holding the digest of every released prompt and tool-definition bundle, keyed
  to the skill it belongs to. Registration precedes rollout, and a digest is never unregistered while
  entries produced under it survive.
* A control-environment change log recording model and skill version changes with effective dates,
  giving `SOC1-35` its change-management narrative. A decision record citing a version with no
  corresponding change-log entry is an unrecorded change to a financial control, and that invariant is
  itself a control worth testing.
* Eval results attach to the change-log entry as the change's test evidence. Evals demonstrate design
  effectiveness, never operating effectiveness, and must not be offered as the latter.
* `docs/product/requirements.md` gains the `actor_class` values as a stated property, since a reader
  comparing CFOKit against another system needs to know the rule path is distinguishable.

**Reversal cost. High.** The four entry columns ship in the first migration that admits an
agent-written entry, for the same reason `recorded_at` did (ADR-0013): added later, every existing row
has an unknowable value and the property can never be reconstructed. The decision record's contents
are cheap to extend and expensive to remove.

Related: [ADR-0034](0034-cfokit-operated-agent-runtime.md) decides what CFOKit is positioned to
observe; ADR-0032 holds the credential mechanism; ADR-0022 § 3 classifies the module.

## Revisit when

* `SOC1-08`'s sequencing decision is made, since it may subsume or replace the hash chain here rather
  than sit beside it.
* An inference provider offers verifiable attestation of model identity, which would move model
  version from asserted to observed independently of who runs the runtime.
* The asserted class grows beyond stated basis and alternatives, which would be a signal that
  something unobservable is being relied on as evidence.
