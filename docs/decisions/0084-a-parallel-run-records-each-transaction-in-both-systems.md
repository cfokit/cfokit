---
status: "proposed"
kind: "requirement-driven"
date: 2026-10-28
decision-makers: [Geoff]
---

# ADR-0084: A parallel run records each transaction in both systems, and CFOKit checks itself against the source

**Requirements served:** `IMP-08`, `NFR-16`.

## Context and Problem Statement

A company moving to CFOKit can switch at once, or run CFOKit beside the system it is leaving until
it trusts CFOKit's books. A parallel run is the established way to prove a new system before
relying on it: the same transactions go into both systems, and their results are compared until
the company is confident enough to stop using the old one.

An import is checked once: its reconciliation compares CFOKit's books with the source's as of the
last day of history (`IMP-08`, [ADR-0050](0050-the-import-oracle-is-basis-free.md)). After that,
nothing compares CFOKit with the system the company is leaving.

An API import already holds a connection to the source
([ADR-0083](0083-a-quickbooks-online-import-reads-the-api.md)), and can read its reports and its
documents.

## Decision Drivers

* CFOKit used in full during the run, entry and matching included, because that is what the
  company will rely on after it switches.
* Differences found by a comparison, per account and per document, not by a person reading two
  sets of reports.
* The run ends when the company decides.

## Considered Options

* Record each transaction in both systems, and check CFOKit against the source
* A one-way sync from the source into CFOKit
* A two-way sync between the two systems
* Offer no parallel run, and switch at once

## Decision Outcome

Chosen option: "Record each transaction in both systems, and check CFOKit against the source",
because it is the only option that uses CFOKit in full before the company relies on it, and the
comparison says where the two disagree.

> A company may run CFOKit and its source in parallel before it switches. Each transaction is
> recorded in both systems, and CFOKit reads the source and reports every difference between the
> two systems' books, until the company stops using the source.

### 1. What is compared

For each period the company closes, the trial balance by account and the open invoices and bills
by document: the comparisons an import's tie-out makes
([ADR-0082](0082-a-quickbooks-online-import-requires-the-aging-reports.md)) and its reconciliation
records (`IMP-08`), made again at each close.

### 2. How the source is read

Through the connection the API import made (ADR-0083). Where the source has no suitable API, the
same comparison reads a fresh file export of the period, with the file import's reader.

### Consequences

* Good, because CFOKit is used in full, entry and close included, before the company relies on it.
* Good, because a difference is found by the comparison and named by account or document.
* Good, because a source without a suitable API can still be compared, through its files.
* Bad, because each transaction is recorded twice for the length of the run.
* Bad, because a transaction recorded on different days in the two systems reads as a difference
  until both periods close.
* Bad, because CFOKit holds the source's credential for the length of the run.

### Confirmation

Once built, a CFOKit entity is run in parallel with the sandbox (ADR-0078) over a period of the
fixture's events, and a difference planted in one system is reported by account and by document.

## Pros and Cons of the Options

### Record each transaction in both systems, and check CFOKit against the source

* Good, because both systems are used as the company uses them.
* Bad, because of the second entry.

### A one-way sync from the source into CFOKit

* Good, because nothing is entered twice.
* Bad, because every transaction is entered in the source first, so CFOKit's entry, matching and
  coding are never used. Only the monthly close is exercised, which proves little about the system
  the company will rely on.

### A two-way sync between the two systems

* Good, because each transaction is entered once, in either system.
* Bad, because it makes two sources of truth, with conflict handling for every record both can
  change.

### Offer no parallel run, and switch at once

* Good, because nothing is entered twice and no credential is held after the import.
* Bad, because nothing checks CFOKit against the source after the import, so a difference surfaces
  only when someone happens to find it.

## Open questions

* Who records each transaction in the source during the run: the person, as a parallel run
  usually works, or CFOKit through the source's API, which spares the second entry but writes to
  the system CFOKit is checked against.

## More Information

**Reversal cost.** Low. The comparison writes nothing to either system's books.

Related: ADR-0050 (the import's reconciliation), ADR-0082 (the tie-out), ADR-0083 (the connection).

## Revisit when

* A company's run ends early because of the second entry, which answers the open question.
* A source's API cannot read what the comparison needs.
