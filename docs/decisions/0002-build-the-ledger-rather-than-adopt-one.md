---
status: "draft"
kind: "requirement-driven"
date: 2026-08-18
decision-makers: [Geoff]
---

# ADR-0002: Build the ledger rather than adopt an existing open source accounting system

> **This record exists to end re-litigation.** Building a double-entry ledger is the largest
> undertaking in the project and the most reasonable thing to second-guess. The alternative you are
> about to propose is below, with the specific reason it was not chosen. If none of them match your
> reasoning, that is new information and worth a new record.

**Requirements served:** `LED-13`, `LED-08`, `AR-02`, `NFR-01`.

## Context and Problem Statement

CFOKit's differentiator is agents that do CFO work. The ledger is infrastructure beneath them. The
obvious strategy is to adopt an open source accounting system with a good API, build the MCP server
and skills on top, and commercialise by hosting it.

That strategy is sound in the abstract and deserves a specific answer.

### The thesis, and the tension it creates

CFOKit is being built partly to test a hypothesis: **the value of software is approaching zero, and
value accrues to an accountable service offering** — hosting, compliance, and everything that
attends them.

That thesis is already load-bearing elsewhere. [ADR-0019](0019-identity-provider-conformance-contract.md)
rejects building an OAuth issuer in its own words: *"Security-critical code with no differentiating
value, and CFOKit's thesis is that software value is zero — writing an OAuth server contradicts it
directly."*

Applied consistently, that argument appears to reject building a ledger too — and this record even
concedes the premise below, calling the ledger the most commodity component in the project. The
tension is real and has to be resolved rather than stepped around.

**The resolution is that the service being sold is accountability, and accountability is a property
of the ledger's design.** The ledger is not valuable as software; it is valuable as the substrate of
the thing being sold. That is precisely what distinguishes it from an OAuth issuer: nobody buys
CFOKit for its token validation, and an issuer's internal behaviour is invisible to the value
proposition. A ledger that can silently lose history is not a quality problem in a component — it is
the product failing at the thing it charges for.

So the thesis survives intact, and it narrows the question usefully. It does not say "never build."
It says **build only what carries the accountability claim, and adopt or delegate everything else.**
By that rule: the issuer is delegated (ADR-0019), the reporting oracle is borrowed (ADR-0010), the
cloud is rented — and the ledger is built, because it is
where the accountability lives.

### What CFOKit actually needs built

"Build our own accounting system" inflates the scope. Against current requirements, with the
deferrals already recorded, the ledger is:

| In scope | Out of scope |
|---|---|
| Chart of accounts with account types | Inventory and cost of goods sold |
| Transactions with balanced postings, `Decimal` | Cost basis, lots, FIFO disposal (LED-18, LED-19, deferred) |
| Draft to posted state machine (ADR-0007) | Payroll |
| Reversing corrections | Fixed asset depreciation *schedules*; a manual depreciation journal is BKP-04 and is in scope |
| Entity isolation and per-entity grants | Multi-currency revaluation |
| Audit log, idempotency keys, entity locking | Manufacturing, CRM, HR, projects |
| Cash basis now, accrual representable (LED-14, LED-17) | Anything on the ADR-0012 non-goals list |
| Trial balance, P&L, balance sheet, journal queries | Purchase orders, quotes, estimates |
| Deterministic categorisation rules (BKP-06, BKP-08) | Accounts payable — until a requirement exists |
| Advisory period close | |
| **Invoicing and accounts receivable (AR-01–AR-19)** | |

**Invoicing and AR are the largest single item here, and they shape the rest.** Invoicing brings
customers as first-class records, invoices as documents with line items, receipt of payment,
**application of a payment to one or more invoices**, and ageing. Payment application is the
genuinely fiddly part: partial payments, overpayments, and write-offs are each ordinary and each has
to be right.

It also **pulls accrual much closer than LED-14 anticipated**. An invoice raised is an obligation and
a payment received is a settlement, so recording both — which invoicing requires regardless — is
exactly the dual-event model that accrual reporting needs. A cash-basis entity still invoices and
still wants to know who owes it money; it simply recognises revenue on settlement. So accrual stops
being a future data-model risk and becomes close to a reporting choice over data already present.
[ADR-0037](0037-accounting-basis-is-a-presentation-property.md) settles that observation as a
decision; this passage is where the reasoning first appeared, as evidence for scope rather than as a
commitment.

The risk argument holds regardless of size: double-entry semantics have been stable for five
centuries, an independent oracle exists to test against (ADR-0010), and the requirements do not
move. The scope is large; its *uncertainty* is not.

### The risk profile inverts the usual heuristic

"Don't build what you can adopt" assumes the thing you would build is the risky part. Here it is the
opposite: the ledger is the **lowest**-risk component — well specified, oracle-testable, static
requirements — while the genuinely uncertain work is whether an agent categorises reliably enough to
trust, what shape the tool contract should take, and whether buyers value accountability at all.

Adopting removes effort from the component carrying least risk and leaves every uncertain component
untouched.

## Decision Drivers

* **Accountability is the product.** Whatever carries the accountability claim is built; everything
  else is adopted or delegated.
* **Where the risk actually sits.** Effort should be spent on uncertain work, not on the
  best-specified component in the project.
* **LED-13: many entities in one deployment.** A fractional CFO with fifteen clients must not mean
  fifteen deployments.
* **Ledger semantics must be enforceable in the schema** — append-only (ADR-0007), zero-sum
  (ADR-0006), `NUMERIC(28,10)` money (ADR-0005), Postgres-only (ADR-0003).
* **Scope must stay bounded.** A general ledger, not an ERP (ADR-0012).
* Licence is explicitly **not** a driver. See More Information.

## Considered Options

* Build the ledger, first-party, as the system of record
* Adopt Bigcapital and build the agents on top
* Adopt ERPNext or Odoo
* Use Beancount as the booking engine
* Build on TigerBeetle
* Adopt now, replace later if the thesis validates
* Contract-first, with the backend staged behind it

## Decision Outcome

Chosen option: **build the ledger.** It is first-party and it is the system of record. Scope is
bounded by the table above: a general ledger, not an ERP.

**Licence is deliberately left open.** See More Information — it is not a reason for this decision in
either direction.

### Consequences

* Good, because the accountability properties the product is sold on can be enforced in the schema
  rather than asserted over a backend that does not guarantee them.
* Good, because the tool contract is shaped by CFOKit's semantics rather than by an adopted system's.
* Bad, because this is the longest path to a demonstrable product. How long is not estimated here —
  the scope table bounds what is built, not how fast.
* Bad, because accounting edge cases that mature systems have absorbed will be discovered late, by us.
* Bad, because no community maintains the ledger. Every booking bug is ours.
* Bad, because reporting is written from scratch, including the cash-and-accrual representation,
  which is the least charted part of the scope.
* Neutral, because scope is larger than the earliest framing admitted — invoicing and AR are
  substantial — while its *uncertainty* is unchanged.

### Confirmation

The Beancount differential oracle (ADR-0010) is CI gate 3 and substitutes for the production exposure
an adopted system would have brought. The accountability properties are enforced by schema and by CI
rather than by convention: append-only (ADR-0007), the zero-sum deferred constraint trigger
(ADR-0006), and CI gate 4 on float storage types (ADR-0005).

## Pros and Cons of the Options

### Build the ledger

* Good, because it is the lowest-risk component in the project: well specified, oracle-testable,
  requirements that do not move.
* Good, because double-entry semantics have been stable for five centuries.
* Bad, because a first-party ledger has no natural boundary, so scope discipline becomes load-bearing.

### Adopt Bigcapital and build the agents on top

The strongest version of the adopt strategy, and the one this record takes most seriously. Its
tenancy model genuinely fits, it is not bloated, and **its licence is not an objection**.

* Good, because it is genuinely headless, accounting-focused rather than an ERP, self-hostable, with
  Plaid and Stripe already integrated.
* Good, because database-per-tenant tenancy fits LED-13 — documented use of 30+ clients on one
  instance.
* Good, because `accounts_transactions` already carries both `date` and `created_at`, so most of
  ADR-0013's two-date model is present.
* Bad, and decisively so, because **`LedgerEntriesStorage.deleteEntries()` issues a hard `.delete()`
  on general ledger rows**, `accounts_transactions` has no `updated_at`, and the audit log is an
  activity log without before/after state. History can be removed without trace. That is
  disqualifying because of what CFOKit sells: a ledger that can lose history is not a quality defect
  in a component, it is a defect in the only thing the thesis says has value.
* Bad, because **adopting means adopting as-is.** Maintaining a fork to add append-only semantics is
  not a real option and is not offered as one here: forking an actively developed project to change
  its core write paths is almost never justifiable. The choice is Bigcapital's ledger semantics or
  our own, not some blend.
* Bad, but **not load-bearing**, because money is held at two scales — `DECIMAL(13,3)` on ledger
  entries, `DECIMAL(15,5)` on account amounts, neither reaching `NUMERIC(28,10)`.
* Bad, but **not load-bearing**, because it is MySQL-only, leaving ADR-0006's zero-sum trigger without
  a mechanism and weakening ADR-0011's locking.

**Reconsider immediately if** GL semantics change upstream to append-only or soft-delete with a change
log carrying before/after state. That is specific, checkable, and would remove the one objection this
rejection now rests on.

### Adopt ERPNext or Odoo

* Good, because both are mature, with enormous communities, real APIs, and years of accounting edge
  cases handled.
* Good, because Odoo Community's LGPL-3 is the most permissive real option available.
* Bad, because tenancy is scoped per site or per database, so fifteen clients means fifteen
  deployments to migrate, back up and upgrade — LED-13 requires many entities in one deployment.
* Bad, because using the general ledger means deploying, securing and upgrading HR, CRM,
  manufacturing and a web UI, an enormous surface for a project whose non-goals exclude a web UI
  outright (ADR-0012).

### Use Beancount as the booking engine

* Good, because it is a correct, independently maintained double-entry implementation.
* Bad, because it is file-based and single-writer, exactly the model ADR-0003 rejected once
  multi-tenant hosting became the point.
* Neutral, because it is retained in the role it does suit: the differential test oracle (ADR-0010).

### Build on TigerBeetle

Worth naming because it will be proposed.

* Good, because it is Apache-2.0, extremely fast, and purpose-built for double-entry transfers — the
  only permissive option with real relevance.
* Bad, because it is a ledger primitive rather than an accounting system: no chart of accounts
  semantics, no fiscal periods, no reporting, no ad-hoc queries. Adopting it means building everything
  in the scope table anyway.
* Bad, because it must run alongside Postgres for the rest, which ADR-0003 forbids.

### Adopt now, replace later if the thesis validates

Ship in weeks on an adopted backend, validate, let revenue fund a ledger later. ADR-0014 supports it
structurally, since skills reach the ledger over HTTP and never import its code.

* Good, because it reaches a demonstrable product fastest.
* Bad, because the validation it buys is available more cheaply. **Proving an agent can categorise
  reliably does not require a production ledger** — it requires fixtures. The uncertain hypotheses are
  about agent behaviour and contract shape, and none are gated on production-grade booking.
* Bad, because adopting incurs non-refundable costs: a tool contract shaped by the adopted system's
  semantics, and an accountability claim that cannot be made while the backend can delete history.

### Contract-first, with the backend staged behind it

Design the tool contract to CFOKit's semantics now, implement it first against an adopted hosted
ledger, swap in the first-party ledger later without changing the skills. The best of the adopt
variants.

* Good, because the contract keeps CFOKit's semantics from the start.
* Bad, because the contract's guarantees would be aspirational until the real ledger existed —
  offering `post` and promising immutability over a backend that deletes rows. That means either
  documenting a gap between contract and behaviour, or selling a correctness property that is not
  enforced.
* Bad, because for a product whose premise is accountable books this is not recoverable by fixing it
  later: the users who relied on it were already misled.

## More Information

### What Bigcapital does

Bigcapital is the strongest candidate and the closest match to the adopt strategy. Findings, all
verified in its repository:

| Property | Finding | Bearing |
|---|---|---|
| **Multi-tenancy** | Database-per-tenant; separate `system` and `tenant` migration trees; documented use of 30+ clients on one instance | **Fits.** |
| **Weight** | Accounting-focused and headless | **Fits.** The ERP-weight objection does not apply. |
| **Two dates** | `accounts_transactions` carries both `date` and `created_at` | **Fits.** Most of ADR-0013's model already present. |
| **Database** | MySQL only — `mysql`/`mysql2`, no `pg`; Knex + Objection.js | Conflicts with ADR-0003 |
| **Money precision** | `accounts_transactions.credit`/`debit` is `DECIMAL(13,3)`; `accounts.amount` is `DECIMAL(15,5)` | Conflicts with ADR-0005 |
| **GL mutability** | `LedgerEntriesStorage.deleteEntries()` issues a hard `.delete()` on `accounts_transactions` | Conflicts with ADR-0007 |
| **Audit trail** | `audit_logs` added April 2026: `action`, `subject`, `subject_id`, nullable JSON `metadata`. No before/after columns | Does not compensate |
| **Data access** | Objection.js ORM | Conflicts with ADR-0028 |

Three of these are material rather than stylistic.

**Ledger rows are hard-deleted, and nothing reconstructs them.** `accounts_transactions` has
`created_at` but no `updated_at`, the delete is a physical row removal, and the audit log is an
*activity* log rather than a *change* log — it records that something happened to a subject, with
before/after state only if a caller chose to serialise it into a nullable JSON column. It also
arrived four months ago, so nothing older is covered at all. The property is stronger than "posted
records are editable": history can be removed without trace.

**Money is held at two different scales in the same system.** Three decimal places on ledger entries,
five on account amounts. Neither reaches `NUMERIC(28,10)`. For a cash-basis USD entity today this is
survivable; for FX rates or sub-cent unit prices it is not, and two scales for money in one system is
a defect regardless of magnitude.

**MySQL is not a swap.** It removes deferred constraint triggers, so ADR-0006's zero-sum guarantee has
no mechanism and would fall back to application-only checking — which ADR-0006 rejects explicitly.
`GET_LOCK` has different semantics from `pg_advisory_xact_lock`, weakening ADR-0011.

### On licence, which is not a reason here

Copyleft is not a factor in this decision, and this section exists so it is not raised as one.

**CFOKit is hosted or self-hosted under a licence we choose, and its server-side dependencies are
resolved from an index rather than shipped by us.** GPL and LGPL trigger on distribution; only AGPL
reaches a hosted service, by triggering on network interaction.

So copyleft is a real constraint for skills and plugins, which are genuinely distributed, and not a
constraint for the server. The licence question is left open and is not load-bearing here.
`CLAUDE.md` scopes the rule that way.

### Follow-on obligations

* The Beancount differential oracle is not optional. It substitutes for the production exposure an
  adopted system would have brought (ADR-0010, CI gate 3).
* Scope discipline is load-bearing. A first-party ledger has no natural boundary; the scope table is
  the boundary, and anything beyond it needs a requirement first.
* Validate the agent hypotheses **early and against fixtures**, so the uncertain work is not gated on
  the certain work.
* The accountability properties must be enforced in the schema rather than by convention (ADR-0007),
  since they are the justification for building at all.
* The licence decision is tracked separately and is not blocked by this record.

### Reversal cost

**Asymmetric.** Abandoning a partly built ledger for an adopted one costs the sunk build, but the tool
contract and skills survive because ADR-0014 keeps the backend swappable — bounded, and cheaper than
it sounds. Going the other way is worse: adopting first and building later means a contract shaped by
someone else's semantics and users who relied on unenforced guarantees.

## Revisit when

* **Bigcapital changes its ledger semantics** — append-only or soft-delete GL rows, a change log with
  before/after state, consistent money precision. That is a specific, checkable trigger, and it would
  remove the objections this record actually rests on.
* **A permissively or copyleft-licensed, multi-tenant, headless double-entry ledger with append-only
  semantics reaches maturity.** Licence is explicitly not the filter; ledger semantics are.
* **The scope table stops holding.** If real use demands inventory, payroll, depreciation and
  multi-currency revaluation, CFOKit is being asked to be an ERP, and adopting one becomes right rather
  than tempting.
* **Agent validation fails.** If agents cannot categorise reliably enough to trust, the ledger was the
  wrong thing to build and the premise needs revisiting, not the storage layer.

Development effort alone is **not** a revisit trigger.
