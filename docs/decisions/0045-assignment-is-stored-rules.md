---
status: "proposed"
kind: "requirement-driven"
date: 2026-09-27
decision-makers: [Geoff Scott]
---

# ADR-0045: Assignment is stored rules in a module of their own, matched by a closed predicate set

**Requirements served:** `BKP-06`, `BKP-08`, `BKP-09`, `BKP-11`, `RPT-08`.

## Context and Problem Statement

`BKP-06` is `Must`/`Approved` and nothing implements it: "assignment of an incoming
transaction to an account is governed by stored rules applied deterministically". Until
something does, categorization either does not happen or a model decides per transaction —
which is what the requirement was written to prevent, and which `ActorClass`'s own docstring
records: "nothing assigns it yet because no rules engine exists".

Three other things wait on it. `RPT-08` (`Must`) requires reaching "from a posting to its
source transaction and the rule that assigned it", and `service/reports.py` marks the gap in
place. `ActorClass.RULE` is a legal value the schema permits and nothing writes. ADR-0042
§ 4 deferred how it should arrive and named its own revisit trigger as "the rules engine
lands".

What makes this more than a lookup table is `BKP-06`'s acceptance — "replaying an entity's
full transaction history against an unchanged rule set reproduces every assignment
identically" — sitting beside `BKP-11`, "changing a rule affects future assignments only".
Together they require that a past assignment stay explicable by the rule *as it then was*,
while the rule is free to change. `BKP-08` adds that overlapping rules resolve "by a stated,
inspectable order rather than by whichever is found first. Determinism depends on this."

Transactions arrive by three routes — `BKP-01`, `BKP-02` and `BKP-03` — with different shapes,
so whatever is decided here must not presume any one of them.

## Decision Drivers

* `BKP-06`'s acceptance must be executable, not aspirational: a replay has to be able to fail.
* A past assignment must stay explicable by the rule that made it, however often the rule
  changes afterwards.
* The operator is a business owner, not an engineer (`NFR-19`).
* The boundary must not accumulate the capability next door, which is how `connectors` went
  wrong (ADR-0031).
* Determinism must survive a move between deployments (`EXP-04`).

## Considered Options

* A module named for the capability, matching on a closed predicate set
* Matching on a standard expression language, adopted as a dependency
* Matching on regular expressions
* Rules inside the ledger

## Decision Outcome

Chosen option: "A module named for the capability, matching on a closed predicate set",
because the hard part of this requirement is temporal rather than syntactic — and because
the person writing a rule runs a business.

> Assignment is `cfokit.assignment`, an in-process module. A rule is a chain of immutable
> versions; the set in force at a moment is a reconstruction, not a lookup. Matching is a
> closed set of fields and operators, ANDed, evaluated in a pure engine. Every assignment
> names the rule *version* that made it, on the posting.

### 1. A module, and named for the capability

ADR-0022 § 3's first criterion settles in-process: a decision and the draft it coded must
reach one `COMMIT`, and a decision naming a transaction that rolled back is the gap `RPT-08`
exists to close.

Not `rules`. Four unrelated capabilities have an equal claim to that word — compliance rules
(`NFR-12`, and the vision's "compliance rules for their own state"), alerting thresholds
(`PLT-07`), autonomy configuration (`SOC1-04`) — and it already means "invariant" in twenty
comments in the ledger alone. `assignment` is `BKP-06`'s own word (ADR-0031).

**The module stores no incoming transactions.** The caller supplies candidates; what
persists is a decision and the draft it coded. Getting transactions in is a separate
capability with three producers in three places — a PDF parsed in the agent runtime
(ADR-0041), a skill that fetches one, and an unattended feed, which ADR-0022 § 3 makes a
component. Letting this module hold their queue is the boundary-around-a-guess ADR-0031
deleted `connectors` for.

### 2. A rule is a chain of versions, and the set in force is a reconstruction

Every row is a version. An edit appends; a retirement appends. There is no current-row flag
and no `effective_to`, because ADR-0013's argument transfers unchanged: nothing is mutated,
so a point in time is a filter rather than a subsystem, and "bitemporality is free, so
nothing is built for it".

**`BKP-11` is then structural rather than remembered.** An existing posting names the version
that coded it, that row is immutable, and a version created later is not in the earlier set —
not because any code path declines to apply it.

Editing and retiring are one mechanism because they are one act seen from two angles: both
change the set from a moment onward. A `retired_at` column on the previous version would
have been an update, and would have put the rule set's history in two places.

The axis is system time, not the transaction's date. `BKP-11` says a change affects future
*assignments*, so a receipt surfacing three months late is coded by today's rule set.

### 3. The order is total, and says which level decided

`(precedence, seniority, rule_id)`. Precedence is what `BKP-08` calls stated. Seniority is
the rule's first appearance — on the rule, not the version, so an edit does not cost it its
place — and it buys a property worth having on its own: **adding a rule can never silently
take a transaction from one that already had it**, which is what makes `BKP-09`'s "an
approved pattern is never asked about again" hold as a rule set grows.

`rule_id` guarantees totality and is never the intended discriminator, so every decision
records *which level* settled it. A decision resolved by the tiebreak means the rule set does
not state what the operator thinks it states, and finding all of them is a `WHERE` clause.

A uuid rather than an insertion counter, because `EXP-04` requires a receiving deployment to
"resolve every posting to the same rule": a uuid survives an export and import unchanged,
where a counter is reassigned on insert into a fresh database and some assignments would
silently differ.

Two live rules may not share a precedence. The service refuses it under the entity's advisory
lock rather than a `UNIQUE` constraint, because the condition is over the versions *in
force*, which is a projection no constraint can express — and a constraint the schema cannot
keep is one the resolution must not lean on, which is why the order is total anyway.

### 4. "Unchanged" is a digest, and that is what makes the acceptance falsifiable

Every decision stores a sha256 over a canonical rendering of the rule set in force. A replay
rebuilds the set, recomputes the digest, and only compares where they match.

Without it `BKP-06`'s acceptance cannot fail honestly: a replay that disagrees has two
possible causes — a determinism defect, or an operator legitimately editing a rule under
`BKP-11` — and a test unable to tell them apart either fails constantly or asserts nothing.

The candidate's facts are stored on the decision for the same reason. The facts matched on
are not the facts booked: a normalized payee and the source kind never reach a posting, so a
replay reconstructing its inputs from its outputs would be asserting that the code agrees
with itself.

### 5. Matching is a closed predicate set, and the case for it is not ADR-0012

Fixed fields, fixed operators, ANDed; no OR, no nesting, no caller-authored expression. A
disjunction is two rules, which is also the form `BKP-08` can order and `RPT-08` can
attribute.

Adopting a standard expression language would satisfy ADR-0012's gate *better*, because we
would build no language at all. It loses on `NFR-19` — "operable by someone who runs a
business rather than someone who keeps books"; a field, an operator and a value is a form,
and an expression is programmer-facing — and on queryability, because `BKP-11` asks what
changing a rule will affect and with conditions as rows that is SQL.

**Matching is evaluated in the pure engine, never in SQL.** Postgres `lower()` and `ILIKE`
follow the database's collation, so the same rule against the same transaction could resolve
differently on two deployments. That breaks `BKP-06` outright and `EXP-04`'s promise with it.

### 6. Attribution is per posting, and `actor_class` becomes `rule`

On the posting because `BKP-05` splits, and because a feed transaction's two legs are decided
by different things: the bank leg is the account the money arrived on and no rule chose it.
Opaque and not a foreign key, exactly as `decision_record_id` already is — a real FK from the
ledger's most-written table to a module's table is the dependency ADR-0022 forbids, written
in SQL instead of Python.

`record_transaction` gains a parameter, which ADR-0042 § 4 reserved: "a value the write path
sets on a posting whose coding a rule determined, not a branch in `principal_from_claims`",
because a token cannot tell you a coding was rule-assigned. It records why a posting was
made and is never an authority check (ADR-0042 § 3), so it widens nothing.

### Consequences

* Good, because `BKP-06`'s acceptance is a call anyone can make, not only a test — the replay
  writes nothing and is published, so an auditor can run the control rather than trust it.
* Good, because `BKP-11` needs no enforcement: the row that decided is immutable and a later
  version is simply not in the earlier set.
* Good, because `ActorClass.RULE` finally means something, which ADR-0033 § 3 wanted
  maximized — "a rule-assigned coding is deterministic and re-derivable, and an auditor tests
  it cheaply and once".
* Good, because a rule is data an operator can read: every condition is a row, so "which
  rules touch this account" is a query rather than a text search.
* Bad, because the closed set will be felt. "Round amounts", "recurring monthly" and "matches
  this reference format" are all legitimate `BKP-07` discriminators and none is expressible;
  each costs a migration and a record.
* Bad, because a decision row per evaluation is a table that grows with the books, holding a
  copy of facts that also exist on the transaction.
* Bad, because the evaluator version is an escape hatch no constraint can close: change what
  matching means, bump it, and the whole history stops being compared.
* Neutral, because the module acts only on candidates a caller supplies. The first producer is
  a recorded statement ([ADR-0046](0046-a-statement-proves-itself.md)).

### Confirmation

`tests/test_assignment_engine.py` holds the invariants without infrastructure: evaluation is
invariant to the order rows arrive in, the order key is total over generated rule sets, and a
version with a later `effective_from` does not change the digest at an earlier moment — which
is `BKP-11` as arithmetic. Beside them are worked cases whose expected values come from
`BKP-08`'s stated order and `BKP-07`'s own example rather than from running the engine,
because otherwise the properties only prove the engine agrees with itself (ADR-0036 § 5).

`tests/integration/test_assignment.py` holds the rest against real books: the coded posting
names the rule and the bank leg does not, an unresolved candidate leaves a one-legged draft
the ledger itself refuses to post, a second rule at one precedence is refused, and a rule
edit leaves what it already coded untouched. Its replay tests are `BKP-06`'s acceptance
executed — every decision re-decided against the set reconstructed as at the moment it was
taken.

`tests/test_composition.py` asserts the module's routes and tools are served by the composed
deployable and that the ledger's own app serves none of them, which is ADR-0022's contract
observed at the surface rather than only over import paths.

Not gated: nothing prevents `EVALUATOR_VERSION` being bumped to make a failing replay pass.
That is the one place `BKP-06` rests on discipline, and it is why bumping it needs a record.
Nothing prevents a table owner rewriting a rule's history either — row-level security and the
append-only triggers do not apply to the owner — though the stored digest means the next
replay reports it.

## Pros and Cons of the Options

### A module named for the capability, matching on a closed predicate set

* Good, because the temporal model falls out of append-only, which the ledger already is.
* Good, because a rule is queryable data, which `BKP-11` and `RPT-08` both want.
* Good, because a form is what `NFR-19`'s operator can actually use.
* Bad, because every new field or operator is a migration, and the first person to want a
  disjunction will find two rules a worse answer than one.

### Matching on a standard expression language, adopted as a dependency

Genuinely strong, and stronger than it was: Google's official CEL implementation for Python
shipped in March 2026 under Apache-2.0, is non-Turing-complete and mutation-free by design,
and is built for safely evaluating expressions somebody else wrote. CLAUDE.md makes license a
non-issue for a server-side runtime dependency. Adopting it would satisfy ADR-0012 better
than arguing a closed set is not a language.

* Good, because we would build no matching language at all, and its semantics are specified.
* Good, because it extends without a migration per operator.
* Bad, because `NFR-19`'s operator does not write expressions, and this product's rules are
  authored by a business owner or proposed to one for approval.
* Bad, because a rule becomes an opaque string: "which rules touch this account" degrades from
  SQL to a text search, and `BKP-11`'s "what will this change affect" degrades with it.
* Bad, because it replaces about a hundred lines. Versioning, the digest, ordering,
  attribution and replay — what this design is actually about — are in no rules package.
* Bad, because it is a sixth runtime dependency with a native extension, against ADR-0004's
  promise that this runs on a laptop.

It is deferred rather than rejected, and cheaply: conditions are rows, so an `expression` kind
is one more row type. Starting there and retreating to something form-authorable is not cheap,
which is the asymmetry that decides the order.

### Matching on regular expressions

The obvious answer for payee matching, and familiar to everyone.

* Good, because one pattern expresses what several `contains` rules would.
* Bad, because catastrophic backtracking is a live denial of service once a rule set runs over
  thousands of transactions.
* Bad, because engine semantics differ enough to break `EXP-04`'s "resolve every posting to
  the same rule" after a move between deployments.
* Bad, because inspectability collapses: a reader must simulate the pattern to see what a rule
  does, and `BKP-08` wants the order and its reasons legible.

### Rules inside the ledger

* Good, because the attribution column and the rules would share a schema with no opaque
  pointer between them.
* Bad, because the ledger would learn what a payee is, which is ADR-0022's own test for the
  boundary having moved wrongly.
* Bad, because `import-linter` already forbids it, so this is not an option so much as a
  contract violation with a rationale attached.

## More Information

**Follow-on obligations.**

* `BKP-13` and `BKP-14` extend `assignment_decision.outcome`. The candidate fingerprint is
  written for them now, because the facts to hash are here now; nothing reads it yet.
* `BKP-12`'s question is returned to the caller, not stored as a worklist. Making it durable,
  dispositioned and reportable is `SOC1-28`–`32`, which the decision index already flags as
  earning its own record — "a subsystem, not a field".
* Bumping `EVALUATOR_VERSION` needs a record, because it silently narrows what replay checks.
* Whatever module receives account activity produces a `Candidate`. It must not be this one.

**Reversal cost.** Medium. The module and its tables are additive and could be dropped, but
the `posting` column and the `record_transaction` parameter are in the ledger and in the
published contract, and postings carrying rule attribution would outlive a decision to remove
it.

Related: ADR-0022 (module or component), ADR-0031 (naming), ADR-0013 (the temporal model this
reuses), ADR-0042 § 4 (which reserved the `actor_class` change), ADR-0012 (the gate the closed
set is argued against), ADR-0036 (the testing layers this is verified at).

## Revisit when

* An operator asks for a disjunction the closed set cannot express, which is the trigger for
  reconsidering an expression language rather than adding a fourth operator family.
* A fetching skill or a feed starts producing candidates, which is when the `Candidate` shape
  meets a producer beyond the statement it was fitted to.
* `BKP-13` or `BKP-14` lands, which extends the outcome set and adds a counterpart search.
* A rule set grows past a few hundred per entity, at which point loading every version on
  every evaluation stops being obviously cheap.
* `SOC1-04` is built, which puts autonomy configuration beside these rules and may make one
  approval surface out of two.
