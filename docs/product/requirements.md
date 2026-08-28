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
| **Priority** | `Must` — a release lacking it is incomplete. `Should` — required for a stated buyer to adopt. `Could` — genuinely wanted; waits on a stated trigger. |
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
| **OBJ-10** | Produce numbers that are right | Booking is exact and demonstrably correct against an independent implementation; no posted record is ever silently altered; a repeated or retried operation never books twice |
| **OBJ-11** | Let only the people an entity has authorised reach its books | No cross-entity access ever occurs; every access resolves to a person and the role they held at the time |

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
| SOX compliance | Sarbanes-Oxley applies to public companies and their auditors. CFOKit does not serve public companies and is not built to. Out of scope until it deliberately is. Note that individual SOX provisions on record destruction reach private companies; those are retention obligations and are handled under PLT-19 and PLT-20, not as SOX scope. |
| Statutory localisation | Jurisdiction-specific tax regimes and their return formats, statutory charts of accounts, and e-invoicing mandates. The incumbents ship separate regional editions rather than configure one product, because these differences are too deep to configure. Out of scope until a jurisdiction is chosen deliberately. |
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
| **A-5** | Inference cost is carried by the runtime the user already operates, not by CFOKit. |
| **A-6** | An independent auditor can be engaged, and the operating history an attestation requires accumulates only from the date the practice begins. |
| **A-7** | Companies migrating in are most often leaving a small-business accounting package whose export fidelity is outside our control. |
| **A-8** | A customer will open an invoice from an unauthenticated link, and neither they nor their supplier regards that as a risk. The incumbents work this way and the market has accepted it. |

---

## 6. Functional requirements

Organised by module.

### 6.1 Ledger — `LED`

The double-entry record itself, and the entity settings that govern how it is kept.

| | Requirement | Priority | Status |
|---|---|---|---|
| **LED-01** | An entity defines its own chart of accounts, organised hierarchically, and can add to it over the life of the books. | Must | Approved |
| **LED-02** | Every account has a type — asset, liability, equity, income, or expense — fixed when the account is created. The type determines which statement the account appears on and the sign convention applied to it. | Must | Approved |
| **LED-03** | Every transaction balances. The system refuses to record one that does not, in any commodity it holds. | Must | Approved |
| **LED-04** | Monetary amounts are recorded exactly. No representation error, no accumulated drift, no tolerance. A balance is the exact sum of its postings. | Must | Approved |
| **LED-05** | Where an amount must be divided and does not divide evenly, the parts sum exactly to the original and the distribution is deterministic. The same division always produces the same parts. | Must | Approved |
| **LED-06** | Recorded amounts are never rounded. Each commodity carries a display scale — the number of decimal places at which its amounts are shown — and rounding occurs only where a figure is presented. | Must | Approved |
| **LED-07** | A transaction is freely editable while it is a draft, and becomes permanent when it is posted. Posting is the point of no return. | Must | Approved |
| **LED-08** | A posted transaction is never altered or removed. Corrections are new entries that reverse the original, leaving both visible. | Must | Approved |
| **LED-09** | Every transaction carries both the date the event occurred and the date it was recorded. Recording a transaction into an earlier period that is still open is permitted and is never silent. | Must | Approved |
| **LED-10** | An entity's books can be opened with balances carried in from before CFOKit held them. Opening balances are ordinary postings, balance to zero against a single identified equity account, and are identifiable as opening balances. | Must | Approved |
| **LED-11** | A period can be marked closed, signifying it has been reviewed. Once closed, no posting enters the period except through a recorded reopening, and anything so recorded is identifiable as such. | Must | Approved |
| **LED-12** | At fiscal year end, income and expense balances are closed to retained earnings so the new year opens with them at zero. The closing entries are ordinary postings and are identifiable as such. | Must | Approved |
| **LED-13** | One deployment holds the books of many entities, each with its own chart of accounts, basis, and fiscal year. | Must | Approved |
| **LED-14** | Each entity declares its accounting basis and its fiscal year end when it is created; neither has an undeclared state. These are properties of the entity, not options on a report. A change of basis is recorded with the date it takes effect, and never rewrites history. | Must | Approved |
| **LED-15** | An entity declares its functional currency when it is created, and every recorded amount carries the currency it is denominated in. An amount in any other currency is refused. | Must | Approved |
| **LED-16** | A transaction in a currency other than the entity's functional currency is converted at the rate in force on its date, and the difference between the rate at obligation and the rate at settlement is recorded as foreign exchange gain or loss. | Could | Deferred — activates when an entity first transacts in another currency. Not built before then |
| **LED-17** | An obligation and its settlement are recorded as two related events rather than one. An invoice raised in one period and paid in another is recoverable as either, depending on the basis in force. | Must | Approved |
| **LED-18** | The ledger holds positions in things other than money — inventory, or investments held in a brokerage account. | Could | Deferred — activates when an entity acquires inventory or holds investments |
| **LED-19** | Where an entity holds fungible units acquired at different costs and disposes of some, disposals consume the earliest lots first, exactly rather than approximately. Where a disposal is ambiguous the system refuses rather than selecting a plausible lot. | Could | Deferred — activates with LED-18 |

**Acceptance, LED-04.** Divide $10.00 three ways: the three resulting postings sum to exactly
$10.00, with no residual and no drift, and repeating the operation a million times introduces
none.

**Acceptance, LED-08.** After a correction, both the original entry and its reversal are
retrievable, and no field of the original has changed.

**Acceptance, LED-12.** The trial balance on the first day of a fiscal year shows every income
and expense account at zero, and retained earnings changed by exactly the prior year's result.

**Acceptance, LED-15.** An amount presented in a currency other than the entity's functional
currency is refused, with a reason, rather than accepted and converted.

### 6.2 Data Migration — `MIG`

Getting an existing company's books in, and any company's books out. Two exports serve
different purposes and are not interchangeable: one hands the books to another accounting
system, the other moves an entity between CFOKit deployments intact.

#### Import

| | Requirement | Priority | Status |
|---|---|---|---|
| **MIG-01** | Import an existing chart of accounts from the system a company already runs. | Should | Approved |
| **MIG-02** | Import transaction history and opening balances from that system. | Should | Proposed — the fidelity promised is an open question |
| **MIG-03** | Import the customers and the categorisation rules the company already has, so a migrated entity does not arrive with an empty receivables ledger and no rules. | Should | Approved |
| **MIG-04** | Every imported record is identifiable as imported and names the system it came from. | Should | Approved |
| **MIG-05** | An import is validated before anything is posted. The operator sees what will be created, and what will not, and can abandon it. | Should | Approved |
| **MIG-06** | An import declares the accounting basis of the data it carries, and is refused where that conflicts with the entity's declared basis. | Should | Approved |
| **MIG-07** | An import carrying amounts in a currency other than the entity's functional currency is refused, on the same terms as any other foreign amount. | Should | Approved |
| **MIG-08** | An import produces a reconciliation the operator can check against the source system — balances by account, and totals by period — so that agreement is demonstrated rather than assumed. | Should | Approved |

#### Export

| | Requirement | Priority | Status |
|---|---|---|---|
| **MIG-09** | **Interchange export.** The books in a form another accounting system can read: chart of accounts, transactions, and balances. | Must | Approved |
| **MIG-10** | **Complete export.** Everything the entity holds — the interchange content, plus supporting documents, attachments, raw ingested payloads, rule definitions and the attribution linking them to postings, approvals, agent records, and the audit trail. | Must | Approved |
| **MIG-11** | Both exports are available at any time, in any entity state short of deletion, without asking anyone and without a support request. | Must | Approved |
| **MIG-12** | A complete export taken from one CFOKit deployment and imported into another reproduces the books, their history, and their attribution. Moving between a self-hosted and a hosted deployment is this operation in either direction. | Must | Approved |

**Acceptance, MIG-08.** The operator compares two figures per account and either agrees the
import or rejects it, without exporting anything from the source system a second time.

**Acceptance, MIG-09.** The export is a single self-contained archive, and a trial balance
derived from the archive alone agrees, line for line, with the trial balance CFOKit produces
for the same date. What a receiving system then computes is outside our control and is not
part of this requirement.

**Acceptance, MIG-11.** A suspended entity can still be exported completely, unaided.

**Acceptance, MIG-12.** The receiving deployment produces identical statements for every
period, and an audit trail that resolves every posting to the same rule, source record, and
actor as the sending one.

### 6.3 Bookkeeping — `BKP`

Getting transactions in, deciding where they belong, and agreeing that the books match reality.

| | Requirement | Priority | Status |
|---|---|---|---|
| **BKP-01** | Transactions arrive from bank and card accounts without manual entry. | Must | Approved |
| **BKP-02** | Transactions arrive from payment processors through the same path as bank and card feeds. | Should | Approved |
| **BKP-03** | An operator can supply transactions by uploading a statement file, for any account no feed reaches. This path needs no third-party account and no credentials, so no deployment depends on a feed provider to get transactions in. | Must | Approved |
| **BKP-04** | An operator can enter a transaction directly — an accrual, a depreciation charge, an adjustment, or anything no feed will ever carry. | Must | Approved |
| **BKP-05** | An incoming transaction can be split across more than one account, with the parts summing exactly to the whole. | Must | Approved |
| **BKP-06** | Assignment of an incoming transaction to an account is governed by stored rules applied deterministically. The same transaction against the same rule set produces the same account, always. | Must | Approved |
| **BKP-07** | A rule matches on more than the payee. One payee legitimately maps to several accounts depending on other properties of the transaction. | Must | Approved |
| **BKP-08** | Where more than one rule matches a transaction, which rule applies is decided by a stated, inspectable order rather than by whichever is found first. Determinism depends on this. | Must | Approved |
| **BKP-09** | Approval is sought for rules, not for individual transactions. An approved pattern is never asked about again. | Must | Approved |
| **BKP-10** | Every assignment records which rule produced it, and that attribution survives for the life of the record. | Must | Approved |
| **BKP-11** | Changing a rule affects future assignments only. Existing postings are untouched. | Must | Approved |
| **BKP-12** | Where the rule set cannot resolve a transaction, the operator is asked. Nothing is guessed, and nothing is quietly parked in a holding account. | Must | Approved |
| **BKP-13** | An incoming transaction can be matched to a record the books already hold — an expected payment, or a transaction entered by hand ahead of the feed — rather than creating a duplicate. | Must | Approved |
| **BKP-14** | A movement between two of the entity's own accounts is recognised as one transfer rather than as unrelated income and expense, whether it arrives as two feed transactions or one. | Must | Approved |
| **BKP-15** | An account can be reconciled against a statement balance for a period, and the reconciliation is a durable record of the account having been agreed as of that date. A reconciliation later found to be wrong is superseded by a new one rather than edited, and both remain visible. | Must | Approved |
| **BKP-16** | Feeds synchronise on a schedule the entity controls, with no person triggering them. | Must | Approved |
| **BKP-17** | A document — a receipt, an invoice, a statement — can be attached to a transaction, an account, or a period, and is retained and exported with what it is attached to. | Could | Deferred — activates when an entity needs supporting documents held with its books. Not built before then |
| **BKP-18** | A document supplies the content of a draft transaction, which is then assigned and posted like any other. | Could | Deferred — activates with BKP-17 |

**Acceptance, BKP-06.** Replaying an entity's full transaction history against an unchanged
rule set reproduces every assignment identically.

**Acceptance, BKP-08.** Two rules that both match a transaction resolve the same way on every
run, and the operator can see which rule won and why before approving either.

**Acceptance, BKP-14.** A transfer between two feed-connected accounts of the same entity
leaves total income and total expense unchanged.

### 6.4 Accounts Receivable — `AR`

Billing customers, collecting from them, and knowing who owes what.

| | Requirement | Priority | Status |
|---|---|---|---|
| **AR-01** | Customers exist as records against an entity. | Must | Approved |
| **AR-02** | Invoices are raised against a customer, with line items. | Must | Approved |
| **AR-03** | Every invoice line names the income account it credits, so an issued invoice is a posting rather than only a document. | Must | Approved |
| **AR-04** | An invoice is freely editable while it is a draft and becomes permanent when it is issued. Issuing is the point of no return, as posting is for a transaction. | Must | Approved |
| **AR-05** | Issued invoices carry numbers from a gapless sequence the entity controls. A cancelled invoice keeps its number and is visible as cancelled; a number is never reused or silently skipped. | Must | Approved |
| **AR-06** | An invoice carries payment terms and a due date derived from them. | Must | Approved |
| **AR-07** | An issued invoice is available as a shareable artifact — a document and a stable link — that an operator can deliver by any means, including by hand into a messaging application CFOKit knows nothing about. | Must | Approved |
| **AR-08** | Access to an invoice through its link is unauthenticated, deliberately: requiring a customer to hold an identity before they can see a bill is an obstacle to being paid. The link is unguessable, reaches that one invoice and nothing else about the entity, and can be revoked. It is the only unauthenticated read path in the system. | Must | Approved |
| **AR-09** | Where a delivery channel is integrated, CFOKit delivers the invoice on the entity's behalf. Email is the first such channel. | Should | Approved |
| **AR-10** | Invoices can be raised on a recurring schedule the entity sets, without a person triggering each one. | Should | Approved |
| **AR-11** | Receipt of payment is recorded. | Must | Approved |
| **AR-12** | A payment is applied to one or more invoices, and an invoice can be settled by more than one payment. Partial payment and overpayment are both representable. | Must | Approved |
| **AR-13** | A deposit arriving in a transaction feed can be applied to the invoice it settles, without re-entering it by hand. | Must | Approved |
| **AR-14** | An issued invoice is never edited. A correction is a credit note or a reversal, and both the original and the correction remain visible to the customer and in the books. | Must | Approved |
| **AR-15** | Outstanding receivables are reportable by age, by customer, and in total. | Must | Approved |
| **AR-16** | An entity on a cash basis still raises invoices and still tracks receivables. It recognises the revenue on settlement rather than on issue. | Must | Approved |
| **AR-17** | Payment reminders are sent automatically on a schedule the entity sets, and stop when the invoice is settled. A schedule can distinguish an invoice never opened from one opened and unpaid. | Should | Approved |
| **AR-18** | An uncollectable balance can be written off, and the write-off is visible as a decision rather than as an absence. | Should | Approved |
| **AR-19** | The system records what it actually knows about an invoice reaching its customer: that CFOKit sent it and when, where a channel is integrated; that a delivery failed, where that is detectable; and that the invoice was opened through its link, whoever delivered it. An invoice CFOKit did not send is never reported as sent. | Should | Approved |

**Acceptance, AR-05.** The invoice series for a period has no gaps, and every number in it
resolves to an invoice that is either live or cancelled.

**Acceptance, AR-17.** A reminder run that is retried, or that overlaps a previous run, does
not send a customer the same reminder twice.

**Acceptance, AR-19.** An invoice CFOKit did not send never reports a send date, and one
opened through a link pasted into a third-party application does report that it was opened.

### 6.5 Reporting — `RPT`

Producing statements, and answering questions the books can support.

| | Requirement | Priority | Status |
|---|---|---|---|
| **RPT-01** | Trial balance as of any date. | Must | Approved |
| **RPT-02** | Profit and loss for any period. | Must | Approved |
| **RPT-03** | Balance sheet as of any date. | Must | Approved |
| **RPT-04** | Statement of cash flows for any period. | Should | Approved |
| **RPT-05** | Account detail for any account and period — every transaction against it, in order, with a running balance. | Must | Approved |
| **RPT-06** | The journal is queryable by account, payee, tag, date, and amount. | Must | Approved |
| **RPT-07** | Any period report can be produced alongside a comparative period — the preceding one, or the same period a year earlier — with the variance between them. | Must | Approved |
| **RPT-08** | Any figure on a statement resolves to the postings that produced it, and from a posting to its source transaction and the rule that assigned it. | Must | Approved |
| **RPT-09** | The standard statements and standard reports — trial balance, profit and loss, balance sheet, cash flows, account detail, receivables ageing — are defined, tested capabilities of the system. The same books produce the same statement every time, whoever asks and however they phrase it. They are never composed afresh per request. | Must | Approved |
| **RPT-10** | Every report states the accounting basis it was produced on, on its face. | Must | Approved |
| **RPT-11** | Any report can be produced as the books stood at an earlier moment, by the date records were made rather than the date events occurred. Where two runs of the same report differ, the difference is exactly the postings recorded between them. | Must | Approved |
| **RPT-12** | A presented figure is rounded half-up to its commodity's display scale. A total is computed from the unrounded values and then rounded, never by summing figures already rounded. | Must | Approved |
| **RPT-13** | A report is available as a document and as a stable link, either of which can be given to a lender, a board, or an accountant by any means. | Must | Approved |
| **RPT-14** | Every report is printable, laid out so a printed copy carries the same figures, headings, and basis statement as the screen. | Should | Approved |
| **RPT-15** | Cash position and runway are reported, and material changes are surfaced without being asked for. | Should | Approved |
| **RPT-16** | In addition to the standard reports, a user can ask a question of their own books that nobody anticipated, and get an answer drawn from what is posted. | Should | Approved |
| **RPT-17** | A statement can be marked issued, fixing what was reported, to whom, and when. | Should | Proposed — the mechanism and the form an issued statement takes when shared are undecided |
| **RPT-18** | Assemble the figures, schedules, and supporting detail a tax return requires, to a standard where a preparer can answer their own questions without contacting the client. CFOKit does not file. | Should | Proposed — jurisdictions and entity types are an open question |
| **RPT-19** | Statements are produced on the accrual basis from the obligation and settlement events the ledger records, and an entity on either basis can be shown the alternate view, labelled as such. | Should | Deferred — activates when an entity must report on an accrual basis. Not built before then |
| **RPT-20** | Budgets are recorded per account and period, and any period report can be produced against budget with the variance. | Could | Deferred — activates when an entity budgets |
| **RPT-21** | Statements are produced for a group of entities together, eliminating balances between them. | Could | Deferred — activates when one owner's entities must report as a group |
| **RPT-22** | Track recurring obligations and deadlines by entity type and jurisdiction. | Could | Deferred — scope and placement are an open question |

**Acceptance, RPT-08.** From a profit and loss line, a reader reaches the postings behind it,
and from any one of them the source transaction and the rule that assigned it, without
composing a query.

**Acceptance, RPT-09.** The same books, queried twice by different callers phrasing the
request differently, produce identical figures.

**Acceptance, RPT-11.** The statement given to a lender in March is reproducible in December,
unchanged by the corrections posted in between.

**Acceptance, RPT-12.** A column of displayed figures summed by hand may differ from the
printed total by less than one unit of display scale. The printed total is the correct one.

**Acceptance, RPT-18.** A CPA preparing a return works from the output alone and sends the
client no questions.

### 6.6 Access & Identity — `IAM`

Who may reach an entity, what they may do there, and how that is evidenced.

| | Requirement | Priority | Status |
|---|---|---|---|
| **IAM-01** | An identity's access to an entity is governed by a role. A role carries a defined set of capabilities, and an identity holding no role for an entity can do nothing with it. | Must | Approved |
| **IAM-02** | Roles distinguish at minimum between reading and reporting, recording and posting, and administering the entity. | Must | Approved |
| **IAM-03** | Suspending or deleting an entity, granting or revoking another identity's access, and changing a role assignment are administrative capabilities and are available to no other role. | Must | Approved |
| **IAM-04** | An entity always has at least one identity holding the administrative role. The last administrator cannot be removed or demoted. | Must | Approved |
| **IAM-05** | Creating an entity assigns its first administrator in the same act. An entity never exists without one, and no separate step is required to make it usable. | Must | Approved |
| **IAM-06** | A deployment is brought into service by establishing its first deployment-scoped administrator, from whom every other role in it descends. This is the only privileged act that does not require a prior role. | Must | Approved |
| **IAM-07** | An administrator can grant a role to a person who has no identity yet. The grant is recorded as an invitation, confers nothing until they authenticate, and binds to their identity when they first do. | Must | Approved |
| **IAM-08** | One identity holds independent roles in each entity it can reach, and holds none in the rest. An advisor working across many entities is the ordinary case, not an exception. | Must | Approved |
| **IAM-09** | A role can be granted for a stated period, after which it lapses without anyone acting. An advisor's access ending with the engagement does not depend on someone remembering. | Should | Approved |
| **IAM-10** | Identity is delegated to the identity provider the organisation already uses. CFOKit never issues credentials, stores passwords, or operates a login flow. | Must | Approved |
| **IAM-11** | An agent skill acts on behalf of an identified person. Every action carries both the skill's own principal and that person's, and its effective authority is the intersection of the two. No shared credential, service account, or ambient authority stands in for either. | Must | Approved |
| **IAM-12** | A person authorises a skill to act for them separately for each entity, and can revoke any one of those authorisations without affecting the others. Authorising a skill in one entity never reaches another. | Must | Approved |
| **IAM-13** | Every grant, invitation, revocation, lapse, and role change is recorded, with who made it and when. | Must | Approved |
| **IAM-14** | The system can produce, for any date in the past, who held which role — in which entity, or at deployment scope — and who granted it. Current state is not sufficient. | Must | Approved |
| **IAM-15** | Revoking or reducing an identity's access takes effect immediately, across every interface and every skill acting for that person, and is evidenced. | Must | Approved |
| **IAM-16** | Where an entity has more than one identity able to post and has elected to segregate duties, the system enforces that the **person** who drafts a transaction is not the person who posts it. Two skills acting for the same person do not satisfy this: a skill's separate principal is a capability constraint, not a segregation of duties. | Should | Approved |
| **IAM-17** | Where only one identity in an entity can post, segregation is impossible. The system determines this from the entity's own roster rather than asking, and neither offers the choice nor mentions it. What stands in segregation's place is what ordinary use already produces — reconciliations performed, exceptions dispositioned, agent-posted entries reviewed — and the system evidences those as the controls in force. The question arises only when a second identity able to post is added. | Should | Approved |
| **IAM-18** | Roles exist at two scopes, entity and deployment, and the two are independent. Holding an administrative role in an entity confers nothing at deployment scope, and holding a deployment-scoped role confers no role in any entity. | Must | Approved |
| **IAM-19** | Deployment-scoped administrative capabilities are enumerable and individually assignable — configuring a provider that receives customer data, setting the retention schedule, authorising a disposal batch, reviewing security events, and approving privileged access. Each is held by a named identity at all times, and the system can say which. | Must | Approved |

**Acceptance, IAM-07.** A person invited to an entity and never authenticated holds nothing,
and appears in IAM-14's history as invited rather than as holding a role.

**Acceptance, IAM-08.** An advisor holding a reporting role in one entity and an
administrative role in another can do nothing in a third.

**Acceptance, IAM-11.** A request arriving from a skill is refused wherever the person it acts
for lacks the role, regardless of what the skill asserts about itself.

**Acceptance, IAM-14.** An examiner asks who could post to an entity eight months ago and
receives an answer, not a current roster.

**Acceptance, IAM-16.** In an entity that has elected segregation, one person invoking a
drafting skill and then an approving skill is refused. In an entity that has not, the same
sequence proceeds.

**Acceptance, IAM-17.** A sole operator is never asked about approval separation, and never
told they lack a second approver. An examination of their books is still answerable, from the
reconciliation, exception, and review records ordinary use produced.

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
| **PLT-07** | CFOKit reaches the people who operate an entity when something needs them — a transaction no rule resolves, a delivery that failed, a material change in position, a scheduled run that did not complete. Where they are reached is theirs to set, and any class of it can be turned off. | Must | Approved |

#### Entity settings and lifecycle

| | Requirement | Priority | Status |
|---|---|---|---|
| **PLT-08** | An entity declares its time zone when it is created. Period boundaries, fiscal year ends, transaction dates, and due dates are determined in it, whatever time zone the deployment or the operator happens to be in. | Must | Approved |
| **PLT-09** | An entity is in exactly one of three states — active, suspended, or deleted — and every transition between them is recorded like any other change of state. | Must | Approved |
| **PLT-10** | Suspending an entity halts: ingestion from all transaction feeds; every outbound message sent on the entity's behalf, including invoice delivery and payment reminders; every scheduled job, including period close, recurring invoices, and scheduled reporting; proactive alerting; and the configuration of any new integration. Work already in flight at the moment of suspension is cancelled rather than delivered. | Must | Approved |
| **PLT-11** | Suspension halts no reading. Querying, reporting on demand, and export continue to work for every identity whose role permitted them before the suspension. | Must | Approved |
| **PLT-12** | Suspension alters no data, revokes no role, and is fully reversible. On resume, transaction data covering the suspended period is backfilled, so the books carry no gap attributable to the suspension. Outbound work the suspension cancelled is not replayed: nobody receives a suspension's worth of invoices or reminders at once. | Must | Approved |
| **PLT-13** | An explicit request to delete an entity is honoured. Deletion destroys that entity's data, is irreversible, and is confirmed to the requester once complete. Other entities are unaffected, including those the same identities can reach. | Must | Approved |

#### Operation, record, and evidence

| | Requirement | Priority | Status |
|---|---|---|---|
| **PLT-14** | Work that must happen on a schedule rather than in response to a request runs on a timer the entity controls. A missed window is recoverable rather than skipped in silence, and every run is attributable in the same way a person's action is. | Must | Approved |
| **PLT-15** | Every change to configuration that affects what the system does — feeds, schedules, reminder cadences, thresholds, display scale, retention — is recorded with what changed, who changed it, and when, and the prior value remains retrievable. | Must | Approved |
| **PLT-16** | An entity can retrieve a complete record of every change made to its books — what changed, who changed it, and when. | Must | Approved |
| **PLT-17** | Security-relevant events — authentication, refused authorisation, role change, export, and deletion — are recorded and retrievable independently of the books they concern. | Must | Approved |
| **PLT-18** | For any past period, the system produces the evidence an external examiner requires: who held access, what changed and on whose authority, what the system did unattended, and what was refused. Evidence covers a period of operation rather than a moment. | Must | Approved |
| **PLT-19** | Records are retained by class rather than under a single period, and disposal is never automatic: candidates are listed, legal hold is evaluated at the time of disposal and overrides the schedule, a named person authorises each batch, and a permanent record captures what was destroyed, when, by whom, and under what authority. | Should | Approved |
| **PLT-20** | The retention schedule is set per record class at deployment scope, applies to every entity the deployment holds, and starts from the defaults below. | Should | Approved |
| **PLT-21** | A deployment can be moved to a later version of CFOKit in place, keeping its books, its history, and its configuration. An upgrade that cannot complete leaves the deployment on the version it started from rather than partway between two. | Must | Approved |

| Record class | Default |
|---|---|
| General ledger, postings, financial statements, chart of accounts | Indefinite |
| Supporting documents — attachments, receipts, statements, raw ingested feed payloads | 7 years |
| Fixed asset records | Life of the asset plus 7 years |
| Audit log | Follows the record it describes |
| Agent records — model and skill versions, context supplied, tool calls, stated basis | Follows the entry they explain |
| Destruction log | Permanent |

**Acceptance, PLT-05.** A person invited to a client's channel who holds no role for that
client's entity receives nothing from the books.

**Acceptance, PLT-08.** An entity whose time zone is twelve hours from the deployment's
reports the same transaction in the same period regardless of where it is asked from.

**Acceptance, PLT-10.** A suspended entity with a configured transaction feed ingests nothing,
and a recurring invoice falling due during suspension is not sent.

**Acceptance, PLT-12.** An entity suspended for thirty days and then resumed produces a trial
balance identical to one never suspended over the same period, and sends nothing on resume
that the suspension cancelled.

**Acceptance, PLT-18.** An examination covering a six-month period is satisfied from the
system's own output, with no reconstruction and no manual evidence gathering.

**Acceptance, PLT-21.** A deployment two versions behind is brought current, and every
statement it produced before the upgrade is reproducible after it.

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
| **NFR-06** | Every request is validated as intended for this deployment and this entity before it is served. A request meant for somewhere else is refused rather than interpreted. | Security | Must | Every request, no exemptions |
| **NFR-07** | Committed financial records survive the loss of any single machine or storage device. A deployment can be restored to a known point, and the restore is exercised rather than assumed. | Durability | Must | No committed record lost to a single failure |
| **NFR-08** | A deployment is available to the people who depend on it. | Availability | Should | Target open |
| **NFR-09** | Interactive queries return quickly enough to be used conversationally, against a stated volume of history that a target customer would actually accumulate. Both the latency and the volume are numbers, or neither means anything. | Performance | Should | Targets open |
| **NFR-10** | The system depends on no single infrastructure provider. Relocating a deployment is an infrastructure change, not a change to the product. | Portability | Must | No provider dependency in the shipped artifact |
| **NFR-11** | The complete product runs on one machine, with no cloud account, no signup, and no credentials, holding real books rather than a demonstration. | Deployability | Must | One command |
| **NFR-12** | A third party can add a financial institution, a payment processor, an email provider, or a jurisdiction's rules as an additive contribution against a stable extension point. | Extensibility | Must | No change to the ledger or the modules around it |
| **NFR-13** | Published interfaces carry stated compatibility obligations, and breaking changes are announced rather than discovered. | Interoperability | Should | No unannounced breaking change |
| **NFR-14** | The software is permissively licensed, permanently, and no component imposes an obligation inconsistent with that on anyone who runs, modifies, or forks it. | Licensing | Must | Zero incompatible obligations |
| **NFR-15** | An operator can determine whether a deployment is alive, whether it is ready to serve, and which request caused any given change. | Supportability | Should | All three, unaided |
| **NFR-16** | Every figure the product states is drawn from what is posted. Where the books cannot support an answer, it says so and identifies what is missing, rather than estimating, recalling, or inferring. | Groundedness | Must | Zero stated figures without a posting behind them |
| **NFR-17** | Every capability is present in every deployment. No build withholds one. | Parity | Must | Zero deployment-specific capabilities |
| **NFR-18** | Controls are evidenced rather than asserted. For every control these requirements state, the system produces the record showing it operated throughout a stated period. A control that cannot be evidenced does not count as implemented. | Auditability | Must | Every stated control evidenced |
| **NFR-19** | The product is operable by someone who runs a business rather than someone who keeps books. Where an accounting term is unavoidable it is explained in place, and no ordinary task requires knowing what a contra account is. | Usability | Should | A non-accountant completes onboarding, categorisation, and a month-end close unaided |
| **NFR-20** | Dates, numbers, and currency are presented in the conventions of the entity's locale, and the interface is available in languages other than English. | Localisation | Could | Deferred — activates when an entity operates outside the initial locale |

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
| **NFR-05** Confidentiality | Platform | Financial detail must not cross into a conversational channel or an outbound message except where the binding and the role have both been established for that entity. |
| **NFR-09** Performance | Reporting | The only module carrying an interactive latency target. Statement production may take longer than a query, and says so. |
| **NFR-16** Groundedness | Bookkeeping | A transaction the rule set cannot resolve is asked about. It is never assigned speculatively, nor parked in a holding account to look resolved. |

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

Mostly carried already: LED-03 balance enforcement, LED-07 the draft-to-posted boundary,
LED-08 correction by reversal, NFR-02 integrity, NFR-03 idempotency.

| | Requirement | Priority | Status |
|---|---|---|---|
| **SOC1-08** | Entries are sequenced gaplessly and verifiably, so that a missing entry is detectable by inspection rather than by inference. | Must | Approved |
| **SOC1-09** | Every write path accepts an idempotency key, and a repeated key returns the original result rather than posting again. This is an interface contract, not an internal convention. | Must | Approved |
| **SOC1-10** | Integrity invariants — the trial balance ties, the sequence is intact, control totals reconcile — are verified on a defined cadence, and each verification is persisted as a durable dated artifact rather than displayed and discarded. | Must | Approved |

> **Constrains the interface contract.** The idempotency key is in the published surface, so it
> binds third-party integrators and cannot be added later without a breaking change.

### 8.3 Completeness and accuracy of ingested data

Covering transaction feeds, uploaded statements, document capture, and any third-party sync.

| | Requirement | Priority | Status |
|---|---|---|---|
| **SOC1-11** | Every ingest boundary records control totals — record count and amount sum — reconciled against what was received and persisted with the batch. | Must | Approved |
| **SOC1-12** | Duplicate, missing, and out-of-order source records are detected and handled explicitly. None is silently accepted, and none is silently dropped. | Must | Approved |
| **SOC1-13** | A source that delivers nothing is distinguished from one that delivers an empty result. A feed silently skipping a period is detected against the coverage it was expected to supply, not inferred from the absence of a batch. | Must | Approved |
| **SOC1-14** | Every ledger entry carries lineage to the originating document or feed record, retained for as long as the entry is. | Must | Approved |
| **SOC1-15** | A coding decision made by an agent is distinguishable from one made by a person **in the data itself**, not only in an audit record, and resolves to which skill acted and which person it acted for. It remains so for the life of the entry. | Must | Approved |

> **Constrains the data model.** Actor class sits on the entry rather than in a side log.

### 8.4 Period integrity and cutoff

Carried already: LED-11 closes a period and admits nothing afterwards except through a recorded
reopening; PLT-08 fixes the time zone period boundaries are determined in.

| | Requirement | Priority | Status |
|---|---|---|---|
| **SOC1-16** | The accounting period is a first-class record, not a date range computed when a report is asked for. | Must | Approved |
| **SOC1-17** | A closed period admits nothing from any actor over any interface, agents included, and reopening it requires an administrative role, is recorded, and captures the reason. There is no privileged path around either. | Must | Approved |
| **SOC1-18** | All timestamps are generated by the server from a synchronised source and stored in UTC. No client-supplied time is trusted for any record affecting financial data. | Must | Approved |
| **SOC1-19** | Which period a transaction falls in is determined in the entity's time zone, never in the deployment's and never in UTC. A UTC timestamp records when something happened; it never decides which period it happened in. | Must | Approved |
| **SOC1-20** | Where a correction posted after a statement was issued changes that statement's figures, the issued statement is marked superseded, and both what was reported and what is now true remain retrievable. | Must | Approved |

**Acceptance, SOC1-19.** A transaction recorded at 23:30 local on the last day of a period
falls in that period, whatever the deployment's clock reads.

**Acceptance, SOC1-20.** An examiner given a statement issued in April and a reopening in June
can see, without reconstruction, that the April figures were superseded and by what.

### 8.5 Audit trail and evidence retrieval

Carried already: PLT-16 the change record, PLT-17 security events, PLT-18 period evidence,
NFR-18 controls evidenced rather than asserted.

| | Requirement | Priority | Status |
|---|---|---|---|
| **SOC1-21** | Every action affecting financial data records the actor, the action, and the time. Where the action changed something that can change — a draft, a rule, a threshold, a configuration setting — the prior and resulting values are both recorded. A posted entry has no prior value, and is never given one. | Must | Approved |
| **SOC1-22** | Audit records are written to storage the application cannot subsequently modify or delete, by any code path, including administrative ones. | Must | Approved |
| **SOC1-23** | The complete lineage of a single transaction — source record, agent actions, approvals, resulting entries, and every subsequent correction — is retrievable in one operation. | Must | Approved |

> **Cost.** Examiners work by sampling. If each sampled item needs an engineer writing an ad hoc
> query, that cost recurs at every examination for the life of the product.

### 8.6 Access control and principal propagation

Carried already: IAM-01 through IAM-19.

| | Requirement | Priority | Status |
|---|---|---|---|
| **SOC1-24** | Authorisation is enforced at the data layer. Interface-level concealment of an operation is never the mechanism by which it is denied. | Must | Approved |
| **SOC1-25** | The acting principal propagates unmodified from the entry point through to authorisation and to the audit record. Where one surface calls another on a principal's behalf, the principal's own credential flows through and authorisation is evaluated against it — never against a shared credential with the real actor passed as a parameter. | Must | Approved |
| **SOC1-26** | No access path authorises against a principal different from the one recorded in the audit trail for the same action. | Must | Approved |
| **SOC1-27** | Whether operator personnel can reach customer financial data at all, and if so under what authorisation, is a product decision. Any such access is logged identically to a customer's own and is subject to the same evidence requirements. | Must | **Proposed** — whether privileged access exists is not decided |

> **The failure this prevents.** A surface that authenticates as itself and passes the real
> actor as a parameter still performs authorisation — it just records the intermediary as the
> actor. The books then attribute
> every agent action to a single system principal, which silently voids SOC1-01 through
> SOC1-03 while every individual control appears to pass. **Constrains the interface contract
> between every surface and the service beneath it.**

### 8.7 Exception handling

What happens when processing fails is the second thing an examiner asks.

| | Requirement | Priority | Status |
|---|---|---|---|
| **SOC1-28** | An item that cannot be processed lands in a durable exception queue. Nothing is silently dropped, and nothing is silently retried into oblivion. | Must | Approved |
| **SOC1-29** | Every exception reaches a recorded disposition — resolved, reprocessed, rejected, or written off — with the actor and the reason. An exception has no terminal state that is merely absence. | Must | Approved |
| **SOC1-30** | Reprocessing an exception is safe against duplication, under the same guarantee as any other write. | Must | Approved |
| **SOC1-31** | Unresolved exceptions age visibly and escalate on a schedule the entity sets. | Should | Approved |
| **SOC1-32** | Exceptions are reportable for any period — what arrived, what was dispositioned and how, and what remains open — as a durable artifact rather than a transient view. This is the report a reviewer reviews and an examiner samples. | Must | Approved |
| **SOC1-33** | Which exception classes an agent may resolve autonomously, and which must escalate to a person, is configured through the same mechanism as SOC1-04. | Must | **Proposed** — the split is not decided |

### 8.8 Change management of agent artifacts

Only the part that is a property of the system belongs here. The rest is engineering practice
and is excluded in 8.11.

| | Requirement | Priority | Status |
|---|---|---|---|
| **SOC1-34** | Skills, their prompts, and their tool definitions are versioned artifacts. Every entry an agent produces records the versions in force when it was produced. A prompt edit that changes how transactions are categorised is a change to a financial control and is treated as one. | Must | Approved |
| **SOC1-35** | A change of model identifier or model version is recorded as a change to the control environment, with the date it took effect and the entries produced on either side of it distinguishable. | Must | Approved |

### 8.9 Subservice organizations

| | Requirement | Priority | Status |
|---|---|---|---|
| **SOC1-36** | Where an external provider supplied or processed data, the system records which provider and which version or endpoint, retrievable as part of the lineage in SOC1-23. | Must | Approved |

Anticipated examination treatment.

| Dependency | Effect on the accuracy of customer financial data | Anticipated treatment | Their report |
|---|---|---|---|
| Infrastructure and database hosting | Loss or corruption of the record itself | Carve-out — we do not operate it and cannot attest to it | Available from major providers |
| Inference provider | Categorisation and reconciliation conclusions originate here | **Undecided.** Carve-out is conventional, but the output feeds the books directly, which is unlike ordinary infrastructure | Varies; not assured |
| Transaction feed aggregator | Completeness and accuracy of what enters the books | Carve-out, with SOC1-11 control totals as our compensating control | Generally available |
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
| **CUEC-5** | Own the materiality thresholds and autonomy configuration in force, whether it set them or accepted the defaults, and be able to say why they are appropriate to the business |

### 8.11 Excluded from this section

| Excluded | Why |
|---|---|
| Evidence collection tooling, auditor portals, control narratives, a control matrix | These make sense once an examination is underway. Building them now is designing for a process we have not scoped. |
| Peer approval on code changes, no direct-to-production deployment, ticket-to-commit-to-deploy traceability | Engineering practice and a property of how we work, not of what the system does. Necessary for an examination, and satisfied outside this document. |
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
| **SOC2-05** | On detection, the turn stops and the content is quarantined rather than processed further. The item becomes an exception under SOC1-28 for a person to disposition. Detection that only records is telemetry, not a control. | Must | Approved |
| **SOC2-06** | The maximum damage a fully successful injection can cause is stated, bounded by the materiality thresholds and human authorisation gates of SOC1-04, and demonstrable by test. The bound is a property of the capability model, never of model behaviour. | Must | Approved |
| **SOC2-07** | Changing where a customer is told to send money, or the identity a customer is told they are paying, requires human authorisation in every case, at any amount, regardless of the agent's stated confidence. This covers the payment details an invoice carries and the customer record behind it. CFOKit moves no money, so this — not a payment instruction — is where revenue can be redirected, and it carries no autonomous path. | Must | Approved |
| **SOC2-08** | The detection approach for injection attempts is a stated, versioned artifact under SOC1-34, so that a change to it is a change to a security control. | Must | **Proposed** — the approach is not decided |

**Acceptance, SOC2-03.** An agent given a document containing an instruction to post an entry
cannot post one within that turn, irrespective of how the instruction is phrased or whether the
model attempts to comply.

**Acceptance, SOC2-06.** The stated blast radius is exercised by a test that assumes the model
is fully compromised and cooperative with the attacker.

> SOC1-04's thresholds and SOC2-03's capability split carry nearly all of the bound in SOC2-06.
> Weakening either for usability moves it.

### 9.3 Inference providers and data flow

| | Requirement | Priority | Status |
|---|---|---|---|
| **SOC2-09** | Every third party that receives customer financial data during agent operation — inference, document extraction, embedding or vector storage — is enumerated in a registry the system maintains, not in a document maintained beside it. | Must | Approved |
| **SOC2-10** | A provider that does not contractually offer zero data retention and no training on submitted data cannot be configured to receive customer data. This is a constraint the system enforces on configuration, not a procurement preference. | Must | Approved |
| **SOC2-11** | What is sent to a provider is the minimum the task requires. Whether raw financial records leave the system, or redacted or tokenised representations, is recorded per provider and per operation. | Must | Approved |
| **SOC2-12** | Where data residency is committed to, inference and extraction routing respects it, and a request that cannot be routed compliantly fails rather than falling back. | Should | **Proposed** — whether we commit to residency at all is undecided |
| **SOC2-13** | Changing an inference provider, or a model version, is a change to the control environment under SOC1-35, and additionally requires the security review of SOC2-31. | Must | Approved |

> **Constrains the provider abstraction.** Provider selection is validated configuration rather
> than a deployment detail. Model swaps are frequent, so enforcement sits in the configuration
> path rather than in a review cycle.

### 9.4 Confidentiality and data handling

| | Requirement | Priority | Status |
|---|---|---|---|
| **SOC2-14** | Customer data is encrypted in transit and at rest. Key custody, rotation, and the ability to revoke access to encrypted data are stated properties of a deployment rather than assumptions about its infrastructure. | Must | Approved |
| **SOC2-15** | Entity isolation is enforced at the data layer, so that a cross-entity read is impossible rather than merely unlikely. No interface, query path, or administrative operation may bypass it. The single exception is the invoice link of AR-08, which is scoped to one invoice and carries nothing else about the entity. | Must | Approved |
| **SOC2-16** | Isolation extends to everything derived. An agent operating for one entity cannot reach another entity's data through any tool, cache, conversation memory, embedding, index, or model context. | Must | Approved |
| **SOC2-17** | Data is classified — financial records, credentials and secrets, personal information, and derived artifacts including embeddings, extracted document text, and agent traces — and handling obligations follow the classification. | Must | Approved |
| **SOC2-18** | Deleting an entity destroys its derived artifacts as well as its records: embeddings, caches, extracted text, agent traces, and any representation held by a provider under SOC2-10. Deletion that leaves derived data behind does not satisfy PLT-13. | Must | Approved |

> SOC2-16 is the harder of the pair: the isolation boundary has to hold across artifacts that
> did not exist in conventional software. An embedding index and a conversation memory are each
> a cross-tenant leak waiting to be built.

### 9.5 Access control and identity

Carried by IAM-01 through IAM-19 and SOC1-24 through SOC1-27. Additional SOC 2 obligations only:

| | Requirement | Priority | Status |
|---|---|---|---|
| **SOC2-19** | Multi-factor authentication is required for every human identity. CFOKit does not implement it — IAM-10 delegates identity — so the requirement is that the system demands the issuer assert it, and refuses a session where it is absent. | Must | Approved |
| **SOC2-20** | Sessions have a bounded lifetime and can be revoked centrally, taking effect everywhere including for skills acting under IAM-11. | Must | Approved |
| **SOC2-21** | Programmatic credentials and tokens have a defined lifecycle — issuance, scope, expiry, rotation, and revocation — and a token's scope is never broader than the role of the identity it was issued to. | Must | Approved |
| **SOC2-22** | The access review of IAM-14 produces its evidence automatically, on a defined cadence, as a persisted artifact. A review that requires someone to assemble screenshots is sampled at every examination and costs money forever. | Must | Approved |
| **SOC2-23** | Where privileged operator access to customer data exists under SOC1-27, it is time-bounded, individually authorised, logged identically to customer access, and visible to the affected customer. | Must | **Proposed** — dependent on the SOC1-27 decision |

### 9.6 System operations and monitoring — CC7

| | Requirement | Priority | Status |
|---|---|---|---|
| **SOC2-24** | Security events under PLT-17 are retained for the full review period plus lookback, and alerting is defined per event class rather than left to inspection. | Must | Approved |
| **SOC2-25** | Dependencies are monitored for known vulnerabilities on a defined cadence, and remediation targets are stated by severity. Supply-chain provenance of dependencies is part of this, not separate from it. | Must | Approved |
| **SOC2-26** | Incidents are detected, classified by severity, escalated, and — where customer data or the accuracy of customer books is affected — notified to the customer within a committed period. | Must | **Proposed** — the period is not set |
| **SOC2-27** | Agent behaviour is monitored as a security signal, not only an operational one: volume anomalies, unusual account or payee targets, repeated authorisation failures, and clustering of exceptions are detected and alertable. | Must | Approved |
| **SOC2-28** | The line between an agent error and a reportable security incident is defined in advance. An agent posting an incorrect but non-malicious entry is a processing exception under SOC1-28; an agent acting outside its capability set, or acting on injected instruction, is a security incident. | Must | Approved |
| **SOC2-29** | Behaviour under degradation is defined, including what happens when an inference or extraction provider is unavailable partway through a workflow. Partial completion never leaves the books in a state no one can account for. | Must | Approved |
| **SOC2-30** | An interrupted agent workflow resumes without duplicate posting, under the idempotency guarantee of SOC1-09 and NFR-03. | Must | Approved |

> Agents will post wrong entries; that is a known property, not an incident. Deciding which is
> which after the first bad week produces a decision shaped by that week.

### 9.7 Change management — CC8

Carried by SOC1-34 and SOC1-35, which cover skills, prompts, tool definitions, and model version
pins. Stated once there rather than twice.

| | Requirement | Priority | Status |
|---|---|---|---|
| **SOC2-31** | A change affecting authentication, authorisation, isolation, or data handling requires security review before it takes effect, and the review is recorded against the change. | Must | Approved |
| **SOC2-32** | Infrastructure and configuration changes are governed identically to application code. A change to a deployment's configuration is a change. | Must | Approved |

### 9.8 Availability

Applies only if the Availability category is taken in 9.1. Durability, restore verification,
degradation behaviour, and resumability are unconditional and sit in NFR-07, SOC2-29, and
SOC2-30. What is left here is what the category alone adds.

| | Requirement | Priority | Status |
|---|---|---|---|
| **SOC2-33** | Recovery time and recovery point objectives are stated as numbers a deployment can be measured against. | Should | **Proposed** — the numbers are not set |

### 9.9 Governance and control environment — CC1–CC5

Satisfied outside this document. The policy set, security training, background checks, risk
assessment process, and vendor due diligence are organisational deliverables, not properties of
the system. The one part that *is* a system property — that security ownership is named and
demonstrable rather than asserted — is IAM-18 and IAM-19.

### 9.10 Shared controls — SOC 1 and SOC 2

Maintained deliberately so the overlap does not drift. Where a row lists both, the requirement is
stated once, in the SOC 1 section, and referenced from SOC 2.

| Control | Stated in | Referenced from | SOC 2 addition |
|---|---|---|---|
| Audit trail, with prior and resulting values where a record can change | SOC1-21 | CC7 | Retention across the review period — SOC2-24 |
| Immutable audit storage | SOC1-22 | CC7 | None |
| Transaction lineage retrieval | SOC1-23 | CC7 | None |
| Data-layer authorisation | SOC1-24 | CC6 | None |
| Principal propagation | SOC1-25 | CC6 | Session revocation reaches skills — SOC2-20 |
| Privileged operator access | SOC1-27 | CC6 | Time bounds, customer visibility — SOC2-23 |
| Exception queue and disposition | SOC1-28, SOC1-29 | CC7 | Error-versus-incident line — SOC2-28 |
| Skills, prompts, tool definitions versioned | SOC1-34 | CC8 | Security review — SOC2-31 |
| Model version as control-environment change | SOC1-35 | CC8, CC9 | Provider review — SOC2-13 |
| Idempotent write paths | SOC1-09 | Processing Integrity | Workflow resumability — SOC2-30 |
| Role-based access and review | IAM-01…IAM-15 | CC6 | MFA, sessions, tokens, automatic review evidence — SOC2-19…SOC2-22 |
| Deployment-scoped roles and named security ownership | IAM-18, IAM-19 | CC1, CC6 | None; written for CC1 |
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

Business decisions this document is waiting on. Most block a `Proposed` or `Deferred`
requirement from being specified; OI-12 blocks a requirement that does not exist yet. None is a
design question; a design question never blocks a business requirement.

| | Question | Blocks | Needed by |
|---|---|---|---|
| **OI-1** | What migration fidelity do we promise? An opening trial balance and a full transaction history are materially different products with different trust implications. | MIG-02 | Before any company with existing books can adopt |
| **OI-2** | Which jurisdictions and entity types does tax support cover? | RPT-18 | Before the first tax season we support |
| **OI-3** | What availability, interactive latency, and history volume do we commit to? A latency target without a volume is untestable. | NFR-08, NFR-09 | Before a deployment carries anyone's real books |
| **OI-4** | Is compliance tracking in scope, and is it reporting at all? It sits under Reporting today for want of a better home, and it is neither a statement nor a query. | RPT-22 | Before it is specified |
| **OI-5** | Deleting a whole entity is settled. What is not: erasing one named person's data from an entity that survives — a payee, a customer contact — where the history is append-only and the surrounding books must still balance. | PLT-19 | Before the first erasure request arrives |
| **OI-6** | What is the role taxonomy? This document requires roles and names the three capability classes they must distinguish, but not the roles themselves. Internal staff, a fractional CFO, and a CPA have genuinely different needs, and fixing the set before those are understood would be designing rather than specifying. | IAM-02 | Before access control is specified |
| **OI-7** | Which compensating controls must an entity have in place before CFOKit will act unsupervised? Segregation is unavailable to a one-person business, so this is what stands in its place, and it has to be specific enough to test. Defaults should be conservative, since a customer inherits whichever ones ship. | SOC1-33, IAM-17 | Before first release |
| **OI-8** | Do operator personnel have any path to customer financial data — break-glass or otherwise? Answering *no* is the strongest position and the hardest to support operationally. | SOC1-27 | Before anyone else's books are held |
| **OI-9** | Do we accept any autonomous ledger write derived from untrusted content at all? Refusing outright is the strongest security position and removes most of the product's value for receipt and invoice capture. Accepting it makes SOC2-03 and SOC2-06 the only things standing between an attacker and the books. | SOC2-03, SOC2-06 | Before document capture ships |
| **OI-10** | Within what period do we commit to notifying a customer of an incident affecting their data or the accuracy of their books? | SOC2-26 | Before the hosted service carries anyone else's books |
| **OI-11** | How is a statement marked issued, and what form does it take when shared? An issued statement is a record of what was told to whom, which is not the same artifact as a report run on demand. | RPT-17 | Before any statement is handed to a lender or a board |
| **OI-12** | Does CFOKit handle sales tax, and if so how much of it does it own rather than delegate? No requirement covers it, and treating it as unsupported is cleaner than supporting it partially — but an owner-operator meets it on day one. | Nothing — no requirement exists yet | Before segment 2 is a supported audience |

---

## 11. Glossary

Terms carrying a specific meaning in this document.

| Term | Meaning |
|---|---|
| **Account** | A line in a chart of accounts. Always this sense, throughout. |
| **Administrator** | An identity holding the role that permits entity lifecycle changes and changes to other identities' access. |
| **Basis** | Whether an entity recognises revenue and expense when the obligation arises or when cash moves. A property of the entity, not a report option. |
| **Close** | Marking a period as reviewed. A workflow milestone, distinct from the permanence a posting confers. |
| **Commodity** | A unit an amount is denominated in. Money in a given currency today; potentially other holdings later. |
| **Compensating control** | What stands in for segregation of duties where an entity has too few people to segregate — a reconciliation performed, an exception dispositioned, an agent-posted entry reviewed. |
| **Display scale** | The number of decimal places at which a commodity's amounts are shown. A presentation property; recorded amounts carry more precision and are never rounded. |
| **Draft** | A candidate transaction, freely editable, not yet part of the books. |
| **Entity** | A set of books for one legal or reporting unit. The isolation boundary throughout. |
| **Exception** | An item that could not be processed, held in a durable queue until someone or something dispositions it. Never a silent failure. |
| **Functional currency** | The single currency an entity's books are denominated in, declared when the entity is created. |
| **Grant** | A role held by an identity in an entity, and the act of assigning one. A grant may lapse. |
| **Identity** | A person, authenticated by the organisation's identity provider. |
| **Invitation** | A role granted to someone who has no identity yet. It confers nothing until they authenticate, and binds to their identity when they do. |
| **Obligation** | A commitment to receive or pay, recorded when it arises, separately from its settlement. |
| **Posting** | Committing a transaction to the books. Irreversible; the point after which corrections are new entries. |
| **Principal** | Whatever an action is attributed to. A person is one; a skill is another. An agent action carries both, and its authority is the intersection. |
| **Reversal** | A new entry that undoes a posted one, leaving both visible. The only form a correction takes. |
| **Role** | A named set of capabilities. An identity's access to an entity is exactly the role it holds there, and nothing else. |
| **Rule** | Stored, operator-approved criteria that assign an incoming transaction to an account deterministically. |
| **Settlement** | The movement of cash against an obligation. |
| **The CFO seat** | Whoever is accountable for the company's finances — a fractional CFO where one is engaged, and otherwise the founder or owner-operator. Never vacant. |
| **Untrusted content** | Anything the customer did not author and CFOKit does not control — a feed memo, an uploaded document, text extracted from one. Classified as such on the record and treated accordingly wherever an agent reads it. |

---

## 12. Traceability

Every requirement traces to at least one business objective. An objective with no requirement
is unserved; a requirement serving no objective does not belong here.

| Objective | Requirements |
|---|---|
| **OBJ-1** Displace the incumbent stack | BKP-01–BKP-06, BKP-13–BKP-16, AR-01–AR-19, RPT-01–RPT-09, MIG-01–MIG-08, NFR-19, NFR-20 |
| **OBJ-2** Current and closed without manual recording | BKP-01, BKP-06, BKP-09, BKP-16, LED-11, LED-12, PLT-07, PLT-12, PLT-14, RPT-15, NFR-15 |
| **OBJ-3** Every number traceable | BKP-10, LED-08, LED-09, PLT-16, PLT-20, IAM-13, NFR-02, RPT-08, RPT-11, SOC1-14, SOC1-15, SOC1-22, SOC1-23, SOC1-36 |
| **OBJ-4** Output professionals accept | RPT-03, RPT-07, RPT-09, RPT-10, RPT-12, RPT-13, RPT-14, RPT-16, RPT-17, RPT-18, LED-02, LED-06, LED-14, LED-17, NFR-01, NFR-16 |
| **OBJ-5** Own and leave with the data | MIG-06, MIG-07, MIG-09–MIG-12, PLT-11, PLT-13, PLT-21, NFR-07, NFR-17 |
| **OBJ-6** No vendor relationship required | BKP-03, PLT-02, PLT-06, IAM-10, NFR-10, NFR-11, NFR-14, NFR-17 |
| **OBJ-7** Additive outside contribution | BKP-02, BKP-17, BKP-18, PLT-01, PLT-02, PLT-03, PLT-06, RPT-22, NFR-12, NFR-13 |
| **OBJ-8** Serves a small business across its range | LED-10, LED-13, LED-14, LED-15, LED-16, LED-17, LED-18, LED-19, RPT-19, RPT-20, RPT-21, IAM-08, IAM-09, PLT-04, PLT-05, PLT-08, NFR-08, NFR-09 |
| **OBJ-9** Examinable by an external auditor | IAM-13–IAM-19, PLT-15–PLT-19, NFR-18, SOC1-01–SOC1-36, SOC2-01–SOC2-33 |
| **OBJ-10** Numbers that are right | LED-01, LED-03, LED-04, LED-05, LED-07, LED-11, BKP-07, BKP-08, BKP-11, BKP-12, MIG-04, MIG-05, RPT-06, NFR-01, NFR-02, NFR-03 |
| **OBJ-11** Only authorised people reach the books | IAM-01–IAM-07, IAM-11, IAM-12, IAM-15, PLT-05, PLT-09, PLT-10, AR-08, NFR-04, NFR-05, NFR-06 |
