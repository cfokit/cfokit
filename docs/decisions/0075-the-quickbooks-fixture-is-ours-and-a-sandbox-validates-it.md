---
status: "proposed"
kind: "requirement-driven"
date: 2026-10-22
decision-makers: [Geoff]
---

# ADR-0075: The QuickBooks fixture is ours, written from business events, with a sandbox as its validator

**Requirements served:** `IMP-01`, `IMP-02`, `IMP-08`, `NFR-01`, `NFR-14`.

## Context and Problem Statement

The QuickBooks reader is tested against `web/src/quickbooks/synthetic.ts`: two transactions, written
by hand in the shape we believe QuickBooks writes. Its expected values are honest — known from its
rows before the reader runs (ADR-0036 § 5) — but its *format* is our belief about QuickBooks. It
cannot catch the reader being wrong about QuickBooks, which is how an import actually goes wrong: a
void kept in the journal at zero, an overpayment left as an unapplied credit, an inactive account
printed under another name, a fiscal year that starts in July. Each would be written the way we
think it looks.

Contributors need a fixture large enough to exercise those cases together — a company's three
years, not two rows — committed in the repository, so CI and anyone with a checkout can run it with
no account anywhere (ADR-0004, gate 2).

Three constraints narrow what that fixture can be:

* **No real books.** A real export, or anything derived from one, is ADR-0044's Tier B: lawful to
  consult, never an oracle, never committed.
* **No QuickBooks output in the repository.** Intuit's Developer Terms of Service (as of
  2025-10-14) forbid distributing the Services "or any output thereof, in any manner not permitted
  under this Agreement" (§ 3.1), grant no right to "reproduce, redistribute … without Intuit's prior
  written consent" (§ 2.2), and confine the sandbox to "creation, testing, and internal evaluation"
  (§ 7.2). Nothing in them permits committing an export or a report the sandbox produced. Under
  ADR-0044 a license question is answered by a check, never by our own judgment, so the answer is no.
* **Export Data has no API.** The `.xlsx` archive the reader takes is produced only by a person in
  the QuickBooks interface. The Reports API returns the same reports' content as JSON, with none of
  the file's layout: no header rows, no indentation as leading spaces, no formula cells, no basis
  printed in a footer — all of which the reader depends on.

## Decision Drivers

* An expected value comes from outside the implementation (ADR-0036 § 5, `NFR-01`).
* Nothing real, and nothing QuickBooks produced, is committed (ADR-0044, the terms above, `NFR-14`).
* CI runs with no cloud credentials and calls no third party (ADR-0004).
* No second accounting system becomes the answer key; that is `LED-18`'s deferred oracle
  (ADR-0010).
* Regenerable and reviewable: a change to the company is a diff in source, not a new binary from
  nowhere.
* The seam that carries the business must be plain enough that a Xero or Sage adapter could be
  added without changing what generates it (`NFR-12`, ADR-0041 § 1).

## Considered Options

* Generate the fixture ourselves from business events; validate it against a sandbox the generator's
  events were posted to
* Pin the sandbox's own export and reports in the repository
* Use the sandbox only to find defects, and keep the hand-written fixture
* Extend the hand-written fixture with no sandbox at all
* Anonymize or transform a real export
* Build an independent ground-truth ledger from the events and compare against it

## Decision Outcome

Chosen option: "Generate the fixture ourselves from business events; validate it against a sandbox",
because it is the only option in which the committed file is wholly ours while its correctness rests
on QuickBooks rather than on us.

> A seeded generator writes a small business as platform-neutral events. One adapter turns them into
> QuickBooks API payloads; our own writer turns them into the export. The payloads are posted to a
> sandbox, and the export is valid when its content agrees with what QuickBooks reports for those
> postings. Only our files, and the record that QuickBooks agreed, are committed.

### 1. The events are the source, and they are neutral

The generator emits business events — "a client pays $400 more than invoice 1042" — in business
terms, with amounts as decimal strings and every reference symbolic. It knows nothing about
QuickBooks. The QuickBooks adapter is the only consumer that does, and it maps events to API
payloads and nothing else, so a second vendor is a second adapter over the same events. A catalog
names every case the company must contain, and each event carries the catalog ids it realizes.

### 2. The fixture is written by us

The committed archive — Journal, General Ledger, Profit and Loss, Balance Sheet, Trial Balance — and
the month-end trial balances beside it are written by our own code from the events. They are our
expression; nothing in them was produced by QuickBooks.

### 3. QuickBooks validates content through the API, and layout once by hand

**Content** is validated on every render: the payloads are posted to a sandbox company that started
empty, and each report's rows, accounts, sections and figures — at every month end for the trial
balance, on the accrual basis — must equal what the Reports API returns. A payload QuickBooks
rejects means an event was modeled wrong, and the generator is fixed, never the post.

**Layout** is validated by comparing our archive with one Export Data download, cell by cell, after
decoding each sheet into rows of cells, with a named list of cells that differ by nature (the time a
report was run). This is repeated only when QuickBooks changes its export format. Bytes are never
compared: an archive's timestamps, compression and style tables differ between any two writers, and
between two exports of the same company.

QuickBooks' responses and its download stay on the machine that ran the check. What is committed is
a validation record: the hash of the archive validated, the date, and the result.

### 4. Agreement proves the file, not the accounting

Agreement with QuickBooks shows that our fixture is what QuickBooks would write for those events,
and therefore that a reader passing it reads QuickBooks correctly. It does not show CFOKit's
accounting is right; that stays with the conformance corpus (ADR-0050 § 3).

### Consequences

* Good, because the reader is tested against a company built to contain the cases that break
  imports, in QuickBooks' real format, with no real company and no QuickBooks output in the
  repository.
* Good, because CI needs nothing but the repository, and the fixture regenerates byte for byte from
  the seed.
* Good, because routine validation is a script against the API; only a format change needs a person.
* Bad, because every figure in the fixture is our arithmetic. It is evidence only because QuickBooks
  agreed with it at the recorded validation, and a fixture changed after that is unvalidated until
  the next one.
* Bad, because our writer must reproduce QuickBooks' presentation rules — ordering of a day's
  transactions, which rows a report prints — learned by comparison, and a rule it never exercised is
  a rule it may have wrong.
* Bad, because the fixture covers only what QuickBooks accepts. A colon in an account's own name, or
  one name as both customer and vendor, cannot be posted, and the catalog records the nearest form
  QuickBooks allows.
* Bad, because validating at all means using the sandbox to compare against QuickBooks, which
  § 3.1's benchmarking clause may reach. That is for review before the first validation run, not
  settled here.
* Neutral, because `synthetic.ts` stays: it is the reader's unit fixture, small enough to read.

### Confirmation

A unit test regenerates the events, payloads and manifest and requires them identical to what is
committed; the same test fails when a catalog id has no event, or a data case's events reached no
payload. A test fails when the committed archive's hash differs from the last validation record's,
so a generator change without a validation run is visible.

**Not gated:** that the sandbox started empty, and that no QuickBooks output was committed. Both are
review at validation time.

## Pros and Cons of the Options

### Generate the fixture ourselves; validate it against a sandbox

* Good, because the file is ours and its correctness is QuickBooks'.
* Bad, because the writer is real work, and its presentation rules are learned rather than known.

### Pin the sandbox's own export and reports in the repository

The most faithful option: QuickBooks' own file, byte for byte, with QuickBooks' own trial balances as
the expected values.

* Good, because nothing about the format is our belief.
* Bad, because it distributes output of Intuit's Services, which § 3.1 and § 2.2 of the terms do not
  permit without written consent, and ADR-0044 does not let us decide that question ourselves.

### Use the sandbox only to find defects, and keep the hand-written fixture

ADR-0044's Tier B route: render locally, find where the reader is wrong, and land each finding as a
fix plus a test on our own small fixture.

* Good, because it needs no writer and commits nothing from anyone else.
* Bad, because no committed fixture contains the cases together, so contributors and CI have nothing
  to run, and evidence of each finding lives only with whoever ran the sandbox.

### Extend the hand-written fixture with no sandbox at all

* Good, because it is cheap and needs no account anywhere.
* Bad, because its format is our belief about QuickBooks, which is the thing under test.

### Anonymize or transform a real export

* Good, because it is maximally realistic.
* Bad, because a derived real export is Tier B (ADR-0044), and anonymization is a judgment that fails
  silently.

### Build an independent ground-truth ledger from the events

* Good, because it is fully automated and needs no third party.
* Bad, because its expected values are our arithmetic checked against our arithmetic (ADR-0050), and
  a second system as an oracle is `LED-18`'s decision, deferred (ADR-0010).

## More Information

**Follow-on obligations.**

* The reader, in `web/`, reads only `docs/contracts/openapi.json` from outside itself (ADR-0054).
  Running it over a fixture in `tests/fixtures/quickbooks/` needs that boundary widened, which is its
  own record, written when the reader first reads the fixture.
* Validation credentials come from the environment and are never committed, logged or printed.
* The benchmarking clause of the terms is read by a person before the first validation run.

**Reversal cost.** Low. The generator, adapter and writer are development tooling outside `src/`,
and the fixture is data. Abandoning the sandbox leaves a hand-written fixture of a different size,
which is where the repository already is.

Related: ADR-0036 (the provenance rule), ADR-0044 (what may be committed), ADR-0050 (what agreement
with QuickBooks proves), ADR-0041 (the neutral shape this mirrors on the reading side).

## Revisit when

* Intuit grants written consent to publish sandbox output, which makes pinning QuickBooks' own files
  the stronger option.
* QuickBooks changes the Export Data format, or a customer's export disagrees with the fixture's
  layout.
* A second adapter lands, which tests whether the events are neutral or QuickBooks-shaped.
* `LED-18` activates.
