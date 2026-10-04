---
status: "proposed"
kind: "requirement-driven"
date: 2026-10-03
decision-makers: [Geoff]
---

# ADR-0058: Onboarding with the organization's own agent is one path, inside its conversation

**Requirements served:** `IAM-05`, `IAM-06`, `IAM-10`, `IAM-22`, `IMP-05`, `IMP-08`, `IMP-09`,
`NFR-19`.

## Context and Problem Statement

CFOKit is used two ways (the vision's commercial thesis). With the hosted backend, or a
self-hosted one, the organization brings its own agent — Claude Desktop, with the bookkeeper
skill and CFOKit's MCP server — and that agent keeps and questions the books. With managed
bookkeeping, CFOKit's own runtime does, with models CFOKit chooses (ADR-0034). This record is
about the first: an organization onboarding through its own agent.

A person starts with nothing and ends talking to their agent about their own books. Between the two
they create an account, create the company (the entity), and import its existing books. Each
route that can carry those steps is a route somebody has to support, document and secure, and a
person told "you can do this here or there" has two things to learn instead of one.

The constraints that shape any route:

* **An account is created in the person's own browser**, on the identity provider's page.
  Credentials never pass through an agent or a model, and CFOKit operates no sign-in of its own
  (`IAM-10`, `IAM-22`).
* **The agent's connection already opens that page.** An MCP client connecting to CFOKit is told
  which issuer guards it (RFC 9728), opens the issuer's sign-in in the person's browser, and
  receives its token back in the client — Claude Desktop through `mcp-remote` locally, a custom
  connector against a hosted deployment. The realm allows sign-up, so that page offers Register.
  The person returns to the chat they started from.
* **Nothing carries a person from a browser tab back to a particular chat.** A browser opened
  from Claude Desktop sends no `Referer`; a link followed from a page sends the origin and never
  the path; an MCP server is not told which conversation called it. `claude://claude.ai/new?q=…`
  opens a *new* chat with a prefilled prompt, and opening a specific chat needs its id, which
  nothing hands to CFOKit. URL-mode elicitation (MCP 2025-11-25) does return to the waiting tool
  call, and its support differs by Claude surface and refuses non-HTTPS URLs.
* **A model must not carry the books.** A 5,556-transaction export rendered for a model is about
  74,000 tokens of figures it re-emits, minutes of generation, and a ceiling near 6–7,000
  transactions on a 200,000-token context (ADR-0041 § 6 measured it).
* **MCP Apps** (the ext-apps specification, 2026-01-26) let a server render a panel inside the
  conversation. The panel is HTML served as a `ui://` resource (`text/html;profile=mcp-app`), run
  by the host in a sandbox whose default CSP is `default-src 'none'` with inline script and style
  only. It calls the server's tools through the host — over the connection the host already
  signed in — and a tool declared `visibility: ["app"]` is hidden from the model, and the host
  must refuse it to anything but the app. The panel can update what the model knows
  (`ui/update-model-context`), silently. A message it sends (`ui/message`) is the person's, not
  the app's: Claude Desktop puts it in the person's message box, under a warning to use caution
  before running it, for the person to send. Claude renders MCP Apps for locally configured
  servers, including through `mcp-remote`.
* **What the specification leaves to the host**: file inputs and drag-and-drop in the panel. It
  has no provision for either.
* Contributors run CFOKit on a laptop and self-hosters on their own machines; both should
  onboard the same way a hosted customer does (`NFR-19`).

## Decision Drivers

* **One path.** A second supported route is a second thing to secure, test and explain.
* **No credential near a model** (`IAM-10`).
* **No figure through a model**: the transfer of books is exact and costs no generation.
* **Fewest switches between the browser and the chat**, and none that depends on finding the
  chat again.
* **The same path on a laptop, a self-hosted server and the hosted service.**
* **Nothing about the books leaves the person's machine except to CFOKit.**

## Considered Options

* One path in the conversation: sign up through the connection's sign-in, then create the company
  and import in an MCP App panel
* One path in the web client: sign up, create the company and import at `/app/`, then hand back
  to Claude with a `claude://` link
* Import relayed through the model over MCP tools
* URL-mode elicitation: Claude sends the person to web onboarding pages and resumes when they
  finish

## Decision Outcome

Chosen option: "One path in the conversation", because it is the only one with a single browser
trip — the one `IAM-10` requires — and no hand-back, and the panel moves the books from the file
to CFOKit without the model reading a figure.

> An organization bringing its own agent onboards in that agent's conversation. The person
> creates their account on the issuer's page when the agent first connects, and creates the
> company and imports its books in a CFOKit panel in that chat. There is no other onboarding route
> for an organization bringing its own agent.

### 1. The account is created where the connection signs in

Connecting the agent to CFOKit opens the issuer's sign-in in the person's browser; a new person
chooses Register there. Nothing else creates an account. The connection's token is the person's
own, so every later step acts as them.

### 2. The company and the import happen in one panel

A tool the model calls when a person has no books, or asks to import, returns the onboarding
panel. In it, the person:

1. creates the company — its basis, fiscal year end, currency and time zone — by `create_entity`
   (`IAM-05`, `IAM-06`);
2. chooses the export, which the panel parses where it is, in the sandbox, with the reader's
   bounds (100 MB archive, 300 MB expanded, 64 members, no document type declarations);
3. sees what will be created and what will not, and confirms or abandons (`IMP-05`);
4. watches the batches post, resumable after anything interrupts it because the idempotency keys
   are derived from the file and the row (ADR-0029);
5. sees the reconciliation (`IMP-08`).

**The import tools are visible to the panel only.** Opening an import, posting its entries and
reconciling carry `visibility: ["app"]`; the model is never offered them. The panel declares no
network domains, so the parsed books go nowhere but to CFOKit's tools through the host.

**The reconciliation is recorded with the import**, append-only in the imports module, and a
read-only tool returns it, so a later conversation can explain it without the file.

### 3. The panel shows the result, and the model is told

When the import ends, the panel shows what happened, in the conversation where it sits —
"Imported 5,553 transactions. 25 of 27 accounts match QuickBooks exactly." — and updates the
model's context with the entity and the reconciliation. The panel writes nothing into the
person's message box: a prompt the person did not write, arriving with a warning to use caution,
is the wrong answer to an import that finished. Whatever the person says next, the model already
knows the books have landed and how they reconciled.

### 4. Retired

* The web client's import page (ADR-0051), and the web client as an onboarding route
  (ADR-0049 § 3).
* The model relaying an import (ADR-0041 § 6): the reader's `--mcp` mode, and the import tools
  as model-visible tools.
* The skill's QuickBooks reader. The panel's reader is the one reader.

### Consequences

* Good, because a person makes one trip to the browser, to create an account, and the
  connection brings them back to the chat; nothing has to find the chat again.
* Good, because the books move from file to CFOKit with no model reading or re-emitting them,
  and no token or generation spent on them.
* Good, because a credential stays in the browser and in the host's connection, never in the
  panel or the model (`IAM-10`).
* Good, because the panel cannot reach the network, so a parsed export has nowhere to go but
  CFOKit.
* Good, because a contributor, a self-hoster and a hosted-backend customer onboard identically;
  only how the agent is connected to CFOKit differs.
* Bad, because onboarding requires a host that renders MCP Apps. A person without one cannot
  onboard.
* Bad, because the server cannot tell a call the panel made from one the model made: both arrive
  on the same connection with the same token. Keeping the import tools from the model rests on
  the host honoring `visibility`, which the specification makes a MUST but CFOKit cannot verify.
* Bad, because the panel's reader is JavaScript in a sandbox CFOKit does not control, and file
  input there is the host's choice, not the specification's.
* Neutral, because the web client stops being an onboarding route for an organization's own
  agent and belongs to managed bookkeeping. There, with mobile and tablet apps, it is the
  container in which CFOKit chooses the model for each part of the experience, and its form —
  onboarding in it included — is defined when that offering is built (ADR-0034).

### Confirmation

* The published MCP tool contract (CI gate 5) shows every import-write tool with
  `visibility: ["app"]`, and a test fails if one is model-visible.
* The panel's reader is tested against the synthetic export, with expected values from the
  export's own stated balances (ADR-0036 layer 3), and refuses an archive past each bound.
* The panel's resource declares no `connectDomains`; a test asserts the served resource carries
  none.
* The host-side facts this rests on — the panel renders through `mcp-remote` in Claude Desktop, a
  file can be chosen and dropped in it, app-only tools are absent from the model's tool list, and
  Register on the connection's sign-in returns the person to the chat — are probed in Claude
  Desktop and the results recorded in this record, as ADR-0041 records its sandbox probe.

A probe server, run in Claude Desktop through `mcp-remote` 0.14.3 on 2026-10-04, with a panel
built on the MCP Apps SDK 2.0.1:

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
* Not gated: that no other onboarding route is built. That is review.

## Pros and Cons of the Options

### One path in the conversation

* Good, because it meets every driver except host independence.
* Bad, because it depends on MCP Apps, a 2026 extension whose file handling the specification
  does not address.

### One path in the web client

Attractive because it is decided (ADR-0049, ADR-0051), its sign-in works end to end, and a
browser page controls its own file input, layout and CSP.

* Good, because it runs in any browser, with no dependency on a host feature.
* Bad, because it needs a second switch — back from the browser to Claude — and nothing can
  return the person to the chat they left. `claude://claude.ai/new?q=…` opens a new chat, which
  is the closest available and still a hand-off a person has to make.
* Bad, because the person signs in twice: once for the web client and once for the Claude
  connection, two clients of the same issuer in two places.

### Import relayed through the model over MCP tools

Attractive because it works today, end to end, in a sandboxed Desktop chat.

* Good, because it needs nothing beyond the tools that exist.
* Bad, because the model re-emits every figure: about 74,000 tokens and minutes of generation for
  5,556 transactions, with a ceiling near 6–7,000 transactions on a 200,000-token context — inside
  ordinary small-business history.
* Bad, because a mistyped figure is caught only by the reconciliation, after it is posted.

### URL-mode elicitation

Attractive because it is the protocol's own "go to the browser and come back": the waiting tool
call resumes in the same chat when the page reports completion.

* Good, because it solves the return trip the web client cannot.
* Bad, because its support differs by Claude surface — reported in Claude Desktop's chat tab, not
  shown in Cowork — and it requires HTTPS, so it is a route that works in some places and not
  others.
* Bad, because it still sends the company and the import to a browser page, with a second
  sign-in, for steps that need no browser at all.

## More Information

**Follow-on obligations.**

* The MCP server serves the panel as a `ui://` resource and marks the import tools app-only; a
  tool returns the panel for onboarding.
* The reader moves into the panel as JavaScript, with the Python reader's bounds and its tests'
  expected values.
* The skill tells the agent to offer the panel when a person has no books or asks to import, and
  stops describing the reader.
* `docs/connect-claude-desktop.md` becomes the onboarding guide: connect, register, then the
  panel.
* The reconciliation record and its read tool are built in the imports module.

**Reversal cost.** Moderate. The panel's screens are the web client's components, and the reader
is the same JavaScript either way, so moving onboarding back to a page would be a new shell and a
second sign-in rather than a rewrite. Reversing it re-opens the hand-back problem this record
exists to avoid.

Supersedes [ADR-0051](0051-books-are-imported-through-the-web-client.md), and § 3 of
[ADR-0049](0049-cfokit-has-a-web-client.md). Onboarding with managed bookkeeping is decided with
the runtime that offering runs on — the web client and mobile and tablet apps
([ADR-0034](0034-cfokit-operated-agent-runtime.md)). Related: ADR-0041 (the neutral shape and its bounds,
which stand), ADR-0029 (derived idempotency keys), ADR-0042 (importing is a person's act).

[MCP Apps specification](https://github.com/modelcontextprotocol/ext-apps) ·
[MCP elicitation, 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/client/elicitation) ·
[Open Claude Desktop with a link](https://support.claude.com/en/articles/14729294-open-claude-desktop-with-a-link)

## Revisit when

* An agent runtime organizations bring, which CFOKit must onboard through, does not render MCP
  Apps.
* The probe finds a file cannot be chosen or dropped in the panel.
* The specification gives the server a way to tell an app's call from the model's, which would
  let CFOKit enforce what it now trusts the host to.
* A host lets an app reply in the conversation as itself, rather than through the person's
  message box, which would let the result appear as a turn of the chat.
* An agent runtime can return a browser tab to a specific chat, which removes the web client's main
  disadvantage.
