---
status: "proposed"
kind: "requirement-driven"
date: 2026-10-27
decision-makers: [Geoff]
---

# ADR-0082: A QuickBooks Online file import requires the A/R and A/P Aging Detail reports, and refuses unless they tie

**Requirements served:** `IMP-02`, `IMP-05`, `IMP-08`, `IMP-09`, `NFR-16`.

## Context and Problem Statement

[ADR-0081](0081-an-import-brings-what-is-open-at-the-cutover-as-open-obligations.md) marks each
invoice and bill open at the switch as owed, on its own imported transaction. That needs a list of
what is open, and QuickBooks Online's Export Data holds none. Every download compared for the
fixture ([ADR-0078](0078-the-quickbooks-fixture-is-ours-and-a-sandbox-validates-it.md)) holds the
same eight files: Journal, General Ledger, Profit and Loss, Balance Sheet, Trial Balance, and the
Customer, Vendor and Employee contact lists. None is an aging or open-item report, and the contact
lists carry no balances. The balance sheet and trial balance state the A/R and A/P totals, not which
documents make them up.

QuickBooks Online's A/R Aging Detail and A/P Aging Detail reports list each open document as of a
date. Practitioners report that its Open Invoices report drops invoices paid after the report date,
so it does not state what was open on that date.

Xero requires the unpaid invoices and bills that support A/R and A/P before its conversion balances
can be saved, and uses the trial balance for the day before conversion
([Enter conversion balances](https://central.xero.com/s/article/Enter-conversion-balances)).

## Decision Drivers

* The source's own statement of what is open, never an inference (`NFR-16`).
* Nothing retyped by a person (`IMP-09`).
* Agreement with the source demonstrated before anything is created (`IMP-05`, `IMP-08`).

## Considered Options

* Require both aging reports as of the last day of history, matched and tied out before import
* Infer the open items from the ledger alone
* Import without a tie-out gate

## Decision Outcome

Chosen option: "Require both aging reports as of the last day of history", because it is the only
statement of what is open that QuickBooks Online gives a file import, and the tie-out proves it
before anything is posted.

> A QuickBooks Online file import requires A/R Aging Detail and A/P Aging Detail, run as of the last
> day of history with the aging method set to "Report date". It refuses the import unless they tie.

### 1. Matched to the imported transaction

The importer matches each aging row to its imported transaction by type, number, counterparty and
date.

### 2. Tied out before anything is posted

The import is refused unless the open amounts, totaled customer by customer and vendor by vendor,
tie to the A/R and A/P balances the source states for the last day of history.

### 3. Every kind of open item, the same way

Unapplied customer payments, customer credits, vendor credits and deposits on the aging reports are
carried as open documents are: their own imported transactions, marked open at their unapplied
amount. On a cash basis, money received on account is recognized as
[ADR-0080](0080-a-cash-basis-report-recognizes-an-obligation-as-it-is-settled.md) § 2 sets out.

### 4. Not the Open Invoices report

The Open Invoices report is not accepted as the source, because an invoice paid after its report
date drops off it.

### Consequences

* Good, because what is open is the source's own statement, matched and proven against its
  balances before the import posts.
* Good, because a tie-out failure stops the import rather than landing receivables that disagree
  with the source.
* Bad, because the person exports two more reports, as of the right date and with the right aging
  method, beside Export Data, and the getting-started pages must ask for them.
* Bad, because an aging run as of the wrong day, or with the wrong method, refuses the import until
  it is run again.
* Neutral, because the same aging-as-of-cutover input is expected to apply to other platforms'
  imports; this is unverified for platforms other than QuickBooks Online and Xero.

### Confirmation

* The fixture writes both reports, validated against the sandbox's `AgedReceivableDetail` and
  `AgedPayableDetail` and a real download (ADR-0078).
* The round trip ([ADR-0079](0079-the-quickbooks-round-trip-imports-what-the-reader-read.md))
  checks that every row matches its transaction, and a file case checks that an aging that does not
  tie is refused.

## Pros and Cons of the Options

### Require both aging reports as of the last day of history, matched and tied out before import

* Good, because the source states what is open, and the tie-out proves it.
* Bad, because it is two more exports for the person.

### Infer the open items from the ledger alone

* Good, because Export Data would be enough.
* Bad, because Export Data carries no payment-to-invoice links, so which invoice is open is a guess:
  a payment covering two invoices, two invoices of one amount, a credit applied (`NFR-16`).

### Import without a tie-out gate

* Good, because a partial or mismatched aging still imports.
* Bad, because receivables that disagree with the source would land as fact, and the disagreement
  would surface later, against a customer.

## Open questions

* The exact Aging Detail column set, to confirm against a real export.

## More Information

**Follow-on obligations.** The web client's reader reads both reports; the getting-started pages ask
for them, as of the journal's last day, with the aging method named; the fixture writes and
validates them.

**Reversal cost.** Low. The requirement is in the reader and the import's gate, and nothing it
writes depends on how the list was supplied.

Related: ADR-0081 (what an open item becomes), ADR-0083 (an API import, which would make the upload
unnecessary).

## Revisit when

* An API import (ADR-0083) states open balances directly.
* A second platform's reader lands, the first test of whether the aging-as-of-cutover input
  generalizes.
* QuickBooks Online's Export Data starts including an aging or open-item report.
