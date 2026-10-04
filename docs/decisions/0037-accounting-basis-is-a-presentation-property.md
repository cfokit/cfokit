---
status: "accepted"
kind: "requirement-driven"
date: 2026-09-01
decision-makers: [Geoff]
---

# ADR-0037: The ledger records obligation and settlement; accounting basis is a presentation property

**Requirements served:** `LED-14`, `LED-17`, `AR-16`.

## Context and Problem Statement

`LED-17` already obliges the expensive half: *"An obligation and its settlement are recorded as two
related events rather than one."* That is `Must`, it is live, and it is the part that cannot be
retrofitted — a ledger that collapsed the two into one posting could never reconstruct them.

What is unsettled is what follows from it. **Does an entity's declared basis change what gets
posted, or only what gets shown?** The requirements point both ways:

- `LED-17` and `RPT-19` describe statements derived from stored obligation and settlement events,
  with the alternate view available — which only makes sense if basis is presentation.
- `AR-03` says *"an issued invoice is a posting rather than only a document"*, so the obligation
  posts at issue.
- `AR-16` says a cash-basis entity *"recognizes the revenue on settlement rather than on issue"*,
  which reads as an instruction about what to post.

Those produce **materially different ledgers from identical inputs**. Under one, an issued invoice
credits income and the cash view excludes what is unsettled. Under the other it credits deferred
revenue and settlement moves it. Different accounts, different postings, different corrections,
different statements.

[ADR-0002](0002-build-the-ledger-rather-than-adopt-one.md) reached this ground first, observing that
invoicing forces the dual-event model anyway so accrual "becomes close to a reporting choice over
data already present." That was scope analysis supporting build-versus-adopt, it was hedged, and it
bound nothing. This record settles it.

## Decision Drivers

* `LED-14` requires that a change of basis **"never rewrites history"**. If basis were a posting rule
  this would be impossible: changing it would either rewrite prior postings or leave the books in two
  incompatible halves. Only a presentation property can satisfy it.
* `RPT-19` requires an entity on either basis to be shown the alternate view. One answer permits
  that; the other makes it a second set of books.
* `AR-16` requires a cash-basis entity to track receivables, which means the obligation must exist as
  a record whatever the basis.
* The events exist regardless under `LED-17`, so the only question is what is derived from them —
  and derivation is cheap where re-recording is not.

## Considered Options

* Record obligation and settlement as linked postings; derive basis at presentation
* Infer the obligation-settlement relationship from account and transaction type at report time
* Post to deferred revenue at issue and move it to income at settlement
* Post according to the entity's declared basis
* Dual posting — maintain a cash ledger and an accrual ledger side by side

## Decision Outcome

Chosen option: "Record obligation and settlement as linked postings; derive basis at presentation",
because `LED-14` forbids a basis change from rewriting history, and no posting-rule answer can honor
that.

### 1. The ledger is intrinsically accrual

Every obligation is a posting and every settlement is a posting, whatever basis the entity declared.
An issued invoice credits income and debits receivables at issue (`AR-03`). A cash-basis entity's
ledger therefore contains receivables, and that is correct rather than a leak.

### 2. Basis is a property of presentation

The cash view is derived by restricting recognition to obligations that have been settled, and by
the amount settled. Nothing is posted differently, nothing is reversed, and nothing is re-recorded
when the basis changes — which is what `LED-14`'s "never rewrites history" requires.

`LED-14`'s "a property of the entity rather than a per-report toggle" means the entity has exactly
one declared basis, that every report defaults to it, and that `RPT-10` states it on the face. It
does not mean the ledger posts differently, and `RPT-19`'s labeled alternate view is not in tension
with it.

`AR-16` is a recognition rule about statements, not an instruction about postings.

### 3. The obligation-settlement link is stored, never inferred

A settlement records which obligation it settles, and for how much. `AR-12` already requires this
shape — a payment applied to one or more invoices, with partial payment and overpayment both
representable.

**This is the decision's whole substance, and it is what makes the derivation exact.** The
alternative — inferring the relationship from account and transaction type at report time — is what
the incumbents do, and it is observably unreliable: QuickBooks excludes invoices and credit memos
from a cash-basis report but a journal entry, check, or payment touching receivables still appears,
so the standing practitioner advice is that selecting cash basis does not reliably produce a
cash-basis presentation. That failure is structural, not a defect, and storing the link makes it
impossible here.

### 4. What this does not decide

**Modified cash.** It is not a third basis on this axis — it is the cash view with certain account
classes, chiefly fixed assets and long-term debt, treated accrually. Under this decision it is a
refinement of a view rather than a new axis, which is why `LED-14` enumerates two values rather than
three, and why deferring it costs nothing. Every small-business platform behaves this way already:
capitalized assets and loans stay on the balance sheet under both views, so an entity that
capitalizes anything is on modified cash whether or not it says so.

**Whether `RPT-10` must say so.** If an entity declares cash and holds capitalized assets with
depreciation, the strictly correct label is *modified cash*. The condition is detectable from the
chart of accounts. The incumbents say "Cash basis" and the market accepts it; CFOKit's positioning is
output an accountant accepts as it stands, and a reader who sees a fixed-asset register under a
"cash basis" heading will notice. This is a product decision and is left open.

### Consequences

* Good, because a basis change never rewrites history, which `LED-14` requires and no other option
  delivers.
* Good, because the cash view is exact rather than heuristic: the incumbents' known failure mode is
  structurally impossible where the link is stored.
* Good, because accrual costs a report rather than a migration, and modified cash later costs a
  refinement of a view.
* Good, because a cash-basis entity still knows who owes it money, which `AR-16` requires and a
  cash-posting ledger could not provide.
* Bad, because a cash-basis user's ledger contains receivables and accrual artifacts they may not
  expect to see, and the interface has to explain that rather than hide it.
* Bad, because the cash view is a real derivation with real edge cases — partial payment,
  overpayment, write-off, credit note, and settlement in a later period each need a defined
  treatment, and none is free.
* Bad, because a hand-entered journal posting directly to receivables has no obligation to link to,
  so it needs its own rule. Storing links solves the invoicing path and narrows this residue; it does
  not eliminate it.

### Confirmation

Property tests over the derivation: for any set of obligations and settlements, accrual-view
revenue equals the sum of obligations and cash-view revenue equals the sum of settled amounts,
both computed from one ledger. Partial payment and overpayment are the cases that break a naive
implementation and belong in the property's generator rather than in a worked example.

Cash-to-accrual conversion is also standard textbook material, so it is exactly the kind of thing the
conformance corpus of [ADR-0036](0036-correctness-is-tested-in-four-layers.md) § 2 exists for —
published problems with published answers, testing whether the derivation is right rather than
whether it matches another system.

**Not gated:** nothing prevents a posting path that branches on the entity's declared basis. That is
the failure this record exists to prevent and it is a review rule, though a branch on declared basis
inside `engine` or `service` would be visible in any diff that introduced it.

## Pros and Cons of the Options

### Record obligation and settlement as linked postings; derive basis at presentation

* Good, because it is the only option under which a basis change rewrites nothing.
* Good, because the link is stored, so the derivation is exact and stays exact for hand-entered
  transactions that defeat inference.
* Bad, because the derivation carries the edge cases rather than the postings, and those cases are
  where the work is.
* Bad, because a cash-basis user sees accrual artifacts in their own ledger.

### Infer the obligation-settlement relationship from account and transaction type at report time

What QuickBooks, Xero and most small-business platforms do, and therefore the option with the most
evidence available about how it behaves in production.

* Good, because it requires nothing of the write path at all — no link to store, no discipline to
  maintain — and works retroactively over books that were never designed for it.
* Good, because it is what every accountant already expects, so it surprises nobody.
* Bad, because it is observably unreliable. Invoices and credit memos are excluded from a cash-basis
  report; a journal entry, check, or payment touching receivables is not, so the conversion silently
  understates or overstates. The standing advice is that cash basis is trustworthy only where the
  receivables and payables modules were used consistently, which is an instruction to the user rather
  than a property of the system.
* Bad, because the failure is silent and lands in a statement someone relies on, which is the class
  of failure `NFR-01` and `NFR-16` exist to prevent.

### Post to deferred revenue at issue and move it to income at settlement

* Good, because a cash-basis entity's income statement is then correct directly from the postings,
  with no derivation and nothing to get wrong at report time.
* Bad, because it makes basis a posting rule, so a change of basis must either rewrite history or
  leave two incompatible halves — which `LED-14` forbids in terms.
* Bad, because `RPT-19`'s alternate view becomes a second derivation in the opposite direction, so
  the complexity moves rather than disappearing.

### Post according to the entity's declared basis

The most literal reading of `AR-16`, and the one a reader would land on without this record.

* Good, because each entity's ledger says exactly what its statements say, which is the simplest
  thing to explain.
* Bad, because it fails `LED-14` for the same reason as the option above, and more sharply: two
  entities on different bases would have structurally different ledgers, so nothing about reporting,
  migration, or the oracle would generalize across them.
* Bad, because a cash-basis entity would post no receivable, contradicting `AR-16`'s own first
  sentence.

### Dual posting — a cash ledger and an accrual ledger side by side

* Good, because both views are direct reads with no derivation, and each is internally consistent.
* Bad, because it doubles every write and creates a reconciliation problem between two ledgers that
  must never disagree — a new class of defect in exchange for avoiding a derivation.
* Bad, because `LED-03`, `LED-08` and the audit trail would all need to hold twice, and a correction
  would have to land correctly in both.

## More Information

**Follow-on obligations.**

- A settlement records which obligation it settles and for how much (`AR-12`), stored rather than
  inferred.
- Defined treatment in the cash view for partial payment, overpayment, write-off (`AR-18`), credit
  note (`AR-14`), and settlement in a later period.
- A rule for a journal entry posting directly to receivables with no obligation to link to.
- `RPT-10`'s labeling question, left open in § 4.
- Accounts payable, when it arrives, is the symmetric case and inherits this decision rather than
  re-deciding it. ADR-0002 currently places it out of scope.

**Reversal cost. High.** Moving to a posting-rule model after books exist means either rewriting
history, which `LED-14` forbids, or accepting a discontinuity at the change date that every report
spanning it must then explain.

Related: [ADR-0002](0002-build-the-ledger-rather-than-adopt-one.md) where the reasoning first
appeared as scope analysis; [ADR-0036](0036-correctness-is-tested-in-four-layers.md) § 2 for how the
derivation is tested; `LED-17` for the storage obligation this builds on.

## Revisit when

* An entity capitalizes an asset or carries a loan, which is when modified cash stops being
  hypothetical and `RPT-10`'s labeling question needs an answer.
* A jurisdiction requires a basis whose recognition cannot be derived from obligation and settlement
  events, which would be the first real challenge to the model rather than to the choice.
* Accounts payable enters scope, which is the symmetric case and the first test of whether this
  generalizes beyond receivables.
