---
status: "proposed"
kind: "requirement-driven"
date: 2026-10-26
decision-makers: [Geoff]
---

# ADR-0081: An import marks each invoice and bill still open at the cutover as an open obligation, from the source's own list of what is open

**Requirements served:** `IMP-02`, `IMP-03`, `IMP-05`, `IMP-09`, `AR-16`, `LED-17`, `NFR-16`.

## Context and Problem Statement

An import lands a company's books as of a cutover: everything the source's journal holds, up to
the last day it carries (`IMP-02`). After it, the company runs on CFOKit, and the invoices its
customers have not yet paid, and the bills it has not yet paid, are paid there.

**An imported invoice is not an open invoice to CFOKit.** The import posts each of the source's
transactions through the ledger's write path, as it was recorded: an invoice debits receivables and
credits income. Nothing marks it as owed, because QuickBooks' Export Data names no invoice a payment
applies to ([ADR-0078](0078-the-quickbooks-fixture-is-ours-and-a-sandbox-validates-it.md) records
the layout, validated against a real download). So a customer paying a pre-cutover invoice after the
cutover pays nothing CFOKit knows is owed:

* **The receivables ledger arrives empty**, which `IMP-03` exists to prevent: nothing is
  outstanding, aged or matched, and a deposit in a bank feed has no invoice to settle (`AR-13`).
* **A cash-basis company's income lands in the wrong period.** Under
  [ADR-0080](0080-a-cash-basis-report-recognizes-an-obligation-as-it-is-settled.md), what no link
  reaches is presented as posted, so a December invoice paid in January is income in December — in
  the old system's year — and the January payment recognizes nothing. Its first months on CFOKit,
  and its first tax year, are wrong.

**Migrations solve this one way.** Moving a company between accounting systems — QuickBooks to
Xero, QuickBooks to NetSuite — carries the opening balances at the cutover and **each invoice and
bill still open as an open document**, taken from the old system's own list of what is open, so
payments after the switch apply against them. History stays in the old system or arrives as
summary journals, and the open documents are loaded against a suspense or conversion account that
the opening balances clear, so nothing is counted twice.

**QuickBooks states what is open.** Its A/R Aging Detail and A/P Aging Detail reports list, as of
a date, each open invoice and bill with its date, type, number, customer or vendor, due date,
amount and open balance, and export to Excel like any report; the Reports API serves them as
`AgedReceivableDetail` and `AgedPayableDetail`. Export Data does not include them. Its "Invoices and
Received Payments" report lists payments beside invoices, but does not reliably say how much of a
payment each invoice took, so it cannot supply the links themselves.

**The ledger can already hold the result.** The import posts through `record_transaction`, which
takes `raises_obligation`: an obligation carried by the one account whose postings in the entry sum
to its amount ([ADR-0059](0059-a-line-is-matched-before-it-is-coded.md) § 3), append-only like the
posting. Unlike the systems migrations target, CFOKit keeps the history *in* the ledger, so the
invoice an aging report names is already there as a posted entry.

## Decision Drivers

* The source's statement of what is open, never an inference from history (`NFR-16`, ADR-0037 § 3).
* No figure retyped by a person (`IMP-09`), and the person sees what will and will not be created
  before anything is (`IMP-05`).
* Nothing counted twice: the books after the import are the books the source holds, on either
  basis.
* A payment after the cutover settles what it pays, so a cash-basis company's income is recognized
  when paid (`AR-16`, ADR-0080), and an accrual company's figures do not move.
* The established practice followed rather than a rule of our own, adapted only where CFOKit's
  model differs.
* Checkable against the source's own figures (`IMP-08`, `NFR-01`).

## Considered Options

* Mark each open invoice and bill, on the imported transaction that is it, as an open obligation
  from the source's aging detail at the cutover
* Bring each open item across as a new document for its open balance, against a conversion account
* Import opening balances only, with the open items as documents carrying their own lines
* Infer what is open from the imported history
* Have a person link each open item after the import
* Link all of history from QuickBooks' "Invoices and Received Payments" report

## Decision Outcome

Chosen option: "Mark each open invoice and bill, on the imported transaction that is it", because it
follows the established practice — the source's own list of what is open, as of the cutover — and,
where that practice adds a new document, marks the one the ledger already holds, which is the only
way the open item is counted once and right on both bases.

> An import reads the source's aging detail as of the cutover and raises an obligation on each
> open invoice's and bill's own imported transaction. A payment after the cutover settles it.

### 1. What is open is what the source says is open

The import reads the source's open receivables and payables, as of the last day its journal
carries: for QuickBooks, A/R Aging Detail and A/P Aging Detail, exported beside Export Data. Nothing
is inferred from the history about what is open, and nothing is typed by a person.

### 2. An open item is marked on its own transaction, not posted again

Each open item is matched to the imported transaction that is that document, by the fields the
source prints for it on both reports — type, number, name, date and amount — and that transaction
is posted raising an obligation for its amount, carried by its receivable or payable account. **This
is identifying one document across two reports of the same source, not inferring a relationship**:
a match is exactly one transaction, and an item matching none, or more than one, is shown to the
person as not created (`IMP-05`), never guessed at.

Nothing is posted twice, so no conversion account is needed. On accrual, nothing moves: the invoice's
income stays on its date. On a cash basis, ADR-0080 defers it to its settlements, so an invoice
unpaid at the cutover is income when it is paid after it, which is when the cash method says it is.

### 3. Part paid before the cutover

An item partly paid before the cutover has an open balance below its amount, and the payments that
made the difference are history the source does not link. The obligation is raised for the
document's amount, as its transaction carries it, and the part already paid is settled on the last
day of the history. On a cash basis that part is recognized on that day rather than on the days it
was paid — inside the history, whose cash-basis figures are the source's own (ADR-0080 § 3), and
never in the company's first period on CFOKit.

### 4. The source's figures check it

The open balances must sum to the receivable and payable balances the source states at the
cutover. A difference is recorded with the import's reconciliation, beside its balances and its
journal total (`IMP-08`, [ADR-0050](0050-the-import-oracle-is-basis-free.md)), as a disagreement
with the source's own figures rather than a note.

### 5. What this does not decide

* Customers and invoices as documents in the receivables module. An open item becomes an obligation
  in the ledger; making it an invoice a customer is reminded of (`AR-17`) or aged by customer
  (`AR-15`) needs the customers imported too (`IMP-03`), and is its own step.
* An import of opening balances without history (`IMP-02` allows either). This decides the import
  that carries history, which is the one that exists.
* Readers for other sources. Each states what is open in its own report, and this rule takes it.

### Consequences

* Good, because a payment after the cutover settles the invoice it pays, so the receivables ledger
  is not empty, a bank deposit has an invoice to match, and a cash-basis company's first months
  recognize income when it is paid.
* Good, because it is the established practice in substance — the source's list of what is open, at
  the cutover — and departs from its mechanism only where CFOKit's history is already in the ledger.
* Good, because an accrual company's books do not move, and nothing is counted twice on either
  basis.
* Good, because it needs no new capability of the write path for an item unpaid at the cutover: an
  obligation raised by the transaction that posts it is what `raises_obligation` already does.
* Good, because the open balances are checked against the source's own receivable and payable
  balances.
* Bad, because the person exports two more reports from QuickBooks, as of the right date, beside
  Export Data, and the getting-started pages must ask for them.
* Bad, because the part of an item paid before the cutover is recognized, on a cash basis, on the
  history's last day rather than when it was paid, and settling it needs a settlement with no
  payment of its own, which the write path does not yet take.
* Bad, because an item whose document cannot be matched exactly once is left for the person, so a
  source with duplicated or missing document numbers leaves more of them.
* Bad, because the obligations are append-only once raised: an import that marked the wrong
  documents is corrected by reversal, not by editing.

### Confirmation

* **The fixture carries the reports.** The generator writes A/R Aging Detail and A/P Aging Detail as
  of the books' last day, validated like the others: against the sandbox's `AgedReceivableDetail`
  and `AgedPayableDetail`, and against one real download (ADR-0078). The synthetic company already
  ends with invoices and bills open; catalog cases add one partly paid and one whose number repeats.
* **The round trip checks the outcome** ([ADR-0079](0079-the-quickbooks-round-trip-imports-what-the-reader-read.md)):
  each open item is an obligation with the open balance the aging states; a payment posted after
  the import settles it; a cash-basis company's profit and loss recognizes that payment's share of
  the invoice's lines, the expected value coming from the invoice's own lines; the open balances
  agree with the receivable and payable balances.
* **Not gated:** that nothing infers an open item. A reader matching by anything other than the
  source's own fields for one document would be visible in review.

## Pros and Cons of the Options

### Mark each open invoice and bill on its own imported transaction

* Good, because it is counted once and is right on both bases.
* Good, because the source states what is open and the import identifies, rather than infers.
* Bad, because partly paid items need a settlement with no payment, recognized on the history's last
  day.
* Bad, because it needs two more reports from the person.

### Bring each open item across as a new document for its open balance, against a conversion account

What Xero and NetSuite migrations do, and therefore what an accountant who has done one expects.

* Good, because it is the practice itself, with nothing adapted.
* Good, because a partly paid item is simply its open balance.
* Bad, because CFOKit's history already holds the invoice, so a new document counts it twice unless a
  conversion account offsets it — and with that account as its other side, its payment after the
  cutover recognizes no income. That serves an accrual company, which is whom those migrations serve,
  and fails `AR-16` for the cash-basis company this record is for.

### Import opening balances only, with the open items as documents carrying their own lines

The pure form of the practice: a trial balance at the cutover, and the open items with their income
and expense lines.

* Good, because nothing in history needs marking and nothing is counted twice on a cash basis.
* Bad, because it drops the history `IMP-02` delivers and the first conversation after an import is
  about — what the books say, over the years they cover.
* Bad, because on accrual the open items' income is already in the opening retained earnings, so
  their lines count it again unless an offset is added, which is the conversion account again.

### Infer what is open from the imported history

Every invoice's receivable either was or was not cleared by later payments from its customer, so
the history appears to say what is open.

* Good, because it needs nothing beyond Export Data.
* Bad, because it is the inference ADR-0037 § 3 rejects and `NFR-16` forbids: a payment covering two
  invoices, two invoices of one amount, a credit applied, a partial payment — each makes "which
  invoice is open" a guess, and the guess becomes what customers are chased for.

### Have a person link each open item after the import

[ADR-0059](0059-a-line-is-matched-before-it-is-coded.md) already has a person confirm a proposed
match.

* Good, because a person decides each one, and nothing is wrong without someone having said so.
* Bad, because the source already states what is open, so asking the person to state it again is
  retyping it (`IMP-09`), across every open item a company has. It stays the path for the items
  the identification cannot resolve.

### Link all of history from QuickBooks' "Invoices and Received Payments" report

The report lists each invoice beside the payments received against it, which looks like the links
themselves.

* Good, because history would then have a cash view too, and partial payments would be dated
  exactly.
* Bad, because the report does not reliably state how much of a payment each invoice took, so the
  amounts settled would be inferred, which is the same guess with a better starting point.
* Bad, because no migration practice links history this way; the open items are what the switch
  needs.

## More Information

**Follow-on obligations.**

* The reader reads A/R Aging Detail and A/P Aging Detail, matches each item to its journal
  transaction by the source's fields, and marks it in the neutral shape; the shape and the import
  endpoints carry the mark. That is a contract change (ADR-0015).
* The getting-started pages ask for the two reports, as of the journal's last day, and show the
  items not matched.
* The ledger records a settlement with no payment of its own, for the part of an item paid before
  the cutover. That is a change to the write path, which needs a person's review before it is built.
* The fixture writes and validates the two reports; the catalog and the round trip gain the cases
  in Confirmation.
* ADR-0079 names the open items among what the round trip checks.

**Reversal cost.** Moderate. Obligations raised by an import are append-only and stay with the
books it landed, so a company imported under this rule carries them for life; a different rule
applies to imports after it, and an import already done is corrected by reversing its entries.

**Sources.** The migration practice, from practitioners' guides to moving between QuickBooks, Xero
and NetSuite; QuickBooks' aging reports and their export, from Intuit's community answers and the
Reports API's report list. Intuit's official help pages on the aging reports' columns were not
found, so the columns are to be confirmed against a real export, as the fixture's validation does.

Related: ADR-0037 (obligations, and why they are never inferred), ADR-0059 (identifying a
counterpart), ADR-0078 and ADR-0079 (the fixture and its round trip), ADR-0080 (what an open item
means on a cash basis).

## Revisit when

* A source states which payment paid which invoice — an export or an API connection carrying the
  links — which would let an import link history, not only what is open.
* More than one open item in a hundred, in a real company's import, fails to match exactly once.
* An import of opening balances without history is built, which needs the open items as documents
  of their own.
* A second source's reader lands, the first test of whether "the source's own list of what is open"
  generalizes.
