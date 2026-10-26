---
status: "proposed"
kind: "requirement-driven"
date: 2026-10-26
decision-makers: [Geoff]
---

# ADR-0080: A cash-basis report recognizes each obligation as it is settled, and changes nothing a stored link does not reach

**Requirements served:** `AR-16`, `LED-14`, `LED-17`, `AR-12`, `AR-14`, `AR-18`, `NFR-16`.

## Context and Problem Statement

`AR-16` is `Must`: an entity on a cash basis *"recognizes the revenue on settlement rather than on
issue"*. `LED-14` makes the declared basis what *"every report defaults to"*.
[ADR-0037](0037-accounting-basis-is-a-presentation-property.md) settled that basis is presentation —
the ledger is accrual, an obligation and its settlement are linked postings, and the cash view is
*"derived by restricting recognition to obligations that have been settled, and by the amount
settled"*. It left the derivation's treatments as follow-on obligations: partial payment,
overpayment, write-off, credit note, settlement in a later period, and a journal entry posting to
receivables with no obligation to link to.

What exists:

* **The link.** An `obligation` row names the transaction that raised it, the account that carries
  it, and its amount, signed as its posting there: a receivable positive, a payable negative. A
  `settlement` row names the obligation, the transaction that settled it, and the amount. Both are
  written by the ledger's write path in the same transaction as the posting, and both are
  append-only. A payment can settle several obligations and an obligation can be settled by
  several payments (`AR-12`). Credit notes (`AR-14`) and write-offs (`AR-18`) are not built.
* **The reports.** One query sums postings by account over a window, whatever the basis. A
  cash-basis entity's trial balance, profit and loss and balance sheet are therefore accrual
  figures under a heading that says "cash". The ledger's receivables service describes the cash
  view as `RPT-19`, which is deferred; but `RPT-19` is the *alternate* view, an entity on either
  basis shown the other. A cash entity's own statements are `AR-16`'s, and nothing defers them.
* **Postings no link reaches.** A journal entry to a receivable, as ADR-0037 foresaw, and imported
  history. QuickBooks' Export Data names no invoice a payment applies to, so an import lands every
  transaction unlinked ([ADR-0078](0078-the-quickbooks-fixture-is-ours-and-a-sandbox-validates-it.md)
  records the layout, validated against a real download).
* **The incumbent's rules**, as a QuickBooks sandbox reported them for the synthetic company's
  postings (ADR-0078): cash basis recognizes an invoice or bill in proportion to the amount paid,
  dated with the payment; each share is rounded half up to the cent and the last line takes the
  rest; a payment no invoice takes is income, reported as "Unapplied Cash Payment Income"; and a
  journal entry to receivables appears in a cash-basis report as posted.
* **Tax.** Under the cash method, income is included when actually or constructively received,
  and expenses are deducted when paid (IRS Publication 538).
* **Allocation.** [ADR-0025](0025-rounding-and-allocation.md) forbids rounding in the ledger and
  makes allocation largest remainder, ties broken by line order, in the pure engine. The engine's
  `allocate` takes non-negative integer weights and an increment, and refuses rather than rounds.

## Decision Drivers

* `AR-16`'s rule exactly: revenue recognized on settlement, by the amount settled.
* Exact and deterministic: the parts recognized sum to what was settled, and an obligation fully
  settled recognizes exactly what raised it, however many settlements it took (`NFR-01`, ADR-0025).
* Nothing from inference: what no stored link states is not guessed (`NFR-16`, ADR-0037 § 3).
* Nothing posted differently and nothing stored twice: the view is derived at presentation, as
  outstanding balances are ([ADR-0003](0003-postgres-as-sole-storage-backend.md)), and no rollup
  layer is added ([ADR-0012](0012-binding-non-goals-and-scope-discipline.md)).
* Every posted figure accounted for: a cash-basis statement balances and drops nothing.
* One rule for every kind of settlement — a payment, a credit note, a write-off — so `AR-14` and
  `AR-18` inherit it rather than each deciding its own.
* Testable without a database (ADR-0036's first layer, the engine's purity under
  [ADR-0008](0008-layered-architecture-pure-engine.md)).

## Considered Options

* Defer each obligation to its settlements, each recognizing its share of what raised it on its own
  date, derived in the engine; present everything a link does not reach as posted, and say so
* Recognize an obligation only once it is fully settled
* Recognize a settled obligation's lines in their order, first line first
* Round each settlement's shares to the cent, as QuickBooks does
* Store the cash view as postings when a settlement is written
* Infer links for unlinked postings, by customer and amount
* Leave unlinked postings on receivable and payable accounts out of a cash-basis report
* Refuse a cash-basis report while an unlinked posting stands on a receivable or payable account

## Decision Outcome

Chosen option: "Defer each obligation to its settlements", because it is `AR-16`'s rule stated
over the link ADR-0037 stores, exact by allocation, and it changes no figure a link does not speak
to.

> A cash-basis report is the ledger's postings, except that a transaction raising an obligation is
> deferred to its settlements. Each settlement recognizes, on its own date, its share of the
> raising transaction's other postings, in place of its own posting on the carrying account.

### 1. What a settlement recognizes

**A raising transaction contributes nothing to a cash view by itself.** Its postings other than on
the carrying account — an invoice's income lines, a bill's expense lines, a tax line — wait for
settlement, and its posting on the carrying account is never presented.

**A settlement recognizes, on the settling transaction's date, the raising transaction's other
postings in proportion to the amount settled over the obligation's amount.** Its own posting on
the carrying account, to the amount settled, is not presented. An invoice of 1,000.00 — 600.00
design and 400.00 workshops — paid 400.00 recognizes 240.00 and 160.00 on the payment's date, and
the bank's 400.00. A settlement in a later period recognizes in that period, which is `LED-17`'s
"recoverable as either".

**The shares are an allocation** (ADR-0025): largest remainder, ties broken by line order, in
increments of the commodity's display scale, or finer where the amount settled is. **They are
cumulative**: the shares through a settlement are the allocation of everything settled so far, and
each settlement recognizes what that adds. An obligation fully settled therefore recognizes exactly
the postings that raised it, whether in one payment or seven.

Every transaction the view changes stays balanced, because the shares sum to the amount settled,
which is what the posting they replace held. A cash-basis trial balance balances, and so does a
cash-basis balance sheet.

### 2. Whatever settles it

**A payment, a credit note and a write-off are the same rule.** A credit note settles the invoice it
corrects: its own debit to income and the share it recognizes cancel, so a credited invoice
recognizes nothing on a cash basis. A write-off settles the invoice: its bad-debt expense and the
share cancel, so an invoice never collected was never income and its write-off is no expense, as
the cash method has it. This holds only if both are recorded as settlements of the obligation, which
is the obligation this record puts on `AR-14` and `AR-18`.

**An overpayment recognizes what it settles and no more.** A settlement records the amount it
applies (`AR-12`). What the payment brought beyond that stays where it was posted, on the carrying
account, as money held for the customer, until a later settlement applies it or a refund returns
it. QuickBooks reports it as income instead; CFOKit does not infer that unapplied money was earned.

**A reversal is presented as the negation of what it reverses, on its own date.** A voided invoice
is deferred with its original, so the pair recognizes nothing. A payment that bounces takes back
what it recognized.

### 3. What no link reaches is presented as posted

A transaction that neither raises nor settles an obligation is the same on both bases: a cash sale,
an expense paid, a transfer, a journal entry. That includes a journal entry to a receivable or a
payable, and imported history. **The report says so on its face** (`NFR-16`): how many postings in
its span stand unlinked on an account that carries an obligation, and how many of its transactions
were imported from a source that links none.

A cash-basis company's imported history therefore reads on accrual. Its difference from the
source's own cash-basis statements is what the import's reconciliation records, and a difference
that nets to zero is reported there as the basis
([ADR-0050](0050-the-import-oracle-is-basis-free.md) § 2).

### 4. Where it lives

**The derivation is a pure function in the ledger's engine**: postings with their transactions'
links in, cash-view postings out, the increment passed in. The repository reads the links beside
the postings; the service applies the derivation to every report that presents balances — the
trial balance, the profit and loss in either form, the balance sheet, an account's detail — where
the entity's declared basis is cash, and `RPT-10` states the basis as it does now. **The journal,
the journal total an import is checked against, and the interchange export are the record rather
than a view of it**, and stay posted figures on every basis (ADR-0050 § 1).

### 5. What this does not decide

* `RPT-19`'s alternate view — an accrual entity shown cash, or the reverse — stays deferred. This
  derivation is what it would use.
* Modified cash, and how `RPT-10` labels it (ADR-0037 § 4).
* How a report spans a change of basis, which `LED-14` records with its date. A report is presented
  on the basis the entity declares.
* Whether an advance payment is income on receipt for tax.

### Consequences

* Good, because a cash-basis company's statements recognize income when it is paid (`AR-16`),
  exactly, from links stored when the money moved.
* Good, because one rule covers payment, partial payment, later-period settlement, credit note,
  write-off, overpayment and reversal, so the features still to be built inherit it.
* Good, because the derivation is a pure function over integers, property-testable without a
  database, and an obligation fully settled recognizes exactly what raised it.
* Good, because nothing is dropped or guessed: an unlinked posting is presented as posted and
  counted on the report.
* Good, because payables inherit it unchanged, as ADR-0037 requires.
* Bad, because every balance-presenting report of a cash-basis entity reads links and runs a
  derivation, where today it sums postings in one query.
* Bad, because an unapplied payment is not income here as it is in QuickBooks, so a cash-basis
  company's statements differ from QuickBooks' — and possibly from its tax treatment of advance
  payments — until the payment is applied.
* Bad, because a cash-basis company's imported history presents on accrual, and an invoice open at
  the cutover, imported unlinked, is recognized at its invoice date and never at its payment.
* Bad, because a partial payment that does not divide evenly can put its odd cent on a different
  line from QuickBooks', whose rule rounds each share and gives the last line the rest. The
  totals agree.
* Bad, because `allocate` takes no negative weight, and an invoice with a discount line has lines
  of both signs.
* Neutral, because an accrual entity's reports do not change.

### Confirmation

* **Property tests over the engine's derivation**, as ADR-0037's Confirmation describes: cash-view
  recognition equals the amounts settled, in proportion; an obligation fully settled recognizes
  exactly the postings that raised it; every transaction the view changes balances. Partial
  payment, overpayment, credit note, write-off and reversal are in the generator.
* **Conformance cases** from published cash-to-accrual worked problems, each citing its source
  (ADR-0036 § 2).
* **A differential check against QuickBooks.** The fixture's events record which invoice each
  payment applies to, so posted to CFOKit with their links they can be compared with the cash-basis
  statements the sandbox agreed with: exactly, with each odd-cent line explained by the allocation
  rule rather than tolerated.
* **Not gated:** that a report branches on the declared basis while no posting path does. That is
  review, as ADR-0037 says.

## Pros and Cons of the Options

### Defer each obligation to its settlements, derived in the engine; present the unlinked as posted

* Good, because it is ADR-0037 § 2's derivation made precise, from the link § 3 stores.
* Good, because one rule covers every settling transaction and every reversal.
* Good, because it is exact by allocation and changes no figure a link does not reach.
* Bad, because every cash-basis report carries a derivation and a second read.
* Bad, because unlinked history stays accrual, which the report has to say.

### Recognize an obligation only once it is fully settled

Simple to state and simple to compute: a settled invoice is income, an open one is not.

* Good, because no allocation is needed at all.
* Bad, because it is not `AR-16`: half an invoice paid is half the revenue received, and the cash
  method includes income when received, not when the last of it arrives. A retainer paid in
  instalments would show nothing until the final one.

### Recognize a settled obligation's lines in their order, first line first

A payment fills the first line, then the next, as a customer might imagine paying item by item.

* Good, because each share is a whole line or a remainder, with no fraction to allocate.
* Bad, because the mix of income a payment recognizes would depend on the order a person typed the
  lines in, which nobody meant as a ranking. Two invoices with the same lines in another order would
  report different income for the same payments.
* Bad, because it is not what the incumbent does: QuickBooks recognizes in proportion, so an
  accountant comparing the two would find every partial payment different.

### Round each settlement's shares to the cent, as QuickBooks does

Matching the incumbent to the cent would let every partial payment agree with a QuickBooks report.

* Good, because a migrated company's cash statements would match its old ones line for line.
* Bad, because it is a second allocation rule beside ADR-0025's, and a rounding call in the
  derivation, which ADR-0025 forbids.
* Bad, because rounding each settlement on its own, without the cumulative correction, can leave a
  fully paid invoice's lines off by cents from what it raised. Largest remainder over the cumulative
  amount cannot.

### Store the cash view as postings when a settlement is written

Reports would stay one query, and the cash view would be a read like any other.

* Good, because no derivation runs at report time.
* Bad, because it stores a second copy of figures the postings and links already determine, which
  is the stored-balance mistake ADR-0003's derived figures avoid, and a rollup layer ADR-0012 forbids
  without its own record.
* Bad, because every correction — a reversal, a late credit note — would have to update the stored
  view correctly, which is a write-path obligation a derivation does not have.

### Infer links for unlinked postings, by customer and amount

An imported payment of exactly an open invoice's amount, from that invoice's customer, is very
probably its settlement, and inferring it would give imported history a cash view.

* Good, because a cash-basis company's imported history would read on its basis.
* Bad, because it is the inference ADR-0037 § 3 rejected, and `NFR-16` forbids: two invoices of the
  same amount, a payment covering three, a partial payment — each is a guess, and the guess lands in
  a statement someone relies on. A person confirming a proposed match, as
  [ADR-0059](0059-a-line-is-matched-before-it-is-coded.md) does for bank lines, is the honest form,
  and is a separate decision.

### Leave unlinked postings on receivable and payable accounts out of a cash-basis report

This is close to what QuickBooks attempts, and it would keep accrual figures out of a cash statement.

* Good, because a cash statement would contain only cash-basis figures.
* Bad, because the statement would no longer balance — the other side of each excluded posting
  stays — or the other side would have to be excluded too, dropping cash that moved.
* Bad, because a figure silently missing from a statement is the failure `NFR-16` exists to prevent.

### Refuse a cash-basis report while an unlinked posting stands on a receivable or payable account

The strictest reading of `NFR-16`: where the books cannot support the answer, give none.

* Good, because a cash-basis figure would never rest on an accrual posting.
* Bad, because every imported cash-basis company would have no reports at all, and one journal entry
  to receivables would stop a company's statements. `NFR-16` asks for the answer to say what is
  missing, which the count on the report's face does.

## More Information

**Follow-on obligations.**

* The derivation in the engine, with its property tests; the links read beside the postings; the
  services applying it where the declared basis is cash; the count of unlinked and imported postings
  on the face of each report.
* `allocate` across weights of both signs.
* `AR-14` and `AR-18`, when built, record a settlement of the obligation they correct.
* The ledger's receivables service names a cash entity's own statements as `AR-16`'s, not
  `RPT-19`'s.
* ADR-0079 notes that a cash-basis company's imported history is presented as posted.
* The differential check against the QuickBooks fixture's cash-basis statements.

Separately: reversing a transaction that raised an obligation does not close the obligation, so a
voided invoice still reads as outstanding (`AR-15`). The cash view needs no fix for it — § 2 defers
the reversal with its original — but the outstanding read does.

**Reversal cost.** Low for the books, which this never writes: a different rule changes what a
report derives and nothing stored. Not nothing for what was issued. An issued statement (`RPT-17`)
keeps the figures it was issued with, and a changed rule would re-derive different ones with no
posting to show why, so supersession would not detect it.

**Sources.** IRS Publication 538, *Accounting Periods and Methods*, "Cash Method". Its wording was
read through secondary sources quoting it; the publication itself was not reachable from the
environment this record was written in, and should be checked against irs.gov before this record is
accepted.

Related: ADR-0037 (the model this derives from), ADR-0025 (allocation), ADR-0050 (the import's
basis difference), ADR-0059 (a person confirms a proposed match), ADR-0078 (the incumbent's rules,
as a sandbox reported them).

## Revisit when

* A cash-basis company or its accountant needs unapplied payments as income on receipt, for tax or
  to match QuickBooks.
* A cash-basis company imports with receivables open at the cutover, which is when linking imported
  open items, by a person's confirmation, needs its own record.
* A cash-basis report over a year's books takes an order of magnitude longer than the accrual one.
* Accounts payable enters scope, the first test of whether the rule is as symmetric as ADR-0037
  expects.
* `RPT-19` activates.
