---
status: "proposed"
kind: "requirement-driven"
date: 2026-10-28
decision-makers: [Geoff]
---

# ADR-0083: An import reads the source's API where it has a suitable one, and its file export where it does not

**Requirements served:** `IMP-01`, `IMP-02`, `IMP-03`, `IMP-08`, `IMP-09`, `AR-16`, `LED-17`.

## Context and Problem Statement

A company moving to CFOKit creates a new entity and brings its books from the system it runs.
QuickBooks Online, like most of its competitors, offers two ways to read them:

* **A file export.** QuickBooks Online's Export Data carries every transaction, but no
  payment-to-invoice links and no list of what is open
  ([ADR-0078](0078-the-quickbooks-fixture-is-ours-and-a-sandbox-validates-it.md)). So pre-switch
  history presents on accrual even for a cash-basis company
  ([ADR-0080](0080-a-cash-basis-report-recognizes-an-obligation-as-it-is-settled.md) § 3), the
  part of an open item paid before the switch is settled on the last day of history
  ([ADR-0081](0081-an-import-brings-what-is-open-at-the-cutover-as-open-obligations.md)), and the
  person runs the aging reports beside it
  ([ADR-0082](0082-a-quickbooks-online-import-requires-the-aging-reports.md)).
* **The source's API.** QuickBooks Online's Accounting API is reported by secondary sources to
  carry an open balance on each invoice and bill, and on each payment the transactions it applies
  to. CFOKit already reads that API in development, to validate the QuickBooks fixture against a
  sandbox (ADR-0078).

Sources differ in what they offer. Xero, Zoho Books and FreshBooks each have an export and an API
of their own. What each one carries is unverified here, and is established when that source's
import is built.

An API import holds a third-party credential. [ADR-0040](0040-import-is-the-first-module.md) kept
import an in-process module because it held none, and named a QuickBooks API sync holding vendor
credentials as what would earn separation (ADR-0022's blast-radius driver).
[ADR-0062](0062-a-bank-feed-is-synchronized-by-cfokit-itself.md) synchronizes bank feeds in
CFOKit's own process through a provider protocol.

## Decision Drivers

* Books in CFOKit as faithful to the source's as the source allows: every document, with its
  links (`IMP-02`, `AR-16`, `LED-17`).
* Nothing retyped, and no report run by hand where the source can be read directly (`IMP-09`).
* Every source importable, whatever it offers: an API is not universal, and a person may decline
  to connect one.
* One import, whatever it reads, checked the same way (`IMP-08`).

## Considered Options

* The source's API where it has a suitable one, its file export as the fallback
* The file export only
* The API only

## Decision Outcome

Chosen option: "The source's API where it has a suitable one, its file export as the fallback",
because the API gives the most faithful books, and the file export keeps every source and every
person able to import.

> An import connects to the source's API where the source has one that carries what an import
> needs, and reads the source's file export where it does not, or where the person declines to
> connect.

### 1. The API import

The person creates the entity in CFOKit, signs in to the source and authorizes CFOKit to read it.
CFOKit imports the chart of accounts, the customers and vendors, and every transaction, with each
open invoice and bill and the links between payments and what they pay. Open balances and links
come from the source, so no aging report is run (ADR-0082), and pre-switch history on a cash basis
uses real payment dates rather than ADR-0081's synthetic settlement.

### 2. The file import

The same import, with less to read. For QuickBooks Online it is Export Data and the aging reports
(ADR-0081, ADR-0082), and any further standard report that recovers what Export Data lacks. What
the files cannot carry is stated on the import's reconciliation, not inferred (`NFR-16`).

### 3. Each source by its capabilities

Each source's import offers the API path where that source's API carries what an import needs, and
the file path always.

The same connection is what a parallel run checks CFOKit against
([ADR-0084](0084-a-parallel-run-records-each-transaction-in-both-systems.md)).

### Consequences

* Good, because a company that connects its source gets its history with links, so a cash-basis
  company's pre-switch statements can be right, not only its post-switch ones.
* Good, because the person runs no reports by hand on the API path.
* Good, because a source without a suitable API, or a person who will not connect one, can still
  import.
* Bad, because CFOKit holds a source's OAuth credential, which ADR-0040 names as the reason an
  import would be separated from the process holding database credentials.
* Bad, because the API path depends on each vendor's API, its app requirements and its rate limits.
* Bad, because a source with both paths has two readers to maintain.

### Confirmation

* Before this record is accepted, the open questions are verified against Intuit's developer
  reference.
* Once built, the fixture's events posted to the sandbox (ADR-0078) are imported through the API
  and through the file export, and the two results are compared: the same books, with the links
  the file import lacks.

## Pros and Cons of the Options

### The source's API where it has a suitable one, its file export as the fallback

* Good, because each company gets the most faithful books its source allows.
* Bad, because a source with both paths has two readers.

### The file export only

* Good, because each source has one reader, and CFOKit holds no third-party credential.
* Bad, because Export Data carries no links, so a cash-basis company's pre-switch history presents
  on accrual, and the person runs extra reports by hand.

### The API only

* Good, because each source has one reader, and the books are the most faithful.
* Bad, because a source without a suitable API, or a person who will not connect one, cannot
  import at all.

## Open questions

Each must be verified against Intuit's developer reference before this record is accepted:

* That `Invoice.Balance`, `Bill.Balance` and `LinkedTxn` on payments behave as secondary sources
  report.
* The OAuth app and rate-limit requirements.

And one for CFOKit's own design: whether the importer is an in-process module, as ADR-0062's bank
feed is, or a separate component under ADR-0022 § 3, as ADR-0040 anticipates for a credential like
this one.

## More Information

**Reversal cost.** Low for the decision, which writes nothing itself. The links an API import
records are append-only in the books it landed, so a different rule reaches only later imports.

Related: ADR-0040 (import as a module, and what would separate it), ADR-0062 (a synchronized feed),
ADR-0078 (the sandbox), ADR-0080 to ADR-0082 (what the file import cannot do), ADR-0084 (a
parallel run).

## Revisit when

* Intuit's developer reference contradicts any of the open questions.
* A second source's import is built, the first test of whether the two paths generalize.
