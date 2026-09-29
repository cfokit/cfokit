---
status: "draft"
kind: "requirement-driven"
date: 2026-08-31
decision-makers: [Geoff]
---

# ADR-0034: CFOKit ships an agent runtime, and the SOC 1 boundary is drawn at it

**Requirements served:** `NFR-22`, `SOC1-06`, `SOC1-35`.

## Context and Problem Statement

Two independent problems arrive at the same answer.

**The system cannot see what decided the accounting.**
[ADR-0033](0033-provenance-captured-at-the-tool-boundary.md) splits provenance by how it is
established — observed at the tool boundary, enforced at credential issuance, or merely asserted.
Against a published MCP surface reached by a client the customer chose, `SOC1-06`'s five items fall
badly:

| `SOC1-06` item | Observable by CFOKit |
|---|---|
| Tool calls made | **Yes.** The API is the tool surface. |
| What was written, timestamps | **Yes.** |
| Acting principal, principal acted for | **Yes.** From the token. |
| Model identifier and version | **No.** Asserted by the client, or absent. |
| Inputs and context supplied | **No.** Only the runtime sees the context window, the operator's messages, and an uploaded file's contents. |

The two missing rows are the ones that matter. Practitioner accounts of what auditors ask first
reduce to *"show me what the AI saw"* and *"is this the same AI that ran last quarter?"*

**A runtime we do not operate makes accounting judgments whose failures are silent.**
This is the larger problem and it is not about evidence at all. `NFR-22` states the limit: correctness
guarantees attach to what the ledger records and computes, never to a judgment an agent made. A
poorly chosen or poorly configured model does not fail visibly — it produces plausible wrong
accounting. A transaction coded to a defensible-looking wrong account is indistinguishable, at a
glance, from a correct one.

That failure mode is categorically unlike every other external dependency. When a mail service is
absent, nothing sends and the operator knows (`PLT-06`). When a feed is absent, no transactions
arrive and the coverage check notices (`SOC1-13`). Absence is visible. **Bad inference is present and
wrong**, and it lands in the books.

The gap is structural rather than a matter of effort: with a published tool surface (`PLT-01`,
ADR-0015) anybody may point any model at it, and CFOKit cannot know what did.

ADR-0021 § 6 deferred the agent runtime as "a separate concern with its own decisions to make". This
is that decision.

## Decision Drivers

* `NFR-22` — no assurance may be claimed for a component CFOKit cannot observe, and the honest scope
  of the correctness claim has to be visible rather than implied.
* Two of `SOC1-06`'s five items are unobservable from outside a runtime CFOKit operates.
* A complementary user entity control the user entity cannot actually perform is worse than none: it
  reads as a disclaimer over the requirement it was meant to satisfy.
* Carve-out is conventional for a subservice organization, but here the carved-out party's output *is*
  the coding decision (`ES-4`).
* `PLT-01` and `NFR-17` are not negotiable: the books stay reachable by agent software the
  organization chooses, and no build withholds a capability.

## Considered Options

* CFOKit ships an agent runtime, and the SOC 1 opinion covers entries produced through it
* A runtime conformance contract, with the obligation carried by the customer as a CUEC
* The inference provider as an inclusive subservice organization
* Carve out the runtime and disclose the gap
* A proprietary first-party runtime, available only to the attested tier
* Restrict the covered population to rule-assigned coding, excluding agent judgment
* No SOC 1 opinion covering agent-produced entries

## Decision Outcome

Chosen option: "CFOKit ships an agent runtime, and the SOC 1 opinion covers entries produced through
it", because model identity and captured context are unobservable from outside a runtime we operate,
for a structural reason that no contract, disclosure or user-entity control removes.

> An entry is inside the SOC 1 boundary when it was produced through a CFOKit-operated runtime.
> Entries produced through any other client are outside it. Coverage is derived from the acting
> principal's client registration, never claimed by a caller.

### 1. The runtime is Apache 2.0, like everything else

This is decided here rather than inherited. Shipping a runtime is what puts `NFR-17` in play, so the
record that ships one has to say what its licence is.

**Apache 2.0** (ADR-0026). A self-hoster builds the same runtime, points it at their own deployment,
supplies their own inference credential, and gets identical provenance capture. It is an
**additional** client, not a replacement for any other: `PLT-01` is untouched, the published tool
surface stays the only route to the ledger (ADR-0014), and nothing is withheld from any build, so
`NFR-17` and `NFR-14` are untouched too.

Three things decide it against a proprietary runtime.

**Secrecy is not what enforces the boundary.** Coverage derives from client registration against
CFOKit's issuer in CFOKit's deployment (§ 2). A runtime someone builds from source cannot mint a
covered-class credential, because registration is controlled, not the code. So the SOC 1 claim is
exactly as strong either way — the one thing that might have argued for proprietary does not.

**Readable capture logic is an asset with this buyer.** The customer asking for SOC 1 is asking
because an agent is making accounting judgments. A black box making those judgments is a harder
conversation with their auditor than a runtime whose capture logic they can read.

**A proprietary runtime would protect the plumbing and not the differentiator.** Skills, prompts and
tool definitions are already Apache 2.0 in `skills/` (ADR-0014, ADR-0020), and `SOC1-34` makes prompts
versioned control artifacts. Coding quality lives in those, and they are public. Closing the runtime
around public prompts buys very little.

What is commercial is not software. It is CFOKit's **attested operation** of that runtime — which a
self-hoster could not receive in any case, because they operate their own deployment and are not a
service organization to themselves. This is the vision's own position: the commercial product is the
hosted service, and what it sells is assurance.

**The clause most likely to erode.** The risk is that "the attested tier" becomes the reason a
capability lands there first and elsewhere later, which is how a complete build becomes a limited
edition one commit at a time. `NFR-17` is the check, and it must keep failing in that case.

### 2. Coverage is derived, and legible to an operator

A CFOKit-operated runtime authenticates as a registered client class a third-party client cannot mint
(ADR-0032). Coverage is therefore a property of how an entry was produced, not a flag,
and the covered population is queryable — which is what an examiner needs when sampling.

Two classes of entry in one ledger is a real cost, and it is not only an examiner's problem. A
fractional CFO with some clients inside the boundary and some outside must be able to see which is
which without asking. That is `NFR-22`'s "states that limit rather than implying uniform assurance",
and it is a product obligation, not a footnote.

### 3. What this does not decide

**Who supplies inference.** A CFOKit-operated runtime can pin a model identifier and version, capture
the context window, and record everything server-side while calling a third-party inference API under
a credential the *customer* supplies. That satisfies `SOC1-06` and `SOC1-35` as completely as owning
inference, and preserves the cost structure the vision argues for — the end user carries the token
cost, and margin does not move with token prices.

Owning inference buys commercial control and a negotiable provider agreement, which matters for
`SOC2-09` and `SOC2-10`. It buys little additional evidence: neither arrangement prevents a provider
changing a model behind a stable identifier.

These are separable — either could be superseded without reopening the other — so under
ADR-0001's one-decision-per-file rule they are two records. This one decides the runtime.

**What the runtime is.** Desktop, mobile, terminal, or something else is a product-surface question,
and a user-facing interaction surface is adjacent enough to the "web UI or admin console" non-goal
that it clears ADR-0012's gate on its own terms, as Slack did in ADR-0021. This record establishes
only that *some* CFOKit-operated runtime exists.

### Consequences

* Good, because the honest scope of the correctness claim becomes a property of the data rather than a
  caveat in a document (`NFR-22`).
* Good, because `SOC1-06` becomes satisfiable instead of partly unmeetable, and `SOC1-35` answerable —
  a pinned model identifier checked against a registry is the difference between a version we can
  refuse when wrong and one we can only hope a client reported honestly.
* Good, because it matches the commercial thesis already in the vision, where the attested operating
  history is the asset a fork cannot copy.
* Good, because nothing is withheld: the runtime ships everywhere and only the attestation is
  commercial.
* Bad, because it puts a client application on the maintenance ledger permanently, with its own
  release cadence, platform targets and support burden. Nothing about the ledger's design prepares for
  that, and it is a much larger commitment than any record so far.
* Bad, because two classes of entry in one ledger is a concept operators must hold, and the boundary
  will be invisible at exactly the moment someone assumes it is not there.
* Bad, because ADR-0014's argument that skills keep the API honest by using the published surface
  weakens once a first-party runtime exists — it is the obvious place for a private privilege to
  appear.
* Neutral, because self-hosted deployments lose no capability and gain no attestation, which is the
  same position they were already in.

### Confirmation

Coverage is derived, never asserted: the acting principal's client registration determines it, and a
third-party client cannot mint a covered-class credential (ADR-0032). A test will assert that an entry
marked covered resolves to a decision record carrying a model identifier in the **verified** class of
ADR-0033 § 1 — checked against the registry of models the runtime is released to call — so a covered
entry whose model was merely asserted fails. Operating the runtime moves model identity from
asserted to verified; it does not make it observed, and this record does not claim otherwise.

The first-party runtime uses the published tool surface and no other. `import-linter` cannot see
across that boundary, so this is a review rule plus the structural fact that the runtime is a separate
artifact with no dependency on ledger code (ADR-0014, ADR-0020).

**Not gated:** the erosion risk in § 1. No check distinguishes "shipped to the attested runtime first"
from "withheld". `NFR-17` and review are the whole of the protection, which is weaker than every other
gate here.

## Pros and Cons of the Options

### CFOKit ships an agent runtime, SOC 1 covering entries produced through it

* Good, because it is the only option where context and model identity are observed rather than
  asserted.
* Good, because coverage is derivable per entry, so the examined population is well defined.
* Bad, because it is a permanent commitment to a client application.
* Bad, because it creates a first-party path that could acquire privileges the published surface lacks.

### A runtime conformance contract, with the obligation carried as a CUEC

The option to beat, and the one that changes least. It mirrors ADR-0019 exactly: publish what a
conforming runtime must do — report model identifier and version, capture the context supplied, retain
it for the life of the entry — and make it a complementary user entity control, which every SOC 1
report carries some of.

* Good, because it needs no client application at all, and reuses a contract-and-conformance pattern
  the corpus already trusts.
* Good, because it keeps every deployment on exactly one path, which is ADR-0014's whole argument.
* Bad, because the user entity cannot perform it. A small business or a fractional CFO running an
  off-the-shelf client has no such control, cannot evidence it, and has no auditor testing it.
* Bad, because unlike ADR-0019's issuer contract, conformance is unverifiable. An issuer either
  supports RFC 8707 or does not, and a suite can tell; whether a runtime faithfully recorded a context
  window cannot be established from outside it.
* Bad, because it does nothing for `NFR-22`. A conformance contract can require a runtime to *report*
  its model; it cannot make that model good.

### The inference provider as an inclusive subservice organization

* Good, because it would put model identity and behavior inside the examined system, which is where
  the problem actually lives.
* Bad, because the inclusive method requires the provider to open its controls to our auditor and
  coordinate the engagement. No major inference provider will do that at this scale, so the option is
  unavailable rather than merely expensive.

### Carve out the runtime and disclose the gap

The conventional treatment, and the cheapest.

* Good, because carve-out is the normal method, needs nobody's cooperation, and would let a report be
  issued sooner.
* Bad, because the carved-out party's output is the coding decision itself. `ES-4` already flags this:
  carve-out is conventional, but this output feeds the books directly, unlike infrastructure. A report
  carving out the thing that decided the accounting has carved out its own subject matter.

### A proprietary first-party runtime, available only to the attested tier

The version of this decision that adds a software moat to the assurance one, and the one that will be
re-proposed the first time a competitor forks the repo.

* Good, because it is a thing a fork cannot reproduce, on top of the attestation that a fork already
  cannot reproduce.
* Good, because it would allow the runtime to diverge commercially without a parity obligation.
* Bad, because it withholds a capability from the self-hosted build, which `NFR-17` forbids and
  `NFR-14` sits badly with. Both would need amending, and the vision's "complete rather than a limited
  edition" would need rewriting.
* Bad, because it buys no additional protection for the SOC 1 boundary, which registration control
  already enforces.
* Bad, because it closes the plumbing while the prompts that actually determine coding quality stay
  public, so the moat it builds is around the wrong asset.
* Bad, because an unreadable component making accounting judgments is a liability in precisely the
  sale this tier exists for.

### Restrict the covered population to rule-assigned coding

Cover only entries a deterministic rule assigned, excluding agent judgment entirely. This is the
option that dissolves the problem rather than solving it, and it deserves more credit than it will
get: rule-assigned coding is re-derivable, cheap to test, and `SOC1-04` and ADR-0033 § 3 already make
it distinguishable in the data.

* Good, because it needs no runtime, no new client, and no unobservable component inside the boundary.
* Good, because it is genuinely the strongest evidence position available, and the rule path is one to
  widen regardless.
* Bad, because agent-made judgments are the product. The segment demanding SOC 1 is demanding it
  precisely because an agent keeps the books, and a report covering everything except that answers a
  question nobody asked.

### No SOC 1 opinion covering agent-produced entries

* Good, because it is honest, costs nothing, and the ledger controls are the strongest part of the
  system regardless. `ES-2` already contemplates a narrower Type 1 first.
* Bad, for the same reason as the option above, and without its compensating gain in evidence quality.

## More Information

**Follow-on obligations.**

* The product-surface decision — desktop, mobile, or otherwise — clears ADR-0012's gate on its own
  terms and is recorded there when it passes, as ADR-0021 was.
* A separate record on inference credential ownership (§ 3).
* The first-party runtime consumes the published tool surface and no other.
* Coverage is legible to an operator, not only to an examiner (§ 2).
* `ES-4` is answered by this record for the covered path and stays open for every other.
* The vision's *Cost structure* section describes installing into a runtime the user already has as
  the only shape. It is now the default shape, and that paragraph needs revising to say so — a
  positioning change, not a record's to make.

**On one decision per file.** The licence clause is kept here rather than split out because shipping a runtime is
what raises the question — there is nothing to license otherwise — and because flipping it would
require amending `NFR-17` and `NFR-14`, which is a superseding record on this one either way.

**Reversal cost. High and asymmetric.** Withdrawing a runtime customers have standardized on is worse
than never shipping one, and withdrawing an attestation is a commercial event rather than an
engineering one. Deciding *not* to do this stays cheap until the first covered customer.

Related: [ADR-0033](0033-provenance-captured-at-the-tool-boundary.md) holds the mechanism this record
scopes; ADR-0021 § 6 deferred the question to here; ADR-0014 holds the tool-surface boundary this must
not erode.

## Revisit when

* An inference provider offers verifiable attestation of model identity to a caller, which would move
  the decisive row from asserted to observed and reopen every option above.
* The AICPA publishes SOC guidance addressing AI systems. None exists for SOC 1 or SOC 2 today, so
  this record reasons without precedent and should be re-read against the first that appears.
* A third-party runtime appears that genuinely evidences context capture, which would make the CUEC
  option meetable rather than nominal.
* `ES-3` is answered. If SOC 1 demand comes from fractional CFOs acting for clients rather than from
  the companies themselves, the entity bearing the requirement changes and so does who must operate
  the runtime.
