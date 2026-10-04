---
status: "proposed"
kind: "requirement-driven"
date: 2026-10-04
decision-makers: [Geoff]
---

# ADR-0058: Getting started is one path, on web pages, for both offerings

**Requirements served:** `IAM-05`, `IAM-06`, `IAM-10`, `IAM-22`, `IMP-05`, `IMP-08`, `IMP-09`,
`NFR-19`.

## Context and Problem Statement

A person goes from a call to action to talking about their own books. Between the two they create
an account, create the company, and import its books from the system it already runs. Importing
delivers nothing by itself: it is a chore, and the measure of it is how little of the person it
takes. What earns the rest of the relationship is everything after it.

CFOKit is offered two ways (the vision's commercial thesis). With managed bookkeeping, CFOKit's own
runtime — the web app — keeps the books. With the hosted backend, or a self-hosted one, the
organization brings its own agent, such as Claude Desktop with the bookkeeper skill. Each needs the
same getting-started steps, and a self-hosted build needs them without any commercial step.

The constraints that shape the path:

* **Acquisition is web.** A prospect arrives from a call to action, leaves a name, email and phone
  in a lead system, chooses a plan and subscribes through Stripe — before any agent is involved.
  A self-hosted build has none of that and starts at registration.
* **An account is created on the issuer's page, in the person's browser** (`IAM-10`, `IAM-22`),
  with a password or Google or Microsoft, and MFA. The commercial path arrives there with what the
  lead already gave, filled in.
* **A model must not carry the books.** A 5,556-transaction export rendered for a model is about
  74,000 tokens it re-emits, with a ceiling near 6–7,000 transactions on a 200,000-token context
  (ADR-0041 § 6 measured it).
* **A browser can hand a person to Claude.** `claude://claude.ai/new?q=…` opens Claude Desktop with
  a new chat and a drafted prompt, and `https://claude.ai/new?q=…` does the same on the web. Nothing
  returns a browser tab to a particular chat: the referrer carries no chat path, and an MCP server is
  not told which conversation called it.
* **MCP App panels render CFOKit's own components in an agent's conversation** — probed in Claude
  Desktop (More Information) — and are where the work after getting started happens, in either
  offering's host (ADR-0034 § 4).

## Decision Drivers

* **One path** for both offerings and the self-hosted build, differing only where a step does not
  apply.
* **As little of the person as possible** between subscribing and seeing their own books.
* **No credential near a model** (`IAM-10`), and **no figure through a model**.
* **Acquisition, plan and payment are web**, so getting started should not change surface midway.
* **The first conversation starts with something worth asking.**

## Considered Options

* Getting started on web pages, ending in the agent with the first question drafted
* Getting started in an MCP App panel in the agent's conversation
* Import relayed through the model over MCP tools

## Decision Outcome

Chosen option: "Getting started on web pages", because acquisition, payment and registration are
already web, and finishing the remaining steps there keeps one surface from the call to action to
imported books, for both offerings.

> Getting started — lead, plan, subscription, registration, export, company, import and connecting
> the agent — is one path, on CFOKit's web pages. The work after it happens wherever the agent runs.

### 1. The path

1. **Lead, plan, subscription** — commercial only.
2. **Registration** on the issuer's page: name, email and phone filled in from the lead, or empty
   when self-hosted; a password or Google or Microsoft; MFA.
3. **Export**: the page shows how to export from QuickBooks; the person chooses the file, and the
   page reads it in the browser, in a Web Worker, with the reader's bounds (100 MB archive, 300 MB
   expanded, 64 members, no document type declarations).
4. **Company**: confirm what the export states — name, basis, fiscal year end, currency — and add
   what it does not, such as the time zone (`IAM-05`, `IAM-06`).
5. **Import**: what will be created and what will not, confirmed or abandoned (`IMP-05`); posted in
   batches, resumable because the idempotency keys are derived from the file and the row
   (ADR-0029); reconciled (`IMP-08`), and the reconciliation recorded with the import so a later
   conversation can explain it.
6. **Connect**: with managed bookkeeping, nothing — the web app is the agent's host. With the
   organization's own agent, the page guides adding CFOKit to it.
7. **First question**: the page offers **Continue in Claude**, opening a chat with the first question
   drafted, and the same prompt in a copy block beside it.

### 2. The first question

After an import a person asks whether it all came across, and then how the business is doing. The
drafted prompt asks both:

> My books are imported into CFOKit. Confirm they match QuickBooks and explain any differences, then
> summarize this year's profit and loss and my cash position.

### 3. Retired

* Import through the model: the reader's `--mcp` mode, and `open_import` and `import_entries` as
  MCP tools.
* The skill's Python reader. The web page's reader is the one reader.

### Consequences

* Good, because one surface carries a person from the call to action to imported books, and the
  self-hosted build is the same path with its commercial steps absent.
* Good, because the books move from file to CFOKit with no model reading them.
* Good, because the first conversation opens on the person's own books, with the question they
  were going to ask already written.
* Bad, because a person with their own agent signs in twice — on the web, and when the agent
  connects. The issuer's session in the same browser makes the second a confirmation, not a form.
* Bad, because `claude://` is Claude-specific, and a browser asks "Open Claude?" the first time; the
  copy block is the fallback for any other agent.
* Neutral, because adding a second company to an account that already has one reopens where that
  happens: the agent is already in use by then.

### Confirmation

* The web page's reader is tested against the synthetic export, with expected values from the
  export's own stated balances (ADR-0036 layer 3), and refuses an archive past each bound.
* The import tools leave the published MCP surface; CI gate 5 shows it.
* Not gated: that getting started has no second route. That is review.

## Pros and Cons of the Options

### Getting started on web pages

* Good, because it meets every driver.
* Bad, because it needs one hand-off, to the agent, which a link makes and nothing can make
  seamless.

### Getting started in an MCP App panel in the agent's conversation

Attractive because the probe showed it works: the panel reads a chosen or dropped file, calls
app-only tools the model cannot see, and renders CFOKit's components in both themes.

* Good, because a person with their own agent never leaves the chat after connecting.
* Bad, because acquisition, payment and registration are web regardless, so the path would change
  surface midway.
* Bad, because with managed bookkeeping the web app is the host anyway, so the panel only helps the
  other offering — two paths, not one.

### Import relayed through the model over MCP tools

Attractive because it works today in a sandboxed Desktop chat.

* Bad, because the model re-emits every figure: about 74,000 tokens for 5,556 transactions, with a
  ceiling inside ordinary small-business history.

## More Information

**Follow-on obligations.**

* The web pages for the path, built from the client's components, and the reader in TypeScript.
* The reconciliation record and its read tool, in the imports module.
* The skill points a person with no books to the web page, and stops describing the reader.
* The import tools leave the MCP surface.

**Reversal cost.** Moderate. The pages are the client's components, which also render in a panel,
so moving a step into the conversation is a new shell around the same screens.

**Probes behind the panels** (Claude Desktop, `mcp-remote` 0.14.3, MCP Apps SDK 2.0.1,
2026-10-04), which the work after getting started rests on:

| Probe | Result |
|---|---|
| The panel renders through `mcp-remote` | Rendered, after the person allowed it |
| A file chosen in the panel | Read in the panel: name, size and contents |
| A file dropped on the panel | Read in the panel, the same |
| An app-only tool, called by the panel | Answered |
| The same tool, asked for by the model | Not in the model's tool list: "I searched for it and nothing matches" |
| `ui/update-model-context` | Accepted, with nothing shown |
| `ui/message` | Placed in the person's message box, under a warning, for them to send |
| The client's own components, with their stylesheet and fonts inlined | Rendered as designed: the field, drop zone, progress, notices, money table and buttons |
| Public Sans and Archivo Narrow, inlined as `data:` URIs | Loaded |
| The host's theme, applied as `data-theme` | Followed, light and dark |
| A file `accept` does not allow, dropped on the drop zone | Refused |
| The panel's width | 399 px when it loads, widening after, to the tablet layout |

Supersedes [ADR-0051](0051-books-are-imported-through-the-web-client.md), and § 3 of
[ADR-0049](0049-cfokit-has-a-web-client.md). Related: ADR-0034 (the runtime and what it hosts),
ADR-0041 (the neutral shape and its bounds, which stand), ADR-0029 (derived idempotency keys).

[Open Claude Desktop with a link](https://support.claude.com/en/articles/14729294-open-claude-desktop-with-a-link) ·
[MCP Apps specification](https://github.com/modelcontextprotocol/ext-apps)

## Revisit when

* Adding a second company is designed, which may move steps 3–5 into the agent for an account
  already in use.
* An agent can return a browser tab to a specific chat, which removes the hand-off.
* A host lets an MCP App reply in the conversation as itself, which matters for the panels after.
