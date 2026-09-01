---
status: "draft"
kind: "substrate"
date: 2026-08-17
decision-makers: [Geoff]
---

# ADR-0020: Repository directories are organised by artifact kind

## Context and Problem Statement

The repository was set up for agentic development while it was still nearly empty: `CLAUDE.md`, a
misplaced `README.md`, and five accepted decision records. `CLAUDE.md` already described a repo map —
`packages/ledger`, `packages/skill`, `packages/plaid-sync`, `infra/` — none of which existed.
Committing to that map without examining it would have made two problems structural.

**`packages/skill` conflates two artifact kinds.** A `packages/` directory in a `uv` workspace holds
Python distributions; `uv sync` installs its members. An agent skill is a `SKILL.md` bundle with
resources. It is not installable, has no dependency graph, and its presence in the workspace globs
would break `uv sync`. ADR-0014 goes further: the skill and the ledger are separate systems that
share only a tool contract. Housing them in one installable tree works against a boundary the project
treats as hard.

**`packages/skill` is singular.** The product vision covers bookkeeping, tax preparation, cash flow
monitoring, compliance tracking, and reporting. Whether these become separate skills or one skill with
several modes is undecided, but "the skill" is wrong under either answer.

What packages are *named* is a separate question, answered in
[ADR-0031](0031-packages-named-for-capabilities.md). Where each kind of *document* lives is a third,
answered in [ADR-0001](0001-documentation-structure.md), which is authoritative for the documentation
tree.

## Decision Drivers

* A `uv` workspace globs `packages/*`, so anything non-installable placed there breaks `uv sync`.
* Immutable records must not sit inside the working area an agent edits constantly.
* The skill/ledger boundary (ADR-0014) should be structural, not merely stated.
* Directories that exist but hold nothing teach a contributor the wrong map.

## Considered Options

* Directories organised by artifact kind, with `packages/` reserved for distributions
* One tree under `docs/`, with `docs/specs/`
* Everything under `specs/`, including decision records
* Keep skills under `packages/`
* Ship skills as a Claude plugin bundle
* Everything is a decision record; no separate policy document
* Split the bundled records into pure requirements and pure decisions

## Decision Outcome

Chosen option: "Directories organised by artifact kind, with `packages/` reserved for distributions",
because artifact kind is what determines whether a thing is installable, immutable, or shipped — and
those are the properties that break when a directory holds two kinds at once.

```
packages/         Python distributions; the uv workspace, and nothing else
skills/           Shipped SKILL.md bundles; plural
docs/decisions/   Decision records; immutable once accepted
docs/product/     vision.md, requirements.md
infra/            OpenTofu for the one maintained cloud target
.claude/          Tooling for developing this repo; never shipped
```

Two artifact kinds carry authority in different ways, and confusing them is what the layout prevents:

| Kind | Answers | Read by | Authority |
|---|---|---|---|
| Requirement | What must it do | Product, contributors, auditors | Traceable to the vision |
| Decision record | Why did we decide | Contributors, future maintainers | Rejected alternatives |

Consequent moves:

- `packages/skill` becomes `skills/bookkeeper/`.
- The decision-record index lives at `docs/decisions/README.md`, where `CLAUDE.md` already said it was
  and where its relative links resolve.

**Directories are not created speculatively.** A surface arrives with the decision that sanctions it.

### Consequences

* Good, because `packages/*` can be globbed rather than enumerated, so a new distribution installs
  without anyone remembering to edit the root manifest.
* Good, because immutable records live outside the working tree an agent edits, making the mistake
  structurally awkward rather than merely forbidden.
* Good, because the skill/ledger boundary has no import path to cross: skills are not distributions at
  all.
* Bad, because there are two top-level documentation trees rather than one.
* Bad, because namespace packages mean no `src/cfokit/__init__.py`; a contributor who adds one breaks
  the other distribution's imports in a way that is confusing to diagnose.

### Confirmation

`uv sync` fails if something non-installable is added under `packages/`, which makes the main rule
self-enforcing. `import-linter` enforces the ADR-0014 boundary as a contract rather than a convention,
inside `uv run task lint`.

`scripts/check_decisions.py` (CI gate 6) asserts that `docs/decisions/` and its index agree, which is
the one part of this layout that could drift silently (ADR-0001).

## Pros and Cons of the Options

### Directories organised by artifact kind, with `packages/` reserved for distributions

* Good, because it splits on the property that actually differs — installable, immutable, shipped.
* Good, because each rule is enforced by tooling that already exists.
* Bad, because it is more top-level directories than a small repository strictly needs.

### One tree under `docs/`, with `docs/specs/`

The simplest taxonomy and one place to look.

* Good, because there is one place to look and nothing to learn.
* Bad, because it houses an append-only immutable store inside the working area an agent edits
  constantly. Immutability is a rule an agent can read and still violate while editing neighbouring
  files.

### Everything under `specs/`, including decision records

Considered because specifications are the primary agentic input and deserve prominence.

* Good, because it would put the most-read documents at the top of the tree.
* Bad, because it inverts the dependency — specifications cite decisions and decisions constrain
  specifications, so nesting decisions inside specifications gets the relationship backwards.
* Bad, because it mixes lifecycles in a worse position than the option above.

### Keep skills under `packages/`

Preserves one tree.

* Good, because everything the project ships would live in one place.
* Bad, because it requires enumerating workspace members instead of globbing them, so every new
  package silently fails to install until someone remembers to edit the root manifest.
* Bad, because it keeps the category error that ADR-0014's boundary exists to prevent.

### Ship skills as a Claude plugin bundle

The official layout for distributing skills, agents, and commands as one versioned, installable unit,
and a plausible eventual answer.

* Good, because it is the supported distribution path and would version the bundle properly.
* Bad, because it commits to plugin installation as the distribution path, and the vision points at a
  hosted service reached through Slack, which ADR-0014 reinforces. Choosing a distribution mechanism
  before the delivery surface is settled is the wrong order. Rejected **for now** rather than on merit.

### Everything is a decision record; no separate policy document

The status quo, and it has a real argument: one place to look, and every decision keeps its rejected
alternatives.

* Good, because it avoids a second document restating settled decisions in different words.
* Good, because `requirements.md` already states what the numbers mean, in the register an auditor
  reads, with stable ids — so a policy document would duplicate it rather than serve an unserved
  audience.
* Bad, because a reader looking for "what is your cost basis method?" must know that requirements,
  not decisions, is where to look. ADR-0001 accepts that cost and makes `requirements.md` serve the
  auditor and the contributor alike.

### Split the bundled records into pure requirements and pure decisions

Tempting for taxonomic cleanliness: move the obligation half of the requirement-driven records into
requirements and leave only the mechanism behind.

* Good, because each document would then contain exactly one kind of statement.
* Bad, because the requirement halves already exist and are cited by id; splitting further would
  double the documents and create two places to keep in sync.
* Bad, because the mechanism is most comprehensible directly beside the obligation it satisfies. This
  is a different question from whether one record holds two *decisions*, which ADR-0001's rule 3
  governs.

## More Information

**Follow-on obligations.**

- `packages/*` globbing stays valid, so nothing non-installable may be added under it.
- `import-linter` enforces the ADR-0014 boundary as a contract rather than a convention.
- The skills layout is provisional pending the delivery-surface decision and the question of whether
  agent roles split.

**Reversal cost.** Low. The directory moves are renames plus a `CLAUDE.md` edit, and git records them
as renames.

Related: [ADR-0001](0001-documentation-structure.md) is authoritative for the documentation tree and
supersedes anything this record would otherwise imply about it;
[ADR-0031](0031-packages-named-for-capabilities.md) holds the naming rule.

## Revisit when

- The delivery surface is decided, at which point the plugin-bundle question is answerable on its
  merits rather than deferred.
- Agent roles are settled as separate skills or one skill with modes, which determines whether
  `skills/` needs internal structure.
- A kind of artifact arrives that none of the directories above fits.
