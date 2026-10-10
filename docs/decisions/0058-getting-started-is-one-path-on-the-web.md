---
status: "proposed"
kind: "requirement-driven"
date: 2026-10-10
decision-makers: [Geoff]
---

# ADR-0058: Getting started is one path: web pages until the agent is connected, then the conversation

**Requirements served:** `IAM-05`, `IAM-06`, `IAM-10`, `IAM-22`, `IMP-05`, `IMP-08`, `IMP-09`,
`NFR-19`.

## Context and Problem Statement

A person goes from a call to action to talking about their own books. Between the two they create
an account, connect their agent, set up the company, and import its books from the system it
already runs. Importing delivers nothing by itself: it is a chore, and the measure of it is how
little of the person it takes. What earns the rest of the relationship is everything after it.

CFOKit is offered two ways (the vision's commercial thesis). With the hosted backend, or a
self-hosted one, the organization brings its own agent, such as Claude Desktop with the bookkeeper
skill. With managed bookkeeping, CFOKit's own runtime, the web app, hosts the same skills, tools and
panels (ADR-0034 § 4). Each needs the same getting-started steps, and a self-hosted build needs them
without any commercial step.

The constraints that shape the path:

* **Acquisition is web.** A prospect arrives from a call to action, leaves a name, email and phone
  in a lead system, chooses a plan and subscribes through Stripe, before any agent is involved.
  A self-hosted build has none of that and starts at registration.
* **An account is created on the issuer's page, in the person's browser** (`IAM-10`, `IAM-22`),
  with a password or Google or Microsoft, and MFA. The commercial path arrives there with what the
  lead already gave, filled in.
* **Setting up a company is advice, and the context for it is in the person's agent.** What applies
  to the business, which basis and fiscal year, what to connect: the answers come from how the
  business works, which the person's agent often already knows (ADR-0068).
* **A model must not carry the books.** A 5,556-transaction export rendered for a model is about
  74,000 tokens it re-emits, with a ceiling near 6–7,000 transactions on a 200,000-token context
  (ADR-0041 § 6 measured it).
* **MCP App panels render CFOKit's own components in an agent's conversation**, read a chosen or
  dropped file in the panel, and call tools the model cannot see. Probed in Claude Desktop through
  `mcp-remote` (More Information).
* **A browser can hand a person to Claude.** `claude://claude.ai/new?q=…` opens Claude Desktop with
  a new chat and a drafted prompt, and `https://claude.ai/new?q=…` does the same on the web. Nothing
  returns a browser tab to a particular chat: the referrer carries no chat path, and an MCP server is
  not told which conversation called it.

## Decision Drivers

* **One path** for both offerings and the self-hosted build, differing only where a step does not
  apply.
* **As little of the person as possible** between subscribing and seeing their own books.
* **No credential near a model** (`IAM-10`), and **no figure through a model** (`IMP-09`).
* **Optimize for the person's own agent** where it and the browser trade off (ADR-0068).
* **One hand-off between browser and agent**, since none can be made seamless.

## Considered Options

* Web pages until the agent is connected, then setup and import in the conversation
* Every step on web pages, ending in the agent with the first question drafted
* Import relayed through the model over MCP tools

## Decision Outcome

Chosen option: "Web pages until the agent is connected, then the conversation", because the steps
before connecting need the browser, and the steps after are advice drawing on what the person's
agent knows, with the books moving through a panel the model cannot read.

> Getting started is one path. Lead, plan, subscription, registration and connecting the agent are
> web pages. Setting up the company and importing its books happen in the agent's conversation, the
> import in an MCP App panel.

### 1. The path

1. **Lead, plan, subscription**: commercial only, on the web.
2. **Registration** on the issuer's page: name, email and phone filled in from the lead, or empty
   when self-hosted; a password or Google or Microsoft; MFA.
3. **Connect**: with the organization's own agent, the page guides adding CFOKit to it and the
   skill, and offers **Continue in Claude**, opening a chat with the setup prompt drafted (§ 2),
   with the same prompt in a copy block beside it. With managed bookkeeping, the web app is the
   host and opens on the same prompt.
4. **Company**, in the conversation: the skill asks how the business works and what it expects to
   transact, says what applies and what does not, and proposes what the company declares (name,
   basis, fiscal year end, currency, time zone). It creates the company when the person confirms
   (`IAM-05`, `IAM-06`).
5. **Import**, in a panel in the conversation: the panel shows how to export from QuickBooks; the
   person chooses or drops the file, and the panel reads it with the reader's bounds (100 MB
   archive, 300 MB expanded, 64 members, no document type declarations). It shows what will be
   created and what will not, confirmed or abandoned (`IMP-05`); posts in batches through tools the
   model cannot see, resumable because the idempotency keys are derived from the file and the row
   (ADR-0029); and reconciles (`IMP-08`), recording the reconciliation with the import. The model
   receives the reconciliation, never the books.
6. **First question**, in the same conversation: the skill explains the reconciliation, then the
   year's profit and loss and cash position.

A host that renders no panels gets the same import components on a web page, reached by a link
from the conversation, and returns to the conversation when the import finishes.

### 2. The setup prompt

> Set up my company's books in CFOKit. Ask me what you need to know about how the business works,
> then help me import them from QuickBooks.

### 3. Retired

* Import through the model: the reader's `--mcp` mode, and `open_import` and `import_entries` as
  MCP tools the model can call.
* The skill's Python reader. The panel's reader, which is the web client's, is the one reader.
* Creating the company on a web page.

### Consequences

* Good, because the setup draws on what the person's agent already knows, and the person explains
  the business once.
* Good, because the self-hosted build is the same path with its commercial steps absent, and
  managed bookkeeping is the same path in CFOKit's host.
* Good, because the books move from file to CFOKit with no model reading them.
* Good, because there is one hand-off, at connecting, and everything after it is one conversation.
* Bad, because a person with their own agent signs in twice: on the web, and when the agent
  connects. The issuer's session in the same browser makes the second a confirmation, not a form.
* Bad, because the import depends on the host rendering panels and relaying the panel's tool
  calls. A host that does not gets the page, which is a second hand-off.
* Bad, because `claude://` is Claude-specific, and a browser asks "Open Claude?" the first time; the
  copy block is the fallback for any other agent.

### Confirmation

* The reader is tested against the synthetic export, with expected values from the export's own
  stated balances (ADR-0036 layer 3), and refuses an archive past each bound.
* The import tools are app-only: the published MCP surface shows them as visible only to the app,
  and CI gate 5 shows any change.
* Not gated: that getting started has no second route. That is review.

## Pros and Cons of the Options

### Web pages until the agent is connected, then the conversation

* Good, because it meets every driver.
* Bad, because the import rests on panel support in each host, which CFOKit does not control.

### Every step on web pages, ending in the agent with the first question drafted

Attractive because acquisition, payment and registration are web anyway, so one surface would
carry the person from the call to action to imported books, and a web page works in every
browser regardless of the agent.

* Good, because the path never depends on a host's panel support.
* Bad, because setting up the company becomes a form, asking the person for what their agent
  already knows. That is the configuration ADR-0068 optimizes away from.
* Bad, because the hand-off to the agent comes last, so the first conversation starts after the
  setup decisions are made, without the agent's knowledge of the business behind them.

### Import relayed through the model over MCP tools

Attractive because it works in any chat, with no panel.

* Bad, because the model re-emits every figure: about 74,000 tokens for 5,556 transactions, with a
  ceiling inside ordinary small-business history.

## More Information

**Follow-on obligations.**

* The import panel, built from the web client's components, with the import tools visible only to
  the app.
* The skill's setup conversation, and its link to the import page for a host without panels.
* The connect page offers the setup prompt; the company and import pages leave the web path.

**Reversal cost.** Moderate. The panel and the page are the same components in two shells, so
moving a step between them is a new shell around the same screens.

The probes below were run through `mcp-remote` in Claude Desktop. The decision also rests on two
facts they did not cover: that a panel renders in claude.ai and Claude Desktop through a custom
connector, and that a host relays a panel's tool calls at the size of an import's batches.

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
[ADR-0049](0049-cfokit-has-a-web-client.md). Related: ADR-0068 (optimizing for the person's own agent), ADR-0034 (the runtime and what it hosts),
ADR-0041 (the neutral shape and its bounds, which stand), ADR-0029 (derived idempotency keys).

[Open Claude Desktop with a link](https://support.claude.com/en/articles/14729294-open-claude-desktop-with-a-link) ·
[MCP Apps specification](https://github.com/modelcontextprotocol/ext-apps)

## Revisit when

* A host most customers use does not render panels through a custom connector, or caps a panel's
  tool calls below an import's batches, which puts the import on the page.
* An agent can return a browser tab to a specific chat, which removes the hand-off.
* A host lets an MCP App reply in the conversation as itself, which matters for the panels after.
