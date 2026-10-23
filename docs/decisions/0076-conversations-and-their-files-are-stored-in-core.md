---
status: "proposed"
kind: "requirement-driven"
date: 2026-10-22
decision-makers: [Geoff]
---

# ADR-0076: Conversations and the files in them are the company's records, stored in core's database

**Requirements served:** `PLT-04`, `SOC1-06`, `SOC2-01`, `SOC2-16`, `SOC2-18`, `BKP-19`, `EXP-02`.

## Context and Problem Statement

CFOKit's runtime is a stateless component (ADR-0075). A conversation still has to be kept: the
person's messages, the agent's replies, each tool call and its result, and the files the person
attaches, such as receipts and bank statement PDFs. This record decides where and in what form.

Facts that bear on the answer:

* **A conversation is evidence.** What the model saw and did must be explainable without re-running
  it (`SOC1-06`), and every content source carries its trusted or untrusted classification for as
  long as it is kept (`SOC2-01`).
* **It is the company's.** It is exported with everything else (`EXP-02`), reaches nothing outside
  its company (`PLT-04`, `SOC2-16`), and deletion reaches it (`SOC2-18`). Supporting documents are
  kept seven years (`requirements.md`, retention).
* **A file is linked to what came from it.** A transaction drafted from an uploaded statement
  records what it came from for its life (`BKP-19`).
* **Postgres is the only store** (ADR-0003), and row-level security scopes every company's rows by
  the grants core holds.
* **Pydantic AI's message history serializes to provider-neutral JSON**, with text, tool calls,
  tool results, and file and image parts (ADR-0075).
* **The Messages API accepts a PDF of up to 32 MB and 600 pages** inline in a request, and
  Anthropic's Files API would instead keep a copy with the provider.

## Decision Drivers

* **One set of protections for the company's records**: row-level security, export, retention,
  deletion and the audit row, built once.
* **Exactly what the model saw is recoverable.**
* **No second store, and no second copy with the provider.**
* **The runtime stays stateless and reaches no database.**

## Considered Options

* In core's database, behind the published API, as Pydantic AI's message JSON with files as rows
* In a separate database the runtime owns
* An object store for files, beside Postgres
* Text or Markdown transcripts

## Decision Outcome

Chosen option: "In core's database, behind the published API, as Pydantic AI's message JSON with
files as rows", because a conversation and its files are the company's records, and core is where
every protection the company's records need already holds.

> A conversation is a row in core's database belonging to one company and one person, with an
> append-only sequence of messages, each Pydantic AI's message JSON with the model, its version and
> the skill version that produced it. A file is a row holding its bytes, once per company per
> SHA-256, marked untrusted. Both are read and written only through the published API.

### 1. Messages

Each message is one row: its place in the conversation, its kind, its content as `jsonb` in
Pydantic AI's serialized form, and, for the model's, the model identifier and version and the
skill version. A file in a message is a reference to the file's row, never its bytes. Text is
Markdown as the model wrote it, rendered by the web client. Rows are never edited (ADR-0007's
reasoning applied to evidence), so what the model saw is recoverable.

### 2. Files

A file is stored once per company by its SHA-256, with its media type, size, uploader, the time
it arrived, and its classification, untrusted. Its bytes are `bytea`. It is kept seven years,
exported with its company, and a transaction drafted from it links to it (`BKP-19`). A file is
sent to the model inline with the request that needs it, never through the provider's Files API.
An upload larger than the Messages API accepts, 32 MB, is refused.

Attaching a file to a transaction, an account or a period as its supporting document is `BKP-17`,
still deferred; nothing here builds it, and the row is what it would attach.

### 3. Where it lives

The conversation and file tables are a module in core, scoped by row-level security like every
company's rows, writing one `audit_log` row per change. The runtime and the web client reach them
through the published API, a contract change reviewed at Gate 5.

### Consequences

* Good, because export, retention, deletion, isolation and the audit row hold for conversations
  without being built again.
* Good, because a file and the transaction drafted from it are linked by a key Postgres enforces.
* Good, because the runtime holds no state, and nothing is kept with the provider.
* Bad, because files make the database larger, and its backups with it.
* Bad, because the stored form is Pydantic AI's, so leaving Pydantic AI means converting stored
  messages once.
* Neutral, because `BKP-17` stays deferred; this record stores the files it would attach.

### Confirmation

* Row-level security on both tables, tested in the integration suite as `cfokit_app`.
* A test that a message is never updated, and that a file sent to the model goes inline.
* Gate 5 holds the API's new endpoints to the committed contract.

## Pros and Cons of the Options

### In core's database, behind the published API, as Pydantic AI's message JSON with files as rows

* Good, because it meets every driver.
* Bad, because the database carries the files' bytes.

### In a separate database the runtime owns

The cleanest separation: the runtime's data apart from the books, its schema free to change alone.

* Good, because the runtime's tables could change without a migration in core.
* Bad, because row-level security needs the company's grants, which are core's, so the second
  database would hold a copy that drifts, and export, retention and deletion would be built twice.
* Bad, because a file cannot be referenced by a transaction across databases (`BKP-19`).
* Bad, because the runtime would hold a database credential, which ADR-0022 keeps components from.

### An object store for files, beside Postgres

* Good, because large files are cheaper there, and the database stays small.
* Bad, because it is a second store, which ADR-0003 forbids, with its own access control, backup
  and deletion to keep in step with the rows that reference it.
* Bad, because at a small business's volume, receipts and monthly statements, the database handles
  the bytes without strain.

### Text or Markdown transcripts

* Good, because a person can read one directly.
* Bad, because the tool calls, their results and the file parts are lost or flattened, so what the
  model saw is not recoverable (`SOC1-06`).

## More Information

**Follow-on obligations.**

* The module, its migration, its row-level security and its endpoints in the published API.
* Export covers conversations and files; deletion reaches them.
* A file's classification travels with it into the model's context (`SOC2-01`), which is what lets
  ADR-0075 withhold every posting tool from a conversation that holds it (`PLT-23`).

**Reversal cost.** Low for files, moderate for messages: files can move to a store a later record
admits by copying bytes; messages in Pydantic AI's form are converted once if the framework changes.

Related: ADR-0003 (Postgres only), ADR-0022 (components hold no database), ADR-0047 (an uploaded
line is drafted), ADR-0075 (the runtime).

## Revisit when

* Files are more than half the database's size, or backups slow because of them.
* An upload larger than 32 MB is needed.
* `BKP-17` activates, and a file must attach to more than the conversation it arrived in.
