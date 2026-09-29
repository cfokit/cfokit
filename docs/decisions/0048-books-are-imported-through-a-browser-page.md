---
status: "proposed"
kind: "requirement-driven"
date: 2026-09-29
decision-makers: [Geoff]
---

# ADR-0048: Books are imported through a browser page that reads the export, not through a model

**Requirements served:** `IMP-01`, `IMP-05`, `IMP-08`, `NFR-01`, `NFR-19`.

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
A browser tab is also near the file, and can.

## Decision Drivers

* No model in the path of a deterministic transfer (ADR-0040).
* No ceiling that an ordinary small business's history can reach.
* The untrusted archive stays out of the process that serves every tenant (`NFR-04`, ADR-0041 § 3).
* Works against a hosted deployment with nothing installed on the operator's machine.
* Importing remains a person's own act (ADR-0040 § 7, ADR-0042).
* Operable by someone who runs a business (`NFR-19`): no terminal, no path, no script.
* ADR-0012's objections to a web UI — its own auth, session handling, XSS surface and design work
  — are answered rather than waived.
* Nothing copyleft shipped to the operator's machine (`CLAUDE.md`, Licensing).

## Considered Options

* A browser page served by CFOKit, reading the export in the browser with a dependency-free reader
* The same page, running the skill's Python reader under Pyodide
* Upload the archive to the server and parse it there
* Keep the model as the bridge (ADR-0041 § 6)
* An MCP App rendered inside the Claude chat

## Decision Outcome

Chosen option: "A browser page served by CFOKit, reading the export in the browser with a
dependency-free reader", because it removes the model from a transfer that needs none while
keeping every property ADR-0041 chose parsing-where-the-file-is for.

> CFOKit serves one page, `/import`, from the REST service. The page reads the export in the
> browser, signs the person in, and posts the neutral `SourceBooks` shape to the existing REST
> import endpoints. The model's part is to hand the operator the link and, afterwards, to explain
> the reconciliation. The MCP import tools that carried transactions are retired.

### 1. One page, and only this page

ADR-0012 gates a web UI because it is a second product surface. This is one page with one job, and
the gate is answered clause by clause:

* **Auth** is the issuer's. The page runs the authorization code flow with PKCE against a public
  client, as the person. CFOKit still issues nothing and operates no login (`IAM-10`).
* **Session handling** does not exist. The token is held in page memory for the duration of the
  import and never written to storage or a cookie; closing the tab ends it. That is ADR-0041 § 5's
  "one sign-in per run, nothing cached", in a browser.
* **XSS.** The page is static HTML and a script of our own, served with
  `Content-Security-Policy: default-src 'self'` and no third-party script. Text read from the
  export — account names, payees, descriptions — is rendered with `textContent` and never as
  markup, because it is somebody else's file.
* **Design work** is one form: choose the file, see what will be created (`IMP-05`), confirm, watch
  progress, read the reconciliation.

It is not a precedent for a console. A second page needs its own record.

### 2. Served by the REST service, so it is same-origin with the API

The page and the endpoints it calls share `PUBLIC_BASE_URL`, so there is no CORS configuration to
get wrong and nothing to deploy separately — it is part of the one image (ADR-0023) and reaches
the maintained cloud target with the rest.

### 3. The reader runs in the browser, and has no dependencies

A `.xlsx` export is a zip of XML. The browser has both halves natively: `DecompressionStream`
with the `deflate-raw` format (Baseline, widely available since May 2023) and `DOMParser`. The
page's reader is a JavaScript port of the skill's, carrying the same bounds — 100 MB archive,
300 MB expanded, 64 members, a document type declaration refused — because the archive is still
somebody else's file, now opened in its owner's browser rather than our process.

**Two readers is the cost**, and it is paid for with a test rather than accepted on trust: CI runs
both against the synthetic export and requires identical `SourceBooks`. A divergence between them
is a failed build, not a customer's wrong books.

### 4. The reconciliation is recorded, and the model reads it back

The page posts the source's stated balances with the reconciliation request, as the model does
today. The result is stored with the import — the source's claims and the comparison, append-only,
in the imports module — and a read-only MCP tool returns it. The operator goes back to the chat
and the model explains what agreed and what did not, which is the part of an import a model is
for.

The skill offers the page as a link built from configuration, never from a request header
(`PUBLIC_BASE_URL`, ADR-0004).

### 5. The model-as-bridge route is retired, not kept as a fallback

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
* Bad, because there are two readers, and every change to the export format lands in both.
* Bad, because the operator leaves the chat for a tab and comes back; nothing links the tab back
  to the conversation.
* Bad, because the product now has a browser surface to keep secure, however small.
* Bad, because the published MCP contract loses two tools (gate 5, ADR-0015).
* Neutral, because a model can still read and reason about the imported books; only the transfer
  moved.

### Confirmation

* CI runs the JavaScript reader and the Python reader over the synthetic export and requires
  identical output — ADR-0036 layer 3, the same way the Python reader is already tested as a
  client.
* A test asserts the page's `Content-Security-Policy` header and that it loads no script from
  another origin.
* `tests/test_published_contracts.py` pins the MCP surface without `open_import` and
  `import_entries`.
* The import endpoints already refuse a delegated token (`not_a_person`); the page's token is the
  person's own, so that check is the enforcement and nothing new is added.
* Not gated: that text from the export is only ever rendered as text. That is review, backed by the
  CSP.

## Pros and Cons of the Options

### A browser page served by CFOKit, reading the export in the browser with a dependency-free reader

* Good, because it meets every driver.
* Good, because it adds no dependency to the server or to the page.
* Bad, because the reader exists twice.
* Bad, because it is a web surface, however narrow.

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

* A public client for the page in `infra/keycloak/cfokit-realm.json`, authorization code with
  PKCE, its redirect URI under `PUBLIC_BASE_URL`. A deployment sets the redirect for its own
  hostname.
* The MCP service learns the page's address from a variable within the existing environment shape;
  `infra/README.md` names it (ADR-0016 requires no record for a variable within the shape).
* A migration for the recorded reconciliation, in the imports module's tables.
* `skills/bookkeeper/SKILL.md` offers the link and reads the reconciliation back; the `--mcp` mode
  and its instructions are removed. `docs/connect-claude-desktop.md` follows.
* ADR-0012's table gains nothing: the gate stands, and this record is what satisfied it for one page.

**Reversal cost.** Low to medium. The page and the JavaScript reader are additive and could be
removed. Restoring § 6 means restoring two published tools and the skill's `--mcp` mode, which is
a contract change but not a data change: books imported either way are identical.

Related: ADR-0040 (the principle this restores), ADR-0041 (§ 6 superseded; §§ 1–5 unchanged),
ADR-0012 (the gate answered in § 1), ADR-0015 (the contract change), ADR-0036 (the differential test).

## Revisit when

* Claude Desktop is verified to render an MCP App that can post an import as the signed-in person,
  which is the trigger for moving this page inside the chat.
* The differential test between the two readers fails more than once for the same kind of export
  change, which says one reader should be generated from the other or retired.
* A second source system's reader lands, which doubles the cost of two readers per source.
* A customer's export exceeds a reader bound, which is the first real measurement of where the page's
  limits are.
