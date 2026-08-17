# ADR-0023: The ledger stays tiny; everything else is an in-process module or a separate component

- **Status:** Accepted
- **Date:** 2026-08-18
- **Deciders:** Geoff

## Context

[ADR-0008](0008-layered-architecture-pure-engine-no-orm.md) specifies **layers** — a pure engine
beneath hand-written SQL, beneath orchestration, beneath protocol adapters. That is horizontal
stratification, and it is settled.

It says nothing about the **vertical** axis: what constitutes a distinct piece of the system. That
gap became visible when invoicing and accounts receivable entered scope (REQ-A9), which is a whole
domain — customers, invoices, line items, payment application, ageing — with its own vocabulary.
Absorbing it into the ledger would roughly double what "the ledger" means.

There is a reason specific to this project to resist that. The differential oracle
([ADR-0010](0010-beancount-as-test-oracle.md)) compares CFOKit's booking against Beancount, and that
comparison is meaningful only while the thing being compared is *about* double-entry. Once invoice
concepts are inside the booking engine, the oracle is comparing two different systems and the
strongest correctness evidence available quietly degrades.

More components are coming — email delivery, notifications, a Slack surface, reconciliation,
categorisation rules — and each will arrive with an argument for where it belongs. What is needed is
the **rule**, not a pre-emptive list.

## Decision

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

**Name a component for the capability it provides in this system** — not for the vendor it talks to,
and not for the *mechanism* by which it does so.

`plaid-sync` was wrong because it named a vendor. `connectors` is wrong for a related reason: it
names the mechanism (integrating with things) rather than a capability, and it answers neither
"connectors to what?" nor "providing what?". It will also, on the current trajectory, be asked to
cover bank feeds, payment processors, and transactional email — which are not one capability, and
conflating them is what a mechanism-name invites.

`connectors` is therefore **renamed before implementation begins**, and probably split. That rename
is deferred rather than done now, because doing it twice is worse than doing it once, and what it
splits into depends on decisions not yet made.

### 5. What this deliberately does not decide

- **The module list.** Only the ledger is fixed. Invoicing is a module because REQ-A9 requires
  atomicity with ledger writes. Everything else is classified when it is built, using § 3.
- **Where ingestion lands.** An earlier draft asserted it must use HTTP. That was over-committed:
  ingestion writes *drafts*, which are ledger records, so a sync batch committing atomically is an
  argument for a module. Credential isolation and a scheduled runtime shape are arguments for a
  component. The criteria in § 3 are recorded; the verdict is not, and the existing import-linter
  contract forbidding that import is a safe provisional default rather than a settled answer.
- **How components map to deployment infrastructure.** Separate components in one repository imply
  separate runtimes, images, and scaling. That needs its own record and does not exist yet.

## Alternatives rejected

### One ledger package containing everything

Simplest, no boundaries to police, and everything can call everything.

Rejected because it degrades the oracle. Once invoicing lives inside the booking engine, the
Beancount comparison no longer isolates double-entry semantics, and the best correctness evidence in
the project weakens. It also makes "the ledger" mean whatever has accumulated, which is exactly the
drift a first-party ledger with no natural boundary is prone to (ADR-0001).

### A `core` module inside the ledger, with siblings beneath it

The conventional shape: `ledger.core`, `ledger.invoicing`, `ledger.reporting`.

Rejected on naming and on what the naming reveals. "Core of what?" has no good answer when the
enclosing package is already the ledger — and needing a core *inside* the ledger concedes that the
ledger has stopped being small. Keeping modules as siblings makes the ledger's size self-policing:
growth shows up as a new sibling rather than as another subdirectory nobody counts.

### Separate distributions per module

Real packaging boundaries, independently versioned, unambiguous dependency direction.

Rejected because they share a database and must commit together, so separate distributions would
advertise an independence that does not exist — and would invite someone to deploy them separately,
which cannot work. import-linter already enforces the boundary statically at no packaging cost.

### Everything talks to the ledger over HTTP, uniformly

Appealing for consistency: one access pattern, everything dogfoods the API, no in-process coupling
anywhere.

Rejected because it makes atomicity impossible where atomicity is required. An invoice and its GL
entries must commit together; over HTTP that becomes a distributed transaction or a compensating
action, which is an enormous cost to pay for uniformity. Consistency of access pattern is not worth
correctness of the write path.

### Decide the full module list now

Would settle the architecture in one pass and avoid re-opening it repeatedly.

Rejected as speculative abstraction, which ADR-0012 forbids. Naming modules before the domains exist
means designing boundaries around guesses, and a wrong boundary written down is harder to move than
one never drawn. The criteria are the durable artifact; the list is the perishable one.

## Consequences

**Accepted costs.**
- The `connectors` package carries a name known to be wrong until it is renamed, which is a small
  ongoing embarrassment and a deliberate one — see § 4.
- Classifying each new capability is a judgement call, and § 3 will occasionally be ambiguous.
- Modules cannot depend on each other, so a genuine cross-module need forces either a ledger concept
  or coordination in the service layer. That friction is intended and will sometimes be annoying.

**Follow-on obligations.**
- import-linter contracts encoding "modules depend on the ledger, never on each other, and the ledger
  depends on no module". Added as the first module lands; the mechanism is already in place and
  proven to fail on violation.
- Reports follow ownership: financial statements depend only on the ledger, while AR ageing belongs
  to invoicing. This keeps a reporting module from depending on invoicing.
- `connectors` renamed, and probably split, before implementation begins.
- A separate ADR mapping components to deployment infrastructure — images, runtimes, scheduling, and
  how a component authenticates to the API. Required before any component ships.
- `CLAUDE.md`'s repository map reflects the ledger/module/component distinction.

**Reversal cost. Low now, high later.** Nothing is built, so boundaries are free to move today.
Once modules exist with import contracts and a published API shaped around them, moving a boundary
means moving code across a package edge and possibly across a contract.

## Revisit when

- A capability genuinely fits neither classification, which would mean § 3 is incomplete rather than
  the capability being wrong.
- The ledger acquires a concept it should not know about. That is the signal the boundary slipped,
  and the fix is extracting a module rather than amending the test.
- Deployment topology is decided, since that record may make components more or less expensive and
  shift where the default sits.
