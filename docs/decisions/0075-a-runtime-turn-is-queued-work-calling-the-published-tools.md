---
status: "proposed"
kind: "requirement-driven"
date: 2026-10-20
decision-makers: [Geoff]
---

# ADR-0075: A turn in CFOKit's runtime is queued work that calls the model through the Messages API and reaches the books only through the published tools

**Requirements served:** `PLT-04`, `PLT-24`, `IAM-11`, `SOC1-06`, `SOC1-35`, `SOC2-16`.

## Context and Problem Statement

CFOKit ships its own agent runtime, and the runtime is the web app (ADR-0034 § 4). It hosts the
same bookkeeper skill, MCP tools and panels that the person's own agent does. With managed
bookkeeping CFOKit supplies the inference (ADR-0035); a self-hoster supplies their own credential
(ADR-0034 § 1). This record decides how one turn of that runtime runs: where the agent loop
executes, how it reaches the books, and how the chat window sees what it did.

Four use cases define the first version, each recorded end to end as a documentation clip
(ADR-0074):

* **Reconcile from a statement.** The person gives a bank statement and asks for checking to be
  reconciled.
* **Answer the agent's questions.** Unattended work leaves transactions nothing resolved
  (`BKP-12`); the person opens the conversation and answers them.
* **Ask about the books.** "How did we do last quarter?"
* **Approve a rule.** The agent proposes an assignment rule and the person approves it.

Facts that bear on the answer:

* **A turn takes seconds to minutes.** It is several model calls with tool calls between them. A
  model call on a hard task can itself run for minutes.
* **The service scales to zero and holds no long connection** (ADR-0017). Websockets and SSE are
  gated (ADR-0012). Unattended work is a row in Postgres, run by a pass that a person's waiting
  request starts at once (ADR-0061).
* **The runtime uses the published tool surface and no other** (ADR-0034), as a client registered
  in a class a third party cannot mint. An agent acts for a person, within the intersection of
  its grant and theirs (`IAM-11`, ADR-0066).
* **What the model saw must be kept**: model identifier and version, skill version, inputs and
  tool calls (`SOC1-06`, `SOC1-35`). Each model call records usage for the company (ADR-0072).
* **A conversation belongs to one company** and reaches nothing outside it (`PLT-04`, `SOC2-16`).
* **The suite runs with no cloud credentials** (ADR-0004), so a model call cannot be in any gate.
* **The ways to run an agent on Claude**, as of this record:
  * **The Messages API**, through the `anthropic` Python SDK (1.15.0, MIT): CFOKit writes the loop,
    or uses the SDK's tool runner, and defines every tool. The tools run where CFOKit runs them, so
    they reach a stack on `localhost`. A skill is instructions CFOKit sends; the API does not read a
    `SKILL.md` itself. Its dependencies are mostly installed already: `anyio`, `httpx2`,
    `pydantic` and `typing-extensions` are in the lockfile through `mcp` and `fastapi`.
  * **The Claude Agent SDK** (`claude-agent-sdk` 0.2.168, MIT): Claude Code packaged as a library,
    async, with built-in file, shell and web tools, and it loads a `SKILL.md`. Each platform's
    wheel is about 114 MB because it carries the Claude Code program, whose npm package states its
    license only as "SEE LICENSE IN README.md".
  * **Managed Agents** (beta): Anthropic runs the loop and a sandbox per session, with skills and
    MCP servers attached. The MCP server must be reachable from Anthropic.
  * **The MCP connector and the Skills API** on the Messages API: Anthropic calls the MCP server and
    runs the skill in its code-execution container. The MCP server must be reachable from
    Anthropic, holding a token CFOKit gives it.

## Decision Drivers

* **The same agent in both hosts**: the bookkeeper skill and the published tools, nothing the
  person's own agent lacks (ADR-0034 § 4).
* **Runs on the local stack**: `docker compose up`, a self-hoster's credential, no public address.
* **No connection held open**, and nothing that lifts ADR-0012's gate.
* **The books are reached as a client would reach them**, with the person's authority and no more.
* **Everything SOC 1 needs is recorded where CFOKit can read it**, because CFOKit makes the call.
* **The least that is new**: a dependency, a process, a shape of work.

## Considered Options

* A queued run that loops over the Messages API, with the published MCP tools as its only tools
* The Claude Agent SDK, in the same queued run
* Managed Agents
* The Messages API's MCP connector and the Skills API
* The loop inside the chat request, streamed to the browser

## Decision Outcome

Chosen option: "A queued run that loops over the Messages API, with the published MCP tools as its
only tools", because it is the only option that runs on the local stack, reaches the books only as
a client, holds no connection open, and adds one dependency to a shape of work CFOKit already runs.

> A person's message is stored in its company's conversation and enqueues a turn in one commit. The
> work pass runs the turn: it calls the model through the Messages API, with the bookkeeper skill as
> its instructions and the published MCP tools as its only tools, called over MCP as the runtime's
> own client acting for that person. Everything the turn does is appended to the conversation, which
> the chat window reads by asking for what is new.

### 1. A conversation is one company's, and is appended to

A conversation belongs to one company and one person, and holds an append-only sequence of
entries: the person's messages, the agent's replies, each tool call and its result, and each model
call's identifier, version and skill version. Row-level security scopes it to the company like
everything else the company holds (`SOC2-16`). It is read and written through the published API,
which the web client and the runtime both call; the web client gains no endpoint of its own
(ADR-0049 § 4). Entries are never edited, so what the model saw is recoverable (`SOC1-06`).

### 2. A turn is a run in the work queue

Sending a message stores it and enqueues a turn in the same transaction (ADR-0061 § 1), and the
person waits on it, so a pass starts at once. The turn's handler runs the loop until the model ends
its turn, appending each entry as it happens. A turn already running for a conversation makes the
next message wait for it, as ADR-0061 keeps one running run per reference.

**Unattended work ends in the same conversation.** When a run of another kind leaves something for
the person, such as a transaction nothing resolved, it appends an entry to the company's
conversation, and the person meets it there when they next open it.

**The chat window asks for what is new.** It reads the entries after the last one it holds, about
once a second while a turn runs and not at all when none is running. No connection stays open.

### 3. The model is called through the Messages API, behind a protocol

The handler calls the model through the `anthropic` SDK, which becomes the seventh runtime
dependency. The call sits behind a protocol with two implementations: the Anthropic one, and a
scripted one the tests use, so the loop, the entries and the tool calls are tested with no
credential (ADR-0004). With no inference credential configured, the runtime is off and the chat
window says so; nothing else changes.

The model identifier is the deployment's configuration and is pinned, and a change to it is
recorded (`SOC1-35`). Each call records its usage (ADR-0072).

### 4. The tools are the published ones, called as the runtime's own client

The handler lists the published MCP tools and offers them to the model as its tools, and nothing
else: no file, shell or web tool. It calls them over MCP with a token issued to the runtime's
registered client, acting for the person whose conversation it is, so the authority is the
intersection `IAM-11` defines and every write's audit row names both. How the runtime obtains that
token for a person, including for a turn no request is waiting on, is decided in its own record.

The bookkeeper skill's `SKILL.md`, at the version the image carries, is the turn's instructions, and
its version is recorded with each model call.

### Consequences

* Good, because the runtime is the person's own agent with CFOKit's model: same skill, same tools,
  same authority checks, so a capability built once serves both hosts.
* Good, because it runs on `docker compose up` with a self-hoster's credential, and its tests need
  none.
* Good, because every model call, tool call and result is a row CFOKit holds, which is what
  `SOC1-06` asks for.
* Good, because a turn and unattended work are one shape, so the conversation is where both end.
* Bad, because the loop is CFOKit's code to maintain: retries, refusals, context growth and tool
  errors are handled here rather than by a harness.
* Bad, because a reply appears when an entry is appended, not word by word, and a pass starting
  adds its startup to the first entry.
* Bad, because the runtime calls CFOKit's own MCP endpoint over HTTP rather than in process, which
  costs a round trip per tool call.
* Bad, because a seventh runtime dependency, with its own release cadence, is now load-bearing.
* Neutral, because the token the runtime holds for a person is a separate decision, and the
  runtime cannot run until it is made.

### Confirmation

* An `import-linter` contract forbids the runtime's package from importing any capability
  package, so it can reach the books only through the published surface.
* The scripted model drives the loop in the suite: a turn's entries, its tool calls through the
  published MCP surface, and the refusals that surface returns, asserted on the records they leave.
* Review: no tool is offered to the model that the published MCP surface does not publish.

## Pros and Cons of the Options

### A queued run that loops over the Messages API, with the published MCP tools as its only tools

* Good, because it meets every driver.
* Bad, because CFOKit owns the loop and its failure handling.

### The Claude Agent SDK, in the same queued run

The strongest alternative. It loads the `SKILL.md` as written, connects to an MCP server on
`localhost`, and brings a tested harness: context management, retries, hooks and sessions.

* Good, because the loop, context management and skill loading are not CFOKit's to write.
* Bad, because it brings file, shell and web tools the bookkeeper must not have, which then have to
  be switched off and kept off. A runtime offering only the published tools is the clearer thing to
  hold to `SOC2-03`.
* Bad, because each image gains about 114 MB of a bundled program whose license is stated only by
  reference, in a product whose runtime ADR-0034 § 1 ships as Apache 2.0 for anyone to build.
* Bad, because its interface is async and its sessions are its own, so the record of a turn would
  be reconstructed from its events rather than written as it happens.

### Managed Agents

* Good, because Anthropic runs the loop and the sandbox, and skills and MCP servers attach as
  configuration.
* Bad, because Anthropic must reach CFOKit's MCP endpoint, so it does not run on the local stack or
  for a self-hoster without a public address.
* Bad, because the session's state lives with the provider, and what `SOC1-06` needs would be read
  back from it rather than recorded by CFOKit.
* Bad, because it is a beta, and the product's main surface would rest on it.

### The Messages API's MCP connector and the Skills API

* Good, because the least code: the API calls the tools and runs the skill.
* Bad, because the provider calls CFOKit's MCP endpoint, so it needs a public address and a token
  for the person that leaves CFOKit.
* Bad, because a tool call is made by the provider, so CFOKit sees its result only in the response
  rather than at the call.

### The loop inside the chat request, streamed to the browser

The most familiar chat experience: the reply appears as it is written.

* Good, because the person sees the reply arrive word by word.
* Bad, because streaming is SSE or a websocket, which ADR-0012 gates, and a request holding a loop
  for minutes defeats scale-to-zero (ADR-0017).
* Bad, because a turn that outlives a closed tab or a dropped connection is lost or orphaned,
  where a queued run finishes and is read later.

## More Information

**Follow-on obligations.**

* A record on how the runtime holds a token for a person, for a waiting request and for an
  unattended run. It bears on `SOC1-25`'s conflict noted in `docs/decisions/README.md`, and on auth,
  so it needs a person's review.
* The conversation's tables, its endpoints in the published API (a contract change, Gate 5), and
  the chat window in the web client, whose transcript and prompt field have accessible names a
  Playwright spec can address (ADR-0074).
* The `anthropic` SDK added as a runtime dependency, with its license and reason in
  `pyproject.toml`, and `CLAUDE.md`'s count of runtime dependencies updated from six to seven.
* A provider registry entry for the provider, before it receives customer data (`SOC2-10`,
  ADR-0035).
* A turn kind in the work queue, and the appended entry an unattended run leaves for the person.

**Reversal cost.** Moderate. The conversation and the queued turn stand whatever runs the loop, so
moving the loop to the Agent SDK or a hosted agent replaces one handler. Moving to streaming
replaces the chat window's reading and needs ADR-0012's gate.

Related: ADR-0034 (the runtime), ADR-0035 (who supplies inference), ADR-0061 (the work queue),
ADR-0066 (an agent acts for a person), ADR-0068 (conversation first), ADR-0072 (usage), ADR-0074
(the use cases recorded as clips).

## Revisit when

* A person waits more than five seconds, at the median, for the first entry of a turn, so polling
  a queued run feels broken.
* The loop's own failure handling grows past what the Agent SDK or a hosted agent would supply,
  measured as more code in the handler than in the rest of the runtime.
* A hosted agent can call an MCP server inside a private network, so the local stack no longer
  rules it out.
* ADR-0012's gate is lifted for streaming.
