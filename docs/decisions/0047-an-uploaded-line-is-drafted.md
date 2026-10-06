---
status: "proposed"
kind: "requirement-driven"
date: 2026-09-28
decision-makers: [Geoff Scott]
---

# ADR-0047: A transaction read from an uploaded document is drafted, never posted by a rule

**Requirements served:** `PLT-23`, `BKP-20`, `BKP-09`.

## Context and Problem Statement

Assignment posts a candidate straight through when an approved rule resolves it. That is
`BKP-09`: "an approved pattern is never asked about again". For a feed it is the whole point.

An uploaded statement is different in a way the rule cannot see. Its payees, dates and amounts
were read out of a document the organization did not author (`BKP-20`), by a model, in the same
session that is now asking to post them. `PLT-23` says that session "cannot post to the books
without a person authorizing it", and requires the constraint to be "enforced by what the agent
is able to do, never by an instruction telling it what not to do".

A rule answers *where* a transaction belongs. It does not answer *whether it happened as
stated* — and a doctored statement whose lines match approved rules would, under straight-through
posting, book itself.

## Decision Drivers

* `PLT-23`: posting after reading untrusted content needs a person, and the server must enforce it.
* `BKP-09`: the operator should not be asked the same coding question twice.
* Enforcement must come from something the caller cannot choose per call.

## Considered Options

* An uploaded candidate is drafted whatever resolves it
* Post what a rule resolves; the rule's approval is the person's authorization
* A per-call `post` flag the caller sets

## Decision Outcome

Chosen option: "An uploaded candidate is drafted whatever resolves it", because a rule approved
for a pattern is not a person confirming that a particular document's figures are real.

> `apply_rules` posts a resolved candidate unless its `source_kind` is `upload`. An uploaded one
> is written as a complete draft — both legs, the coded one attributed to its rule — and a person
> posts it.

`BKP-09` still holds for what it governs: the coding question is not asked again. What is asked is
a different question, and a person answers it by posting.

### Consequences

* Good, because a statement crafted to match approved rules drafts itself and goes no further.
* Good, because the draft is complete, so posting it is one act with nothing left to decide.
* Bad, because every uploaded line needs a posting act, and a statement of two hundred lines is
  two hundred of them.
* Bad, because `source_kind` is supplied by the caller, so the rule holds only if no caller can
  describe an upload as a feed. [ADR-0062](0062-a-bank-feed-is-synchronized-by-cfokit-itself.md)
  § 1 makes that so: no interface accepts `feed`, and only CFOKit's own sync creates such a line.

### Confirmation

`tests/integration/test_assignment.py` asserts that an uploaded candidate a rule resolves is a
two-legged draft. `tests/integration/test_account_statements.py` asserts, over MCP, that the
books do not move until each draft is posted.

The refusal of a caller-supplied `feed` is gated by ADR-0062's tests.

## Pros and Cons of the Options

### An uploaded candidate is drafted whatever resolves it

* Good, because the server decides, from the kind of source, not from a flag the caller sets.
* Bad, because it weakens straight-through booking for the one path with no feed.

### Post what a rule resolves; the rule's approval is the person's authorization

* Good, because it is what assignment already did, and the balance proof
  ([ADR-0046](0046-a-statement-proves-itself.md)) limits a doctored statement to one that is at
  least internally consistent.
* Bad, because an internally consistent forgery is easy to produce, and `PLT-23` would then rest
  on the skill's instructions — the weaker thing it exists to replace.

### A per-call `post` flag the caller sets

* Good, because it is flexible.
* Bad, because the party the constraint binds would be the party that sets it.

## Revisit when

* `PLT-23`'s capability boundary exists — a session that has read untrusted content holding a
  reduced capability set — at which point the boundary can be on the principal rather than the
  source kind.
* Posting drafts one at a time is what stops operators uploading statements, which is the case
  for a single act posting a whole statement's drafts.
