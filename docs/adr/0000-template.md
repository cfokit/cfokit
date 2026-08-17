# ADR-NNNN: <short imperative title>

- **Status:** Draft | Proposed | Accepted | Superseded by ADR-NNNN | Deprecated
- **Date:** YYYY-MM-DD
- **Deciders:** <names>
- **Supersedes:** ADR-NNNN (omit if none)

`Draft` means pre-initial-commit: still being written, not yet offered for review, and freely
editable — the immutability rule does not bind until a record is Accepted. `Proposed` means
finished and awaiting a decision.

## Context

What forced the decision. State the constraints and the workload facts that matter —
scale, concurrency, regulatory, team size. Enough that someone with no memory of the
discussion can evaluate whether the reasoning still holds.

Do not include the answer here.

## Decision

The decision, in the imperative, in one or two sentences.

> We will use Postgres as the sole storage backend.

## Alternatives rejected

**The most important section in this file.** Each alternative gets its own subsection
so a future reader — human or agent — does not re-propose it.

### <Alternative A>

Why it was attractive, then the specific reason it was rejected. Cite numbers where
they exist; "didn't feel right" is not a rejection reason.

### <Alternative B>

...

## Consequences

**Accepted costs.** What is now harder or more expensive because of this.

**Follow-on obligations.** What must now be built or maintained that otherwise
wouldn't. These often become CLAUDE.md rules.

**Reversal cost.** How expensive this is to undo later, honestly. This is what tells
a future reader whether to revisit or live with it.

## Revisit when

Concrete triggers, not "periodically". A threshold crossed, a dependency reaching GA,
a limit hit in production. If nothing would trigger a revisit, say so.
