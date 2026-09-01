---
status: "draft"
kind: "requirement-driven"
date: 2026-08-17
decision-makers: [Geoff]
---

# ADR-0015: Three published interfaces, each with a committed artifact and a diff gate

**Requirements served:** `PLT-03`, `NFR-13`.

## Context and Problem Statement

CFOKit publishes interfaces that other people build against: third-party integrators write against
the REST API, MCP clients and the bookkeeper skill call the tool surface, and callers of both branch
on error codes. Skills reach the ledger only through that published surface and never through code
(ADR-0014), which makes the contract load-bearing internally as well as externally.

The failure mode to prevent is specific and mundane: **a breaking change that nobody noticed
making.** Renaming a field, tightening a validation, reordering an enum, or rewording an error
string are all one-line edits that look harmless in review and break a caller in production. Nothing
about writing the change makes its consequence visible, which is why this needs a mechanism rather
than a rule.

Semantic versioning does not solve it. A version number records an intention after the fact; it does
not detect that the change requiring a major bump has occurred.

## Decision Drivers

* A breaking change must become visible to a reviewer who was not thinking about compatibility.
* One source of truth for behaviour. ADR-0009 makes the service layer the single definition, and
  nothing here may create a second.
* Internal structure must stay free to change; only what is published is frozen.
* Additive evolution must stay cheap, or a published interface stops growing.

## Considered Options

* Three published interfaces, each with a committed generated artifact and a CI diff gate
* Semantic versioning of the service, without committed artifacts
* Generate the documents but do not commit them
* Hand-maintain the OpenAPI document as the source of truth, generating code from it
* Publish only REST, and treat MCP as internal
* Free-text error messages, no codes
* Treat every interface change as breaking and version aggressively

## Decision Outcome

Chosen option: "Three published interfaces, each with a committed generated artifact and a CI diff
gate", because a committed artifact is the only mechanism that detects a breaking change rather than
relying on the author to recognise one.

`PLT-03` obliges a documented interface for third parties carrying stated obligations about how and
when it may change, and `NFR-13` obliges breaking changes to be announced rather than discovered.
This record decides which interfaces those are and what makes the obligation real.

Three interfaces are **published**, meaning third parties may depend on them and we may not change
them without review:

| Interface | Committed artifact | Consumers |
|---|---|---|
| **REST API** | Generated OpenAPI document | Third-party integrators |
| **MCP tool surface** | Generated tool descriptions | Skills, MCP clients, agents |
| **Error codes** | Enumerated stable `code` values | Callers of both surfaces |

For each: **the generated artifact is committed to the repository, and CI regenerates it and fails
on any diff.** A diff is not an error — it is the signal that a contract changed and needs review.

Everything else — the service layer, the repository, module structure, the schema — is internal and
may change freely.

**Error codes are part of the contract.** Adding a code is a contract change; renaming or removing
one is breaking. Error *messages* are explicitly **not** contractual and may be reworded at will,
which is the entire reason the code exists.

The environment-variable surface is deliberately not a fourth published interface here. ADR-0016
owns it as the deployment contract, and splitting ownership across two records would give it two
change procedures.

### Consequences

* Good, because a breaking change appears as a diff in review rather than as a support ticket.
* Good, because generating from the implementation keeps one source of truth while still making
  changes visible.
* Good, because a stable `code` makes error messages safely editable, rather than accidentally
  contractual.
* Bad, because generated artifacts appear in reviews and produce diff noise on unrelated refactors.
* Bad, because a deliberate contract change requires regenerating and committing, an extra step that
  will occasionally be forgotten and caught by CI. That is the gate working, not a defect.
* Bad, because error codes accumulate and cannot be tidied up, since removing one is breaking.

### Confirmation

CI gate 5: regenerate the OpenAPI document and the MCP tool descriptions, then `git diff
--exit-code`. **Scaffolded and commented out** in `.github/workflows/ci.yml`, pending the adapters
existing (M4). Until it is switched on, this record is enforced by review.

The gate depends on the generator being deterministic — nondeterministic ordering in the generated
output would make the diff meaningless rather than merely noisy.

## Pros and Cons of the Options

### Three published interfaces, each with a committed artifact and a CI diff gate

* Good, because it detects breaking changes mechanically instead of relying on the author's
  judgement.
* Good, because it leaves internal structure entirely free.
* Bad, because it puts generated files in the repository and in every review.
* Bad, because it requires a deterministic generator, which is a real constraint on tooling choice.

### Semantic versioning of the service, without committed artifacts

The conventional approach: declare a version, bump it appropriately, publish a changelog.

* Good, because it is universally understood and communicates intent to consumers.
* Bad, because it detects nothing. It relies on the author of a change recognising it as breaking,
  which is precisely the judgement that fails — the whole difficulty is that breaking changes do not
  announce themselves at the keystroke. Versioning remains useful *on top* of this, as a way to
  communicate a change we have already detected.

### Generate the documents but do not commit them

Cleaner repository, no generated files in review, artifacts always current by construction.

* Good, because the artifact can never be stale, and reviews stay free of generated noise.
* Bad, because it removes the only moment at which a breaking change becomes visible. If the
  document is generated at build time and discarded, nothing compares this build's contract to the
  last one. The generated file in the diff *is* the mechanism.

### Hand-maintain the OpenAPI document as the source of truth, generating code from it

The design-first approach, and genuinely good practice in many projects: the contract cannot drift
because it is authored deliberately.

* Good, because the contract is then designed rather than emergent, and review happens before the
  code exists.
* Bad, because it inverts a dependency ADR-0009 deliberately set. The service layer is the single
  definition of behaviour, with two thin adapters over it; a hand-written contract would become a
  third definition, able to disagree with both adapters.

### Publish only REST, and treat MCP as internal

Tempting because MCP is consumed mainly by our own skill, so it feels like an implementation detail.

* Good, because it would halve the committed surface and leave the tool descriptions free to churn
  during early development.
* Bad, because it is untrue in a way that would eventually embarrass us. The tool surface is
  documented for MCP clients generally, third-party agents are an explicit audience, and skills are
  forbidden from any other route (ADR-0014). Shipping an interface while calling it internal means
  breaking it without notice, which is worse than not offering it.

### Free-text error messages, no codes

Less machinery, and messages can be improved freely.

* Good, because it removes an enumeration to maintain and lets error text improve continuously.
* Bad, because callers parse whatever distinguishes one failure from another. Without a code, the
  message *becomes* the API by accident — and then it cannot be improved without breaking someone,
  which is the reverse of the intended outcome.

### Treat every interface change as breaking and version aggressively

Maximally safe.

* Good, because no consumer is ever surprised.
* Bad, because it makes additive changes — a new optional field, a new tool — as expensive as
  removals, which discourages the additive evolution a published interface is supposed to allow.

## More Information

**Follow-on obligations.**

* A generation command — `task generate-contracts` or similar — that is deterministic.
* CI gate 5: regenerate, then `git diff --exit-code`.
* Committed artifacts live in a stable location, versioned with the code.
* A deprecation policy: how long a deprecated field, tool, or code survives before removal. **Not yet
  decided** — needs settling before the first removal, not before the first release.
* Error codes are enumerated in one place (`errors.py` already exists for this) rather than
  string-literalled at raise sites.
* Both adapters surface the same code for the same condition.

**Reversal cost. Low mechanically, high reputationally.** Dropping the gate is deleting a CI job. But
once integrators depend on the surfaces, withdrawing the stability commitment is a breach of what
they built against.

## Revisit when

* The diff gate produces mostly noise rather than signal, which would indicate the generator is
  nondeterministic and needs fixing rather than the gate needing removal.
* A fourth published interface appears — a webhook surface or an export format would qualify — at
  which point this record is extended rather than replaced.
* The first deprecation is needed, which forces the deprecation policy to be written.
