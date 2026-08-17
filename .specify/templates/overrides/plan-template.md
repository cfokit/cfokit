# Implementation Plan: [FEATURE]

**Branch**: `[###-feature-name]` | **Date**: [DATE] | **Spec**: [link]

**Input**: Feature specification from `/specs/[###-feature-name]/spec.md`

**Note**: Filled in by `/speckit-plan`.

## Summary

[The primary requirement from the spec, plus the technical approach in two or three
sentences.]

## Decisions relied on *(carried from the spec — verify, do not copy blindly)*

<!--
  Re-check the spec's ADR list against what this plan actually proposes. The plan is where
  a settled decision gets quietly contradicted, because the spec stayed at the level of
  "what" and the violation only becomes expressible in the "how".

  If the plan needs to contradict a cited ADR, STOP and escalate. Do not design around it.
-->

| ADR | Constrains this plan by | Plan complies because |
|---|---|---|
| ADR-NNNN | [what it forbids] | [how this plan stays inside it] |

## Technical Context

Most of this is already decided project-wide. State the value; do not re-open it.

| | |
|---|---|
| **Language** | Python 3.12+ |
| **Package manager** | `uv` only — not pip, not poetry |
| **Concurrency model** | Synchronous throughout; async needs an ADR (ADR-0012) |
| **Storage** | PostgreSQL, the only backend (ADR-0002) |
| **Data access** | Hand-written SQL. No ORM, no query builder (ADR-0008) |
| **Monetary type** | `decimal.Decimal` / `NUMERIC(28,10)` (ADR-0004) |
| **Testing** | pytest; tests written alongside the code |
| **Type checking** | `mypy --strict` |
| **Configuration** | Environment variables only (ADR-0003) |
| **New runtime dependencies** | [none, or name them — each needs approval before adding] |
| **Performance goals** | [feature-specific, or n/a] |
| **Scale/scope** | [feature-specific, or n/a] |

## Constitution Check

*GATE: must pass before Phase 0 research, and again after Phase 1 design.*

The constitution is `CLAUDE.md` plus the ADRs it cites. There is no separate constitution
document (ADR-0021). Confirm each, and name the CI gate that will prove it:

- [ ] **Money** — `Decimal` everywhere, `NUMERIC(28,10)` columns, no float in code, tests,
      or fixtures. *(CI gate 4)*
- [ ] **Append-only** — no `UPDATE` on financial fields, no `DELETE`; corrections reverse.
- [ ] **Storage** — Postgres only. No second store, not even for local development.
- [ ] **Layering** — the booking engine stays pure; nothing skips a layer. *(CI gate 1,
      import-linter)*
- [ ] **Boundary** — the skill and the ledger share only the tool contract; connectors use
      the public API. *(CI gate 1, import-linter)*
- [ ] **Portability** — env-var configuration only, no provider SDK at module scope, no
      cloud metadata, migrations never at startup. *(CI gate 2)*
- [ ] **Observability** — one `audit_log` row per state-changing call; one request id;
      stable error codes; no sensitive values at info level.
- [ ] **Interfaces** — committed OpenAPI and MCP tool descriptions regenerated and matching.
      *(CI gate 5)*
- [ ] **Licensing** — no copyleft in the distributed artifact; licences verified currently,
      not from memory.
- [ ] **Scope** — builds nothing on the ADR-0012 non-goals list.

**Violations:** [none, or record each in Complexity Tracking below]

## Project Structure

### Documentation (this feature)

```text
specs/[###-feature-name]/
├── spec.md
├── plan.md              # this file
├── research.md          # Phase 0
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
├── contracts/           # Phase 1
└── tasks.md             # /speckit-tasks, not /speckit-plan
```

### Source code

The repository layout is fixed by ADR-0020. Place work in the existing structure; do not
introduce a parallel one.

```text
packages/ledger/src/cfokit/ledger/
├── engine/        # pure booking logic — no I/O, no config
├── repository/    # hand-written SQL
├── service/       # orchestration, audit, locking
├── api/           # REST adapter
├── mcp/           # MCP adapter
└── migrations/sql/

packages/connectors/src/cfokit/connectors/
└── providers/     # one module per provider, one credential-free default

skills/            # shipped SKILL.md bundles — not Python distributions
infra/             # OpenTofu, one maintained target
```

**There is deliberately no frontend option.** A web UI or admin console is a binding
non-goal (ADR-0012). If this feature seems to need one, it needs an ADR first.

**Structure Decision**: [Which of the directories above this feature touches, and why.]

## Phasing

Order the work so each phase is verifiable before the next begins. In this codebase that
usually means: pure engine logic first (testable with no database), then persistence, then
the service layer, then adapters.

| Phase | Work | Verified by |
|---|---|---|
| 0 | [research / open questions] | |
| 1 | [design artifacts] | |
| 2 | [implementation slices] | |

## Complexity Tracking

> Fill in **only** if the Constitution Check has violations needing justification. A filled
> row here means human review before implementation proceeds.

| Violation | Why needed | Simpler alternative rejected because |
|---|---|---|
| | | |

## Decisions this plan creates

<!-- If the plan settles something future work should be bound by, it becomes an ADR, not a
     code comment (CLAUDE.md, Working style). List candidates here. -->

- [Candidate ADR, or "none"]
