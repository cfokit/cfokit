# Feature Specification: [FEATURE NAME]

**Feature Branch**: `[###-feature-name]`

**Created**: [DATE]

**Status**: Draft

**Input**: User description: "$ARGUMENTS"

## Decisions relied on *(mandatory)*

<!--
  CFOKit-specific and NOT optional. Stock spec-driven workflows start each feature from
  empty context and cheerfully re-argue questions that were settled months ago. This block
  is what prevents that.

  List every ADR that constrains this feature, and what it forbids. Read the ADR — do not
  guess from its title. Index: docs/adr/README.md

  If this feature appears to require contradicting a cited ADR, STOP. Do not design around
  it. Either the spec is wrong, or a new ADR supersedes the old one — and that is a
  decision for a human, not a workaround for an agent.

  If an ADR you need is in the backlog rather than written, say so here and treat the
  feature as blocked.
-->

| ADR | Constrains this feature by |
|---|---|
| ADR-NNNN | [what it forbids or requires here] |

**Blocked by unwritten decisions:** [list, or "none"]

## Requirements traceability *(mandatory)*

<!-- REQ- ids from docs/product/requirements.md. A spec tracing to nothing is scope creep
     until someone says otherwise — if that is the case, say so explicitly. -->

| REQ | Capability |
|---|---|
| REQ-XX | [capability this feature delivers] |

## User Scenarios & Testing *(mandatory)*

<!--
  Prioritised user journeys, each INDEPENDENTLY TESTABLE — implementing only P1 must still
  deliver something usable. Add stories as needed; two are shown, not required.
-->

### User Story 1 - [Brief Title] (Priority: P1)

[The journey, in plain language.]

**Why this priority**: [What breaks or stays broken without it.]

**Independent Test**: [How this is verified on its own.]

**Acceptance Scenarios**:

1. **Given** [state], **When** [action], **Then** [outcome]
2. **Given** [state], **When** [action], **Then** [outcome]

---

### User Story 2 - [Brief Title] (Priority: P2)

[The journey, in plain language.]

**Why this priority**: [Rationale.]

**Independent Test**: [How this is verified on its own.]

**Acceptance Scenarios**:

1. **Given** [state], **When** [action], **Then** [outcome]

---

### Edge Cases

<!-- In an accounting system the interesting cases are almost always: the backdated entry,
     the concurrent write, the retried request, the multi-currency transaction, the
     zero-amount posting, and the entity boundary. Cover the ones that apply. -->

- What happens when [boundary condition]?
- What happens when the same request arrives twice?
- What happens when two writes target the same entity concurrently?

## Requirements *(mandatory)*

### Functional Requirements

<!-- What the system must do. No libraries, no schemas, no endpoints — those belong in the
     plan. Mark genuine unknowns [NEEDS CLARIFICATION: question] rather than guessing. -->

- **FR-001**: System MUST [capability]
- **FR-002**: System MUST [capability]
- **FR-003**: Users MUST be able to [interaction]

### Key Entities *(include if the feature involves data)*

<!-- What each represents and how they relate. No column types here. Monetary values are
     `Decimal`, never `float` (ADR-0004) — state which fields are monetary. -->

- **[Entity]**: [What it represents; which fields are monetary]

## Correctness obligations *(mandatory)*

<!--
  CFOKit keeps books. A defect here misstates someone's financial position. Answer each —
  "n/a" is a valid answer, an omission is not.
-->

| Obligation | How this feature satisfies it |
|---|---|
| Monetary values are `Decimal`; no float anywhere, including fixtures (ADR-0004) | |
| No `UPDATE` or `DELETE` on financial fields; corrections are reversing entries (ADR-0006) | |
| Every state-changing call writes exactly one `audit_log` row | |
| Writes carry an idempotency key and take the per-entity lock (ADR-0011) | |
| No token values, posting amounts, account numbers, or payee names logged at info level | |
| Errors carry a stable machine-readable `code` (ADR-0015) | |
| Nothing derives external URLs from request headers; `PUBLIC_BASE_URL` is authoritative | |

## Success Criteria *(mandatory)*

<!-- Measurable and technology-agnostic. "Correct" is not measurable; "matches the
     Beancount oracle on the divergence suite" is. -->

- **SC-001**: [Measurable outcome]
- **SC-002**: [Measurable outcome]

## Human review required

<!-- Booking semantics, auth, and the write path stop for human review before
     implementation proceeds (CLAUDE.md, Working style). Tick what applies. -->

- [ ] Booking semantics — how a transaction is recorded
- [ ] Authentication — issuer contract, audience validation, entity grants
- [ ] The write path — locking, idempotency, audit trail
- [ ] A new runtime dependency
- [ ] None of the above

## Assumptions

<!-- Defaults chosen where the description was silent. State them; do not bury them. -->

- [Assumption]

## Out of scope

<!-- What a reader might reasonably expect here and will not get. Prevents scope drift
     during implementation. -->

- [Excluded item]
