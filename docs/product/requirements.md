# CFOKit — Business Requirements

- **Status:** Draft
- **Owner:** Geoff

## 1. Purpose and scope

This document states what CFOKit must do for the people who pay for it and the people who
depend on its output. Requirements state what, never how; design decisions derive from it and
are recorded elsewhere. Identifiers are stable and are never reused.

### Reading a requirement

| Field | Meaning |
|---|---|
| **Priority** | `Must` — the product is not a general ledger without it. `Should` — required for a stated buyer to adopt. `Could` — genuinely wanted; waits on a stated trigger. |
| **Status** | `Approved` — agreed and specifiable now. `Proposed` — agreed in intent, but an open business question must be settled before it can be specified. `Deferred` — agreed, waiting on a named trigger. |
| **Acceptance** | The observable outcome that settles whether it is met. |

---

## 2. Business objectives

Each objective carries a measure. A requirement that serves no objective below does not
belong in this document.

| | Objective | Measure of success |
|---|---|---|
| **OBJ-1** | Displace the spend a small company makes on bookkeeping software plus an outsourced bookkeeping service | A company running CFOKit cancels both, at a combined saving of $340–1,000 per month |
| **OBJ-2** | Keep books current and closed without a person doing the recording | Books current to within one day; period close lands on schedule rather than two to six weeks after month end |
| **OBJ-3** | Make every number traceable to its origin | Any posting resolves to the source transaction and the rule that assigned it, for the full life of the record |
| **OBJ-4** | Produce output that outside professionals accept without rework | A CPA answers their own questions from the books without contacting the client; a lender or board accepts the statements as presented |
| **OBJ-5** | Guarantee the company owns and can leave with its data | A complete, re-importable export is available at any moment, self-service, without contacting anyone |
| **OBJ-6** | Be adoptable with no vendor relationship of any kind | The software runs with no cloud account, no signup, and no third-party credentials |
| **OBJ-7** | Accept outside contributions the way a healthy open-source project does | Adding a financial institution, a payment processor, or a jurisdiction's rules is an additive change against a stable extension point, submitted and reviewed as an ordinary pull request, and requires no alteration to the ledger or the modules around it |
| **OBJ-8** | Serve a small business across the whole range its incumbents serve | A company growing within the small-business segment — adding entities, moving from cash to accrual, engaging a fractional CFO — is never forced to migrate away. The segment is the one QuickBooks, Xero, and Zoho Books compete for |
| **OBJ-9** | Be examinable by an external auditor wherever it runs | The system supplies, from its own records, the access, change, and processing evidence a SOC 1 and a SOC 2 Type II examination require, over a period of operation rather than at a moment |

---

## 3. Stakeholders

| Stakeholder | Relationship | What they need from CFOKit |
|---|---|---|
| **The company** | Pays, in every case | Books it can trust, at a cost proportionate to its size |
| **Founder** | Operates; often holds the CFO seat | Correct books without spending time on them; straight answers about runway and affordability |
| **Owner-operator** | Operates; holds the CFO seat | Categorisation as transactions arrive; answers about pay, tax, and whether a job or location makes money |
| **Fractional CFO** | Operates across four to eight clients; advocates | Each client arriving current, closed, and traceable, so the engagement is strategy rather than reconstruction |
| **Controller / staff accountant** | Operates at scale | A close process and a review boundary that survive staffing changes |
| **CPA** | Consumes output; recommends | A closed year, schedules, and supporting detail sufficient to prepare a return unaided |
| **Lender, board, investor** | Consumes output | Statements in a conventional form, on a stated basis |
| **Auditor, forensic accountant** | Consumes history | A complete, unaltered history with attribution |
| **Self-hoster** | Operates their own deployment | A complete build with no cloud account, no signup, and no feature held back |
| **Contributor** | Extends the system | Extension points that make a new provider or ruleset an additive change |

---

## 4. Scope

### In scope

Recording, reconciling, and closing a double-entry general ledger; ingesting transactions
from financial institutions and processors; billing customers and collecting from them;
producing financial statements and answering questions against the books; migrating in from
an incumbent system and out to any other; and supplying, from the system's own records, the
evidence an external examination of its controls requires.

### Out of scope

These are decided. Each bounds what the product may promise.

| Not in scope | Boundary |
|---|---|
| Acting as a CFO | CFOKit does the bookkeeper and controller work beneath the role. The role is always held by a person. |
| A web application or admin console | CFOKit is agents and an interface, not a dashboard. Reversible only by deliberate decision, not by drift. |
| Moving money | CFOKit reads financial data and keeps books. It does not initiate payment. |
| Filing returns | CFOKit produces the closed year and supporting detail. A preparer files. |
| Being hosted-only | Self-hosting is a product promise, not a trial edition. |
| Any commercial service built on CFOKit | Its existence, pricing, billing, subscriptions, and operating policies — including disclosure practice — are business decisions, not product requirements. The product must not presume a commercial operator exists. |
| Accounts payable, purchase orders, quotes, estimates | Not included until a stated need arrives. |
| Payroll | Not included. |
| SOX compliance | Sarbanes-Oxley applies to public companies and their auditors. CFOKit does not serve public companies and is not built to. Out of scope until it deliberately is. Note that individual SOX provisions on record destruction reach private companies; those are retention obligations and are handled under NFR-13, not as SOX scope. |
| Enterprise-scale accounting | Consolidation across dozens of entities, multi-currency treasury, statutory reporting regimes, and the volumes that come with them. The target is the small-business segment the incumbents serve. Revisit only once that segment is won. |

---

## 5. Assumptions and dependencies

Business conditions this document relies on.

| | Assumption or dependency |
|---|---|
| **A-1** | The company's financial institutions are reachable through at least one commercial aggregation service, and that service's coverage is adequate for the target segments. |
| **A-2** | A commercial email delivery service is available on ordinary terms. |
| **A-3** | The company has, or can obtain, an identity provider. CFOKit does not become one. |
| **A-4** | A CPA remains in the loop for every company, and is the party who files. |
| **A-5** | Inference cost is carried by the runtime the user already operates, not by CFOKit. Pricing therefore tracks the value of the displaced stack rather than token prices. |
| **A-6** | An independent auditor can be engaged, and the operating history an attestation requires accumulates only from the date the practice begins. |
| **A-7** | Companies migrating in are most often leaving a small-business accounting package whose export fidelity is outside our control. |

---

## 6. Functional requirements

Organised by module.

### 6.1 Ledger — `LED`

The double-entry record itself, and the entity settings that govern how it is kept.

| | Requirement | Priority | Status |
|---|---|---|---|
| **LED-01** | An entity defines its own chart of accounts, organised hierarchically, and can add to it over the life of the books. | Must | Approved |
| **LED-02** | Every transaction balances. The system refuses to record one that does not, in any commodity it holds. | Must | Approved |
| **LED-03** | Monetary amounts are recorded and reported exactly. No representation error, no accumulated drift, no tolerance. A balance is the exact sum of its postings, and amounts are presented at the conventional precision for their commodity. | Must | Approved |
| **LED-04** | Where an amount must be divided and does not divide evenly, the parts sum exactly to the original and the distribution is deterministic. The same division always produces the same parts. | Must | Approved |
| **LED-05** | A transaction is freely editable while it is a draft, and becomes permanent when it is posted. Posting is the point of no return. | Must | Approved |
| **LED-06** | A posted transaction is never altered or removed. Corrections are new entries that reverse the original, leaving both visible. | Must | Approved |
| **LED-07** | Every transaction carries both the date the event occurred and the date it was recorded. Recording a transaction into an earlier period is permitted and is never silent. | Must | Approved |
| **LED-08** | A period can be marked closed, signifying it has been reviewed. Once closed, no posting enters the period except through a recorded reopening, and anything so recorded is identifiable as such. | Must | Approved |
| **LED-09** | One deployment holds the books of many entities. Reaching an entity's records requires an explicit grant to that entity. | Must | Approved |
| **LED-10** | Each entity declares its accounting basis and its fiscal year end when it is created; neither has an undeclared state. These are properties of the entity, not options on a report. A change of basis is recorded with the date it takes effect, and never rewrites history. | Must | Approved |
| **LED-11** | An obligation and its settlement are recorded as two related events rather than one. An invoice raised in one period and paid in another is recoverable as either, depending on the basis in force. | Must | Approved |
| **LED-12** | The ledger holds positions in things other than money — inventory, or investments held in a brokerage account. | Could | Deferred — activates when an entity acquires inventory or holds investments |
| **LED-13** | Where an entity holds fungible units acquired at different costs and disposes of some, disposals consume the earliest lots first, exactly rather than approximately. Where a disposal is ambiguous the system refuses rather than selecting a plausible lot. | Could | Deferred — activates with LED-12 |

**Acceptance, LED-03.** Divide $10.00 three ways: the three resulting postings sum to exactly
$10.00, with no residual and no drift, and repeating the operation a million times introduces
none.

**Acceptance, LED-06.** After a correction, both the original entry and its reversal are
retrievable, and no field of the original has changed.

### 6.2 Data Migration — `MIG`

Getting an existing company's books in, and any company's books out.

| | Requirement | Priority | Status |
|---|---|---|---|
| **MIG-01** | Import an existing chart of accounts from the system a company already runs. | Should | Approved |
| **MIG-02** | Import transaction history and opening balances from that system. | Should | Proposed — the fidelity promised is an open question |
| **MIG-03** | Every imported record is identifiable as imported and names the system it came from. | Should | Approved |
| **MIG-04** | An import is validated before anything is posted. The operator sees what will be created, and what will not, and can abandon it. | Should | Approved |
| **MIG-05** | An import declares the accounting basis of the data it carries, and is refused where that conflicts with the entity's declared basis. | Should | Approved |
| **MIG-06** | An entity can export its complete books — accounts, transactions, balances, and the attribution behind them — at any time and in any state short of deletion, without asking anyone and without a support request. | Must | Approved |
| **MIG-07** | The export is in a form another accounting system can read. | Must | Approved |
| **MIG-08** | An export produced by CFOKit can be re-imported into CFOKit and reproduces the books it came from. | Should | Approved |

**Acceptance, MIG-06.** A suspended entity can still be exported completely, unaided.

**Acceptance, MIG-07.** The export is a single self-contained archive, and a trial balance
derived from the archive alone agrees, line for line, with the trial balance CFOKit produces
for the same date. What a receiving system then computes is outside our control and is not
part of this requirement.

### 6.3 Bookkeeping — `BKP`

Getting transactions in, deciding where they belong, and agreeing that the books match reality.

| | Requirement | Priority | Status |
|---|---|---|---|
| **BKP-01** | Transactions arrive from bank and card accounts without manual entry. | Must | Approved |
| **BKP-02** | Transactions arrive from payment processors through the same path as bank and card feeds. | Should | Approved |
| **BKP-03** | An operator can supply transactions directly by uploading a statement file, for any account no feed reaches. | Must | Approved |
| **BKP-04** | At least one way of getting transactions in works with no third-party account and no credentials of any kind. | Must | Approved |
| **BKP-05** | Assignment of an incoming transaction to an account is governed by stored rules applied deterministically. The same transaction against the same rule set produces the same account, always. | Must | Approved |
| **BKP-06** | A rule matches on more than the payee. One payee legitimately maps to several accounts depending on other properties of the transaction. | Must | Approved |
| **BKP-07** | Approval is sought for rules, not for individual transactions. An approved pattern is never asked about again. | Must | Approved |
| **BKP-08** | Every assignment records which rule produced it, and that attribution survives for the life of the record. | Must | Approved |
| **BKP-09** | Changing a rule affects future assignments only. Existing postings are untouched. | Must | Approved |
| **BKP-10** | Where the rule set cannot resolve a transaction, the operator is asked. Nothing is guessed, and nothing is quietly parked in a holding account. | Must | Approved |
| **BKP-11** | An incoming transaction can be matched to a record the books already hold — an expected payment, or a transaction entered ahead of the feed — rather than creating a duplicate. | Must | Approved |
| **BKP-12** | An account can be reconciled against a statement balance for a period, and the reconciliation is a durable record of the account having been agreed as of that date. | Must | Approved |
| **BKP-13** | Feeds synchronise on a schedule the entity controls, with no person triggering them. | Must | Approved |

**Acceptance, BKP-05.** Replaying an entity's full transaction history against an unchanged
rule set reproduces every assignment identically.

**Acceptance, BKP-07.** Question volume for a stable business trends toward zero over
successive months rather than recurring monthly for the same charge.

### 6.4 Accounts Receivable — `AR`

Billing customers, collecting from them, and knowing who owes what.

| | Requirement | Priority | Status |
|---|---|---|---|
| **AR-01** | Customers exist as records against an entity. | Should | Approved |
| **AR-02** | Invoices are raised against a customer, with line items. | Should | Approved |
| **AR-03** | An invoice is delivered to the customer by email. | Should | Approved |
| **AR-04** | Invoices can be raised on a recurring schedule the entity sets, without a person triggering each one. | Should | Approved |
| **AR-05** | Receipt of payment is recorded. | Should | Approved |
| **AR-06** | A payment is applied to one or more invoices, and an invoice can be settled by more than one payment. Partial payment and overpayment are both representable. | Should | Approved |
| **AR-07** | An uncollectable balance can be written off, and the write-off is visible as a decision rather than as an absence. | Should | Approved |
| **AR-08** | An issued invoice is never edited. A correction is a credit note or a reversal, and both the original and the correction remain visible to the customer and in the books. | Should | Approved |
| **AR-09** | Payment reminders are sent automatically on a schedule the entity sets, and stop when the invoice is settled. | Should | Approved |
| **AR-10** | Outstanding receivables are reportable by age, by customer, and in total. | Should | Approved |
| **AR-11** | Every delivery is recorded — what was sent, to whom, when, and against which record. A failed delivery is visible rather than silent. | Should | Approved |
| **AR-12** | An entity on a cash basis still raises invoices and still tracks receivables. It recognises the revenue on settlement rather than on issue. | Should | Approved |

**Acceptance, AR-09.** A reminder run that is retried, or that overlaps a previous run, does
not send a customer the same reminder twice.

### 6.5 Reporting — `RPT`

Producing statements, and answering questions the books can support.

| | Requirement | Priority | Status |
|---|---|---|---|
| **RPT-01** | Trial balance as of any date. | Must | Approved |
| **RPT-02** | Profit and loss for any period. | Must | Approved |
| **RPT-03** | Balance sheet as of any date. | Must | Approved |
| **RPT-04** | Statement of cash flows for any period. | Should | Approved |
| **RPT-05** | The journal is queryable by account, payee, tag, date, and amount. | Must | Approved |
| **RPT-06** | The standard statements and standard reports — trial balance, profit and loss, balance sheet, cash flows, receivables ageing — are defined, tested capabilities of the system. The same books produce the same statement every time, whoever asks and however they phrase it. They are never composed afresh per request. | Must | Approved |
| **RPT-07** | Every report states the accounting basis it was produced on, on its face. The alternate basis is available on request and is labelled as such. | Must | Approved |
| **RPT-08** | Cash position and runway are reported, and material changes are surfaced without being asked for. | Should | Approved |
| **RPT-09** | Statements are produced in a form a person can hand to a lender, a board, or an accountant. A conversational message is not that form. | Should | Approved |
| **RPT-10** | In addition to the standard reports, a user can ask a question of their own books that nobody anticipated, and get an answer drawn from what is posted. | Should | Approved |
| **RPT-11** | Assemble the figures, schedules, and supporting detail a tax return requires, to a standard where a preparer can answer their own questions without contacting the client. CFOKit does not file. | Should | Proposed — jurisdictions and entity types are an open question |
| **RPT-12** | Track recurring obligations and deadlines by entity type and jurisdiction. | Could | Deferred — scope and placement are an open question |
| **RPT-13** | Any report can be produced as the books stood at an earlier moment, by the date records were made rather than the date events occurred. Where two runs of the same report differ, the difference is exactly the postings recorded between them. | Must | Approved |
| **RPT-14** | Statements are produced on the accrual basis from the obligation and settlement events the ledger records. | Should | Deferred — activates when an entity must report on an accrual basis |
| **RPT-15** | A statement can be marked issued, fixing what was reported, to whom, and when. | Should | Proposed — the mechanism and the form an issued statement takes when shared are undecided |

**Acceptance, RPT-06.** The same books, queried twice by different callers phrasing the
request differently, produce identical figures.

**Acceptance, RPT-11.** A CPA preparing a return works from the output alone and sends the
client no questions.

**Acceptance, RPT-13.** The statement handed to a lender in March is reproducible in December,
unchanged by the corrections posted in between.


### 6.6 Access & Identity — `IAM`

Who may reach an entity, what they may do there, and how that is evidenced.

| | Requirement | Priority | Status |
|---|---|---|---|
| **IAM-01** | An identity's access to an entity is governed by a role. A role carries a defined set of capabilities, and an identity holding no role for an entity can do nothing with it. | Must | Approved |
| **IAM-02** | Roles distinguish at minimum between reading and reporting, recording and posting, and administering the entity. | Must | Approved |
| **IAM-03** | Suspending or deleting an entity, granting or revoking another identity's access, and changing a role assignment are administrative capabilities and are available to no other role. | Must | Approved |
| **IAM-04** | An entity always has at least one identity holding the administrative role. The last administrator cannot be removed or demoted. | Must | Approved |
| **IAM-05** | One identity holds independent roles in each entity it can reach, and holds none in the rest. An advisor working across many entities is the ordinary case, not an exception. | Must | Approved |
| **IAM-06** | Identity is delegated to the identity provider the organisation already uses. CFOKit never issues credentials, stores passwords, or operates a login flow. | Must | Approved |
| **IAM-07** | An agent skill acts on behalf of an identified person. Every action carries both the skill's own principal and that person's, and its effective authority is the intersection of the two. No shared credential, service account, or ambient authority stands in for either. | Must | Approved |
| **IAM-08** | A person authorises a skill to act for them once, and can revoke that authorisation at any time without contacting anyone. | Must | Approved |
| **IAM-09** | Every grant, revocation, and role change is recorded, with who made it and when. | Must | Approved |
| **IAM-10** | The system can produce, for any date in the past, who held which role — in which entity, or at deployment scope — and who granted it. Current state is not sufficient. | Must | Approved |
| **IAM-11** | Revoking an identity's access takes effect immediately, across every interface and every skill acting for that person, and the revocation is evidenced. | Must | Approved |
| **IAM-12** | Where an entity requires it, the system enforces that the identity which drafts a transaction is not the identity which posts it. | Should | Approved |
| **IAM-13** | Roles exist at two scopes, entity and deployment, and the two are independent. Holding an administrative role in an entity confers nothing at deployment scope, and holding a deployment-scoped role confers no role in any entity. | Must | Approved |
| **IAM-14** | Deployment-scoped administrative capabilities are enumerable and individually assignable — configuring a provider that receives customer data, setting the retention schedule, authorising a disposal batch, reviewing security events, and approving privileged access. Each is held by a named identity at all times, and the system can say which. | Must | Approved |

**Acceptance, IAM-05.** An advisor holding a reporting role in one entity and an
administrative role in another can do nothing in a third.

**Acceptance, IAM-07.** A request arriving from a skill is refused wherever the person it acts
for lacks the role, regardless of what the skill asserts about itself.

**Acceptance, IAM-10.** An examiner asks who could post to an entity eight months ago and
receives an answer, not a current roster.

### 6.7 Platform — `PLT`

How the books are reached, how work happens without a person present, and what the system
records about itself.

#### Reaching the books

| | Requirement | Priority | Status |
|---|---|---|---|
| **PLT-01** | The books are readable and writable by agent software the organisation chooses, rather than only by software CFOKit supplies. | Must | Approved |
| **PLT-02** | CFOKit installs into an agent runtime the organisation already operates, and that runtime supplies the inference. CFOKit does not bundle, require, or charge for inference of its own. | Must | Approved |
| **PLT-03** | A documented programmatic interface is available to third parties, carrying stated obligations about how and when it may change. | Should | Approved |
| **PLT-04** | An operator managing several entities can work with each one in a dedicated conversational channel, with the product's reach limited to that channel's entity. | Should | Approved |
| **PLT-05** | Presence in a channel confers no access. A request is permitted only where a linked CFOKit identity independently holds a role for the entity that channel is bound to. The binding is a stored decision and is never inferred from a channel's name, topic, or contents. | Should | Approved |
| **PLT-06** | CFOKit sends email on an entity's behalf, and can do so with no third-party account and no credentials, so that no deployment is degraded for want of one. | Should | Approved |

#### Entity lifecycle

| | Requirement | Priority | Status |
|---|---|---|---|
| **PLT-07** | An entity is in exactly one of three states — active, suspended, or deleted — and every transition between them is recorded like any other change of state. | Must | Approved |
| **PLT-08** | Suspending an entity halts: ingestion from all transaction feeds; every outbound message sent on the entity's behalf, including invoice delivery and payment reminders; every scheduled job, including period close, recurring invoices, and scheduled reporting; proactive alerting; and the configuration of any new integration. Work already in flight at the moment of suspension is cancelled rather than delivered. | Must | Approved |
| **PLT-09** | Suspension halts no reading. Querying, reporting on demand, and export continue to work for every identity whose role permitted them before the suspension. | Must | Approved |
| **PLT-10** | Suspension alters no data, revokes no role, and is fully reversible. On resume, transaction data covering the suspended period is backfilled, so the books carry no gap attributable to the suspension. | Must | Approved |
| **PLT-11** | An explicit request to delete an entity is honoured. Deletion destroys that entity's data, is irreversible, and is confirmed to the requester once complete. Other entities are unaffected, including those the same identities can reach. | Must | Approved |

#### Operation, record, and evidence

| | Requirement | Priority | Status |
|---|---|---|---|
| **PLT-12** | Work that must happen on a schedule rather than in response to a request runs on a timer the entity controls. A missed window is recoverable rather than skipped in silence, and every run is attributable in the same way a person's action is. | Must | Approved |
| **PLT-13** | An entity can retrieve a complete record of every change made to its books — what changed, who changed it, and when. | Must | Approved |
| **PLT-14** | Security-relevant events — authentication, refused authorisation, role change, export, and deletion — are recorded and retrievable independently of the books they concern. | Must | Approved |
| **PLT-15** | For any past period, the system produces the evidence an external examiner requires: who held access, what changed and on whose authority, what the system did unattended, and what was refused. Evidence covers a period of operation rather than a moment. | Must | Approved |
| **PLT-16** | Records are retained by class rather than under a single period, and disposal is never automatic: candidates are listed, legal hold is evaluated at the time of disposal and overrides the schedule, a named person authorises each batch, and a permanent record captures what was destroyed, when, by whom, and under what authority. | Should | Approved |
| **PLT-17** | Retention defaults are set per record class as below. An entity configures its own schedule, and these are what it starts from. | Should | Approved |

| Record class | Default |
|---|---|
| General ledger, postings, financial statements, chart of accounts | Indefinite |
| Supporting documents — attachments, receipts, statements, raw ingested feed payloads | 7 years |
| Fixed asset records | Life of the asset plus 7 years |
| Audit log | Follows the record it describes |
| Destruction log | Permanent |

**Acceptance, PLT-05.** A person invited to a client's channel who holds no role for that
client's entity receives nothing from the books.

**Acceptance, PLT-08.** A suspended entity with a configured transaction feed ingests nothing,
and a recurring invoice falling due during suspension is not sent.

**Acceptance, PLT-10.** An entity suspended for thirty days and then resumed produces a trial
balance identical to one never suspended over the same period.

**Acceptance, PLT-15.** An examination covering a six-month period is satisfied from the
system's own output, with no reconstruction and no manual evidence gathering.

---

## 7. Non-functional requirements — `NFR`

These constrain how well the system does what section 6 says it does. Each is stated once,
globally, with a priority and a target. Section 7.2 records where a module is held to a
stricter target than the global one.

### 7.1 Global

| | Requirement | Category | Priority | Target |
|---|---|---|---|---|
| **NFR-01** | Booking results are demonstrably correct against an independent implementation of double-entry accounting, and every divergence is documented rather than tolerated. | Correctness | Must | Zero undocumented divergences |
| **NFR-02** | No financial record is silently altered or destroyed, by any operation, at any layer. | Integrity | Must | Zero |
| **NFR-03** | A repeated or retried operation produces the same result and creates no duplicate record. | Integrity | Must | Zero duplicates under retry |
| **NFR-04** | No operation reads or writes across an entity boundary except as the acting identity's role in that entity permits. Roles are evaluated by the system regardless of what a request, or a skill acting for a person, asserts about itself. | Security | Must | Zero cross-entity reads or writes |
| **NFR-05** | Amounts, account numbers, payee names, and credentials never appear in logs, telemetry, or error output. | Confidentiality | Must | Zero occurrences |
| **NFR-06** | Every request's intended audience is validated before it is served. | Security | Must | Every request, no exemptions |
| **NFR-07** | A deployment is available to the people who depend on it. | Availability | Should | Target open |
| **NFR-08** | Interactive queries return quickly enough to be used conversationally, over a realistic volume of history. | Performance | Should | Target open |
| **NFR-09** | The system depends on no single infrastructure provider. Relocating a deployment is an infrastructure change, not a change to the product. | Portability | Must | No provider dependency in the shipped artifact |
| **NFR-10** | The complete product runs on one machine, with no cloud account, no signup, and no credentials, holding real books rather than a demonstration. | Deployability | Must | One command |
| **NFR-11** | A third party can add a financial institution, a payment processor, an email provider, or a jurisdiction's rules as an additive contribution against a stable extension point. | Extensibility | Must | No change to the ledger or the modules around it |
| **NFR-12** | Published interfaces carry stated compatibility obligations, and breaking changes are announced rather than discovered. | Interoperability | Should | No unannounced breaking change |
| **NFR-13** | Records are retained according to their class, and disposal is a deliberate, authorised, recorded act. | Compliance | Should | No automatic disposal |
| **NFR-14** | The software is permissively licensed, permanently, and no component imposes an obligation inconsistent with that on anyone who runs, modifies, or forks it. | Licensing | Must | Zero incompatible obligations |
| **NFR-15** | An operator can determine whether a deployment is alive, whether it is ready to serve, and which request caused any given change. | Supportability | Should | All three, unaided |
| **NFR-16** | Every figure the product states is drawn from what is posted. Where the books cannot support an answer, it says so and identifies what is missing, rather than estimating, recalling, or inferring. | Groundedness | Must | Zero stated figures without a posting behind them |
| **NFR-17** | Every capability is present in every deployment. No build withholds one. | Parity | Must | Zero deployment-specific capabilities |
| **NFR-18** | Controls are evidenced rather than asserted. For every control these requirements state, the system produces the record showing it operated throughout a stated period. A control that cannot be evidenced does not count as implemented. | Auditability | Must | Every stated control evidenced |

**Two kinds of guardrail, and only one of them is trustworthy.** NFR-16 constrains what the
product is asked to do, and is therefore a behavioural standard an agent can fail to meet.
NFR-04 constrains what the system permits regardless of what any agent attempts, and holds
even when the agent misbehaves or is deliberately manipulated. Anything that actually matters
belongs in the second category. A guardrail stated only as NFR-16 is a preference, not a
control.

### 7.2 Module-specific targets

Where a module is held to something stricter than the global statement. A module absent from
a row inherits the global target unchanged.

| NFR | Module | Stricter target |
|---|---|---|
| **NFR-01** Correctness | Ledger | Exactness, not accuracy within a tolerance. A tolerance is a defect, not a target. |
| **NFR-02** Integrity | Data Migration | An import applies completely or not at all. A partially applied import is never left in the books. |
| **NFR-03** Idempotency | Bookkeeping | A transaction appearing in two overlapping pulls, or in a re-run of the same pull, is recorded once. Synchronisation may be repeated freely. |
| **NFR-03** Idempotency | Accounts Receivable | A retried or overlapping scheduled run does not send a customer a duplicate invoice or reminder, and does not post a payment twice. |
| **NFR-05** Confidentiality | Platform | Financial detail must not cross into a conversational channel or an outbound message except where the binding and the grant have both been established for that entity. |
| **NFR-16** Groundedness | Bookkeeping | A transaction the rule set cannot resolve is asked about. It is never assigned speculatively, nor parked in a holding account to look resolved. |
| **NFR-08** Performance | Reporting | The only module carrying an interactive latency target. Statement production may take longer than a query, and says so. |

---

## 8. SOC 1 readiness — `SOC1`

Whoever operates CFOKit is a **service organization** under SSAE 18, and the businesses whose
books it keeps are user entities whose financial statements depend on what this system and its
agents produce. That dependency, and nothing else, sets the scope of this section: controls
relevant to a user entity's internal control over financial reporting. Anything touching
security, availability, or privacy without touching ICFR belongs to the SOC 2 track and is not
here.

**The goal is Type 2 readiness, not an audit.** These requirements exist to make a future
examination cheap and to avoid design decisions we would have to reverse. Requirements that
only make sense once an examination is underway are named in section 8.11 and excluded.

**Automated in preference to procedural.** A control a person performs is sampled at every
examination and costs money forever. A control the system enforces is tested once, plus change
management. Where both are possible, these requirements choose the system.

### 8.1 Agent authority and segregation of duties

Conventional segregation of duties assumes two people: one records, another approves. An agent
performing both bookkeeper and controller work collapses that separation, and *the model is
instructed not to* is not a control. This subsection is the substantial work, and the part an
examiner will press on first.

| | Requirement | Priority | Status |
|---|---|---|---|
| **SOC1-01** | Every agent action carries a distinct non-human principal identifying the skill that acted. It is never recorded as the supervising person's own action, and never as a shared service account. | Must | Approved |
| **SOC1-02** | Each skill has an explicit, enumerable set of permitted operations, enforced at the interface and at the data layer. A `bookkeeper` skill performing a `controller` approval is impossible, not discouraged, and no prompt or instruction participates in the enforcement. | Must | Approved |
| **SOC1-03** | An agent's effective authority is the intersection of its skill's permitted operations and the role of the person it acts for. Neither widens the other, and no combination of the two exceeds either. | Must | Approved |
| **SOC1-04** | Each class of action is configured as either autonomously completable by an agent or requiring human authorisation before it posts. The configuration is per entity, versioned, and carries a full change history. | Must | Approved |
| **SOC1-05** | Where a person authorises agent work, the record captures what was presented to them, what the agent proposed and on what stated basis, what alternatives were offered, who decided, when, and what they decided. An approval recording only the decision is not evidence and does not satisfy this. | Must | Approved |
| **SOC1-06** | A posted entry can be explained after the fact without re-running a model. The system persists, against the entry: the model identifier and version, the skill version, the inputs and context supplied, the tool calls made, and the agent's stated basis for the conclusion. | Must | Approved |
| **SOC1-07** | No agent holds any capability to mutate or delete a posted record, under any configuration. Agent-originated errors are corrected through the ordinary correction path and no other. | Must | Approved |
| **SOC1-08** | The default autonomy posture — which action classes an agent may complete unsupervised out of the box — is a product decision with a named owner. | Must | **Proposed** — the defaults are not decided |

**Acceptance, SOC1-02.** A `bookkeeper` skill issued a controller approval operation is
refused at the interface, and the refusal is recorded, regardless of how the request is phrased
or what context precedes it.

**Acceptance, SOC1-05.** An examiner selects an approved agent-posted entry and reconstructs,
from stored data alone, exactly what the approver was shown before deciding.

**Acceptance, SOC1-06.** Two runs of the same skill over the same input that reach different
conclusions are both individually explainable from what was persisted.

> **Cost.** Persisting context, tool calls, and stated reasoning against every agent-touched
> entry is meaningful storage and a real write-path burden, realised at examination time rather
> than in daily use.

### 8.2 Ledger integrity

Mostly carried already: LED-02 balance enforcement, LED-05 the draft-to-posted boundary,
LED-06 correction by reversal, NFR-02 integrity, NFR-03 idempotency.

| | Requirement | Priority | Status |
|---|---|---|---|
| **SOC1-09** | Entries are sequenced gaplessly and verifiably, so that a missing entry is detectable by inspection rather than by inference. | Must | Approved |
| **SOC1-10** | Every write path accepts an idempotency key, and a repeated key returns the original result rather than posting again. This is an interface contract, not an internal convention. | Must | Approved |
| **SOC1-11** | Integrity invariants — the trial balance ties, the sequence is intact, control totals reconcile — are verified on a defined cadence, and each verification is persisted as a durable dated artifact rather than displayed and discarded. | Must | Approved |

> **Constrains the interface contract.** The idempotency key is in the published surface, so it
> binds third-party integrators and cannot be added later without a breaking change.

### 8.3 Completeness and accuracy of ingested data

Covering transaction feeds, uploaded statements, document capture, and any third-party sync.

| | Requirement | Priority | Status |
|---|---|---|---|
| **SOC1-12** | Every ingest boundary records control totals — record count and amount sum — reconciled against what was received and persisted with the batch. | Must | Approved |
| **SOC1-13** | Duplicate, missing, and out-of-order source records are detected and handled explicitly. None is silently accepted, and none is silently dropped. | Must | Approved |
| **SOC1-14** | Every ledger entry carries lineage to the originating document or feed record, retained for as long as the entry is. | Must | Approved |
| **SOC1-15** | A coding decision made by an agent is distinguishable from one made by a person **in the data itself**, not only in an audit record, and remains so for the life of the entry. | Must | Approved |

> **Constrains the data model.** Actor class sits on the entry rather than in a side log.

### 8.4 Period integrity and cutoff

| | Requirement | Priority | Status |
|---|---|---|---|
| **SOC1-16** | The accounting period is a first-class concept in the domain model, not a date range computed at report time. | Must | Approved |
| **SOC1-17** | A closed period rejects postings from every actor over every interface, agents included. There is no privileged path around it. | Must | Approved |
| **SOC1-18** | Reopening a closed period is an administrative action, authorised and recorded, with the reason captured. It is a defined path, never a bypass. | Must | Approved |
| **SOC1-19** | All timestamps are generated by the server from a synchronised source and stored in UTC. No client-supplied time is trusted for any record affecting financial data. | Must | Approved |

### 8.5 Audit trail and evidence retrieval

Carried already: PLT-13 the change record, PLT-14 security events, PLT-15 period evidence,
NFR-18 controls evidenced rather than asserted.

| | Requirement | Priority | Status |
|---|---|---|---|
| **SOC1-20** | Every action affecting financial data records the actor, the action, the time, and the values before and after. | Must | Approved |
| **SOC1-21** | Audit records are written to storage the application cannot subsequently modify or delete, by any code path, including administrative ones. | Must | Approved |
| **SOC1-22** | The complete lineage of a single transaction — source record, agent actions, approvals, resulting entries, and every subsequent correction — is retrievable in one operation. | Must | Approved |

> **Cost.** Examiners work by sampling. If each sampled item needs an engineer writing an ad hoc
> query, that cost recurs at every examination for the life of the product.

### 8.6 Access control and principal propagation

Carried already: IAM-01 through IAM-12.

| | Requirement | Priority | Status |
|---|---|---|---|
| **SOC1-23** | Authorisation is enforced at the data layer. Interface-level concealment of an operation is never the mechanism by which it is denied. | Must | Approved |
| **SOC1-24** | The acting principal propagates unmodified from the entry point through to authorisation and to the audit record. Where one surface calls another on a principal's behalf, the principal's own credential flows through and authorisation is evaluated against it — never against a shared credential with the real actor passed as a parameter. | Must | Approved |
| **SOC1-25** | No access path authorises against a principal different from the one recorded in the audit trail for the same action. | Must | Approved |
| **SOC1-26** | Whether operator personnel can reach customer financial data at all, and if so under what authorisation, is a product decision. Any such access is logged identically to a customer's own and is subject to the same evidence requirements. | Must | **Proposed** — whether privileged access exists is not decided |

> **The failure this prevents.** A surface that authenticates as itself and passes the real
> actor as a parameter still performs authorisation — it just records the intermediary as the
> actor. The books then attribute
> every agent action to a single system principal, which silently voids SOC1-01 through
> SOC1-03 while every individual control appears to pass. **Constrains the interface contract
> between every surface and the service beneath it.**

### 8.7 Exception handling

What happens when processing fails is the second thing an examiner asks. Almost none of this
exists in the requirements today.

| | Requirement | Priority | Status |
|---|---|---|---|
| **SOC1-27** | An item that cannot be processed lands in a durable exception queue. Nothing is silently dropped, and nothing is silently retried into oblivion. | Must | Approved |
| **SOC1-28** | Every exception reaches a recorded disposition — resolved, reprocessed, rejected, or written off — with the actor and the reason. An exception has no terminal state that is merely absence. | Must | Approved |
| **SOC1-29** | Reprocessing an exception is safe against duplication, under the same guarantee as any other write. | Must | Approved |
| **SOC1-30** | Unresolved exceptions age visibly and escalate on a schedule the entity sets. | Should | Approved |
| **SOC1-31** | Which exception classes an agent may resolve autonomously, and which must escalate to a person, is configured through the same mechanism as SOC1-04. | Must | **Proposed** — the split is not decided |

### 8.8 Change management of agent artifacts

Only the part that is a property of the system belongs here. The rest is engineering practice
and is excluded in 8.11.

| | Requirement | Priority | Status |
|---|---|---|---|
| **SOC1-32** | Skills, their prompts, and their tool definitions are versioned artifacts. Every entry an agent produces records the versions in force when it was produced. A prompt edit that changes how transactions are categorised is a change to a financial control and is treated as one. | Must | Approved |
| **SOC1-33** | A change of model identifier or model version is recorded as a change to the control environment, with the date it took effect and the entries produced on either side of it distinguishable. | Must | Approved |

### 8.9 Subservice organizations

| | Requirement | Priority | Status |
|---|---|---|---|
| **SOC1-34** | Where an external provider supplied or processed data, the system records which provider and which version or endpoint, retrievable as part of the lineage in SOC1-22. | Must | Approved |

Anticipated examination treatment.

| Dependency | Effect on the accuracy of customer financial data | Anticipated treatment | Their report |
|---|---|---|---|
| Infrastructure and database hosting | Loss or corruption of the record itself | Carve-out — we do not operate it and cannot attest to it | Available from major providers |
| Inference provider | Categorisation and reconciliation conclusions originate here | **Undecided.** Carve-out is conventional, but the output feeds the books directly, which is unlike ordinary infrastructure | Varies; not assured |
| Transaction feed aggregator | Completeness and accuracy of what enters the books | Carve-out, with SOC1-12 control totals as our compensating control | Generally available |
| Document capture and extraction | Accuracy of amounts read from source documents | Carve-out, with human or agent confirmation as the compensating control | Varies |
| Email delivery | No ICFR effect — delivery is not a financial assertion | Out of SOC 1 scope entirely | n/a |

### 8.10 Complementary User Entity Controls

Obligations on the customer, not requirements on CFOKit. Each one narrows examination scope and
adds customer burden.

| | The user entity must |
|---|---|
| **CUEC-1** | Review and approve agent work above the materiality thresholds it has configured, rather than allowing approvals to accumulate unexamined |
| **CUEC-2** | Administer its own identities and roles, including removing access promptly when a person leaves or an engagement ends |
| **CUEC-3** | Review exception and reconciliation reports on a defined cadence |
| **CUEC-4** | Verify opening balances at onboarding, and confirm that migrated history agrees with the system it came from |
| **CUEC-5** | Set materiality thresholds and autonomy configuration deliberately, rather than accepting defaults without consideration |

### 8.11 Excluded from this section

| Excluded | Why |
|---|---|
| Evidence collection tooling, auditor portals, control narratives, a control matrix | These make sense once an examination is underway. Building them now is designing for a process we have not scoped. |
| Peer approval on code changes, no direct-to-production deployment, ticket-to-commit-to-deploy traceability | Engineering practice and a property of how we work, not of what the system does. Necessary for an examination; belongs in the engineering handbook. |
| Incident response and problem management procedures | Operating process. |
| Personnel screening, onboarding, and security training | Operating process. |
| Anything touching security, availability, or privacy without touching ICFR | The SOC 2 track, handled separately. |

### 8.12 Examination scoping questions

| | Question |
|---|---|
| **ES-1** | What is the target audit period, and therefore the date from which controls must demonstrably be operating? A Type 2 opinion covers a period, so this date is the real deadline, not the engagement date. |
| **ES-2** | Do we pursue a Type 1 opinion first? It is cheaper and faster and attests only to design at a point in time, which may be enough to unblock a specific deal while the Type 2 period accrues. |
| **ES-3** | Which customer segment is actually driving SOC 1 demand? A one-person business will never ask. If the demand is coming from fractional CFOs and CPAs acting for clients, the requirement is theirs rather than the payer's, and that changes what has to be ready and when. |
| **ES-4** | How is an inference provider treated in the examination? It is not ordinary infrastructure — its output reaches the books — and there is little precedent to follow. |

---

## 9. SOC 2 Type II readiness — `SOC2`

Unlike SOC 1, the criteria are fixed. We do not define control objectives; we map controls to
the AICPA Trust Services Criteria, and scope is chosen by selecting categories rather than by
negotiating objectives. A Type II opinion tests **operating effectiveness across a review
period**, which is why every requirement below prefers a control that evidences itself
continuously over one that a person assembles at examination time.

Section 9.10 holds the shared control map.

### 9.1 Category scope

**Status: Proposed.** The whole of this subsection is a business decision not yet made.

| Category | Position | Rationale |
|---|---|---|
| **Security** (CC1–CC9) | In scope | Mandatory. Not elective for any SOC 2 report. |
| **Confidentiality** | In scope | Customer financial data is the core asset, and it is what a buyer is actually worried about. Declining this category invites the question of why. |
| **Availability** | **Undecided** | The criteria test against *our own stated commitments*, so this category costs what we choose to promise. Making no commitment and excluding the category is defensible; making one and excluding it is not. |
| **Processing Integrity** | **Recommended in scope** | Completeness and accuracy of processing is the substance of section 8. If those controls are built, this category is close to free — and it is the one a buyer most associates with an accounting product. |
| **Privacy** | **Out unless triggered** | Business contact data alone does not trigger it. Payroll, contractor 1099 data, and employee expense reimbursement each pull personal information in. Each is out of scope today; adding any one of them makes this category unavoidable. |

### 9.2 Untrusted content and agent manipulation

CFOKit's agents read content the customer did not author and we do not control: uploaded
receipts and invoices, feed transaction memos, vendor email, extracted document text. An agent
that reads such content and then acts on the ledger is executing against untrusted input. Text
embedded in a PDF invoice instructing an agent to reclassify an account, change a payment
destination, or suppress an exception is an attack, and input validation does not address it.

No established audit practice covers this. An examiner assessing CC6 and CC7 will have no
template, so we should be able to describe our controls before we are asked.

| | Requirement | Priority | Status |
|---|---|---|---|
| **SOC2-01** | Every content source is classified as trusted or untrusted in the data model, and the classification travels with the content for as long as it is retained. It is a property of the record, not a runtime judgement. | Must | Approved |
| **SOC2-02** | Untrusted content never enters an agent's instruction context undemarcated. The boundary between instruction and data is explicit and machine-checkable rather than a matter of formatting convention. | Must | Approved |
| **SOC2-03** | An agent turn that reads untrusted content operates with a reduced capability set, enforced at the interface. Reading an untrusted document and writing to the ledger are not simultaneously available within one turn. A prompt instructing the model to disregard embedded instructions is not a control and does not satisfy this. | Must | Approved |
| **SOC2-04** | Attempts to inject instructions through ingested content are detected and recorded as security events, retrievable alongside other security events. They are never silently handled. | Must | Approved |
| **SOC2-05** | The maximum damage a fully successful injection can cause is stated, bounded by the materiality thresholds and human authorisation gates of SOC1-04, and demonstrable by test. The bound is a property of the capability model, never of model behaviour. | Must | Approved |
| **SOC2-06** | Changing a vendor's payment destination, and creating or altering a payee's banking details, require human authorisation in every case, at any amount, regardless of the agent's stated confidence. These are the highest-value target in the system and carry no autonomous path. | Must | Approved |
| **SOC2-07** | The detection approach for injection attempts is a stated, versioned artifact under SOC1-32, so that a change to it is a change to a security control. | Must | **Proposed** — the approach is not decided |

**Acceptance, SOC2-03.** An agent given a document containing an instruction to post an entry
cannot post one within that turn, irrespective of how the instruction is phrased or whether the
model attempts to comply.

**Acceptance, SOC2-05.** The stated blast radius is exercised by a test that assumes the model
is fully compromised and cooperative with the attacker.

> SOC1-04's thresholds and SOC2-03's capability split carry nearly all of the bound in SOC2-05.
> Weakening either for usability moves it.

### 9.3 Inference providers and data flow

| | Requirement | Priority | Status |
|---|---|---|---|
| **SOC2-08** | Every third party that receives customer financial data during agent operation — inference, document extraction, embedding or vector storage — is enumerated in a registry the system maintains, not in a document maintained beside it. | Must | Approved |
| **SOC2-09** | A provider that does not contractually offer zero data retention and no training on submitted data cannot be configured to receive customer data. This is a constraint the system enforces on configuration, not a procurement preference. | Must | Approved |
| **SOC2-10** | What is sent to a provider is the minimum the task requires. Whether raw financial records leave the system, or redacted or tokenised representations, is recorded per provider and per operation. | Must | Approved |
| **SOC2-11** | Where data residency is committed to, inference and extraction routing respects it, and a request that cannot be routed compliantly fails rather than falling back. | Should | **Proposed** — whether we commit to residency at all is undecided |
| **SOC2-12** | Changing an inference provider, or a model version, is a change to the control environment under SOC1-33, and additionally requires the security review of SOC2-28. | Must | Approved |

> **Constrains the provider abstraction.** Provider selection is validated configuration rather
> than a deployment detail. Model swaps are frequent, so enforcement sits in the configuration
> path rather than in a review cycle.

### 9.4 Confidentiality and data handling

| | Requirement | Priority | Status |
|---|---|---|---|
| **SOC2-13** | Customer data is encrypted in transit and at rest. Key custody, rotation, and the ability to revoke access to encrypted data are stated properties of a deployment rather than assumptions about its infrastructure. | Must | Approved |
| **SOC2-14** | Entity isolation is enforced at the data layer, so that a cross-entity read is impossible rather than merely unlikely. No interface, query path, or administrative operation may bypass it. | Must | Approved |
| **SOC2-15** | Isolation extends to everything derived. An agent operating for one entity cannot reach another entity's data through any tool, cache, conversation memory, embedding, index, or model context. | Must | Approved |
| **SOC2-16** | Data is classified — financial records, credentials and secrets, personal information, and derived artifacts including embeddings, extracted document text, and agent traces — and handling obligations follow the classification. | Must | Approved |
| **SOC2-17** | Deleting an entity destroys its derived artifacts as well as its records: embeddings, caches, extracted text, agent traces, and any representation held by a provider under SOC2-09. Deletion that leaves derived data behind does not satisfy PLT-11. | Must | Approved |

> SOC2-15 is the harder of the pair: the isolation boundary has to hold across artifacts that
> did not exist in conventional software. An embedding index and a conversation memory are each
> a cross-tenant leak waiting to be built.

### 9.5 Access control and identity

Carried by IAM-01 through IAM-12 and SOC1-23 through SOC1-26. Additional SOC 2 obligations only:

| | Requirement | Priority | Status |
|---|---|---|---|
| **SOC2-18** | Multi-factor authentication is required for every human identity. CFOKit does not implement it — IAM-06 delegates identity — so the requirement is that the system demands the issuer assert it, and refuses a session where it is absent. | Must | Approved |
| **SOC2-19** | Sessions have a bounded lifetime and can be revoked centrally, taking effect everywhere including for skills acting under IAM-07. | Must | Approved |
| **SOC2-20** | Programmatic credentials and tokens have a defined lifecycle — issuance, scope, expiry, rotation, and revocation — and a token's scope is never broader than the role of the identity it was issued to. | Must | Approved |
| **SOC2-21** | The access review of IAM-10 produces its evidence automatically, on a defined cadence, as a persisted artifact. A review that requires someone to assemble screenshots is sampled at every examination and costs money forever. | Must | Approved |
| **SOC2-22** | Where privileged operator access to customer data exists under SOC1-26, it is time-bounded, individually authorised, logged identically to customer access, and visible to the affected customer. | Must | **Proposed** — dependent on the SOC1-26 decision |

### 9.6 System operations and monitoring — CC7

| | Requirement | Priority | Status |
|---|---|---|---|
| **SOC2-23** | Security events under PLT-14 are retained for the full review period plus lookback, and alerting is defined per event class rather than left to inspection. | Must | Approved |
| **SOC2-24** | Dependencies are monitored for known vulnerabilities on a defined cadence, and remediation targets are stated by severity. Supply-chain provenance of dependencies is part of this, not separate from it. | Must | Approved |
| **SOC2-25** | Incidents are detected, classified by severity, escalated, and — where customer data or the accuracy of customer books is affected — notified to the customer within a stated period. | Must | Approved |
| **SOC2-26** | Agent behaviour is monitored as a security signal, not only an operational one: volume anomalies, unusual account or payee targets, repeated authorisation failures, and clustering of exceptions are detected and alertable. | Must | Approved |
| **SOC2-27** | The line between an agent error and a reportable security incident is defined in advance. An agent posting an incorrect but non-malicious entry is a processing exception under SOC1-27; an agent acting outside its capability set, or acting on injected instruction, is a security incident. | Must | Approved |

> Agents will post wrong entries; that is a known property, not an incident. Deciding which is
> which after the first bad week produces a decision shaped by that week.

### 9.7 Change management — CC8

Carried by SOC1-32 and SOC1-33, which cover skills, prompts, tool definitions, and model version
pins. Stated once there rather than twice.

| | Requirement | Priority | Status |
|---|---|---|---|
| **SOC2-28** | A change affecting authentication, authorisation, isolation, or data handling requires security review before it takes effect, and the review is recorded against the change. | Must | Approved |
| **SOC2-29** | Infrastructure and configuration changes are governed identically to application code. A change to a deployment's configuration is a change. | Must | Approved |

### 9.8 Availability

Applies only if the Availability category is taken in 9.1. Kept proportional deliberately: the
criteria test against our own commitments, so a modest commitment carries modest controls.

| | Requirement | Priority | Status |
|---|---|---|---|
| **SOC2-30** | Backups are restored on a defined cadence and the restore is verified against the source. A configured backup that has never been restored is not a control. | Must | Approved |
| **SOC2-31** | Recovery time and recovery point objectives are stated as numbers a deployment can be measured against. | Should | **Proposed** — the numbers are not set |
| **SOC2-32** | Behaviour under degradation is defined, including what happens when an inference or extraction provider is unavailable partway through a workflow. Partial completion never leaves the books in a state no one can account for. | Must | Approved |
| **SOC2-33** | An interrupted agent workflow resumes without duplicate posting, under the idempotency guarantee of SOC1-10 and NFR-03. | Must | Approved |

### 9.9 Governance and control environment — CC1–CC5

Satisfied outside this document. The policy set, security training, background checks, risk
assessment process, and vendor due diligence are organisational deliverables, not properties of
the system. The one part that *is* a system property — that security ownership is named and
demonstrable rather than asserted — is IAM-13 and IAM-14.

### 9.10 Shared controls — SOC 1 and SOC 2

Maintained deliberately so the overlap does not drift. Where a row lists both, the requirement is
stated once, in the SOC 1 section, and referenced from SOC 2.

| Control | Stated in | Referenced from | SOC 2 addition |
|---|---|---|---|
| Audit trail with before and after values | SOC1-20 | CC7 | Retention across the review period — SOC2-23 |
| Immutable audit storage | SOC1-21 | CC7 | None |
| Transaction lineage retrieval | SOC1-22 | CC7 | None |
| Data-layer authorisation | SOC1-23 | CC6 | None |
| Principal propagation | SOC1-24 | CC6 | Session revocation reaches skills — SOC2-19 |
| Privileged operator access | SOC1-26 | CC6 | Time bounds, customer visibility — SOC2-22 |
| Exception queue and disposition | SOC1-27, SOC1-28 | CC7 | Error-versus-incident line — SOC2-27 |
| Skills, prompts, tool definitions versioned | SOC1-32 | CC8 | Security review — SOC2-28 |
| Model version as control-environment change | SOC1-33 | CC8, CC9 | Provider review — SOC2-12 |
| Idempotent write paths | SOC1-10 | Processing Integrity | Workflow resumability — SOC2-33 |
| Role-based access and review | IAM-01…IAM-12 | CC6 | MFA, sessions, tokens, automatic review evidence — SOC2-18…SOC2-21 |
| Deployment-scoped roles and named security ownership | IAM-13, IAM-14 | CC1, CC6 | None; written for CC1 |
| Controls evidenced rather than asserted | NFR-18 | CC4 | None; it was written for both |

### 9.11 Examination scoping questions

| | Question |
|---|---|
| **ES-5** | Which Trust Services categories do we commit to? Security is not elective; the other four are, and each one taken is scope we carry at every examination for the life of the report. |
| **ES-6** | What availability commitment are we prepared to be measured against? The category costs what we promise, so this is a pricing and positioning decision before it is an engineering one. |
| **ES-7** | Does the roadmap trigger Privacy? Payroll, contractor 1099 handling, and employee expense reimbursement each do. None is in scope today, and the first one that arrives makes the category unavoidable. |
| **ES-8** | Are the controls in 9.2 and 9.3 sufficient? No established audit practice covers agent manipulation through untrusted content. We are describing controls an examiner has no template for, which means we may be over-building, under-building, or building the wrong shape — and the framework will not tell us which. |

---

## 10. Open issues

Business decisions this document is waiting on. Each blocks a `Proposed` or `Deferred`
requirement from being specified. None of these is a design question; a design question never
blocks a business requirement.

| | Question | Blocks | Needed by |
|---|---|---|---|
| **OI-1** | What migration fidelity do we promise? An opening trial balance and a full transaction history are materially different products with different trust implications. | MIG-02 | Before any company with existing books can adopt |
| **OI-2** | Which jurisdictions and entity types does tax support cover? | RPT-11 | Before the first tax season we support |
| **OI-3** | What availability and interactive performance do we commit to? | NFR-07, NFR-08 | Before a deployment carries anyone's real books |
| **OI-4** | Is compliance tracking in scope, and is it reporting at all? It sits under Reporting today for want of a better home, and it is neither a statement nor a query. | RPT-12 | Before it is specified |
| **OI-5** | Deleting a whole entity is settled. What is not: erasing one named person's data from an entity that survives — a payee, a customer contact — where the history is append-only and the surrounding books must still balance. | PLT-16, NFR-13 | Before the first erasure request arrives |
| **OI-6** | What is the role taxonomy? This document requires roles and names the three capability classes they must distinguish, but not the roles themselves. Internal staff, a fractional CFO, and a CPA have genuinely different needs, and fixing the set before those are understood would be designing rather than specifying. | IAM-02 | Before access control is specified |
| **OI-7** | Can one agent reviewing another agent's work constitute segregation of duties? If yes, SOC 1 readiness is reachable for a one-person business. If no, autonomy for that customer is capped by the availability of a second human, which most of segment 2 does not have. | SOC1-08 | Before autonomy defaults are set |
| **OI-8** | What is the default autonomy posture for a business with no second person available to review? Refusing to act is safe and useless; acting unsupervised is useful and unattestable. CUEC-5 shifts the decision to a customer who may not be equipped to make it, which argues for conservative defaults. | SOC1-08, SOC1-31 | Before first release |
| **OI-9** | Do operator personnel have any path to customer financial data — break-glass or otherwise? Answering *no* is the strongest position and the hardest to support operationally. | SOC1-26 | Before anyone else's books are held |
| **OI-10** | Do we accept any autonomous ledger write derived from untrusted content at all? Refusing outright is the strongest security position and removes most of the product's value for receipt and invoice capture. Accepting it makes SOC2-03 and SOC2-05 the only things standing between an attacker and the books. | SOC2-03, SOC2-05 | Before document capture ships |
| **OI-11** | How is a statement marked issued, and what form does it take when shared? An issued statement is a record of what was told to whom, which is not the same artifact as a report run on demand. | RPT-15 | Before any statement is handed to a lender or a board |
| **OI-12** | Does CFOKit handle sales tax, and if so how much of it does it own rather than delegate? The accounting policy currently treats it as unsupported rather than partially supported, and no requirement covers it — but an owner-operator meets it on day one. | Nothing — no requirement exists yet | Before segment 2 is a supported audience |

---

## 11. Glossary

Terms carrying a specific meaning in this document.

| Term | Meaning |
|---|---|
| **Basis** | Whether an entity recognises revenue and expense when the obligation arises or when cash moves. A property of the entity, not a report option. |
| **Close** | Marking a period as reviewed. A workflow milestone, distinct from the permanence a posting confers. |
| **Commodity** | A unit an amount is denominated in. Money in a given currency today; potentially other holdings later. |
| **Draft** | A candidate transaction, freely editable, not yet part of the books. |
| **Entity** | A set of books for one legal or reporting unit. The isolation boundary throughout. |
| **Account** | A line in a chart of accounts. Always this sense, throughout. |
| **Administrator** | An identity holding the role that permits entity lifecycle changes and changes to other identities' access. |
| **Grant** | The act of assigning an identity a role in an entity. |
| **Identity** | A person, authenticated by the organisation's identity provider. Skills act as identities; they are not identities themselves. |
| **Role** | A named set of capabilities. An identity's access to an entity is exactly the role it holds there, and nothing else. |
| **Obligation** | A commitment to receive or pay, recorded when it arises, separately from its settlement. |
| **Posting** | Committing a transaction to the books. Irreversible; the point after which corrections are new entries. |
| **Reversal** | A new entry that undoes a posted one, leaving both visible. The only form a correction takes. |
| **Rule** | Stored, operator-approved criteria that assign an incoming transaction to an account deterministically. |
| **Settlement** | The movement of cash against an obligation. |
| **The CFO seat** | Whoever is accountable for the company's finances — a fractional CFO where one is engaged, and otherwise the founder or owner-operator. Never vacant. |

---

## 12. Traceability

Every requirement traces to at least one business objective. An objective with no requirement
is unserved; a requirement serving no objective does not belong here.

| Objective | Requirements |
|---|---|
| **OBJ-1** Displace the incumbent stack | BKP-01, BKP-02, BKP-03, BKP-05, BKP-11, BKP-12, AR-01–AR-12, RPT-01–RPT-06, MIG-01, MIG-02 |
| **OBJ-2** Current and closed without manual recording | BKP-01, BKP-05, BKP-07, BKP-13, LED-08, PLT-12, RPT-08 |
| **OBJ-3** Every number traceable | BKP-08, LED-06, LED-07, PLT-13, PLT-17, IAM-09, NFR-02, RPT-13, SOC1-14, SOC1-15, SOC1-22 |
| **OBJ-4** Output professionals accept | RPT-03, RPT-06, RPT-07, RPT-09, RPT-11, RPT-13, RPT-14, RPT-15, LED-10, LED-11, NFR-01 |
| **OBJ-5** Own and leave with the data | MIG-06, MIG-07, MIG-08, PLT-09, PLT-11, NFR-17 |
| **OBJ-6** No vendor relationship required | BKP-04, PLT-02, PLT-06, IAM-06, NFR-09, NFR-10, NFR-14, NFR-17 |
| **OBJ-7** Additive outside contribution | BKP-02, PLT-01, PLT-02, PLT-03, PLT-06, RPT-12, NFR-11, NFR-12 |
| **OBJ-8** Serves a small business across its range | LED-09, LED-10, LED-11, LED-12, LED-13, RPT-14, IAM-05, PLT-04, PLT-05, RPT-11 |
| **OBJ-9** Examinable by an external auditor | IAM-09, IAM-10, IAM-11, IAM-12, IAM-13, IAM-14, PLT-13, PLT-14, PLT-15, PLT-16, NFR-04, NFR-05, NFR-18, SOC1-01–SOC1-34, SOC2-01–SOC2-33 |
