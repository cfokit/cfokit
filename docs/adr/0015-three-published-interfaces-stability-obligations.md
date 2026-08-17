# ADR-0015: Three published interfaces, each with a committed artifact and a diff gate

- **Status:** Accepted
- **Date:** 2026-08-17
- **Deciders:** Geoff

> **Note on provenance.** The backlog title was "Three published interfaces and their stability
> obligations", but *which* three was never recorded. They are derived here from the rules that cite
> this ADR: `CLAUDE.md`'s CI gate 5 names OpenAPI and MCP tool descriptions, and its observability
> section attributes stable machine-readable error codes to ADR-0015. The environment-variable
> surface was the other candidate and was ruled out because ADR-0016 already owns it as the
> deployment contract.
>
> This was reconstruction rather than recollection, and it is recorded as such. If the original
> intent differs, that is a superseding ADR, not an edit.

## Context

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

## Decision

Three interfaces are **published**, meaning third parties may depend on them and we may not change
them without review:

| Interface | Committed artifact | Consumers |
|---|---|---|
| **REST API** | Generated OpenAPI document | Third-party integrators |
| **MCP tool surface** | Generated tool descriptions | Skills, MCP clients, agents |
| **Error codes** | Enumerated stable `code` values | Callers of both surfaces |

For each: **the generated artifact is committed to the repository, and CI regenerates it and fails
on any diff.** A diff is not an error — it is the signal that a contract changed and needs review.
This is CI gate 5.

Everything else — the service layer, the repository, module structure, the schema — is internal and
may change freely.

**Error codes are part of the contract.** Adding a code is a contract change; renaming or removing
one is breaking. Error *messages* are explicitly **not** contractual and may be reworded at will,
which is the entire reason the code exists.

## Alternatives rejected

### Semantic versioning of the service, without committed artifacts

The conventional approach: declare a version, bump it appropriately, publish a changelog.

Rejected because it detects nothing. It relies on the author of a change recognising it as breaking,
which is precisely the judgement that fails — the whole difficulty is that breaking changes do not
announce themselves at the keystroke. A committed artifact plus a diff makes the change visible to a
reviewer who was not thinking about compatibility. Versioning remains useful *on top* of this, as a
way to communicate a change we have already detected.

### Generate the documents but do not commit them

Cleaner repository, no generated files in review, artifacts always current by construction.

Rejected because it removes the only moment at which a breaking change becomes visible. If the
document is generated at build time and discarded, nothing compares this build's contract to the
last one. The generated file in the diff *is* the mechanism.

### Hand-maintain the OpenAPI document as the source of truth, generating code from it

The design-first approach, and genuinely good practice in many projects: the contract cannot drift
because it is authored deliberately.

Rejected here because it inverts a dependency that ADR-0009 deliberately set. The service layer is
the single definition of behaviour, with two thin adapters over it; a hand-written contract would
become a third definition, able to disagree with both adapters. Generating from the implementation
and gating on the diff keeps one source of truth while still making changes visible.

### Publish only REST, and treat MCP as internal

Tempting because MCP is consumed mainly by our own skill, so it feels like an implementation detail.

Rejected as untrue in a way that would eventually embarrass us. The tool surface is documented for
MCP clients generally, third-party agents are an explicit audience, and skills are forbidden from any
other route (ADR-0014). Shipping an interface while calling it internal means breaking it without
notice, which is worse than not offering it.

### Free-text error messages, no codes

Less machinery, and messages can be improved freely.

Rejected because callers parse whatever distinguishes one failure from another. Without a code, the
message *becomes* the API by accident — and then it cannot be improved without breaking someone,
which is the reverse of the intended outcome. A stable code is what makes messages safely editable.

### Treat every interface change as breaking and version aggressively

Maximally safe.

Rejected as impractical: it makes additive changes — a new optional field, a new tool — as expensive
as removals, which discourages the additive evolution that a published interface is supposed to
allow.

## Consequences

**Accepted costs.**
- Generated artifacts appear in reviews and produce diff noise on unrelated refactors.
- A deliberate contract change requires regenerating and committing, which is an extra step that
  will occasionally be forgotten and caught by CI. That is the gate working, not a defect.
- Error codes accumulate and cannot be tidied up, since removing one is breaking.

**Follow-on obligations.**
- A generation command — `task generate-contracts` or similar — that is deterministic. Nondeterministic
  ordering in the generated output would make the diff gate useless.
- CI gate 5: regenerate, then `git diff --exit-code`. **Scaffolded and commented out** in
  `.github/workflows/ci.yml`, pending the adapters existing (M4).
- Committed artifacts live in a stable location, versioned with the code.
- A deprecation policy: how long a deprecated field, tool, or code survives before removal. **Not yet
  decided** — needs settling before the first removal, not before the first release.
- Error codes are enumerated in one place (`errors.py` already exists for this) rather than
  string-literalled at raise sites.
- Both adapters surface the same code for the same condition.

**Reversal cost. Low mechanically, high reputationally.** Dropping the gate is deleting a CI job.
But once integrators depend on the surfaces, withdrawing the stability commitment is a breach of
what they built against.

## Revisit when

- The diff gate produces mostly noise rather than signal, which would indicate the generator is
  nondeterministic and needs fixing rather than the gate needing removal.
- A fourth published interface appears — a webhook surface or an export format would qualify — at
  which point this record is extended rather than replaced.
- The first deprecation is needed, which forces the deprecation policy to be written.
