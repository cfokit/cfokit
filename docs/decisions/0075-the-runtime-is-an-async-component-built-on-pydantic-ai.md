---
status: "proposed"
kind: "requirement-driven"
date: 2026-10-22
decision-makers: [Geoff]
---

# ADR-0075: CFOKit's runtime is an async component built on Pydantic AI, streaming AG-UI to an assistant-ui chat window

**Requirements served:** `PLT-04`, `PLT-24`, `PLT-23`, `BKP-20`, `IAM-11`, `SOC1-06`, `SOC1-35`.

## Context and Problem Statement

CFOKit ships its own agent runtime, and the runtime is the web app (ADR-0034 § 4). It hosts the
same bookkeeper skill and published MCP tools as the person's own agent. With managed bookkeeping
CFOKit supplies the inference (ADR-0035); a self-hoster supplies their own credential (ADR-0034
§ 1). This record decides what the runtime is built from and how a turn reaches the person.

Four use cases define the first version, each recorded end to end as a documentation clip
(ADR-0074): reconcile from a statement, answer the agent's questions after unattended work, ask
about the books, and approve a proposed rule. A person attaches receipts and statement PDFs.

A chat over an agent with tools, file attachments and a streamed reply is a solved problem with
open-source frameworks for each part, so the question is which to build on, not how to design one.

Facts that bear on the answer:

* **By ADR-0022 § 3 the runtime is a component.** It commits nothing with a ledger write; its shape
  is long turns and long-lived streams, unlike the API's; it holds the one credential worth
  isolating, the inference key; and any MCP client is already a third party's version of it. A
  component chooses its own execution model (ADR-0024).
* **It reaches CFOKit through the published interfaces and no other** (ADR-0034): the books
  through the MCP tools, and its conversations through the REST API (ADR-0076), as its own
  registered client acting for a person, within the intersection of their grants (`IAM-11`,
  ADR-0066).
* **On Cloud Run, a stream is a request.** An open SSE or websocket stream keeps its instance
  active and billed, up to the request timeout of at most sixty minutes, and one instance serves
  many streams. Under request-based billing, CPU is allocated only while a request is in flight.
  Over HTTP/1.1, a client's disconnect is not passed to the container.
* **The candidates**, with licenses read from PyPI and npm for this record:
  * **Pydantic AI** (`pydantic-ai-slim` 2.59.0, MIT): an async agent framework that calls Claude
    through the `anthropic` SDK, connects to MCP servers through `fastmcp-slim` (4.1.3,
    Apache-2.0), serializes its message history to provider-neutral JSON including file and image
    parts, ships a test model for running agents with no credential, and emits AG-UI and the
    Vercel AI SDK's stream protocol through adapters.
  * **AG-UI** (`ag-ui-protocol` 1.0.0, `@ag-ui/core` 1.0.3, MIT): an open, event-based protocol
    between an agent and a user interface, with events for streamed text, tool calls and a run's
    lifecycle, over SSE. It has SDKs from more than one vendor, Microsoft's among them.
  * **assistant-ui** (`@assistant-ui/react` 0.15.30, MIT): React chat components built on headless
    primitives, with a composer, attachments through upload adapters, Markdown rendering, and a
    runtime that speaks AG-UI (`@assistant-ui/react-ag-ui`). Its optional `assistant-cloud`
    package carries the address of the vendor's hosted backend, used only when configured.
  * **The Vercel AI SDK** (`ai` 7.0.148, Apache-2.0): a TypeScript toolkit whose UI protocol
    Pydantic AI also emits.
  * **The Claude Agent SDK**, **Managed Agents**, and **the Messages API's MCP connector with the
    Skills API**, each Anthropic's.

## Decision Drivers

* **Build on maintained open-source parts**, adopting their protocols and patterns rather than
  inventing ours.
* **The same agent in both hosts**: the bookkeeper skill and the published tools, nothing more
  (ADR-0034 § 4).
* **Runs on the local stack**: `docker compose up`, a self-hoster's credential, no public address.
* **The books are reached as a client would reach them**, with the person's authority and no more.
* **No copyleft in the browser, nothing AGPL on the server** (`CLAUDE.md`, Licensing).
* **Tests need no credential** (ADR-0004).

## Considered Options

* An async component on Pydantic AI, streaming AG-UI to an assistant-ui chat window
* The same component streaming the Vercel AI SDK's protocol to its `useChat`
* The Claude Agent SDK in the component
* Managed Agents, or the Messages API's MCP connector with the Skills API
* A loop of our own on the `anthropic` SDK, run from the work queue

## Decision Outcome

Chosen option: "An async component on Pydantic AI, streaming AG-UI to an assistant-ui chat window",
because each part is a maintained, MIT-licensed project that already does its piece, the protocol
between them is an open standard rather than one vendor's, and together they leave CFOKit only what
is CFOKit's own.

> The runtime is an async component, an entrypoint of the one image, built on Pydantic AI. A turn
> is a Pydantic AI run with the bookkeeper skill as its instructions and the published MCP tools as
> its only tools, called as the runtime's own client acting for the person. It streams AG-UI events
> over SSE to a chat window built from assistant-ui. The runtime stores nothing: it reads and
> appends the conversation through the published API (ADR-0076).

### 1. A turn is one streamed request

The chat window sends the person's message to the runtime, at a path on the API's origin the load
balancer routes to it, so the CSP's `default-src 'self'` holds. The runtime reads the
conversation's history from core, runs the turn, and streams its AG-UI events in the response. As
each message completes, it is appended to the conversation in core, so a reload or a reconnect
shows everything up to the last completed message.

A turn cut off mid-way leaves what it completed. Every write it made carried an idempotency key
(ADR-0029) and an uploaded line is only ever drafted (ADR-0047), so a cut-off turn leaves drafts
and a conversation to continue, never a half-booked transaction. Rejoining a turn's stream while it
runs, which AG-UI and assistant-ui support, is not built until a person needs it.

**Unattended work starts a turn the same way.** A run in the work queue (ADR-0061) that leaves
something for the person calls the runtime's endpoint and keeps the result, and the queue retries a
call that fails.

### 2. What the model is offered

The model is Claude through Pydantic AI's Anthropic model, its identifier pinned in the
deployment's configuration and recorded with every message (`SOC1-35`); each call's usage is
recorded for the company (ADR-0072). Its tools are the published MCP tools, listed from CFOKit's
own MCP endpoint, and no others: no file, shell or web tool. The bookkeeper skill's `SKILL.md`, at
the version the image carries, is the instructions, and its version is recorded too (`SOC1-06`).

**Once a conversation holds content the organization did not author, the model is offered no
tool that posts, for the rest of that conversation** (`PLT-23`, `BKP-20`). A receipt or a
statement the person attaches is such content, and it stays in the history every later turn
sends, so bounding the rule to one turn would be defeated by reading in one turn and posting in
the next. The model may still read the books and draft, and an uploaded line is drafted whatever
resolves it (ADR-0047). A draft from such a conversation is posted only by the person, as
themselves, outside the model: a posting act in the web client that calls the published API with
their own token, never a tool the model holds.

The runtime enforces this by what it offers, not by an instruction: it knows what each
conversation holds, because the conversation is stored with each part's classification
(ADR-0076), and a model cannot call a tool it was not offered. This is the boundary the
bookkeeper skill otherwise has to keep in its own instructions, built where CFOKit runs the agent.
The person's own agent, which CFOKit does not run, still relies on the skill's rule until the
published surface can enforce it.

With no inference credential configured, the runtime is off and the chat window says so. The suite
drives the runtime with Pydantic AI's test model, so a turn's messages, tool calls and refusals are
asserted on with no credential.

### 3. The chat window

The web client's conversation page is built from assistant-ui's primitives, styled from
`design/tokens.json` like every other component, with its AG-UI runtime. Its Markdown renders as
elements, never as raw HTML (ADR-0049 § 6). Attachments go through an upload adapter to the
published API (ADR-0076). `assistant-cloud` is never configured, and the CSP would refuse its
backend if it were.

### Consequences

* Good, because the loop, the MCP client, the stream protocol, the chat components and the test
  model are maintained by others, and CFOKit writes what is its own: the skill, the tools, storage
  and authority.
* Good, because AG-UI is a standard, so another client can follow a conversation, and moving from
  assistant-ui changes the window without touching the runtime.
* Good, because the runtime holds no state and no database credential, so it scales to zero and
  reaches the books only as a client.
* Good, because the reply streams as it is written, as people expect of a chat.
* Good, because `PLT-23` is enforced by capability wherever CFOKit runs the agent, rather than
  only by the skill's instruction.
* Bad, because a conversation that has read a document needs the person to post its drafts
  themselves, one more step than asking the agent to.
* Bad, because three projects, pre-1.0 in assistant-ui's case, now carry a main surface, and their
  releases are CFOKit's to follow.
* Bad, because a turn cut off mid-way stops, and the person continues it by asking again.
* Bad, because a stream keeps an instance billed while it is open; the window closes it when the
  tab is hidden (the Page Visibility API's `visibilitychange`).
* Neutral, because SSE passes ADR-0012's gate here, for this one stream; websockets stay gated.

### Confirmation

* The runtime is its own package and entrypoint, with an `import-linter` contract forbidding it
  every capability package, so it reaches the books and its conversations only through the
  published MCP and REST interfaces.
* Pydantic AI's test model drives a turn in the suite: its stream, its appended messages, and
  that once a conversation holds an untrusted file no later turn in it is offered a posting tool,
  including when the model is scripted to try (`PLT-23`'s acceptance).
* Review: no tool is offered that the published MCP surface does not publish.

## Pros and Cons of the Options

### An async component on Pydantic AI, streaming AG-UI to an assistant-ui chat window

* Good, because it meets every driver.
* Bad, because it depends on three outside projects for a main surface.

### The same component streaming the Vercel AI SDK's protocol to its `useChat`

The most widely used chat stack in TypeScript, with resumable streams and file parts documented.

* Good, because the client and its patterns are the most familiar to anyone joining.
* Bad, because its protocol is one company's SDK format, where AG-UI is a protocol with SDKs from
  several, and Pydantic AI and assistant-ui each speak both, so choosing AG-UI costs nothing.

### The Claude Agent SDK in the component

* Good, because it loads the `SKILL.md` as written and brings Claude Code's harness.
* Bad, because it brings file, shell and web tools the bookkeeper must not have, which make
  `PLT-23`'s boundary harder to hold rather than merely unused.
* Bad, because each platform's wheel is about 114 MB, carrying a program whose license is stated
  only by reference, in a runtime ADR-0034 § 1 ships as Apache 2.0.

### Managed Agents, or the Messages API's MCP connector with the Skills API

* Good, because the least code: the provider runs the loop and calls the tools.
* Bad, because the provider must reach CFOKit's MCP endpoint, so neither runs on the local stack.
* Bad, because a tool call is made by the provider with a token for the person that leaves CFOKit.

### A loop of our own on the `anthropic` SDK, run from the work queue

* Good, because it needs one dependency and keeps every line in view.
* Bad, because it writes again what Pydantic AI already maintains: the loop, the MCP client, the
  message format, the stream, and the test model.
* Bad, because the queue's pass is a separate process from what the browser reaches, so streaming
  the reply would need a channel between them that nothing provides.

## More Information

**Follow-on obligations.**

* A record on how the runtime holds a token for a person, for a request and for a queued run. It
  bears on `SOC1-25`'s conflict in `docs/decisions/README.md`, and on authentication, so it needs a
  person's review, and the runtime cannot act until it exists.
* `pydantic-ai-slim` with its `anthropic`, `mcp` and `ag-ui` extras, added to the runtime
  dependencies with license and reason, and `CLAUDE.md`'s count of them updated.
* `@assistant-ui/react`, its Markdown and AG-UI packages, added to the web client, checked against
  ADR-0049 § 9.
* A provider registry entry before the provider receives customer data (`SOC2-10`, ADR-0035).
* The load balancer routes the runtime's path to its service (ADR-0060); `compose.yaml` adds it.

**Reversal cost.** Moderate. Replacing assistant-ui changes the chat window only; replacing
Pydantic AI replaces the runtime's loop but not the stored conversations, which are its message
JSON (ADR-0076) and would be converted once.

Related: ADR-0022 (components), ADR-0034 (the runtime), ADR-0035 (inference), ADR-0061 (the work
queue), ADR-0066 (an agent acts for a person), ADR-0068 (conversation first), ADR-0072 (usage),
ADR-0074 (the use cases as clips), ADR-0076 (where conversations are stored).

## Revisit when

* Turns cut off mid-way are more than one in fifty, so rejoining a running turn, or running it
  under one of Pydantic AI's durable-execution engines, earns its cost.
* Pydantic AI, AG-UI or assistant-ui stops being maintained, or changes license.
* Open streams on an instance cost more than the requests they replace would.
