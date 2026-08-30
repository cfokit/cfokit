---
status: "deprecated"
kind: "substrate"
date: 2026-08-17
decision-makers: [Geoff]
---

# ADR-0022: Spec Kit is the specification workflow; CLAUDE.md remains the sole constitution

> Spec Kit and `.specify/` are removed from the repository. Documentation
> structure is settled by ADR-0001.

## Context

The repository had rules (`CLAUDE.md`) and reasoning (ADRs) but no specification layer. For
a codebase built primarily by agents, the missing artifact is the one that says what a
feature must do before an agent starts writing it.

The question was whether to invent a house format or adopt an existing one. Two facts
settled it.

**The ADR format was already conventional.** It looked bespoke but maps almost section for
section onto [MADR](https://adr.github.io/madr/): the same frontmatter, and mandatory
rejected alternatives, which is MADR's central improvement over Nygard's original five
sections. The local additions — *reversal cost* and *revisit when* — are additive. There was
nothing to standardise.

**Spec Kit is not an ADR tool.** It ships five templates — constitution, spec, plan, tasks,
checklist — and no decision-record template. It is a forward-looking feature workflow, so it
does not compete with the ADRs; it fills the gap beside them.

Spec Kit has one documented weakness that matters here more than in most projects: it does
not reconcile a new plan against decisions already made, so each feature starts from empty
context and re-litigates settled questions. This project has nineteen ADRs and a `CLAUDE.md`
whose stated purpose is preventing exactly that.

## Decision

Adopt **GitHub Spec Kit** (MIT), pinned to a specific tag, as the specification workflow.
Specifications live in `specs/`.

`CLAUDE.md` plus the ADRs remain the **sole constitution**. We do not run
`/speckit-constitution`; its constitution file is reduced to a pointer at `CLAUDE.md` and
the ADR index.

Two templates are overridden locally in `.specify/templates/overrides/`:

1. `spec-template.md` and `plan-template.md` open with a mandatory **"Decisions relied on"**
   block citing ADR numbers, which closes the re-litigation gap.
2. Both are trimmed to the ADRs' terse register.

## Alternatives rejected

### A bespoke specification format

Attractive because the existing documentation has an unusually consistent voice, and
generated Spec Kit output is comparatively verbose. Rejected because the project is actively
recruiting contributors, and a contributor arriving with their own agent gets a workflow it
already recognises for free — Spec Kit is agent-agnostic across many tools. A house format
means every contributor learns ours first. The verbosity objection is answered by the
override mechanism, which is a supported feature rather than a fork.

### Spec Kit's file shape, hand-written, without the tooling

The initial recommendation. It gets the conventional filenames while avoiding a dependency.
Rejected once `.specify/templates/overrides/` was confirmed to exist: the only substantive
objection to the real tooling was template control, and the tooling supplies it. Hand-writing
the shape would have meant reimplementing `/speckit-clarify`, `/speckit-analyze`, and
`/speckit-converge` badly or doing without them.

### Adopting Spec Kit wholesale, including its constitution

Rejected. `CLAUDE.md` is a stronger constitution than the template produces: it cites the
ADR behind each rule and encodes five machine-checkable CI gates. Maintaining both would
create two sources of truth for the project's rules, and the failure mode is silent — an
agent follows whichever it read, and nobody discovers the divergence until a rule is broken
with justification.

### `adrkit` for machine-readable ADRs with lint and CI

Genuinely adjacent: it would let CI verify ADR structure and citations. Rejected for now
because the specific need — no rule may cite an ADR that exists in neither the accepted set
nor the backlog — is met by a twenty-line test with no dependency. Revisit if ADR tooling
needs grow beyond that.

## Consequences

**Accepted costs.**
- A pinned external tool in the development workflow. It is dev tooling, not a runtime
  dependency, so it does not touch the distributed artifact.
- Overridden templates must be reconciled when upgrading, which is why the version is
  pinned and recorded in `docs/roadmap.md`.
- Spec Kit's generated prose is wordier than this project's documentation. The overrides
  reduce this; they do not eliminate it.

**Follow-on obligations.**
- The version is pinned and recorded; upgrades are deliberate, and template overrides are
  re-checked on each one.
- Every spec carries its "Decisions relied on" block. A spec without one is incomplete, and
  a spec contradicting a cited ADR is a defect in the spec, not in the ADR.
- `/speckit-constitution` is not run. If a future contributor runs it, the generated
  constitution is reduced back to a pointer.
- Specs cite `REQ-` ids from `docs/product/requirements.md` so requirements stay traceable.

**Reversal cost.** Low. Specs are markdown in `specs/`; abandoning the tooling leaves the
documents intact and costs only the slash commands.

## Revisit when

- Spec Kit changes its template override mechanism or its directory layout in a way that
  conflicts with `docs/` — the pin means this surfaces at upgrade time, deliberately.
- Spec Kit gains native reconciliation against prior decisions, which would make the local
  "Decisions relied on" override redundant.
- The specification layer outgrows markdown, which would be a signal something else is
  wrong.
