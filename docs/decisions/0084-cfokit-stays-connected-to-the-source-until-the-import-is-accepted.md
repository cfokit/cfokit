---
status: "proposed"
kind: "requirement-driven"
date: 2026-10-28
decision-makers: [Geoff]
---

# ADR-0084: CFOKit stays connected to the system it imports from until the import is accepted

**Requirements served:** `IMP-08`, `IMP-18`, `IMP-25`, `NFR-16`.

## Context and Problem Statement

An import brings a company's books from the system it is leaving, and its reconciliation compares
CFOKit's books with the source's as of the last day of history (`IMP-08`,
[ADR-0050](0050-the-import-oracle-is-basis-free.md)). Accepting the import completes the
switch-over: after it, the company is done with the source.

Between the pull and acceptance the company's books in the source can still change, and the company
needs to see CFOKit's books agree with them before it accepts.

While it imports through the source's API, CFOKit holds a connection to the source system, and
keeps its archive current through change tracking ([ADR-0083](0083-a-quickbooks-online-import-reads-the-api.md) § 5).

## Decision Drivers

* The company accepts the import once it is satisfied that CFOKit's books agree with the source's.
* A change made in the source before acceptance reaches CFOKit's books, rather than being lost.
* Differences found by a check, per account and per document, not by a person reading two sets of
  reports.
* Done with the source at acceptance: no connection, and no credential, after it.

## Considered Options

* Stay connected to the source until the import is accepted, checking again as it changes
* Disconnect as soon as the pull completes

## Decision Outcome

Chosen option: "Stay connected to the source until the import is accepted, checking again as it changes",
because it is the only option in which what the company accepts agrees with what its source holds
when it accepts it.

> CFOKit stays connected to the system it imports from, such as QuickBooks Online, until the
> person accepts the import. While connected, change tracking keeps the archive current, and CFOKit
> checks its books against the source's again and reports every difference. Accepting the import
> completes the switch-over: CFOKit disconnects, and the company is done with the source.

### 1. What is checked

The trial balance by account and the open invoices and bills by document: the comparisons an
import's tie-out makes ([ADR-0082](0082-a-quickbooks-online-import-requires-the-aging-reports.md))
and its reconciliation records (`IMP-08`), run again on what changed, and on request.

### 2. How the source is read

From the import's archive, kept current through change tracking (ADR-0083 § 5). Where the source
has no suitable API, the same check reads a fresh file export, with the file import's reader.

### 3. At acceptance

As ADR-0083 § 5 and § 6 set out: the source's closing date is set, a last change capture and a last check
run, the connection is revoked and its credential deleted, and the import skill is turned off.

### Consequences

* Good, because what the company accepts agrees with its source on the day it accepts it.
* Good, because a difference is found by the check and named by account or document.
* Good, because a source without a suitable API can still be checked, through its files.
* Bad, because CFOKit holds the source's credential until the import is accepted.
* Bad, because change tracking looks back only 30 days, so a connection left longer than that
  between checks pulls again (ADR-0083 § 5).

### Confirmation

Once built, a company is imported from the sandbox (ADR-0078), a change is made in the sandbox
before acceptance, and the check reports it by account and by document until CFOKit's books carry
it. After acceptance, the connection and its credential are gone.

## Pros and Cons of the Options

### Stay connected to the source until the import is accepted, checking again as it changes

* Good, because changes before acceptance are carried, and agreement is shown when the company
  accepts.
* Bad, because the credential is held until acceptance.

### Disconnect as soon as the pull completes

* Good, because the credential is held only for the pull.
* Bad, because a change made in the source after the pull is missed, and nothing shows agreement
  when the company accepts.

## More Information

**Reversal cost.** Low. The check writes nothing to either system's books.

Related: ADR-0050 (the import's reconciliation), ADR-0082 (the tie-out), ADR-0083 (the connection
and the archive).

## Revisit when

* A source's API cannot read what the check needs.
