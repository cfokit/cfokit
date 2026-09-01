---
status: "draft"
kind: "requirement-driven"
date: 2026-08-18
decision-makers: [Geoff]
---

# ADR-0022: The ledger stays tiny; everything else is an in-process module or a separate component

**Requirements served:** `AR-03`, `NFR-01`, `NFR-12`.

## Context and Problem Statement

[ADR-0008](0008-layered-architecture-pure-engine.md) specifies **layers** — a pure engine beneath
hand-written SQL, beneath orchestration, beneath protocol adapters. That is horizontal
stratification, and it is settled.

It says nothing about the **vertical** axis: what constitutes a distinct piece of the system. That gap
became visible when invoicing and accounts receivable entered scope (`AR-01`–`AR-19`), which is a
whole domain — customers, invoices, line items, payment application, ageing — with its own vocabulary.
Absorbing it into the ledger would roughly double what "the ledger" means.

There is a reason specific to this project to resist that. The differential oracle
([ADR-0010](0010-beancount-as-test-oracle.md)) compares CFOKit's booking against Beancount, and that
comparison is meaningful only while the thing being compared is *about* double-entry. Once invoice
concepts are inside the booking engine, the oracle is comparing two different systems and the
strongest correctness evidence available quietly degrades.

More components are coming — email delivery, notifications, a Slack surface, reconciliation,
categorisation rules — and each will arrive with an argument for where it belongs. What is needed is
the **rule**, not a pre-emptive list.

## Decision Drivers

* The oracle's value depends on the booking engine staying about double-entry and nothing else.
* Atomicity where the domain requires it. An invoice and its GL entries must reach one `COMMIT`.
* Blast radius: a process holding third-party credentials should not also hold database credentials.
* The published API stays honest only if we are also a consumer of it where a third party would be.
* Boundaries drawn before the domains exist are guesses, and a wrong boundary written down is hard to
  move (ADR-0012).

## Considered Options

* A tiny ledger, with everything else classified as an in-process module or a separate component
* One ledger package containing everything
* A `core` module inside the ledger, with siblings beneath it
* Separate distributions per module
* Everything talks to the ledger over HTTP, uniformly
* Decide the full module list now

## Decision Outcome

Chosen option: "A tiny ledger, with everything else classified as an in-process module or a separate
component", because it preserves the oracle's meaning and keeps atomicity available where the domain
demands it, while leaving the module list to be decided when each domain actually exists.

### 1. The ledger stays tiny

`cfokit.ledger` owns the double-entry primitive and nothing else: accounts, postings, transactions,
the draft-to-posted boundary, reversal, period close, and the invariants that make those correct
(zero-sum, append-only, entity isolation).

It knows nothing about customers, invoices, banks, email, agents, or any other domain.

**The test:** if the ledger needs to know what a customer is, the boundary has moved wrongly.

There is no module named `core`. The ledger *is* the kernel, and a `ledger.core` would be either
redundant or an admission that the ledger had grown too big to be its own kernel. Modules are
**siblings of** the ledger, not children of it.

### 2. Everything else is one of exactly two things

**An in-process module** — a sibling package, in the same deployable, sharing the database and its
transactions. Depends on the ledger. Never depended on by the ledger.

**A separate component** — its own runtime, reaching the ledger through the published API.

### 3. The criteria

Classify by asking these in order. The first that applies decides it.

| Question | If yes |
|---|---|
| Must it commit **atomically** with a ledger write? | **Module.** Distributed transactions or compensating actions to achieve one `COMMIT` is the wrong trade. |
| Does it hold third-party credentials or secrets worth isolating? | **Component.** Blast radius is a real reason to separate a process. |
| Does it have a different **runtime shape** — scheduled, long-polling, worker, or externally triggered? | **Component.** A request-serving container and a scheduled job are different deployment units. |
| Could a third party plausibly build it against the published API? | **Component.** If they must use the API, we should, or the API will not stay honest. |
| Otherwise | **Module.** In-process is the cheaper default; separation must be earned. |

**In-process is the default.** Forcing an HTTP hop inside a single deployable is self-imposed
friction, and it is only worth paying for one of the reasons above.

### 4. Naming

Modules and components are named for the capability they provide, never for a vendor and never for a
mechanism. [ADR-0031](0031-packages-named-for-capabilities.md) holds that rule and its reasoning.

Applying it here: `connectors` names a mechanism, and on the current trajectory it will be asked to
cover bank feeds, payment processors, and transactional email — which are not one capability. It is
**renamed before implementation begins**, and probably split. The rename is deferred rather than done
now, because doing it twice is worse than doing it once, and what it splits into depends on decisions
not yet made.

### 5. What this deliberately does not decide

- **The module list.** Only the ledger is fixed. Invoicing is a module because `AR-03` requires
  atomicity with ledger writes. Everything else is classified when it is built, using § 3.
- **Where ingestion lands.** The criteria pull both ways and the verdict is deliberately left open.
  Ingestion writes *drafts*, which are ledger records, so a sync batch committing atomically argues
  for a module; credential isolation and a scheduled runtime shape argue for a component. The
  `import-linter` contract forbidding `cfokit.connectors` from importing `cfokit.ledger` stands as a
  safe provisional default rather than a settled answer.
- **How components map to deployment infrastructure.** Settled subsequently by
  [ADR-0023](0023-one-image-many-entrypoints.md) and
  [ADR-0032](0032-component-authentication-and-configuration.md).

### Consequences

* Good, because the oracle keeps comparing double-entry against double-entry, which preserves the
  strongest correctness evidence in the project.
* Good, because growth in the ledger is visible: it shows up as a new sibling rather than another
  subdirectory nobody counts.
* Good, because the criteria are the durable artifact and the module list is the perishable one, so
  the record does not go stale as domains arrive.
* Bad, because the `connectors` package carries a name known to be wrong until it is renamed — a
  small ongoing embarrassment, and a deliberate one.
* Bad, because classifying each new capability is a judgement call, and § 3 will occasionally be
  ambiguous.
* Bad, because modules cannot depend on each other, so a genuine cross-module need forces either a
  ledger concept or coordination in the service layer. That friction is intended and will sometimes
  be annoying.

### Confirmation

`import-linter` contracts encode "modules depend on the ledger, never on each other, and the ledger
depends on no module", and run inside `uv run task lint`. The mechanism is already in place and
observed to fail on violation; the module-to-module contracts are added as the first module lands.

**The tiny-ledger test itself is not gated.** No check asserts that the ledger does not know what a
customer is — that is review, and the signal is a ledger module acquiring a domain noun.

## Pros and Cons of the Options

### A tiny ledger, with modules and components classified by criteria

* Good, because it keeps the oracle meaningful and atomicity available.
* Good, because the criteria outlive any particular module list.
* Bad, because every new capability needs a classification judgement.
* Bad, because it forbids module-to-module dependencies, which will occasionally be inconvenient.

### One ledger package containing everything

Simplest, no boundaries to police, and everything can call everything.

* Good, because there is no classification question, no import contract, and no HTTP hop anywhere.
* Bad, because it degrades the oracle. Once invoicing lives inside the booking engine, the Beancount
  comparison no longer isolates double-entry semantics.
* Bad, because "the ledger" comes to mean whatever has accumulated, which is exactly the drift a
  first-party ledger with no natural boundary is prone to (ADR-0002).

### A `core` module inside the ledger, with siblings beneath it

The conventional shape: `ledger.core`, `ledger.invoicing`, `ledger.reporting`.

* Good, because it is the familiar layout and needs no argument to explain.
* Bad, because "core of what?" has no good answer when the enclosing package is already the ledger —
  and needing a core *inside* the ledger concedes that the ledger has stopped being small.
* Bad, because growth hides: another subdirectory attracts less attention than another sibling.

### Separate distributions per module

Real packaging boundaries, independently versioned, unambiguous dependency direction.

* Good, because the boundary would be enforced by packaging itself rather than by a lint contract.
* Bad, because modules share a database and must commit together, so separate distributions would
  advertise an independence that does not exist — and would invite someone to deploy them
  separately, which cannot work.

### Everything talks to the ledger over HTTP, uniformly

Appealing for consistency: one access pattern, everything dogfoods the API, no in-process coupling
anywhere.

* Good, because it would guarantee the API stays honest, and make every boundary identical.
* Bad, because it makes atomicity impossible where atomicity is required. An invoice and its GL
  entries must commit together; over HTTP that becomes a distributed transaction or a compensating
  action. Consistency of access pattern is not worth correctness of the write path.

### Decide the full module list now

Would settle the architecture in one pass and avoid re-opening it repeatedly.

* Good, because it would give a stable target to design against and remove repeated judgement calls.
* Bad, because it is speculative abstraction, which ADR-0012 gates. Naming modules before the domains
  exist means designing boundaries around guesses.

## More Information

**Follow-on obligations.**

* `import-linter` contracts encoding the module dependency rules, added as the first module lands.
* Reports follow ownership: financial statements depend only on the ledger, while AR ageing belongs to
  invoicing. This keeps a reporting module from depending on invoicing.
* `connectors` renamed, and probably split, before implementation begins (ADR-0031).
* `CLAUDE.md`'s repository map reflects the ledger/module/component distinction.

**Reversal cost. Low now, high later.** Nothing is built, so boundaries are free to move today. Once
modules exist with import contracts and a published API shaped around them, moving a boundary means
moving code across a package edge and possibly across a contract.

## Revisit when

* A capability genuinely fits neither classification, which would mean § 3 is incomplete rather than
  the capability being wrong.
* The ledger acquires a concept it should not know about. That is the signal the boundary slipped, and
  the fix is extracting a module rather than amending the test.
* A module needs to depend on another module for a reason that is not solvable in the service layer.
