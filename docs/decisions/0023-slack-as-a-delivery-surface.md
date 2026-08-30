---
status: "accepted"
kind: "requirement-driven"
date: 2026-08-18
decision-makers: [Geoff]
---

# ADR-0023: Slack is a delivery surface, built as a separate component over HTTP events

## Context

The product vision depends on Slack. *"Deploy once, manage multiple clients through Slack"* is the
value proposition for fractional CFOs, and the "save 15+ hours per client per month" claim rests on
per-client channels (REQ-D1). It is currently the only `Blocked` P1 requirement.

It is blocked because scope discipline gates adjacent surfaces
([ADR-0013](0013-binding-non-goals-and-scope-discipline.md)). Slack is not literally on the
non-goals list, but two of the ways one might build it are:

- **Socket Mode** is a websocket connection, and websockets are a binding non-goal.
- A Slack app is a user-facing interaction surface, which is adjacent enough to "web UI or admin
  console" that building one without a record would be exactly the drift the gate exists to catch.

So the gate applies, and this is the ADR that lifts it.

The genuinely hard part is not Slack's API. It is that **a channel is not an authorization boundary
and must not be mistaken for one.** A fractional CFO holding fifteen clients in one deployment has
fifteen sets of books that must not leak into each other, and Slack channel membership is managed by
whoever has permission to invite people — which is not the same as who is entitled to see a
company's financial position.

## Decision

### 1. Slack is a separate component, not a module

Applying the criteria in [ADR-0024](0024-tiny-ledger-modules-and-components.md) section 3:

| Question | Answer |
|---|---|
| Must it commit atomically with a ledger write? | No — it receives messages and calls the API |
| Does it hold third-party credentials worth isolating? | **Yes** — bot token and signing secret |
| Could a third party plausibly build it against the published API? | **Yes**, and some will |

Two criteria point the same way, so it is a component. It authenticates with the client credentials
grant and reads `CFOKIT_API_URL` like any other ([ADR-0025](0025-component-deployment-and-authentication.md)).

This is the first real test of ADR-0024's criteria, and they resolved it without argument.

### 2. HTTP Events API, not Socket Mode

Slack delivers events by signed HTTP POST to a public endpoint. Every request is verified against
the signing secret with a timestamp freshness window, and unverified requests are rejected before
any work is done.

The component is a **service** in the sense of ADR-0025 — request-serving, scale-to-zero, no
long-running connection.

**This means the Slack surface requires public ingress**, which core self-hosting does not. A
self-hoster who wants Slack needs a tunnel and `PUBLIC_BASE_URL` set to the public hostname — a
requirement ADR-0019 already documents for cross-device access. **Self-hosting without Slack is
unaffected**, and that is the honest framing: this is a limitation of one surface, not a change to
the self-hosting promise.

### 3. A channel is bound to exactly one entity, server-side

The binding from Slack channel to CFOKit entity is a **stored record**, created deliberately. It is
never inferred from channel name, topic, or message content.

Every request originating in a channel carries that channel's entity and no other. There is no way
to ask about a different entity from inside a channel, because the entity is not a parameter the
message can influence.

### 4. Channel membership is not authorization

**This is the load-bearing rule.** Being in a Slack channel grants nothing.

A request is authorised only if **both** hold:

1. The Slack user is **linked** to a CFOKit identity, and that identity holds a grant for the
   channel's entity.
2. The component's own client holds a grant for that entity.

The effective permission is the **intersection**. An unlinked user in a bound channel can do
nothing, and a linked user cannot exceed their own grants by being invited somewhere.

Entity grants are validated server-side regardless of what the component asserts
([ADR-0012](0012-entity-advisory-lock-idempotency-keys.md)). The component is a **trusted delegate**
— it asserts which linked user is acting, and the ledger enforces what that user may do.

### 5. Slack is a surface, not a published interface

It does not become a fourth entry in [ADR-0016](0016-three-published-interfaces-stability-obligations.md).
Slack users interact with a product surface; nobody writes software against it. The published
interfaces remain REST, MCP tools, and error codes — and this component is a *consumer* of them, which
is part of why building it this way keeps those interfaces honest.

### 6. Deliberately not decided here

**How an agent is invoked and executed.** REQ-D1 says the agent operates in the channel, but the
agent runtime — where a skill runs, how it is scheduled, how conversation state is held — is a
separate concern with its own decisions to make. This record covers the delivery surface: receiving
a verified message, resolving identity and entity, and calling the API. What produces the reply is
out of scope.

## Alternatives rejected

### Socket Mode

Genuinely attractive, and better than the chosen option in one important respect: it needs **no
public ingress at all**, so a self-hoster behind NAT could run the Slack surface with no tunnel. For
a project that treats self-hosting as a product promise, that is a real argument.

Rejected on two counts, either sufficient. It is a websocket, which is a binding non-goal
(ADR-0013). And it requires a persistently connected process, which is not one of the two runtime
shapes (ADR-0025) — it would be the long-running worker that decision explicitly excludes, on a
platform where scale-to-zero is assumed (ADR-0018).

The self-hosting cost is real and is accepted rather than dismissed: Slack needs a tunnel, the core
product does not.

### Slack as an in-process module inside the service

Fewer moving parts, no second deployment, no client credentials to manage.

Rejected because it fails ADR-0024's criteria on two counts — it holds third-party credentials, and
it is exactly the kind of thing a third party could build against the API. Co-locating it would also
put Slack's signing secret and bot token in the serving container, widening the blast radius of the
process that holds database credentials.

### Channel membership as the authorization model

By far the simplest, and superficially intuitive: you are in the client's channel, so you may see the
client's books.

Rejected because it delegates financial authorization to whoever can send a Slack invite. Channel
membership is administered by workspace users for collaboration reasons, and the failure is silent
and severe — someone invited to discuss one matter gains a client's complete financial position. For
a deployment holding fifteen unrelated companies, this is the worst available failure.

### Inferring the entity from message content

Let the user say which client they mean, and resolve it.

Rejected because it makes the tenancy boundary a function of parseable text. Ambiguity, similar
company names, and prompt injection all become paths across an entity boundary. Binding the entity
to the channel means the boundary cannot be addressed by anything a message contains.

### One Slack app installed per client

Maximum isolation: separate app, separate token, separate everything.

Rejected on the operational reality it creates for the audience it is meant to serve. A fractional
CFO with fifteen clients would install, configure and rotate credentials for fifteen apps —
directly contradicting "deploy once, manage multiple clients".

### Email instead of Slack

Universal, no app to install, no platform dependency, and it works for clients who do not use Slack.

Rejected as the *primary* surface because the interaction model is wrong for the workflow: the value
is a running per-client conversation with the books, and email is poor at that. It remains a
plausible additional surface later, and would need its own record.

### Build a small web UI instead

Would avoid the Slack dependency and serve clients regardless of what chat platform they use.

Rejected as squarely the non-goal ADR-0013 exists to gate. It is also not what the vision describes,
and it would be a larger commitment — sessions, its own authentication, a design surface — than the
component chosen here.

## Consequences

**Accepted costs.**
- A platform dependency. Slack's API, rate limits, and app-review policies become constraints, and a
  breaking change there is a breaking change here.
- The Slack surface needs public ingress, so a self-hoster wanting it needs a tunnel.
- Linking Slack users to CFOKit identities is an onboarding step, and it will be the friction people
  complain about. It is also the only thing standing between a channel invite and a client's books.
- Another OAuth client, another secret to populate out of band and rotate.

**Follow-on obligations.**
- Request signature verification with a timestamp freshness window, rejecting before any work.
  Failure to verify is not a logged warning; it is a rejection.
- Channel-to-entity bindings are records, created deliberately, and changing one writes an
  `audit_log` row like any other state change.
- A Slack user identity link, with an explicit unlink path.
- Every action taken from Slack is attributed in the audit trail to the **linked CFOKit user**, not
  to the component. "The Slack bot did it" is not an audit trail.
- Never post posting amounts, account numbers, or payee names into a channel that is not bound to
  that entity — and treat message content as untrusted input throughout.
- ADR-0013's non-goals list is updated to record that this item passed the gate, and when.
- REQ-D1 moves from `Blocked` to `Accepted`.
- `infra/README.md` documents the Slack component's variables and its public-ingress requirement.

**Reversal cost. Moderate.** The component is separable and the ledger knows nothing about Slack, so
removing it costs the component and the bindings. But users who have organised their practice around
per-client channels would be badly disrupted, so the cost is to them rather than to the codebase.

## Revisit when

- Slack changes its event delivery model, or Socket Mode becomes the only supported path — which
  would force a return to ADR-0013, since websockets would then be unavoidable rather than chosen.
- A second delivery surface is genuinely needed, at which point the channel-to-entity binding
  generalises to a conversation-to-entity binding and should be designed once rather than twice.
- Self-hosted demand for Slack without public ingress becomes real, which is the case that would
  justify re-examining Socket Mode against the non-goals list.
