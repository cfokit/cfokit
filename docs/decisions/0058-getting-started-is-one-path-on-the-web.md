---
status: "proposed"
kind: "requirement-driven"
date: 2026-10-11
decision-makers: [Geoff]
---

# ADR-0058: Getting started has two doors, the web and the person's agent, and both end at imported books

**Requirements served:** `IAM-05`, `IAM-06`, `IAM-10`, `IAM-22`, `IMP-05`, `IMP-08`, `IMP-09`,
`NFR-19`.

## Context and Problem Statement

A person goes from first hearing of CFOKit to talking about their own books. Between the two they
create an account, set up the company, and import its books from the system it already runs.
Importing delivers nothing by itself: it is a chore, and the measure of it is how little of the
person it takes. What earns the rest of the relationship is everything after it.

People arrive in two places:

* **On the web**, from a call to action on the marketing site. They are in a browser, mid-decision,
  and every step that is not about their own books is a step at which they can leave.
* **In their agent**, having found CFOKit in Claude's directory of connectors. They are already in
  the conversation, and connecting CFOKit is how they arrived.

CFOKit is offered two ways (the vision's commercial thesis): the hosted backend or a self-hosted one,
where the organization brings its own agent, and managed bookkeeping, where CFOKit's own runtime, the
web app, hosts the same skills, tools and panels (ADR-0034 § 4). A self-hosted build needs getting
started without any commercial step.

The constraints that shape the path:

* **Connecting an agent is friction.** Adding a connector, signing in through it and allowing it are
  several steps in another application, and in the middle of getting started each is a point of
  abandonment. For a person who arrived in their agent, the same steps are already behind them.
* **An account is created on the issuer's page, in the person's browser** (`IAM-10`, `IAM-22`),
  with a password or Google or Microsoft, and MFA, whichever door they came through.
* **Setting up a company is advice, and in the agent the context for it is at hand.** What applies to
  the business, which basis and fiscal year: the person's agent often already knows (ADR-0068). On
  the web, the export states most of it.
* **A model must not carry the books.** A 5,556-transaction export rendered for a model is about
  74,000 tokens it re-emits, with a ceiling near 6–7,000 transactions on a 200,000-token context
  (ADR-0041 § 6 measured it).
* **MCP App panels render CFOKit's own components in an agent's conversation**, read a chosen or
  dropped file in the panel, and call tools the model cannot see (More Information).
* **A browser can hand a person to Claude.** A link opens Claude's add-connector dialog with CFOKit's
  name and address filled in, and `claude://claude.ai/new?q=…` (or `https://claude.ai/new?q=…`)
  opens a new chat with a drafted prompt. Nothing returns a browser tab to a particular chat.

## Decision Drivers

* **Value before friction.** The person sees their own books before being asked to do anything that
  is not about them.
* **Stay where the person arrived** until the books are in.
* **One reader, one import, one company step's rules**, whichever door: the doors differ in shell,
  not in what they do.
* **No credential near a model** (`IAM-10`), and **no figure through a model** (`IMP-09`).
* **The self-hosted build is the same path** with its commercial steps absent.

## Considered Options

* Two doors, each staying where the person arrived until the books are in
* One path on web pages, ending in the agent
* One path: web pages until the agent is connected, then the conversation
* Import relayed through the model over MCP tools

## Decision Outcome

Chosen option: "Two doors, each staying where the person arrived until the books are in", because it
puts no agent connection in front of a person on the web before they see their books, and no web form
in front of a person whose agent is already connected.

> Getting started has two doors. On the web door, registration, the company and the import are web
> pages, and then the person chooses between continuing in their agent and continuing in the browser.
> On the agent door, the person connects from their agent's directory, and the company and the import
> happen in the conversation, the import in a panel. Both read the books with the same reader and post
> them through the same import.

### 1. The web door

1. **Plan**: only where the deployment names a commercial service, which takes it before
   registration.
2. **Registration** on the issuer's page: name and email filled in from what the person already gave,
   or empty; a password or Google or Microsoft; MFA.
3. **Export**: the page shows how to export from QuickBooks; the person chooses or drops the file,
   and the page reads it in the browser with the reader's bounds (100 MB archive, 300 MB expanded,
   64 members, no document type declarations).
4. **Company**: confirm what the export states (name, basis, fiscal year end, currency) and add what
   it does not, such as the time zone (`IAM-05`, `IAM-06`).
5. **Import**: what will be created and what will not, confirmed or abandoned (`IMP-05`); posted in
   batches, resumable because the idempotency keys are derived from the file and the row (ADR-0029);
   reconciled (`IMP-08`), with the reconciliation recorded with the import.
6. **The choice**, on the page that shows the reconciliation:
   * **Continue in Claude.** The page opens Claude's add-connector dialog with CFOKit filled in, waits
     until the agent's first connection arrives, and then opens a new chat with the first question
     drafted (§ 3), with the same prompt in a copy block beside it.
   * **Continue in the browser.** The web client opens on the company. Settings offers connecting an
     agent at any time, with the same steps.

   With managed bookkeeping there is no choice: the web app is the agent's host, and it opens on the
   first question.

### 2. The agent door

1. **Connect**, from Claude's directory: the connector and the skill. Connecting signs the person in
   on the issuer's page, which is registration for a new person.
2. **Company**, in the conversation: the skill asks how the business works and what it expects to
   transact, says what applies and what does not, and proposes what the company declares. It creates
   the company when the person confirms. Where the deployment names a commercial service and the
   person has not chosen a plan, creating it is refused with the plan's address, which the skill
   gives them, and they come back to the conversation to finish.
3. **Import**, in a panel in the conversation: the same steps as the web door's 3 and 5, in the same
   components. The model receives the reconciliation, never the books.
4. **First question**, in the same conversation.

A host that renders no panels gets the web door's import page, reached by a link from the
conversation, which ends by sending the person back to it.

### 3. The first question

After an import a person asks whether it all came across, and then how the business is doing. The
drafted prompt asks both:

> My books are imported into CFOKit. Confirm they match QuickBooks and explain any differences, then
> summarize this year's profit and loss and my cash position.

### 4. One reader

The reader is the web client's, in TypeScript, and runs in the page and in the panel. Importing
through the model is retired: the reader's `--mcp` mode, the skill's Python reader, and `open_import`
and `import_entries` as tools the model can call. The import tools are visible only to the app.

### Consequences

* Good, because a person on the web sees their own books, reconciled, before anything asks them to
  connect an agent, and the choice to connect is made with the value in front of them.
* Good, because a person in their agent never leaves the conversation, except to sign in and, where
  one applies, to choose a plan.
* Good, because both doors share the reader, the import and the company's rules, so a fix reaches
  both.
* Good, because the books move from file to CFOKit with no model reading them.
* Good, because the self-hosted build is the same two doors with the plan absent.
* Bad, because a company is set up two ways, a form on the web and a conversation in the agent, and
  the two must reach the same declarations.
* Bad, because a person on the web who connects their agent signs in a second time. The issuer's
  session in the same browser makes it a confirmation, not a form.
* Bad, because the agent door's import depends on the host rendering panels and relaying their tool
  calls. A host that does not gets the page, which is a second hand-off.
* Bad, because the add-connector link and `claude://` are Claude-specific; the copy block and
  Settings' instructions are the fallback for any other agent.

### Confirmation

* The reader is tested against the synthetic export, with expected values from the export's own
  stated balances (ADR-0036 layer 3), and refuses an archive past each bound.
* The import tools are app-only: the published MCP surface shows them as visible only to the app, and
  CI gate 5 shows any change.
* Creating a company through the page and through the tool is tested for the same refusals and the
  same declarations.
* Not gated: that no step asks a person on the web door to connect an agent before the choice. That
  is review.

## Pros and Cons of the Options

### Two doors, each staying where the person arrived until the books are in

* Good, because it meets every driver.
* Bad, because two shells of getting started are built and kept consistent.

### One path on web pages, ending in the agent

Every arrival, including from the directory, would go to the web pages and come back to the agent
with the first question drafted.

* Good, because there is one shell, and it never depends on a host's panel support.
* Bad, because a person who arrived in their agent, already connected, is sent to a browser to fill
  in a form about what their agent already knows.

### One path: web pages until the agent is connected, then the conversation

* Good, because setup draws on the agent's context for everyone.
* Bad, because a person on the web must connect an agent before seeing anything of their own, which
  puts the largest point of abandonment in front of the value.

### Import relayed through the model over MCP tools

Attractive because it works in any chat, with no panel.

* Bad, because the model re-emits every figure: about 74,000 tokens for 5,556 transactions, with a
  ceiling inside ordinary small-business history.

## More Information

**Follow-on obligations.**

* The web door's pages, and the choice on the reconciliation page.
* The import panel, built from the same components, with the import tools visible only to the app.
* The skill's setup conversation, its handling of a refusal that carries a plan's address, and its
  link to the import page for a host without panels.
* The reconciliation record and its read tool, in the imports module.

**Reversal cost.** Moderate. The page and the panel are the same components in two shells, so moving
a step between doors is a new shell around the same screens.

The probes below were run through `mcp-remote` in Claude Desktop. The agent door also rests on two
facts they did not cover: that a panel renders in claude.ai and Claude Desktop through a directory
connector, and that a host relays a panel's tool calls at the size of an import's batches.

**Probes behind the panels** (Claude Desktop, `mcp-remote` 0.14.3, MCP Apps SDK 2.0.1, 2026-10-04):

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
[ADR-0049](0049-cfokit-has-a-web-client.md). Related: ADR-0068 (optimizing for the person's own
agent after getting started), ADR-0034 (the runtime and what it hosts), ADR-0041 (the neutral shape
and its bounds, which stand), ADR-0029 (derived idempotency keys).

[Open Claude Desktop with a link](https://support.claude.com/en/articles/14729294-open-claude-desktop-with-a-link) ·
[MCP Apps specification](https://github.com/modelcontextprotocol/ext-apps)

## Revisit when

* The funnel shows people on the web door choosing the browser and never connecting, which would say
  the choice should come later or differently.
* A host most customers use does not render panels through a directory connector, or caps a panel's
  tool calls below an import's batches, which sends the agent door's import to the page.
* An agent can return a browser tab to a specific chat, which removes the hand-offs.
