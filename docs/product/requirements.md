# CFOKit — Business Requirements

- **Status:** Draft
- **Date:** 2026-08-17
- **Owner:** Geoff

Capabilities CFOKit must deliver, derived from [`vision.md`](vision.md). Each has a stable
`REQ-` id; specifications in [`specs/`](../../specs/) cite these, and so should commit
messages and ADRs.

## How to read this

- **Requirements state *what*, never *how*.** A requirement naming a library, schema, or
  endpoint has leaked into design and belongs in a spec.
- **Ids are permanent.** Superseded requirements are struck through and kept, never
  renumbered or deleted.
- **`Constraints` cite the ADRs that bound the solution space**, so a spec author does not
  rediscover them.
- **`Status`** is `Accepted` (decided, not yet built), `Blocked` (needs a decision first),
  or `Built`.

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
**Serves:** fractional CFOs — this is what makes 10+ clients on one deployment safe.
**Constraints:** ADR-0002, ADR-0011, ADR-0019.

### REQ-A3 — Exact decimal arithmetic
**P0 · Accepted.** No monetary value is ever represented as a binary float, at any layer,
including tests and fixtures.
**Serves:** all. **Constraints:** ADR-0004. **Verified by:** CI gate 4.

### REQ-A4 — Append-only history with reversing corrections, from the moment of posting
**P0 · Accepted.** **Posting is the point of no return.** A candidate transaction is
mutable while it is a draft — categorising an incoming bank-feed transaction is an
ordinary edit, not a correction. Once posted, it is never updated or deleted; corrections
are new reversing entries, so the audit trail is complete by construction.

Period close is a **second, coarser boundary**: advisory rather than hard, marking a period
as reviewed. It is a workflow signal, not the mechanism that guarantees auditability —
append-only posting already does that.
**Serves:** all; prerequisite for any audit or tax defence. **Constraints:** ADR-0006.
**User-facing statement:** [`accounting-policy.md`](accounting-policy.md) § 2 and § 4.
**Rationale:** without the draft/posted boundary, categorising a bank-feed transaction —
the single most common operation in the product (REQ-B1, REQ-C1) — would require a
three-line reversing entry. Enterprise ledgers (NetSuite, Sage Intacct) draw the line at
posting for exactly this reason; QuickBooks and Xero draw it at period close and rely on a
retention-limited audit log instead.
**Product consequence, stated without overreach:** a correction made by an agent is an entry in
the books rather than an event in a separate log. QuickBooks and Xero also record changes — their
audit logs cannot be disabled — so this is not "invisible edits elsewhere, visible here". What
changes with agents is reviewability: an audit trail sized for a human making a few corrections a
month is not sized for software making hundreds of decisions. Immutability also does nothing about
whether an entry was *right*; that is what the draft state and rule approval are for (REQ-B7).

### REQ-A5 — Demonstrable correctness against an independent oracle
**P1 · Accepted.** Booking results are differentially tested against an established
accounting implementation, and every divergence is documented rather than tolerated.
**Serves:** developers, and anyone deciding whether to trust the books.
**Constraints:** ADR-0010. **Verified by:** CI gate 3.

### REQ-A6 — Cost basis and lot tracking
**P2 · Deferred.** Disposals select lots deterministically so capital gains are computable.
**Deferred until there is an asset that needs it.** Lot selection arises only for *fungible units
held in a pool, acquired at different costs, and later partly disposed of*. It is not
inventory-specific, but neither is it universal:

| Needs lots | Does not |
|---|---|
| Inventory (COGS) | **Interest income** — no basis, no disposal, no gain |
| Securities: equities, bond funds, ETFs | Ordinary income and expense |
| Crypto | Fixed assets — tracked individually, so no *selection* problem |
| Foreign currency balances that are spent | Anything not held and later disposed of |

No current entity holds inventory or investments. Checking-account interest needs nothing beyond
an income account.

**Reserve the shape, defer the feature.** ADR-0002 chose Postgres partly because "FIFO lot
selection is a read-modify-write against lot state", so lots are presumed by decisions already
accepted. A posting must therefore be able to carry an **optional cost and lot reference** from
the first schema version, even though nothing populates it. Adding that later is a migration on
the most-written table in the system.

**What deferring this also defers.** Three accepted decisions were shaped by lot tracking:
- **ADR-0013 (backdating) simplifies substantially.** A backdated acquisition invalidating every
  later disposal's basis happens *through the FIFO queue*. Without lots, a backdated entry moves
  period totals and nothing cascades.
- **`rebook` is probably not needed in v1**, since it exists to recalculate downstream basis.
- **ADR-0017's long-running compute path** was justified by `rebook`, so that requirement relaxes.

**Instrument-dependent when it does arrive:** a stable-NAV money market fund yields ~zero gain
(basis equals proceeds); T-bill discount is accreting *interest income*, not capital gain; bond
funds, ETFs and equities are where real lot selection begins.
**Serves:** entities holding inventory or investments. **Constraints:** ADR-0007, ADR-0013.
**Trigger to activate:** an entity acquires inventory, or holds investments in a brokerage account.


### REQ-A7 — Reporting over arbitrary periods
**P1 · Accepted.** Trial balance as of any date, P&L for any period, and journal queries
filtered by account, payee, or tag.
**Serves:** all. **Constraints:** ADR-0002 (chosen partly to keep ad-hoc queries possible).

### REQ-A8 — Entity-level accounting settings: basis and fiscal year
**P0 · Accepted. Cash basis first; accrual is a known future requirement, not a speculative one.**
The first entity is cash basis, so accrual reporting is not built now — but the ledger must be able
to represent it without a rewrite, which is a data-model constraint rather than a feature (see
"cannot be retrofitted" below). Same pattern as lots in REQ-A6: **reserve the shape, defer the
feature.**

Each entity declares its accounting basis (cash or accrual) and its fiscal
year end. Both are entity properties, not report options. Reports use the declared basis by
default and state it on their face; the alternate basis is available on request and labelled as
such. Changing an entity's basis is recorded with an effective date.
**Serves:** all; prerequisite for tax preparation. **Constraints:** ADR-0006 (a basis change is
recorded, never retroactively rewritten).
**User-facing statement:** [`accounting-policy.md`](accounting-policy.md) § 1.
**Rationale:** the tax method is *elected* and changing it generally requires IRS Form 3115, so
presenting it as a per-report dropdown — as QuickBooks does — misrepresents a formal election as
a view preference, and makes it easy to hand someone a cash-basis statement for an accrual-basis
business unnoticed.
**Cannot be retrofitted:** accrual and cash are different events, not two formattings of one
event. An invoice raised in March and settled in May is March revenue on accrual and May revenue
on cash, so the ledger must record the obligation *and* the settlement and relate them. A ledger
that records only settlements can never produce accrual statements.

### REQ-A9 — Invoicing and accounts receivable
**P1 · Accepted.** Raise invoices to customers, record receipt of payment, apply payments to
invoices, and report who owes what and for how long.

Covers: customers as records; invoices with line items; payment receipt; **application of a payment
to one or more invoices**, including partial payments, overpayments and write-offs; AR ageing.
**Serves:** consultants and service businesses, who invoice rather than take card payments; and any
entity that needs to chase money owed.
**Constraints:** ADR-0006 (an issued invoice is a posted record — corrections are credit notes or
reversals, never edits), ADR-0004, ADR-0011 (payment application is a read-modify-write and takes the
entity lock).
**User-facing statement:** [`accounting-policy.md`](accounting-policy.md) — *pending*.

**Effect on REQ-A8.** Invoicing records an obligation and a settlement as separate related events,
which is precisely the dual-event model accrual reporting needs. Accrual therefore stops being a
data-model risk to guard against and becomes closer to a reporting choice over data already present.
A cash-basis entity still invoices and still tracks receivables; it recognises revenue on settlement.

**Out of scope:** purchase orders, quotes and estimates. Accounts payable is *not* included until a
requirement exists for it — the mirror-image argument is tempting and should be resisted until
someone actually needs to track what they owe.

**Note:** payment application is the fiddly part, not invoice rendering. Partial payments,
overpayments and write-offs are each ordinary and each must be right.


---

## B. Agent capabilities

Each of these is the work "a CFO would do" from the value proposition.

### REQ-B1 — Bookkeeping automation
**P0 · Accepted.** Categorise and book incoming transactions, ask when genuinely ambiguous
rather than guessing, and never book silently to a suspense account.
**Serves:** all. **Constraints:** ADR-0014. **Note:** booking semantics need human review.

### REQ-B7 — Deterministic, rule-based transaction assignment
**P0 · Accepted.** Assignment of ingested transactions to accounts is governed by **stored rules
applied deterministically**. The same transaction against the same rule set yields the same
account, always. The agent proposes rules; the user approves rules; applying them is ordinary
tested code, not a judgement made afresh each time.

Approval is sought for **rules, not individual transactions**, so an approved pattern is never
asked about again. Every assignment records which rule produced it. Changing a rule affects
future assignments only — re-categorising something already posted is a correction with a
visible reversing entry (REQ-A4).
**Serves:** all; this is the daily experience of using CFOKit.
**Constraints:** ADR-0006, ADR-0008 (rule application is deterministic logic and belongs below
the agent, where it can be tested).
**User-facing statement:** [`accounting-policy.md`](accounting-policy.md) § 3.
**Rationale — the failure being designed against.** QuickBooks' automatic assignment rules are
not applied consistently or deterministically, so users find themselves re-teaching the same
categorisation repeatedly. An LLM judging each transaction independently would be *worse*:
non-deterministic by construction, with the same merchant landing in different accounts in the
same month and no way to make a correction stick. Determinism requires that the decision be
stored as data and applied by code; the model's contribution is proposing the rule.
**Standard:** assignment must be at least as consistent as a competent human bookkeeper, where
consistent means deterministic rather than usually right.

### REQ-B2 — Cash flow monitoring
**P1 · Accepted.** Report position and runway, and surface changes without being asked.
**Serves:** founders, small business owners.

### REQ-B3 — Financial reporting
**P1 · Accepted.** Produce the standard statements on request, in a form a human can hand
to a lender or board.
**Serves:** all.
**Open — how output is rendered.** "A form a human can hand to a lender" is not a chat
message, so this requirement already implies rendered output. Whether that is a generated
file, a served report URL, or something else is undecided. ADR-0012's scope gate is now
written, so this needs an ADR passing that gate — the route ADR-0022 took for Slack. A
served URL additionally has to answer ADR-0018's rejection of a second authentication path.
Do not specify this requirement until that ADR exists.

### REQ-B4 — Tax preparation support
**P1 · Blocked.** Assemble the figures and schedules a return needs. **CFOKit does not
file.** Scope of jurisdictions and entity types is undecided; needs a decision before
specification.
**Serves:** solo founders with S-corps and LLCs.

### REQ-B5 — Compliance tracking
**P2 · Blocked.** Track recurring obligations and deadlines by entity type. The rules are
jurisdiction-specific and the vision anticipates these being *contributed*
("Contributing S-corp compliance rules"), so the extension mechanism must be designed
before the content.
**Serves:** solo founders managing S-corps.

### REQ-B6 — Distinct agent roles
**P2 · Blocked.** Whether the roles above are separate skills or one skill with several
modes is an open question in `vision.md`, and it determines the layout of `skills/`.
**Serves:** developers.

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
**Serves:** consultants, service businesses.

### REQ-C4 — Idempotent ingestion
**P0 · Accepted.** Re-running a sync never double-books.
**Serves:** all. **Constraints:** ADR-0011.

---

## D. Delivery and access

### REQ-D1 — Per-client Slack channels
**P1 · Accepted.** A fractional CFO manages each client in a dedicated channel, and the
agent operates in that channel with access scoped to that client's entity.
**Serves:** fractional CFOs — the "save 15+ hours per client per month" claim rests on this.
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

---

## E. Deployment and operations

### REQ-E1 — Self-hostable on a laptop with no cloud account
**P0 · Accepted.** One command brings up a working deployment holding real books, not a
demo.
**Serves:** self-hosters, developers, and the anti-lock-in promise.
**Constraints:** [ADR-0018](../adr/0018-local-compose-dev-and-production.md), ADR-0003, ADR-0019. **Verified by:** CI gate 2.

### REQ-E2 — Managed cloud deployment
**P1 · Accepted.** A hosted tier on one maintained cloud target.
**Serves:** non-technical audiences. **Constraints:** [ADR-0016](../adr/0016-opentofu-single-cloud-target-iac.md), [ADR-0017](../adr/0017-gcp-initial-cloud-target.md).

### REQ-E3 — No lock-in to any provider
**P1 · Accepted.** Configuration is environment variables only; moving deployment targets
is new infrastructure code against the same artifact, not an application change.
**Serves:** self-hosters. **Constraints:** ADR-0003, ADR-0016. **Verified by:** CI gate 2.

### REQ-E4 — Complete audit trail
**P0 · Accepted.** Every state-changing operation is attributable to a request and an
actor, and sensitive values never appear in logs.
**Serves:** all. **Constraints:** ADR-0011.

### REQ-E5 — Data export and portability
**P1 · Accepted.** A user can get their complete books out in a form another system can
read. Owning your data is only true if you can leave with it.
**Serves:** self-hosters.

### REQ-E6 — Subscription billing and metering
**P2 · Blocked.** The $15/month price point in `vision.md` implies billing that is
entirely unspecified, and it must not exist in the self-hosted artifact.
**Serves:** the managed tier.

### REQ-E7 — Retention schedule by record class, with audited disposal
**P1 · Accepted.** Retention is a company policy, **layered by record class rather than a single
period**:

| Class | Default |
|---|---|
| Ledger, postings, statements, chart of accounts | Indefinite |
| Supporting documents, attachments, raw feed payloads | 7 years |
| Fixed asset records | Life of asset + 7 years |
| Destruction log | Permanent — outlives what it documents |

Append-only governs whether a record can be silently altered; retention governs how long a class
is kept. Separate obligations.

Disposal, where it applies, is never a background job. Candidates are listed, **legal hold is
evaluated at disposal time and overrides the schedule**, a named approver authorises the batch,
and a permanent record captures what was destroyed, when, by whom, and under what authority.
**Serves:** all. **Constraints:** ADR-0006.
**User-facing statement:** [`accounting-policy.md`](accounting-policy.md) § 8.
**Rationale.** Research into mid-market practice found the ledger is normally in the *permanent*
tier — the seven-year rule refers to supporting documents — and that mainstream ERPs do not delete
it at all: NetSuite refuses to delete posted transactions in closed periods, and its archiving
tools keep data retrievable rather than destroying it. So an append-only ledger retained
indefinitely is the ordinary posture for a system of record.

The default leans toward retention because the penalties are asymmetric: SOX 802 / 18 U.S.C.
§ 1519 applies to private companies, carries up to twenty years' imprisonment, and reaches
*contemplated* investigations. Storage is cheap by comparison.

**Consistency is the legal protection**, not the schedule itself. Destruction in the ordinary
course of a uniformly applied written schedule is defensible; selective destruction is not — which
makes an inconsistently applied schedule worse than none, and is why disposal is deliberate,
approved, and logged.
**Open:** whether ledger disposal is ever offered at all, and how a GDPR erasure request interacts
with an append-only ledger holding payee names.
---

## Traceability

| Vision claim | Requirements |
|---|---|
| "Bookkeeping automation" | REQ-B1, REQ-B7, REQ-C1, REQ-C4 |
| Invoicing and getting paid | REQ-A9 |
| "Tax preparation" | REQ-B4, REQ-A6 |
| "Cash flow monitoring" | REQ-B2, REQ-A7 |
| "Compliance tracking" | REQ-B5 |
| "Financial reporting" | REQ-B3, REQ-A7 |
| "Deploy once, manage multiple clients through Slack" | REQ-A2, REQ-D1, REQ-E1 |
| "Save 15+ hours per client per month" | REQ-B1, REQ-C1, REQ-D1 |
| "Extensible via MCP" | REQ-D2 |
| "Open source, modular architecture" | REQ-C2, REQ-E3 |
| "$15/month" | REQ-E6 |

**Unblocking work is the critical path.** Six requirements are `Blocked`, and five of the
ten vision claims depend on at least one of them. REQ-D1 and REQ-B4 block the two audiences
the positioning leans on hardest.
