---
status: "proposed"
kind: "requirement-driven"
date: 2026-10-25
decision-makers: [Geoff]
---

# ADR-0079: The QuickBooks round trip imports what the web client's reader read from the fixture

**Requirements served:** `IMP-01`, `IMP-02`, `IMP-05`, `IMP-08`, `IMP-09`, `NFR-01`.

## Context and Problem Statement

[ADR-0078](0078-the-quickbooks-fixture-is-ours-and-a-sandbox-validates-it.md) puts a synthetic
company's QuickBooks Online export in `tests/fixtures/quickbooks/`: five archives, each holding
the reports Export Data writes, beside the trial balance at every month end and a catalog of the
cases the company contains. Every archive agrees with what a QuickBooks sandbox reports for the
same postings, and the accrual one with a real download cell for cell. What the fixture is for is
still unexercised: whether CFOKit, given that export, ends up holding the books QuickBooks holds.

Answering it takes two programs in two languages.

* **The reader is TypeScript, in the web client.** It runs where the file is, in the person's
  browser ([ADR-0058](0058-getting-started-is-one-path-on-the-web.md)), and turns an archive into
  the neutral shape the import endpoints take
  ([ADR-0041](0041-import-is-parsed-where-the-file-is.md)). The server never sees an archive.
* **The import and the books are Python, in the server.** The import endpoints land the shape,
  and the reconciliation compares the books with what the source states (`IMP-08`). Their tests
  run inside the compose network, against Postgres as a role that does not own the tables
  ([ADR-0018](0018-local-compose-dev-and-production.md)), and
  write the shape by hand.

The catalog's checks fall on both sides of that line. A damaged file is refused by the reader. A
balance at a month end, a journal total that agrees, a divergence that nets to zero, an entry
whose description survived, a row the import plan declines — each is a fact about CFOKit's books
after the import, and the figures they are compared with are QuickBooks'.

[ADR-0054](0054-the-web-client-lives-in-web.md) lets `web/` read nothing from outside itself but the
API contract and, to publish, the design system, so the reader cannot read the fixture as things
stand, and ADR-0078 names that boundary as one to widen by its own record. CI runs the client's
checks in a Node job and the integration suite in a Python image with no Node in it, and ADR-0054
holds that a change on one side needs no toolchain from the other. A reading of the accrual
archive is the shape for 1,785 transactions and 41 accounts.

## Decision Drivers

* The reader under test is the one that ships, not a copy of it.
* Every expected value comes from outside the implementation (ADR-0036 § 5): QuickBooks' own
  figures, as the validation record says they were agreed, and the outcomes the catalog states.
* Each side keeps its own toolchain: a Python change needs no Node, a client change no Python
  (ADR-0054), and CI runs with no credentials and calls no third party (ADR-0004).
* The two sides meet at an interface that already exists, rather than a new one.
* A change to the reader is reviewable as a change to what CFOKit receives.
* The checks run on every commit, as a test does, not on a person's machine.

## Considered Options

* The reader's reading of each archive is committed beside it; a web test holds the readings
  current and checks refusals; an integration test imports each reading and runs the catalog's
  checks against CFOKit's books
* Each archive imported through the getting-started pages, end to end, in a browser
* A second reader, in Python, so the whole round trip runs in the integration suite
* The reader run inside the integration suite, by adding Node to its image, or by handing CI's
  web job's readings to the integration job
* The reader checked against the fixture in the web tests alone

## Decision Outcome

Chosen option: "The reader's reading of each archive is committed beside it", because it tests the
reader that ships against the import that ships, with each side in its own toolchain and the two
meeting at the shape the import endpoints already take.

> `web/` reads each archive in `tests/fixtures/quickbooks/archives/` and writes what it read, as
> `read.json`, beside it. A web test fails when a committed reading is not what the reader reads
> now. An integration test imports each reading through the import endpoints and runs every catalog
> check against CFOKit's books and QuickBooks' figures.

### 1. What `web/` reads and writes

A script in `web/` reads every archive and writes its reading beside it: the neutral shape and the
company the reader found, or the refusal it gave. It is the only thing in `web/` that reads or
writes outside it besides the contract and the design system. The client's build and the reader
itself do not change: the script hands the reader the file's bytes, as the getting-started page
does.

### 2. What the web tests check

* **That every reading is current.** The test reads each archive again and compares with the
  committed reading; a difference names the script to run.
* **That a damaged file is read as the catalog says.** Each file case's mutation of the accrual
  archive is made at test time, as ADR-0078 § 2 requires, and the reader refuses it with the
  catalog's code or reads it as the undamaged one. The mutations exist in Python, where the
  generator makes them, and are written again in TypeScript, not shared: there is no shared code
  between the two languages, and each is a few lines over a zip.

### 3. What the integration test checks

It creates a company for each reading, imports the reading through the import endpoints as a
person would — open, entries, reconcile — and runs each catalog case's check for that archive:

* `balance` — CFOKit's balance for the account at the month end equals the trial balance the
  archive carries for that date.
* `stated` — the figure the reading took from a statement equals the one the archive states.
* `account` — the chart CFOKit holds has the account, of the type, with the name and parent, or
  does not.
* `text` — an entry carrying the description, byte for byte, is in CFOKit's books, or is not.
* `skipped` — the import plan declines the row with the refusal code.
* `reconciliation` — the reconciliation's journal total agrees or does not, and its divergences
  are none, net to zero, or are unexplained.

A check of a kind the test does not run fails rather than passing unexamined. Every row the
import declines must be one that moves nothing, which `IMP-05` shows the person rather than
drops. A case CFOKit cannot hold yet is marked as an expected failure, strictly, with what CFOKit
lacks: it is a finding on record, and the day it passes the suite fails until the mark comes off.

### 4. Where the expected values come from

Never from the reading. A reading is the reader's output: it is what is under test, and a drift
test that holds it current asserts nothing about whether it is right. Each check's expected value
is QuickBooks' — the month-end trial balances and the stated figures, which the validation record
says QuickBooks agreed with — or the outcome the catalog names, which a person reviewed. A reading
regenerated without looking satisfies the drift test and fails every check it got wrong.

### Consequences

* Good, because the shipped reader is tested against the books of a company built to break
  imports, in QuickBooks' real format, and a defect shows up as a failing catalog check.
* Good, because a change to the reader is a diff of `read.json`: the reviewer sees what CFOKit
  will receive differently, transaction by transaction.
* Good, because both checks run in CI as they do today, the web one in Node and the round trip in
  the integration suite, and neither job gains the other's toolchain.
* Good, because the two meet at the import endpoints' own shape, which gate 5 already holds to the
  contract, so the round trip tests the same interface a person's import uses.
* Bad, because every change to the reader or the fixture means running a script and committing
  its output, and the readings add a few megabytes of JSON to the repository.
* Bad, because the mutations exist twice, in Python and TypeScript, and can drift apart. The web
  tests check the TypeScript ones against the catalog's codes, so a drift is a failing case rather
  than a silent one.
* Bad, because the round trip skips the getting-started pages between the reader and the
  endpoints. The browser test of those pages, over the reader's own synthetic export, stays.
* Neutral, because the reader's unit tests keep `synthetic.ts`, small enough to read.

### Confirmation

* The web tests fail when a committed reading differs from what the reader reads, and when a
  mutated archive is not read as its catalog case says.
* The integration test fails for any catalog case whose check fails, and for any check of a kind
  it does not run.
* `web/CLAUDE.md` and ADR-0054 § 2 name `tests/fixtures/quickbooks/` as the one place `web/` reads
  and writes besides the contract and the design system. That `web/` touches nothing else outside
  itself is review, as before.

## Pros and Cons of the Options

### The reader's reading committed beside each archive, checked on both sides

* Good, because each side tests what it owns, in the toolchain it already has, against expected
  values neither side computed.
* Good, because the readings make a reader change reviewable as a change in the books.
* Bad, because the readings are a generated artifact to keep current, and the mutations are
  written twice.

### Each archive imported through the getting-started pages, end to end

The truest path: the file is chosen on the page, read in the page's worker, and imported by the
page's own calls, exactly as a person does it.

* Good, because nothing between the file and the books is skipped or stood in for.
* Bad, because it runs in a browser against a running stack for each of five archives of 1,785
  transactions, which makes the slowest CI job slower, and its failures are a browser's.
* Bad, because the checks — 36 month-end balances an archive, the reconciliation, the chart —
  would be written in TypeScript against the API, putting the oracle on the client's side of a
  line where the books are the server's.

### A second reader, in Python

The whole round trip would run in one language and one job.

* Good, because the integration suite would need nothing from `web/`.
* Bad, because it tests a reader nobody ships. The defects that matter are the shipped reader's,
  and a port agrees with the fixture by being written against it, not by being the code a person
  runs.

### The reader run inside the integration suite

The readings would never be committed: the integration job would make them, either with Node in
its image or from an artifact the web job uploads.

* Good, because there is no generated file to keep current.
* Bad, because Node in the test image breaks ADR-0054's rule that a Python change needs no Node,
  for every contributor who runs the suite locally.
* Bad, because handing artifacts between jobs makes the integration job depend on the web job's
  output, so neither runs alone, and what the reader produced is visible only in CI's artifacts,
  never in review.

### The reader checked in the web tests alone

* Good, because it needs nothing from the server and no boundary but the read.
* Bad, because most of the catalog is about CFOKit's books — balances, the reconciliation, what the
  import declines — and the web tests have no books to check.

## More Information

**Follow-on obligations.**

* `web/CLAUDE.md`'s boundary rule, the repository map in `CLAUDE.md`, and ADR-0054 § 2 name
  `tests/fixtures/quickbooks/` alongside the contract and the design system.
* `CONTRIBUTING.md`'s section on the fixture names the script that writes the readings, beside the
  command that regenerates the archives: a change to either is followed by both.
* The integration test image carries `tests/fixtures/quickbooks/`, readings included, and the
  generator's own workbook reader in `scripts/synthetic_books/`, so the round trip reads an
  archive's stated figures with the code that wrote them rather than a second reader.

**Reversal cost.** Low. The script, the readings and the two tests are additions; removing them
leaves the reader and the import as they are, and the fixture as ADR-0078 left it.

Related: ADR-0036 (where expected values come from), ADR-0041 (the neutral shape), ADR-0054 (the
boundary this widens), ADR-0058 (the reader runs where the file is), ADR-0078 (the fixture).

## Revisit when

* The reader moves to the server, which puts both halves in one language and removes the reading.
* A second vendor's reader lands, which adds a reading per vendor and tests whether the round
  trip's checks are vendor-neutral.
* The readings grow past what a review can take in — a fixture several times this company's size —
  at which point they are compressed or generated in CI rather than committed.
