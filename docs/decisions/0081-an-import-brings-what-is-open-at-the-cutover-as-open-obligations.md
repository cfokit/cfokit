---
status: "proposed"
kind: "requirement-driven"
date: 2026-10-26
decision-makers: [Geoff]
---

# ADR-0081: An import marks each invoice and bill open at the switch as owed, on its own imported transaction

**Requirements served:** `IMP-02`, `IMP-03`, `IMP-05`, `IMP-07`, `IMP-09`, `AR-16`, `LED-15`, `LED-17`, `NFR-16`.

## Context and Problem Statement

A QuickBooks Online import lands the company's whole history: every transaction its journal
carries, up to the last day of history (`IMP-02`). After the switch the company runs on CFOKit, and
the invoices and bills still unpaid are paid there.

**An imported invoice is not owed to CFOKit.** The import posts each transaction as it was
recorded, and QuickBooks' Export Data names no invoice a payment applies to
([ADR-0078](0078-the-quickbooks-fixture-is-ours-and-a-sandbox-validates-it.md) records its layout,
checked against real downloads). So a payment after the switch has nothing to settle. The
receivables ledger arrives empty, which `IMP-03` exists to prevent, and on a cash basis
([ADR-0080](0080-a-cash-basis-report-recognizes-an-obligation-as-it-is-settled.md)) a December
invoice paid in January is December income and the January payment recognizes nothing.

**How migrations carry open items, as the vendors and practitioners document it:**

* Xero's official conversion guide enters each unpaid invoice and bill at its original date and due
  date, at the unpaid balance only, with ordinary line accounts; a partly paid item is entered at
  its remaining balance
  ([Enter unpaid invoices and bills for your conversion balances](https://central.xero.com/s/article/Enter-unpaid-invoices-and-bills-for-your-conversion-balances)).
* Xero's conversion journal nets the pre-conversion transactions account by account, so balances
  match the old trial balance, which is how it avoids counting them twice
  ([The accounting behind Xero conversion balances](https://central.xero.com/s/article/The-accounting-behind-Xero-conversion-balances)).
* No vendor's official documentation (Xero, Intuit, Zoho, Sage, FreshBooks, Wave) gives a
  procedure specific to a cash-basis company. Cash-basis practitioner guidance (QuickBooks
  Community, the Odoo forum) and Wave's official FreshBooks-to-Wave guide put open items on their
  real income and expense lines, never on equity or a clearing account.
* QuickBooks-to-NetSuite consultant practice loads a summary trial balance and re-enters the open
  items at their open balance against a clearing account
  ([Load financials and open transactions from QuickBooks to NetSuite](https://optimaldataconsulting.com/resources/load-financials-and-open-transactions-from-quickbooks-to-netsuite)).
  It serves accrual companies and assumes history stays behind in QuickBooks.

**CFOKit keeps the history in the ledger.** The invoice an open-item list names is already there as
a posted entry, and the ledger can mark it: the import posts through `record_transaction`, which
raises an obligation carried by the one account whose postings sum to its amount
([ADR-0059](0059-a-line-is-matched-before-it-is-coded.md) § 3), and records settlements against
it ([ADR-0037](0037-accounting-basis-is-a-presentation-property.md)).

## Decision Drivers

* Follow the established practice: open items carried at their unpaid balance, with their original
  dates and their real lines.
* Count nothing twice: the books after the import are the books the source holds, on either basis.
* A payment after the switch settles what it pays, so on a cash basis its income or expense is
  recognized then (`AR-16`), and an accrual company's figures do not move.
* One rule for accrual and cash-basis companies.
* Nothing inferred and nothing retyped (`NFR-16`, `IMP-09`).

## Considered Options

* Mark each open document's own imported transaction as owed, at its open balance
* Opening balances plus re-entered open items at their open balance against a clearing account
* The same, with a cash-basis company's open items on their real lines
* Opening balances only, with no open items

## Decision Outcome

Chosen option: "Mark each open document's own imported transaction as owed", because it carries
each open item as the established practice does, at its unpaid balance with its original dates and
real lines, without re-entering a document the imported history already holds.

> The importer keeps full history and marks each invoice and bill open at the switch as owed, on
> that document's own imported transaction. It creates no opening-balance documents, clearing
> account, placeholder customers or vendors, or netting journal, for accrual and cash-basis
> companies alike.

### 1. What an open document keeps

Each open document keeps its original date, due date, number, counterparty and real income and
expense lines, because it is the imported transaction itself.

### 2. What it owes

The owed amount is its open balance at the last day of history. The obligation is raised on the
document's transaction for the amount it carries, and the part paid before the switch is settled by
a synthetic settlement dated the last day of history, or dated the real payment where it is known,
as an API import would supply ([ADR-0083](0083-a-quickbooks-online-import-reads-the-api.md)).

### 3. What a payment after the switch does

It settles the document. On a cash basis the income or expense is recognized at that payment, on
the document's own lines (ADR-0080). On accrual nothing moves: the document's lines stay on its
date.

### 4. An open item that matches nothing, or more than one

Matching is one to one, as a bank line's is
([ADR-0059](0059-a-line-is-matched-before-it-is-coded.md) § 2): a transaction is claimed by one
open item at most. Two open items alike in everything the aging shows, such as two payments of one
amount from one customer on one day, claim two transactions. An item that matches no transaction,
or whose candidates differ in anything else the books record, refuses the import, naming the item,
since which transaction is open would be a guess. Xero, likewise, will not save conversion balances
until the unpaid invoices and bills support A/R and A/P
([Enter conversion balances](https://central.xero.com/s/article/Enter-conversion-balances)).
Nothing is guessed (`IMP-05`, `NFR-16`).

### 5. Where the document is kept

The ledger's obligation holds the transaction, the account and the amount, and knows nothing about
customers or vendors ([ADR-0022](0022-tiny-ledger-modules-and-components.md)). An open invoice is recorded in the
receivables module, on its imported transaction, with its customer, number, and issue and due
dates. An open bill is recorded the same way in a payables module, with its vendor.

### 6. In another currency

An open item in a currency other than the entity's functional currency is refused, as any foreign
amount is (`LED-15`, `IMP-07`).

Where the open items come from, and how they are checked, is
[ADR-0082](0082-a-quickbooks-online-import-requires-the-aging-reports.md).

### Consequences

* Good, because a payment after the switch settles the invoice it pays, so the receivables ledger
  is not empty and a cash-basis company's first months recognize income when it is paid.
* Good, because nothing is counted twice and no netting entry rebuilds by hand what history already
  contains.
* Good, because one rule serves accrual and cash-basis companies.
* Bad, because the synthetic settlement moves the cash-basis timing of the part paid before the
  switch to the last day of history when the real payment date is unknown, so periods already
  reported may differ slightly on a cash basis from QuickBooks.
* Bad, because invoices fully paid before the switch have no payment-to-invoice links from
  Export Data, so cash-basis reports of pre-switch history are not fixed by this decision (see
  ADR-0083).
* Bad, because the write path takes a settlement only with a payment of its own, and a synthetic
  settlement has none; changing that needs a person's review.
* Bad, because obligations are append-only once raised: a wrongly marked document is corrected by
  reversal.
* Bad, because an open bill needs a payables module to keep its vendor and due date.

### Confirmation

* The fixture writes A/R Aging Detail and A/P Aging Detail as of the books' last day, validated
  against the sandbox and a real download (ADR-0078); the catalog adds an item partly paid before
  the switch.
* The round trip ([ADR-0079](0079-the-quickbooks-round-trip-imports-what-the-reader-read.md))
  checks that each open item owes its open balance, that a payment after the import settles it, and
  that a cash-basis profit and loss recognizes that payment's share of the document's own lines. A
  file case checks that an open item matching no imported transaction is refused.

## Pros and Cons of the Options

### Mark each open document's own imported transaction as owed, at its open balance

* Good, because the open item is the original document, counted once, right on both bases.
* Bad, because the part paid before the switch needs a synthetic settlement, dated by assumption
  where the real date is unknown.

### Opening balances plus re-entered open items at their open balance against a clearing account

The QuickBooks-to-NetSuite consultants' practice.

* Good, because it is a documented practice an accountant may already know.
* Bad, because it duplicates documents already in the imported history.
* Bad, because a cash-basis company's payment after the switch settles a clearing line, so no
  income is recognized (`AR-16`).

### The same, with a cash-basis company's open items on their real lines

* Good, because a payment after the switch recognizes income on a cash basis.
* Bad, because it still duplicates the original imported invoices, and needs a netting entry per
  account to offset them, rebuilding by hand what history already contains.

### Opening balances only, with no open items

* Good, because it is the least to import.
* Bad, because a payment after the switch has nothing to settle, and a cash-basis company's income
  from invoices open at the switch is lost.

## More Information

**Follow-on obligations.** The neutral shape and the import endpoints carry the mark of an open
document, which is a contract change (ADR-0015). The write path takes a synthetic settlement, after
review. The fixture and the round trip gain the cases in Confirmation.

**Reversal cost.** Moderate. Obligations an import raised stay with the books it landed; a
different rule applies to imports after it.

Related: ADR-0037 (obligations and settlements), ADR-0080 (what an open item means on a cash
basis), ADR-0082 (the open-item list), ADR-0083 (an API import).

## Revisit when

* An API import (ADR-0083) delivers real payment dates, which replaces the synthetic settlement.
* A real company's import is refused for an open item that matches no imported transaction, and the
  source's own records explain the item.
* `LED-16` activates or `IMP-07` changes, so that an open item can carry its own currency.
* An import of opening balances without history is built.
