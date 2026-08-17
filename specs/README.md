# Specifications

What we are going to build. One directory per feature, created by Spec Kit. (ADR-0021)

```
specs/
  NNNN-short-slug/
    spec.md         # what and why      — /speckit-specify
    plan.md         # how               — /speckit-plan
    tasks.md        # work breakdown    — /speckit-tasks
    research.md     # optional, phase 0
    data-model.md   # optional, phase 1
    contracts/      # optional, phase 1
```

## Why this is not inside `docs/`

Specifications churn: clarified, replanned, superseded by the implementation that follows
them. ADRs are immutable once accepted. Keeping an append-only store inside a working area
invites an agent to "update" an ADR while editing neighbouring files, so the two live in
separate trees. (ADR-0020)

| | `specs/` | `docs/adr/` |
|---|---|---|
| Answers | What we will build | Why we decided |
| Lifecycle | Churns, then closes | Immutable once accepted |
| Direction | Cites ADRs | Constrains specs |

**Specs cite ADRs. ADRs never cite specs.** If a spec seems to require contradicting an ADR,
that is a defect in the spec, or grounds for a new ADR superseding the old one. It is never
grounds for designing around the ADR.

## The workflow

```
/speckit-specify    → spec.md      what and why
/speckit-clarify    → optional, before planning; de-risks ambiguity
/speckit-plan       → plan.md      how
/speckit-tasks      → tasks.md     work breakdown
/speckit-analyze    → optional, consistency check before implementing
/speckit-implement  → execute
```

Do not run `/speckit-constitution`. `CLAUDE.md` plus the ADRs are the constitution;
`.specify/memory/constitution.md` is a pointer and stays one.

## Two mandatory blocks

Every `spec.md` and `plan.md` opens with:

1. **Decisions relied on** — the ADRs constraining this feature and what each forbids. Read
   the ADR; do not infer from its title. This is what stops each feature starting from empty
   context and re-arguing settled questions.
2. **Requirements traceability** — the `REQ-` ids from
   [`../docs/product/requirements.md`](../docs/product/requirements.md) this feature
   delivers. A spec tracing to nothing is scope creep until someone says otherwise.

Templates in `.specify/templates/overrides/` enforce both. Those overrides fully replace the
stock templates, so reconcile them when the pinned Spec Kit version changes.

## Numbering

Sequential, never reused, gaps fine — the same convention as the ADRs. Nothing here is
renumbered once a branch exists.
