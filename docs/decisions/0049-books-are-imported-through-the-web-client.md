---
status: "proposed"
kind: "requirement-driven"
date: 2026-09-29
decision-makers: [Geoff]
---

# ADR-0049: Books are imported through the web client, which reads the export, not through a model

**Requirements served:** `IMP-01`, `IMP-05`, `IMP-08`, `IMP-09`, `NFR-01`.

## Context and Problem Statement

An operator onboards by landing their company's history from the system it already runs. The
surface they work in is a Claude chat, and CFOKit is hosted: nothing runs on the operator's
machine but a browser and the Claude app.

[ADR-0041](0041-import-is-parsed-where-the-file-is.md) § 6 makes the model the bridge for that
case. The export is attached to the chat, the skill's reader parses it in the sandbox, and the
model re-emits every transaction as MCP tool arguments, because the sandbox cannot open a socket
to CFOKit. That route has three properties the operator pays for on every onboarding.

**It spends a model on deterministic work.** Parsing an export and posting its entries has one
right answer and no judgement in it. [ADR-0040](0040-import-is-the-first-module.md) states the
principle: a model carrying transactions "is a lossy pipe that adds nothing to the operation it is
carrying". For a real export of 5,556 transactions and 11,580 posting lines, the model emits about
74,000 tokens (measured, ADR-0041 § 6) and first reads the reader's output, which is the same
information — an estimated 150,000 tokens in all, and minutes of generation a person watches.

**It has a ceiling inside the population it serves.** Everything the model reads and emits stays
in one conversation, at an estimated 27 tokens per transaction. On a 200,000-token context that
caps an import near 6,000–7,000 transactions, less whatever the conversation already holds. A
small business recording 50–100 transactions a month produces 6,000–12,000 in ten years, so the
ceiling falls among ordinary, long-lived customers rather than outliers. The read-side figure is
an estimate; the route has not been measured end to end against the ceiling.

**Every figure is retyped.** `IMP-08`'s reconciliation catches a mistyped amount as a divergence,
so transcription error is detected rather than silent — but it is still introduced, and `NFR-01`
allows no tolerance for it to be carried.

What § 6 rests on is that the sandbox is the only thing near the file that cannot reach CFOKit.
A browser tab is also near the file, and can — and CFOKit has a web client
([ADR-0048](0048-cfokit-has-a-web-client.md)).

## Decision Drivers

* No model in the path of a deterministic transfer (ADR-0040).
* No ceiling that an ordinary small business's history can reach.
* The untrusted archive stays out of the process that serves every tenant (`NFR-04`, ADR-0041 § 3).
* Works against a hosted deployment with nothing installed on the operator's machine.
* Importing remains a person's own act (ADR-0040 § 7, ADR-0042).
* Operable by someone who runs a business: no terminal, no path, no script.
* Nothing copyleft shipped to the operator's machine (`CLAUDE.md`, Licensing).

## Considered Options

* A web-client page reading the export in the browser with a dependency-free reader
* The same page, running the skill's Python reader under Pyodide
* Upload the archive to the server and parse it there
* Keep the model as the bridge (ADR-0041 § 6)
* An MCP App rendered inside the Claude chat

## Decision Outcome

Chosen option: "A web-client page reading the export in the browser with a dependency-free
reader", because it removes the model from a transfer that needs none while
keeping every property ADR-0041 chose parsing-where-the-file-is for.

> Import is a page of the web client. It reads the export in the browser and posts the neutral
> `SourceBooks` shape to the existing REST import endpoints as the signed-in person. The model's
> part is to hand the operator the link and, afterwards, to explain the reconciliation. The MCP
> import tools that carried transactions are retired.

### 1. The reader runs in the browser, and has no dependencies

A `.xlsx` export is a zip of XML. The browser has both halves natively: `DecompressionStream`
with the `deflate-raw` format (Baseline, widely available since May 2023) and `DOMParser`. The
page's reader is a JavaScript port of the skill's, carrying the same bounds — 100 MB archive,
300 MB expanded, 64 members, a document type declaration refused — because the archive is still
somebody else's file, now opened in its owner's browser rather than our process.

**Two readers is the cost**, and it is paid for with a test rather than accepted on trust: CI runs
both against the synthetic export and requires identical `SourceBooks`. A divergence between them
is a failed build, not a customer's wrong books.

### 2. The reconciliation is recorded, and the model reads it back

The page posts the source's stated balances with the reconciliation request, which is the shape
the endpoint already takes. The result is stored with the import — the source's claims and the comparison, append-only,
in the imports module — and a read-only MCP tool returns it. The operator goes back to the chat
and the model explains what agreed and what did not, which is the part of an import a model is
for.

The page must handle, whatever it looks like: signed out; choosing a file; a file the reader
refuses, with the bound it crossed; the summary of what will be created and what will not
(`IMP-05`); confirmation; progress through the batches, resumable after a dropped connection;
the reconciliation; and the way back to the conversation.

The skill offers the page as a link built from configuration, never from a request header
(`PUBLIC_BASE_URL`, ADR-0004).

### 3. The model-as-bridge route is retired, not kept as a fallback

`open_import` and `import_entries` leave the MCP surface, and the skill loses its `--mcp` mode.
ADR-0041 argued that "a convenience kept alongside a supported route becomes a supported route by
accident", and kept § 6 only because a sandboxed runtime had no other way in. A runtime with a
browser has one, and the Claude app is such a runtime. Keeping § 6 would keep its ceiling as a
live path a customer could hit after the page existed.

The REST endpoints and ADR-0041 §§ 1–5 are unchanged: the neutral shape is still the contract,
and a script posting it is still a client like any other.

### Consequences

* Good, because an import costs no tokens and no generation time, and the transfer is exact.
* Good, because there is no ceiling short of the reader's own bounds: at the measured 10 ms per
  transaction, 100,000 transactions post in under twenty minutes, resumable because ADR-0029's
  derived keys make a repeated batch a replay.
* Good, because the untrusted archive still never reaches a shared process.
* Good, because the operator needs a browser and nothing else, against any deployment.
* Good, because import becomes the first page of the web client rather than a special case.
* Bad, because there are two readers, and every change to the export format lands in both.
* Bad, because the operator leaves the chat for a tab and comes back; nothing links the tab back
  to the conversation.
* Bad, because the published MCP contract loses two tools (gate 5, ADR-0015).
* Neutral, because a model can still read and reason about the imported books; only the transfer
  moved.

### Confirmation

* CI runs the JavaScript reader and the Python reader over the synthetic export and requires
  identical output — ADR-0036 layer 3, the same way the Python reader is already tested as a
  client.
* `tests/test_published_contracts.py` pins the MCP surface without `open_import` and
  `import_entries`.
* The import endpoints already refuse a delegated token (`not_a_person`); the page's token is the
  person's own, so that check is the enforcement and nothing new is added.

## Pros and Cons of the Options

### A web-client page reading the export in the browser with a dependency-free reader

* Good, because it meets every driver.
* Good, because it adds no dependency to the server or to the page.
* Bad, because the reader exists twice.

### The same page, running the skill's Python reader under Pyodide

The strongest case for a browser page: one reader, the same code the skill ships, no port.

* Good, because the format is understood in one place.
* Bad, because Pyodide is MPL-2.0 (verified against the project's repository, release 314.0.7), and
  serving it to the operator's browser ships weak copyleft to their machine, which `CLAUDE.md`
  excludes. Loading it from Pyodide's CDN instead avoids distributing it and makes every
  deployment — self-hosted ones included — depend at runtime on a third party's CDN.
* Bad, because it is roughly a 10 MB download before the first byte of the export is read.

### Upload the archive to the server and parse it there

The conventional shape, and the simplest for the operator: a file input and a submit button.

* Good, because one reader, in Python, running where CI tests it.
* Bad, for every reason ADR-0041 rejected it: an untrusted archive in the process serving every
  tenant (a genuine export compresses 1.08:1; a hostile one 1,029:1), plus an object store behind a
  portability protocol, a worker entrypoint and a polling loop.

### Keep the model as the bridge (ADR-0041 § 6)

* Good, because it is built, tested, and needs no new surface.
* Good, because the operator never leaves the chat.
* Bad, because of the context's three costs — waste, ceiling and retyping — and the ceiling alone
  disqualifies it once an alternative exists.

### An MCP App rendered inside the Claude chat

An MCP server can declare an interactive UI that a supporting host renders inside the
conversation. It would give this page's behaviour without the operator leaving the chat.

* Good, because it removes the one consequence this decision is worst at: the round trip to a tab.
* Bad, because it is unverified here whether Claude Desktop renders such a UI with the network
  access and the person's own token that posting an import requires. A decision resting on an
  unverified host capability is a guess.
* Bad, because it ties the import to a host feature; the page works from any browser.

## More Information

**Follow-on obligations.**

* The MCP service learns the page's address from a variable within the existing environment shape;
  `infra/README.md` names it (ADR-0016 requires no record for a variable within the shape).
* A migration for the recorded reconciliation, in the imports module's tables.
* `skills/bookkeeper/SKILL.md` offers the link and reads the reconciliation back; the `--mcp` mode
  and its instructions are removed. `docs/connect-claude-desktop.md` follows.
* The page's layout is designed in Claude Design against the states in § 2.

**Reversal cost.** Low to medium. The page and the JavaScript reader are additive and could be
removed. Restoring § 6 means restoring two published tools and the skill's `--mcp` mode, which is
a contract change but not a data change: books imported either way are identical.

Related: ADR-0048 (the web client this is a page of), ADR-0040 (the principle this restores),
ADR-0041 (§ 6 superseded; §§ 1–5 unchanged), ADR-0015 (the contract change), ADR-0036 (the
differential test).

## Revisit when

* Claude Desktop is verified to render an MCP App that can post an import as the signed-in person,
  which is the trigger for moving this page inside the conversation.
* The differential test between the two readers fails more than once for the same kind of export
  change, which says one reader should be generated from the other or retired.
* A second source system's reader lands, which doubles the cost of two readers per source.
* A customer's export exceeds a reader bound, which is the first real measurement of where the page's
  limits are.
