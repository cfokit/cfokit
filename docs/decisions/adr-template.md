---
status: "draft | proposed | accepted | rejected | deprecated | superseded by ADR-NNNN"
kind: "requirement-driven | substrate"
date: YYYY-MM-DD
decision-makers: [names]
consulted: [names, or omit]
informed: [names, or omit]
---

# ADR-NNNN: {short title, naming the problem and the chosen solution}

<!--
MADR 4.0.0. https://adr.github.io/madr/

Two sections that MADR marks optional are MANDATORY in this repository:
"Considered Options" and "Pros and Cons of the Options". A record that names
alternatives without refuting each one does not prevent re-litigation, which is
the main thing an ADR is for. See ADR-0001.

"Revisit when" is a local addition. MADR permits added sections.

ONE DECISION PER RECORD. Several clauses are fine when they stand or fall
together. The test: could one clause be superseded without reopening the others?
If it could, they are two decisions — write two records. A title containing "and"
is a signal to apply the test, not a violation by itself.

`uv run task check-decisions` checks the mechanical parts of all this.

`status: draft` means pre-initial-commit: still being written, not yet offered
for review, and freely editable. The immutability rule does not bind until a
record is accepted. `proposed` means finished and awaiting a decision.

`kind: requirement-driven` means the product forces the question; such a record
MUST cite at least one requirement id. `kind: substrate` means a choice any project of
this shape must make — language, package manager, tooling, this template —
which cites no requirement because it has none. The test: would this decision
change if the requirements changed? See ADR-0001.
-->

## Context and Problem Statement

What forced the decision. State the constraints and the workload facts that matter —
scale, concurrency, regulatory, team size. Enough that someone with no memory of the
discussion can evaluate whether the reasoning still holds.

Do not include the answer here.

## Decision Drivers

The criteria the options are judged against, named before the options so the
evaluation cannot be reverse-engineered from the answer.

* {driver 1}
* {driver 2}

## Considered Options

* {option 1 — the chosen one}
* {option 2}
* {option 3}

## Decision Outcome

Chosen option: "{option 1}", because {justification — the decision in the
imperative, in one or two sentences}.

> We will use Postgres as the sole storage backend.

### Consequences

* Good, because {what this buys}
* Bad, because {what is now harder or more expensive}
* Neutral, because {what changes without being better or worse}

### Confirmation

How compliance is verified: a CI gate, a linter contract, a test, a review step.
If nothing enforces this, say so plainly — an unenforced decision is a convention,
not a constraint.

## Pros and Cons of the Options

**The most important section in this file.** Each option gets its own subsection so
a future reader — human or agent — does not re-propose it. Give the rejected ones
their strongest case first, then the specific reason they lost. Cite numbers where
they exist; "didn't feel right" is not a rejection reason.

### {option 1}

* Good, because {argument}
* Bad, because {argument}

### {option 2}

Why it was attractive.

* Good, because {argument}
* Bad, because {the specific reason this was rejected}

## More Information

**Follow-on obligations.** What must now be built or maintained that otherwise
wouldn't. These often become `CLAUDE.md` rules.

**Reversal cost.** How expensive this is to undo later, honestly. This is what tells
a future reader whether to revisit or live with it.

Links to related records, superseded records, and external sources.

## Revisit when

Concrete triggers, not "periodically". A threshold crossed, a dependency reaching GA,
a limit hit in production. If nothing would trigger a revisit, say so.
