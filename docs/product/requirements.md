# CFOKit — Business Requirements

- **Status:** Draft
- **Date:** 2026-08-20
- **Owner:** Geoff

Capabilities CFOKit must deliver, derived from [`vision.md`](vision.md). Each has a stable
`REQ-` id; specifications in [`specs/`](../../specs/) cite these, and so should commit
messages and ADRs.

## How to read this

- **Requirements state *what*, never *how*.** A requirement naming a library, schema, or
  endpoint has leaked into design and belongs in a spec.
- **Ids are permanent once something depends on them.** After a spec, test, or commit cites an
  id, a superseded requirement is struck through and kept rather than renumbered or deleted.
  Before that, a requirement that should never have been written is simply removed.
- **`Constraints` cite the ADRs that bound the solution space**, so a spec author does not
  rediscover them.
- **`Status`** is `Accepted` (decided, not yet built), `Blocked` (needs a decision first),
  `Deferred` (accepted in principle, with a stated trigger), or `Built`.

## How this document changes

This document is live, unlike the ADRs. An ADR is immutable because the reasoning at a
point in time *is* the artifact; a requirement states what the product owes someone now,
so it is revised whenever that changes. Revise on decisions rather than on a release
cadence — specs cite these ids continuously, not at release boundaries.

Four kinds of change, handled differently:

| Change | Handling |
|---|---|
| **Activation** — a `Deferred` or `Blocked` requirement's trigger fires | Status change only. The id, the text, and everything citing it are untouched. |
| **Refinement** — the intent is unchanged and the statement gets sharper | Edit in place. |
| **Reversal** — the requirement was wrong | Strike through, keep it, and write a new id. Never renumber, never delete. |
| **Redefinition** — the id survives but its meaning moves | **New id, once anything relies on it.** A spec, test, or commit citing REQ-X will silently drift if REQ-X quietly acquires a different scope. The test is whether something already depends on it, not whether the change felt small while writing it. |

**Where the reasoning lives.** An edit overwrites its own history, so the only surviving
explanation is the commit message. That is adequate when commits are written to carry it
and worthless when they say "update requirements". A change to what the product owes
someone wants an ADR rather than a good commit message.

**One coupling to watch.** P1 is defined against the positioning in `vision.md`, so a
vision change re-prioritises requirements without a word of requirement text changing.
When positioning moves, re-read the priorities before trusting them.

## Priority definitions

| | Meaning |
|---|---|
| **P0** | Without this there is no product. |
| **P1** | Required for the positioning in `vision.md` to be honest. |
| **P2** | Expected by the target audience; can follow first release. |

---

## A. Ledger and booking

### REQ-A1 — Double-entry ledger with enforced zero-sum
**P0 · Accepted.** Every transaction balances to zero per commodity, and the system refuses
to record one that does not.
**Serves:** all audiences. **Constraints:** [ADR-0002](../adr/0002-postgres-as-sole-storage-backend.md), ADR-0004, ADR-0005.

### REQ-A2 — Multi-entity isolation
**P0 · Accepted.** One deployment holds books for many entities; no operation can read or
write across an entity boundary without an explicit grant.
**Serves:** fractional CFOs, who carry four to eight clients at once, and any deployment
holding books for more than one entity.
**Constraints:** ADR-0002, ADR-0011, ADR-0019.

### REQ-A3 — Exact decimal arithmetic
**P0 · Accepted.** No monetary value is ever represented as a binary float, at any layer,
including tests and fixtures.
**Serves:** all. **Constraints:** ADR-0004. **Verified by:** CI gate 4.

### REQ-A4 — Append-only history with reversing corrections, from the moment of posting
**P0 · Accepted.** **Posting is the point of no return.** A candidate transaction is mutable
while it is a draft — categorising an incoming bank-feed transaction is an ordinary edit, not a
correction. Once posted it is never updated or deleted; corrections are new reversing entries,
so the audit trail is complete by construction.

Period close is a second, coarser boundary: advisory rather than hard, marking a period as
reviewed. It is a workflow signal, not the mechanism that guarantees auditability.
**Serves:** all; prerequisite for any audit or tax defence. **Constraints:** ADR-0006.
**User-facing statement:** [`accounting-policy.md`](accounting-policy.md) § 2 and § 4.

### REQ-A5 — Demonstrable correctness against an independent oracle
**P1 · Accepted.** Booking results are differentially tested against an established
accounting implementation, and every divergence is documented rather than tolerated.
**Serves:** developers, and anyone deciding whether to trust the books.
**Constraints:** ADR-0010. **Verified by:** CI gate 3.

### REQ-A7 — Reporting over arbitrary periods
**P1 · Accepted.** Trial balance as of any date, P&L for any period, and journal queries
filtered by account, payee, or tag.
**Serves:** all. **Constraints:** ADR-0002 (chosen partly to keep ad-hoc queries possible).

### REQ-A8 — Entity-level accounting settings: basis and fiscal year
**P0 · Accepted.** Each entity declares its accounting basis (cash or accrual) and its fiscal
year end. Both are entity properties, not report options. Reports use the declared basis by
default and state it on their face; the alternate basis is available on request and labelled as
such. Changing an entity's basis is recorded with an effective date.

**Cash basis is what gets built first. Accrual is a known future requirement, not a speculative
one**, and it constrains the data model now: accrual and cash are different events rather than
two formattings of one. An invoice raised in March and settled in May is March revenue on
accrual and May revenue on cash, so the ledger has to record the obligation *and* the settlement
and relate them. A ledger recording only settlements can never produce accrual statements.
**Serves:** all; prerequisite for tax preparation.
**Constraints:** ADR-0006 (a basis change is recorded, never retroactively rewritten).
**User-facing statement:** [`accounting-policy.md`](accounting-policy.md) § 1.

### REQ-A9 — Invoicing and accounts receivable
**P1 · Accepted.** Raise invoices to customers, deliver them, record receipt of payment, apply
payments to invoices, chase what is late, and report who owes what and for how long.

Covers: customers as records; invoices with line items; **delivery by email**, raised manually or
on a recurring schedule; payment receipt; **application of a payment to one or more invoices**,
including partial payments, overpayments and write-offs; AR ageing; **automated payment reminders
on a schedule the entity sets**.

Invoicing records an obligation and a settlement as separate related events, which is the
dual-event model REQ-A8 needs for accrual. A cash-basis entity still invoices and still tracks
receivables; it recognises revenue on settlement.

**Out of scope:** purchase orders, quotes, estimates, and accounts payable, none of which is
included until something needs it.
**Serves:** any entity that bills customers rather than taking payment at the point of sale.
**Constraints:** ADR-0006 (an issued invoice is a posted record — corrections are credit notes or
reversals, never edits), ADR-0004, ADR-0011 (payment application is a read-modify-write and takes
the entity lock), REQ-D5 (delivery), REQ-E9 (recurring invoices and reminders).
**User-facing statement:** [`accounting-policy.md`](accounting-policy.md) — *pending*.

---

## B. Agent capabilities

The bookkeeper and controller work described in [`vision.md`](vision.md), plus the bounded
guidance offered where the CFO seat is held by a founder or an owner-operator rather than by a
professional. Whoever holds that seat consumes what these produce rather than performing any
of it.

### REQ-B1 — Bookkeeping automation
**P0 · Accepted.** Categorise and book incoming transactions, ask when genuinely ambiguous
rather than guessing, and never book silently to a suspense account.
**Serves:** all. **Constraints:** ADR-0014. **Note:** booking semantics need human review.

### REQ-B2 — Cash flow monitoring
**P1 · Accepted.** Report position and runway, and surface changes without being asked.
**Serves:** founders, and owner-operators deciding whether they can pay themselves.

### REQ-B3 — Financial reporting
**P1 · Blocked.** Produce the standard statements on request, in a form a human can hand to a
lender or a board.
**Blocked on: how output is rendered.** A chat message is not that form, so this requirement
already implies rendered output. Whether that is a generated file, a served report URL, or
something else is undecided, and a served URL additionally has to answer ADR-0018's rejection of
a second authentication path.
**Serves:** all. **Constraints:** ADR-0012, ADR-0018.

### REQ-B4 — Tax preparation support
**P1 · Blocked.** Assemble the figures, schedules, and supporting detail a return needs.
**CFOKit does not file.**
**Standard:** a CPA can answer their own questions from the books without emailing the client.
**Blocked on:** scope of jurisdictions and entity types.
**Serves:** every entity, and the CPA who prepares its return.
**Constraints:** REQ-B8 (the query surface is how a preparer asks), REQ-A8 (the declared basis is
a tax election rather than a report option), REQ-E5.

### REQ-B5 — Compliance tracking
**P2 · Blocked.** Track recurring obligations and deadlines by entity type. The rules are
jurisdiction-specific and the vision anticipates these being *contributed*
("Contributing S-corp compliance rules"), so the extension mechanism must be designed
before the content.
**Serves:** owner-operators and founders carrying recurring entity obligations.

### REQ-B6 — Distinct agent roles
**P2 · Blocked.** Whether the roles above are separate skills or one skill with several
modes is undecided, and it determines the layout of `skills/`.
**Serves:** developers.

### REQ-B7 — Deterministic, rule-based transaction assignment
**P0 · Accepted.** Assignment of ingested transactions to accounts is governed by **stored rules
applied deterministically**. The same transaction against the same rule set yields the same
account, always. The agent proposes rules; the user approves rules; applying them is ordinary
tested code rather than a judgement made afresh each time.

Approval is sought for **rules, not individual transactions**, so an approved pattern is never
asked about again. A rule matches on more than the payee, since one payee legitimately maps to
several accounts. Every assignment records which rule produced it. Changing a rule affects future
assignments only.
**Standard:** assignment must be at least as consistent as a competent human bookkeeper, where
consistent means deterministic rather than usually right.
**Serves:** all; this is the daily experience of using CFOKit.
**Constraints:** ADR-0006, ADR-0008 (rule application is deterministic logic and belongs below
the agent, where it can be tested), REQ-A4.
**User-facing statement:** [`accounting-policy.md`](accounting-policy.md) § 3.

### REQ-B8 — Ad hoc query over the books, with a declared refusal boundary
**P1 · Accepted.** A user can ask questions of their own books that nobody anticipated, over MCP
or the HTTP interface, and get answers drawn from what is posted.

**The refusal boundary is part of the requirement rather than a later refinement.** Answers come
from postings and never from estimation or recall. Entity scope is enforced server-side
regardless of what is asked. Where the books cannot support an answer, the skill says so and says
why.
**Serves:** owners asking what they spent; CPAs assembling a return; whoever holds the CFO seat
asking considerably harder things.
**Constraints:** ADR-0009, ADR-0014, ADR-0015, ADR-0011, REQ-A2, REQ-D4.
**User-facing statement:** [`accounting-policy.md`](accounting-policy.md) § 10.

### REQ-B9 — Bounded financial guidance for a non-professional in the CFO seat
**P2 · Blocked.** The CFO seat is never empty. Where no professional holds it, the founder or
owner-operator does, on top of running the business. Answer the questions that person asks:
runway, margin, whether a hire is affordable, what changed since last month.

**What it declines matters more than what it answers.** Guidance is bounded to what the books
support. Anything turning on tax election, entity structure, financing, or jurisdiction is
referred to a professional and named as such.
**Blocked on:** the boundary itself. It cannot be specified as "be careful" — it needs stated
categories a test can hold it to.
**Serves:** owner-operators, and founders before institutional money brings a fractional CFO.
**Constraints:** REQ-B8, REQ-A8 (guidance ignoring the declared basis is wrong by construction).
**User-facing statement:** [`accounting-policy.md`](accounting-policy.md) § 10.

---

## C. Data ingestion

### REQ-C1 — Bank and card transaction feeds
**P0 · Accepted.** Pull transactions from financial institutions without manual entry.
**Serves:** all. **Constraints:** ADR-0003, ADR-0014.

### REQ-C2 — Vendor-neutral connectors with a working local default
**P0 · Accepted.** Every provider sits behind one protocol, and at least one provider works
with no cloud account or credentials.
**Serves:** self-hosters, developers, CI. **Constraints:** ADR-0003.
**Rationale:** this is what makes "I built the CFOKit Stripe integration" an additive
change rather than a fork.

### REQ-C3 — Payment processor feeds
**P2 · Accepted.** Revenue from processors is ingested through the same protocol as bank
feeds.
**Serves:** owner-operators taking card payments; any entity with revenue arriving through a
processor rather than a bank.

### REQ-C4 — Idempotent ingestion
**P0 · Accepted.** Re-running a sync never double-books.
**Serves:** all. **Constraints:** ADR-0011.

### REQ-C5 — Migration from an incumbent system
**P1 · Blocked.** Import an existing chart of accounts, transaction history, and balances from
the system a company already runs, most often QuickBooks. Imported records are marked as
imported, with their source.
**Blocked on: what fidelity is promised.** An opening trial balance and a full transaction
history are materially different products with different trust implications, and a QuickBooks
file holds constructs with no clean double-entry equivalent.
**Serves:** every company that already keeps books somewhere, which is every company past its
first year.
**Constraints:** ADR-0006 (imported history is posted history), REQ-A8 (an import carries a basis
and it must match the entity's declared one), REQ-A1, REQ-C4.
**User-facing statement:** [`accounting-policy.md`](accounting-policy.md) § 12.

---

## D. Delivery and access

### REQ-D1 — Per-client Slack channels
**P1 · Accepted.** A fractional CFO manages each client in a dedicated channel, and the
agent operates in that channel with access scoped to that client's entity.
**Serves:** fractional CFOs, and any deployment holding more than one entity.
**Constraints:** ADR-0022 (unblocked it through the ADR-0012 scope gate), ADR-0011, ADR-0023,
ADR-0024.
**The rule that matters:** *channel membership is not authorization.* A request is permitted only
where a **linked** CFOKit identity holds a grant for the channel's bound entity — the intersection,
never the union. Being invited to a channel grants nothing. The channel-to-entity binding is a
stored record and is never inferred from channel name, topic, or message content.
**Limitation:** the Slack surface requires public ingress, so a self-hoster wanting it needs a
tunnel. Core self-hosting is unaffected.

### REQ-D2 — MCP tool surface
**P0 · Accepted.** The ledger is usable from any MCP client, so "extensible via MCP" holds.
**Serves:** developers. **Constraints:** ADR-0009, ADR-0014, ADR-0015.

### REQ-D3 — REST API for third parties
**P1 · Accepted.** A documented HTTP interface with stability obligations.
**Serves:** developers. **Constraints:** ADR-0009, ADR-0015. **Verified by:** CI gate 5.

### REQ-D4 — Delegated authentication with mandatory audience validation
**P0 · Accepted.** Identity is delegated to a swappable OAuth 2.1 issuer; CFOKit never
mints tokens or implements a login flow.
**Serves:** all. **Constraints:** [ADR-0019](../adr/0019-identity-provider-conformance-contract.md), ADR-0011.

### REQ-D5 — Outbound email delivery
**P1 · Accepted.** CFOKit sends email on the entity's behalf — invoices and payment reminders
today, whatever else needs delivering later. Every provider sits behind one protocol, and at
least one provider works with no cloud account or credentials, so the local stack and CI can
send and inspect mail without one.

Delivery is recorded: what was sent, to whom, when, and against which record. A failed send is
visible rather than silent.
**Serves:** any entity that invoices.
**Constraints:** ADR-0003 (a provider-specific dependency at module scope would break
portability), REQ-A9, REQ-E4.

---

## E. Deployment and operations

### REQ-E1 — Self-hostable on a laptop with no cloud account
**P0 · Accepted.** One command brings up a working deployment holding real books, not a
demo.
**Serves:** self-hosters, developers, and the anti-lock-in promise.
**Constraints:** [ADR-0018](../adr/0018-local-compose-dev-and-production.md), ADR-0003, ADR-0019. **Verified by:** CI gate 2.

### REQ-E2 — Managed cloud deployment
**P1 · Accepted.** A hosted tier on one maintained cloud target, operated under independent
attestation (REQ-E8).
**Serves:** every audience above stage 0. **Constraints:** REQ-E8 (the attestation is what this
tier sells), [ADR-0016](../adr/0016-opentofu-single-cloud-target-iac.md), [ADR-0017](../adr/0017-gcp-initial-cloud-target.md).

### REQ-E3 — No lock-in to any provider
**P1 · Accepted.** Configuration is environment variables only; moving deployment targets
is new infrastructure code against the same artifact, not an application change.
**Serves:** self-hosters. **Constraints:** ADR-0003, ADR-0016. **Verified by:** CI gate 2.

### REQ-E4 — Complete audit trail
**P0 · Accepted.** Every state-changing operation is attributable to a request and an
actor, and sensitive values never appear in logs.
**Serves:** all. **Constraints:** ADR-0011.

### REQ-E5 — Data export and portability
**P1 · Accepted.** A user can get their complete books out in a form another system can read,
continuously and without asking. Owning your data is only true if you can leave with it.
**Serves:** all. **Constraints:** ADR-0003.

### REQ-E6 — Subscription billing and metering
**P2 · Blocked.** The managed tier needs billing and metering, and neither may exist in the
self-hosted artifact. Metering counts entities and hosted-ledger usage rather than tokens, since
inference is supplied by the runtime the skill installs into.
**Blocked on:** the price point.
**Serves:** the managed tier. **Constraints:** ADR-0003, ADR-0014.

### REQ-E7 — Retention schedule by record class, with audited disposal
**P1 · Accepted.** Retention is layered by record class rather than set as a single period, and
disposal is never a background job. Candidates are listed, legal hold is evaluated at disposal
time and overrides the schedule, a named approver authorises each batch, and a permanent record
captures what was destroyed, when, by whom, and under what authority.

Append-only governs whether a record can be silently altered. Retention governs how long a class
is kept. Separate obligations.
**Open:** whether ledger disposal is ever offered at all, and how a GDPR erasure request
interacts with an append-only ledger holding payee names.
**Serves:** all. **Constraints:** ADR-0006.
**User-facing statement:** [`accounting-policy.md`](accounting-policy.md) § 8, which holds the
schedule itself and the reasoning behind each tier.

### REQ-E8 — Independent attestation of the hosted service
**P1 · Blocked.** The managed deployment is audited by an independent third party, and the report
is available to customers and to their advisors.
**Blocked on: which report.** SOC 2 Type II is the recognised one. SOC 1 speaks to controls over
financial reporting and may matter more for a system of record whose output feeds a return.
Possibly both, and the answer changes what has to be built.
**Why this is a requirement rather than a procurement task.** Evidence collection, access review,
change management, and incident handling have to be properties of how the service is operated. A
control that was not operating cannot be attested retroactively, so the audit period begins when
the practice begins rather than when an auditor is engaged.
**Serves:** the managed tier, and every audience beyond a founder running it alone.
**Constraints:** ADR-0011, ADR-0016, REQ-E4, REQ-E7.
**User-facing statement:** [`accounting-policy.md`](accounting-policy.md) § 13.

### REQ-E9 — Recurring scheduled work
**P1 · Accepted.** Work that has to happen on a schedule rather than in response to a request —
feed syncs, recurring invoices, payment reminders — runs on a timer the entity controls, without
a person triggering it.

Runs are idempotent, so a retry or an overlapping trigger does not double-send or double-book. A
missed window is recoverable rather than skipped silently, and every run is attributable in the
audit trail like any other actor.
**Serves:** all; this is what makes "surface changes without being asked" possible at all.
**Constraints:** ADR-0003 (no cloud scheduler — it must run in the self-hosted stack), REQ-C4,
REQ-E4, REQ-A9, REQ-B2.

---

## Traceability

| Vision claim | Requirements |
|---|---|
| Bookkeeper and controller work against a ledger you own | REQ-A1, REQ-A4, REQ-B1, REQ-B7 |
| Rules you approve; every posting traces to the rule that made it | REQ-B7 |
| Feeds arrive without manual entry | REQ-C1, REQ-C3, REQ-C4, REQ-C2 |
| Periods close on a schedule | REQ-A4, REQ-A8 |
| Statements a lender, board, or accountant will accept | REQ-B3, REQ-A7 |
| Questions do not have to be anticipated in advance | REQ-B8, REQ-A7, REQ-D2, REQ-D3 |
| A CPA can answer their own questions | REQ-B4, REQ-B8, REQ-E5 |
| Invoicing, delivery, and chasing what is owed | REQ-A9, REQ-D5, REQ-E9 |
| Guidance for a non-professional in the CFO seat | REQ-B9, REQ-B2 |
| Displaces QuickBooks plus a bookkeeping service | REQ-C5, REQ-B1, REQ-B7 |
| Runs on a laptop with no cloud account | REQ-E1, REQ-C2, REQ-E3 |
| The hosted service is operated under third-party audit | REQ-E2, REQ-E8, REQ-E4 |
| Leaving is genuinely easy, or the software is not free | REQ-E5 |
| A client per Slack channel | REQ-A2, REQ-D1 |
| Extensible over MCP | REQ-D2, REQ-C2 |

**Unblocking work is the critical path.** Eight requirements are `Blocked`: REQ-B3, REQ-B4,
REQ-B5, REQ-B6, REQ-B9, REQ-C5, REQ-E6, REQ-E8. Two of them sit under the commercial thesis
rather than under a feature — REQ-E8 decides what the hosted tier sells, and REQ-C5 decides
whether a company that already keeps books can adopt at all.

**Nothing here describes a capability nobody intends to build.** Where a need is real but
unscoped, it is `Blocked` with the decision named. Where it is not a need yet, it is absent.
