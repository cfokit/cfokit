---
status: "proposed"
kind: "requirement-driven"
date: 2026-09-29
decision-makers: [Geoff]
---

# ADR-0050: An import is checked against the journal's own total, and a basis difference must net to zero

**Requirements served:** `IMP-08`, `NFR-01`.

## Context and Problem Statement

`IMP-08` asks an import to produce "a reconciliation the operator can check against the source
system — **balances by account, and totals by period**". Only the first half is built. The second
half is where the answer to a standing problem was sitting.

**The reports in a QuickBooks export are run on whichever basis the company uses, and most small
companies use cash.** The journal is the raw record and is accrual whatever the reports say
(ADR-0037). So the reconciliation compares our accrual balances against their cash-basis ones,
and diverges on exactly the obligation accounts — on a real export, by 25,469.00 appearing as both
the receivable and the income not yet recognised against it.

That divergence is arithmetic rather than a defect, and it has been reported as a finding and
explained by a person every time. `NFR-01` allows no disagreement to be carried, so "a human reads
the note and decides it is fine" is not a resolution — it is a tolerance with a person in it.

The obvious repair is to ask the operator to set QuickBooks to accrual and export again. It is
refused: an operator onboarding a company should not have to reconfigure the system they are
leaving in order to prove the system they are arriving at read the file correctly. The export as
it comes is what has to be checkable.

**Deriving a cash view of our own and comparing like with like is not available either.** ADR-0037
makes the cash view a derivation over stored obligation–settlement links, and an imported journal
carries none — that record names this residue exactly: "a hand-entered journal posting directly to
receivables has no obligation to link to". Inferring the links is what makes QuickBooks' own cash
basis unreliable, and reproducing their inference would be implementing their heuristic in order to
match their output.

## Decision Drivers

* `NFR-01`: "a tolerance is a defect, not a target", and a disagreement is resolved rather than
  carried. A standing explained-away divergence is neither.
* The check must work on the export as the operator already has it.
* `IMP-08`'s purpose is to demonstrate that **the file was read correctly**, not that our
  accounting is right. The second is what the conformance corpus is for (ADR-0036 § 2).
* An oracle must be the source's own arithmetic. Summing the journal ourselves and comparing that
  against our books would be comparing our arithmetic against itself.

## Considered Options

* Reconcile against the journal's stated total, and adjudicate the basis difference arithmetically
* Require the operator to re-export on an accrual basis
* Derive a cash view from the imported journal and compare like with like
* Leave the divergence to be explained by a person each time

## Decision Outcome

Chosen option: "Reconcile against the journal's stated total, and adjudicate the basis difference
arithmetically".

### 1. The journal's own total is an oracle, and it is basis-free

`Journal.xlsx` ends with a `TOTAL` row — 8,480,703.91 against 8,480,703.91 on the export in hand —
and, alone among the files, **prints no accounting basis**, because it is the raw record rather
than a view of one. It is the source's arithmetic over exactly the rows we import.

Checked against the books that export produced, our debits and our credits are 8,480,703.91 each.

This is `IMP-08`'s "totals" half, and it catches what an import actually gets wrong: a row dropped,
an amount misread, a batch posted twice. It is immune to the basis question because the figure it
states has no basis.

It does **not** catch allocation — two accounts transposed total the same. That is what the
per-account comparison is for, and the two are complementary rather than alternatives.

### 2. A cross-basis divergence must net to zero, or it is not the basis

Cash basis excludes whole transactions. An unpaid invoice is a debit to receivables and a credit to
income; dropping it removes both. So whatever the difference between an accrual journal and a
cash-basis report, **it is composed of balanced transactions and must sum to zero in posting
signs**. On the export in hand:

| account | ours − theirs |
|---|---|
| Accounts Receivable (A/R) | 25,469.00 |
| Services | −25,469.00 |
| **net** | **0** |

A set of divergences that nets to zero is consistent with a basis difference and is reported as
one. A set that does not is a defect, and fails. That converts a note a person had to agree with
into an arithmetic check, which is what `NFR-01` means by resolved.

**Necessary, not sufficient, and the record says so rather than overselling it.** A transaction
posted to the wrong account also nets to zero. Three things hold together and none alone is the
claim: the journal total proves every row landed at the right magnitude; the accounts that agree
exactly prove allocation where the basis does not reach; and the netting proves the remainder is
made of whole transactions rather than arithmetic that went astray.

### 3. What this does not claim

It does not establish that the cash-basis figures are right, that our accrual reading of their
journal matches what their accountant would say, or that the books are GAAP-conformant. Those are
`NFR-01`'s "source of truth CFOKit did not author" and belong to the conformance corpus, which
carries published worked examples for exactly that reason (ADR-0036 § 2).

What it establishes is narrower and is the thing `IMP-08` asks for: **the export was read
correctly, and the only remaining difference is one the accounting basis fully explains.**

### Consequences

* Good, because the operator changes nothing about the system they are leaving.
* Good, because the strongest single check is the one that needs no basis at all, so it holds for
  a source that states no basis, states one we do not recognise, or mixes them across reports.
* Good, because `IMP-08`'s "totals" half stops being unimplemented.
* Good, because a divergence that is *not* the basis now fails rather than joining a note a person
  has learned to skim.
* Bad, because the journal total is one figure over the whole file: it proves completeness and
  magnitude and says nothing about which account a row landed in.
* Bad, because netting to zero is necessary and not sufficient, so the check admits a
  wrong-account posting that the per-account comparison happens not to reach.
* Bad, because a source whose raw journal prints no total has only the per-account half, and the
  reader cannot supply one — computing it would be our arithmetic again.

### Confirmation

Integration tests over an import whose journal total is stated: agreement reported when the books
match it, and a failure when a row is dropped or an amount altered — the two ways the total moves.

A test that a set of divergences netting to zero is reported as a basis difference, and one that a
set which does not net fails. The second is the case that would otherwise never be exercised,
because a real export does not produce it.

**Not gated:** nothing forces a reader to emit the stated total where a source prints one. That is
a review rule and a weak one; what is mechanical is that an import stating a total is checked
against it, and that a divergence set which does not net is a failure rather than a note.

## Pros and Cons of the Options

### Reconcile against the journal's stated total, and adjudicate the basis difference arithmetically

* Good, because both halves use only what the export already contains.
* Good, because the basis-free half is the strongest and depends on nothing the source declares.
* Bad, because neither half localises a wrong-account posting on its own.

### Require the operator to re-export on an accrual basis

* Good, because it compares like with like and the divergence disappears entirely.
* Good, because it needs no new code at all.
* Bad, because it asks somebody onboarding to reconfigure the system they are leaving, to prove
  something about the one they are joining. Most small companies keep cash-basis books and have no
  reason to change that.
* Bad, because it makes the evidence depend on an operator following an instruction correctly, and
  an import run against the wrong export looks like a passing reconciliation.

### Derive a cash view from the imported journal and compare like with like

* Good, because it would compare per account, which is where the other options are weakest.
* Bad, because ADR-0037 makes the cash view a derivation over stored obligation–settlement links,
  and an imported journal carries none.
* Bad, because inferring them is what that record rejects as "observably unreliable" — and
  reproducing the incumbent's inference to match the incumbent's output is not evidence about
  anything.

### Leave the divergence to be explained by a person each time

* Good, because it is what happens now and it has never produced a wrong answer.
* Bad, because it is a tolerance with a person in it, which `NFR-01` forbids in terms.
* Bad, because it degrades: a divergence reported on every import is one a reader learns to expect,
  and the first real defect arrives wearing the same clothes.

## Revisit when

* A second reader lands whose source prints no journal total, which tests whether the basis-free
  half generalises or is a QuickBooks convenience.
* Obligation–settlement links exist for imported books, which would make a per-account cash view
  derivable and turn the rejected option into the best one.
* The conformance corpus covers cash-to-accrual conversion, which is where the claim this record
  declines to make actually belongs.
