---
status: "proposed"
kind: "requirement-driven"
date: 2026-10-27
decision-makers: [Geoff]
---

# ADR-0083: A later QuickBooks Online import reads its API, with an optional one-way shadow sync

**Requirements served:** `IMP-02`, `IMP-08`, `IMP-09`, `AR-16`, `LED-17`.

## Context and Problem Statement

A file import from QuickBooks Online's Export Data has two limits that no reading of the file can
remove:

* **It carries no payment-to-invoice links.** So pre-switch history presents on accrual even for a
  cash-basis company ([ADR-0080](0080-a-cash-basis-report-recognizes-an-obligation-as-it-is-settled.md)
  § 3), and the part of an open item paid before the switch is settled on the last day of history
  rather than when it was paid
  ([ADR-0081](0081-an-import-brings-what-is-open-at-the-cutover-as-open-obligations.md)).
* **It holds no list of what is open.** So the person uploads the two aging reports beside it
  ([ADR-0082](0082-a-quickbooks-online-import-requires-the-aging-reports.md)).

QuickBooks Online's Accounting API is reported by secondary sources to carry both: an open balance
on each invoice and bill, and on each payment the transactions it was applied to. CFOKit already
reads that API in development, to validate the QuickBooks fixture against a sandbox
([ADR-0078](0078-the-quickbooks-fixture-is-ours-and-a-sandbox-validates-it.md)).

An API import holds a third-party credential. [ADR-0040](0040-import-is-the-first-module.md) kept
import an in-process module because it held none, and named a QuickBooks API sync holding vendor
credentials as what would earn separation (ADR-0022's blast-radius driver).
[ADR-0062](0062-a-bank-feed-is-synchronized-by-cfokit-itself.md) synchronizes bank feeds in
CFOKit's own process through a provider protocol, and
[ADR-0061](0061-unattended-work-is-a-queue-in-postgres.md) runs unattended work as a queue in
Postgres.

## Decision Drivers

* Real payment-to-invoice links and dates, so pre-switch cash-basis history is right (`AR-16`,
  `LED-17`).
* Nothing retyped and no extra report for the person to run (`IMP-09`).
* One source of truth at every moment.
* The file import kept for platforms and people who will not connect an API.

## Considered Options

* Read QuickBooks Online through its API, with an optional one-way shadow sync until the switch
* Two-way sync between QuickBooks Online and CFOKit

## Decision Outcome

Chosen option: "Read QuickBooks Online through its API, with an optional one-way shadow sync",
because it gives open balances and payment-to-invoice links directly, while QuickBooks stays the one
system of record until the company switches.

> A later importer reads QuickBooks Online through its API. A company may run a shadow period
> first: a one-way, scheduled, read-only sync from QuickBooks into CFOKit, with QuickBooks the
> system of record, until it compares the reports, switches, and the sync stops.

### 1. What the API import replaces

Open balances and payment-to-invoice links come from the API, so no aging upload is needed
(ADR-0082), and pre-switch cash-basis history uses real payment dates rather than the synthetic
settlement of ADR-0081.

### 2. The shadow period

Optional, one-way, scheduled and read-only. CFOKit never writes to QuickBooks. The company compares
CFOKit's reports with QuickBooks' own, then switches; the sync stops at the switch.

### 3. The file import stays

The file import (ADR-0081, ADR-0082) remains for other platforms and for people who will not
connect the API.

### Consequences

* Good, because history arrives with its links, so a cash-basis company's pre-switch statements can
  be right, not only its post-switch ones.
* Good, because the person runs no extra reports.
* Good, because a shadow period lets a company see its books in CFOKit before switching, with
  QuickBooks still in charge.
* Bad, because CFOKit holds a QuickBooks OAuth credential, which ADR-0040 names as the reason an
  import would be separated from the process holding database credentials.
* Bad, because the import depends on Intuit's API, its app requirements and its rate limits.
* Bad, because a scheduled sync is unattended work with its own failure modes, run as ADR-0061
  runs every other.

### Confirmation

* Before this record is accepted, the open questions are verified against Intuit's developer
  reference.
* Once built, the fixture's events posted to the sandbox (ADR-0078) are imported through the API,
  and the result is compared with the file import of the same company: the same books, with links
  the file import lacks.

## Pros and Cons of the Options

### Read QuickBooks Online through its API, with an optional one-way shadow sync

* Good, because links and open balances come from the source directly.
* Good, because a one-way sync keeps one system of record.
* Bad, because it holds a third-party credential and depends on a vendor API.

### Two-way sync between QuickBooks Online and CFOKit

* Good, because a company could work in either system during the shadow period.
* Bad, because it makes two sources of truth, with conflict handling between them for every record
  both can change.

## Open questions

Each must be verified against Intuit's developer reference before this record is accepted:

* That `Invoice.Balance`, `Bill.Balance` and `LinkedTxn` on payments behave as secondary sources
  report.
* Whether a change-tracking endpoint exists for an incremental sync.
* The OAuth app and rate-limit requirements.

And one for CFOKit's own design: whether the importer is an in-process module, as ADR-0062's bank
feed is, or a separate component under ADR-0022 § 3, as ADR-0040 anticipates for a credential like
this one.

## More Information

**Reversal cost.** Low while proposed and unbuilt. Once built, an import's links are append-only
records in the books it landed.

Related: ADR-0040 (import as a module, and what would separate it), ADR-0062 (a synchronized feed),
ADR-0078 (the sandbox), ADR-0080 to ADR-0082 (what the file import cannot do).

## Revisit when

* Intuit's developer reference contradicts any of the open questions.
* A second platform's API import is wanted, which tests whether the shape generalizes.
