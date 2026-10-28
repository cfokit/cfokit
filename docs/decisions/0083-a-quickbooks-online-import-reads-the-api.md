---
status: "proposed"
kind: "requirement-driven"
date: 2026-10-28
decision-makers: [Geoff]
---

# ADR-0083: A QuickBooks Online import is a component that archives the API, with its own skill, and exports as tie-out evidence

**Requirements served:** `IMP-01`, `IMP-02`, `IMP-03`, `IMP-08`, `IMP-09`, `IMP-10`, `IMP-11`, `IMP-12`, `IMP-13`, `IMP-14`, `IMP-15`, `IMP-16`, `IMP-17`, `IMP-18`, `IMP-19`, `IMP-20`, `IMP-21`, `IMP-22`, `IMP-23`, `IMP-24`, `IMP-25`, `AR-16`, `LED-17`.

## Context and Problem Statement

Owners arrive at CFOKit with years of QuickBooks Online (QBO) history. The first import is the
founder's own company: eight years of history, to be moved at full fidelity, including uploaded
documents and the evidence that the books were right.

What the QBO Accounting API provides, per Intuit's documentation:

* Queries return at most 1,000 entities per response. No documented limit on how far back a query
  can reach.
* Limits: 500 requests per minute per company, 10 requests per second per company and app.
  Exceeding a limit returns HTTP 429; Intuit says to wait 60 seconds before retrying.
* Change Data Capture (CDC) looks back at most 30 days and returns at most 1,000 objects per
  request, with no paging. Deleted entities come back with a status of `Deleted`.
* Payment application (which invoice or bill a payment settled) is on the payment's lines, as
  `LinkedTxn`, with each line's amount. The sandbox also shows an invoice's and a bill's own
  `LinkedTxn` naming their payments. No report shows it.
* `Balance` on an Invoice or Bill is the remaining open amount. QBO computes it.
* Attachments are `Attachable` records, each with its file name, content type, size, a download
  URI, and links to the records it is attached to.

What the API does not provide:

* The Banking "For review" queue of downloaded bank-feed lines. Intuit support confirms there is no
  API for it.
* The Receipts "For review" queue of uploaded receipts not yet matched to a transaction. No API
  found.
* The audit log. It exists only in the QBO interface, and Intuit keeps audit events for two years.
* Reconciliation statement ending balances. These appear only in reconciliation reports, which QBO
  cannot export to Excel directly.

QBO's Settings, then Export Data produces Excel files for the General Ledger, Profit and Loss,
Balance Sheet, Trial Balance, and Journal, plus customer, vendor, and employee lists
([ADR-0078](0078-the-quickbooks-fixture-is-ours-and-a-sandbox-validates-it.md) records their
layout). They carry no payment application and no list of what is open, which is what the file
import works around
([ADR-0081](0081-an-import-brings-what-is-open-at-the-cutover-as-open-obligations.md),
[ADR-0082](0082-a-quickbooks-online-import-requires-the-aging-reports.md)).

An import that reads the API holds a third-party credential for as long as it runs.
[ADR-0040](0040-import-is-the-first-module.md) kept import an in-process module because it held
none, and named a QuickBooks API sync holding vendor credentials as what would earn separation:
isolated credentials are one of ADR-0022 § 3's criteria for a separate component. Every file import
already posts the published neutral shape to CFOKit's import endpoints
([ADR-0041](0041-import-is-parsed-where-the-file-is.md) § 1).

## Decision Drivers

* Full fidelity: every record for every year, with payment application, attachments and record
  identity.
* A mapping error fixed by reading again what was stored, never by pulling again or losing data.
* Fidelity proven, year by year, not asserted.
* The owner does only what the API cannot.
* The QuickBooks credential held apart from the process that holds the database's, and never in a
  model's context.
* A job done once costs nothing once it is done.

## Considered Options

* A component that archives the API, with its own skill, and exports as tie-out evidence
* A skill whose scripts do the pull
* Import from file exports first, then sync through the API
* Import from the General Ledger report
* API only, with no tie-out
* Import as permanent MCP tools

## Decision Outcome

Chosen option: "A component that archives the API, with its own skill, and exports as tie-out
evidence", because it is the only option that keeps everything QBO holds, proves the result
against QBO's own figures, and keeps the credential out of every process that does not need it.

> A QuickBooks Online import is a separate component with its own skill. The component pulls every
> entity type for every year through the API into an append-only archive of the raw responses,
> with every attachment, and builds the import from the archive; QBO's exports are evidence that
> the books tie out. The skill guides the owner through what the API cannot supply. The connection
> ends at the approved switch-over.

### 1. The API archive is the source

Pull every entity type for every year through the API. Store the raw responses unmodified in an
append-only archive. Build the CFOKit ledger by parsing the archive, so a mapping error is fixed by
re-parsing, never by re-pulling or by losing data. What the parse builds reaches CFOKit through its
import endpoints, as a file import's does.

### 2. Every attachment is captured

Download every Attachable's file. Store its link to its transaction, verify its size against the
Attachable's `Size`, and record a SHA-256 checksum. Reconcile the count against QBO's attachment
list. Files are stored as the company's other files are, once per company per checksum
([ADR-0076](0076-conversations-and-their-files-are-stored-in-core.md)).

### 3. The owner supplies what the API cannot

In this order:

1. Export the audit log first, since events older than two years are already gone and more expire
   daily.
2. Clear the bank-feed and Receipts review queues in QBO before the switch-over.
3. Supply reconciliation statement dates and ending balances as a CSV. Saving reconciliation
   reports as PDFs is optional evidence.
4. Run Export Data once per fiscal year.
5. Record bank rules.

### 4. Fidelity is proven, not asserted

A deterministic check compares CFOKit's trial balance with QBO's at every fiscal year-end. Any
difference, to the cent, blocks the switch-over and names the year.

### 5. The archive stays current until the approved switch-over

Changes made during the pull are captured by CDC from the archive's start timestamp. While CFOKit
stays connected to QBO ([ADR-0084](0084-cfokit-stays-connected-to-the-source-until-the-import-is-accepted.md)), CDC
runs at least every 30 days, since it looks back no further; past that, the changed entities are
pulled again. The switch-over completes when the import is accepted: QBO's closing date is set, a
last CDC and a last comparison run, and the connection is revoked and its credential deleted.

### 6. A component, with its own skill

**The component** is a separate component under ADR-0022 § 3, for its credential: an entrypoint of
the one image, as the agent is. It holds the QBO credential for one company only, and the credential
never enters a model's context, a log or a job's output. Its operations are fixed entry points whose
parameters are validated before anything runs. The pull runs in the background, survives failures
and resumes without repeating completed work. Its checks return structured results, pass or fail
with details, which the agent explains to the owner but cannot override. The owner connects QBO in
the browser, where a credential for another service is entered
([ADR-0068](0068-cfokit-optimizes-for-the-persons-own-agent.md) § 2).

**Its skill** (`SKILL.md`, in the Claude plugin's folder format) guides the owner through the steps
in § 3 and reads the component's status. It is enabled for a company when the import starts and
disabled at the switch-over
([ADR-0075](0075-cfokit-s-agent-is-an-async-component-built-on-pydantic-ai.md) § 4). The same skill
folder serves self-hosters using the Claude plugin.

### 7. Without the API

A QBO company that will not connect, and a source whose API does not carry what an import needs,
import through files instead (ADR-0081, ADR-0082), with what the files lack stated on the import's
reconciliation (`NFR-16`). Another source gets this component's shape where its API allows.

### Consequences

* Good, because the archive and attachments make the import auditable: a CPA or auditor can trace
  any imported entry to its raw source and its documents.
* Good, because the credential lives only in the component, for one company, until the switch-over.
* Bad, because audit history older than two years at the time of export cannot be imported. That is
  a QBO retention limit, not a CFOKit choice.
* Bad, because items left in QBO's review queues at the switch-over are not imported.
* Bad, because the hosted tier needs Intuit production keys, which require completing Intuit's app
  assessment questionnaire.
* Bad, because self-hosters register their own Intuit developer account and app and obtain their
  own production keys, including completing the app assessment questionnaire. Self-host setup
  documentation must walk them through it.
* Bad, because storage grows with attachments. Eight years of receipts is the expected worst case
  for an early customer.
* Bad, because a component is one more deployable to run and keep working.

### Confirmation

* Before this record is accepted, each open question is settled by testing against the founder's
  company, and this record is updated.
* Once built, the fixture's events posted to the sandbox (ADR-0078) are imported through the
  component: every year-end trial balance agrees, the attachment count agrees, and a difference
  planted in the sandbox blocks the switch-over and names its year.

## Pros and Cons of the Options

### A component that archives the API, with its own skill, and exports as tie-out evidence

* Good, because nothing QBO's API holds is lost, and a mapping error costs a re-parse.
* Good, because the credential is isolated in one process.
* Bad, because it is the most to build: a component, an archive, and a skill.

### A skill whose scripts do the pull

* Good, because one folder holds the instructions and the code.
* Bad, because the scripts would have to run in the agent, which acts only during a person's turn
  and stores no token (ADR-0075, [ADR-0077](0077-the-agent-acts-with-a-token-exchanged-from-the-persons.md)),
  or in core, with which a skill never shares code
  ([ADR-0014](0014-single-tool-surface-hosted-backend-only.md)). An eight-year pull needs neither.

### Import from file exports first, then sync through the API

* Good, because the first import needs no connection.
* Bad, because report exports are not expected to carry entity Ids or payment links, so every
  exported row would need matching to an API entity before CDC updates could apply. That matching
  is error-prone, and it adds a second import path.

### Import from the General Ledger report

* Good, because it is one file.
* Bad, because it loses payment application, attachment links, and record identity.

### API only, with no tie-out

* Good, because it is the least to build.
* Bad, because nothing would prove the imported books match QBO.

### Import as permanent MCP tools

* Good, because the agent reaches them as it reaches every other tool.
* Bad, because tool schemas sit in context whenever the server is connected, for a job done once.

## Open questions

Settle each by testing against the founder's company, then update this record.

1. Do queries return transactions from all eight years?
2. Does the TransactionList report's `cleared` parameter reliably identify reconciled
   transactions? The only source is a third party.
3. Do unmatched receipts in the Receipts review queue appear as Attachables?
4. Do Export Data files carry entity Ids? If they do, exports could do more than tie-out.
5. Batch request size: Intuit's limits page recommends at most 30 payloads per batch, and its batch
   guide says 10. Use 10 until tested.
6. How do voided transactions appear in CDC? Intuit's docs are silent.
7. Does the API cover payroll detail and sales tax filing history?

And for CFOKit's own design:

8. How the pull's background work maps onto existing infrastructure: ADR-0061's queue runs core's
   unattended work.
9. How the agent learns the pull finished: the component noting it in the conversation, or the
   agent checking on the person's next turn (ADR-0077).
10. Where the archive is stored: in Postgres, the only store
    ([ADR-0003](0003-postgres-as-sole-storage-backend.md)), behind the published API as ADR-0076
    stores files, or in the component's own tables.
11. How the agent reaches the component's operations: as tools on the published MCP surface
    (ADR-0014), or as the component's own.

## More Information

**Follow-on obligations.** The published import shape carries payment application, open balances
and attachment links, which is a contract change (ADR-0015). The skill ships in `skills/cfokit/`.
Self-host setup documentation covers registering an Intuit app.

**Reversal cost.** Moderate once built: the archive and the books built from it stay with the
company. While proposed, low.

Related: ADR-0040 (import as a module, and what would separate it), ADR-0041 (the neutral shape),
ADR-0050 (the import's reconciliation), ADR-0075 (skills enabled per company), ADR-0076 (files),
ADR-0081 and ADR-0082 (the file import), ADR-0084 (connected to QBO until the import is accepted).

**Sources.**

* API call limits and throttles:
  https://developer.intuit.com/app/developer/qbo/docs/learn/limits-and-throttles
* Batch operation:
  https://developer.intuit.com/app/developer/qbo/docs/learn/explore-the-quickbooks-online-api/batch
* ChangeDataCapture reference: https://developer.intuit.com/docs/api/accounting/changedatacapture
* Change data capture guide:
  https://developer.intuit.com/app/developer/qbo/docs/learn/explore-the-quickbooks-online-api/change-data-capture
* Invoice reference:
  https://developer.intuit.com/app/developer/qbo/docs/api/accounting/most-commonly-used/invoice
* Basic invoicing implementation (payment LinkedTxn):
  https://developer.intuit.com/app/developer/qbo/docs/develop/basic-implementations/basic-invoicing-implementation
* Attach images and notes:
  https://developer.intuit.com/app/developer/qbo/docs/workflows/attach-images-and-notes
* Publish your app (production keys):
  https://developer.intuit.com/app/developer/qbo/docs/go-live/publish-app
* Intuit support, no API for the bank-feed review queue:
  https://help.developer.intuit.com/s/question/0D5TR00001VhrZq0AJ/
* Audit log retention:
  https://quickbooks.intuit.com/learn-support/en-us/help-articles/learn-about-the-audit-log/00/262225
* Reconciliation reports cannot export to Excel directly:
  https://quickbooks.intuit.com/learn-support/en-uk/banking/reconcile-accounts/00/239072
* Export Data contents: https://community.intuit.com/articles/1770643
* Reconciled status via TransactionList (third party):
  https://satvasolutions.com/blog/reconciled-transactions-quickbooks-online-api

## Revisit when

* An open question's answer contradicts a decision here.
* Intuit changes its limits or the CDC window.
* A second source's import is built, the first test of whether this shape generalizes.
