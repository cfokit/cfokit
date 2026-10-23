---
status: "proposed"
kind: "requirement-driven"
date: 2026-10-23
decision-makers: [Geoff]
---

# ADR-0077: The runtime acts for a person with a token exchanged from theirs, and only while they are there

**Requirements served:** `IAM-10`, `IAM-11`, `SOC1-25`, `NFR-06`.

## Context and Problem Statement

CFOKit's runtime is a component that calls the published MCP tools and REST API as its own client,
acting for a person (ADR-0075). This record decides what token it presents, where that token comes
from, and what happens when no person is there to supply one.

Facts that bear on the answer:

* **The server already reads a token's client as the agent.** A token issued to `cfokit-web` is the
  person; a token issued to any other client is the agent `client:<client_id>` acting for `sub`,
  which acts in a company only where the person has allowed it, within the intersection of their
  grants (ADR-0066, `IAM-11`). An `act` claim, where an issuer sends one, is read as delegation
  (ADR-0033).
* **`SOC1-25` requires the acting principal's own credential to flow through**, "never against a
  shared credential with the real actor passed as a parameter". Components authenticate by the
  client credentials grant (ADR-0032), which `docs/decisions/README.md` lists as a conflict with
  `SOC1-25`, naming OAuth token exchange (RFC 8693) as the fix.
* **The issuer is swappable behind a conformance contract**, and no issuer-specific code exists
  (ADR-0019). Credentials never pass through an agent or a model (`IAM-10`).
* **Keycloak, the default issuer, at 26.8.0**: standard token exchange (RFC 8693, its "V2") has been
  fully supported since 26.2, for exchanging one of the realm's access tokens for another, with the
  `audience` parameter narrowing the result. The requesting client must be confidential and named
  in the subject token's audience. Impersonation is not part of standard exchange, and delegation
  with consent, which marks the client with an `act` claim, is a preview in 26.8.0.
* **The realm's access tokens last eight hours by default** (`CFOKIT_ACCESS_TOKEN_LIFESPAN`), longer
  than any turn.
* **Nothing unattended needs the model yet.** The four first use cases (ADR-0075) run while a
  person is in the conversation. What unattended work leaves for the person — a transaction
  nothing resolved (`BKP-12`), a statement recorded — is produced by core's own handlers without a
  model.

## Decision Drivers

* **The person's own credential flows through** (`SOC1-25`), so the books see a person and an agent,
  never an agent claiming a person.
* **No new path the server must trust**: the authority checks ADR-0066 already makes apply unchanged.
* **No long-lived credential for a person held anywhere** that a breach of the runtime would expose.
* **Standard OAuth, in the issuer conformance contract**, with no issuer-specific code.

## Considered Options

* Exchange the person's token for one issued to the runtime, per turn; nothing unattended runs the
  model
* Offline tokens: the runtime stores each person's refresh token and acts whenever needed
* Client credentials, with the person named in each request
* Forward the web client's own token
* Keycloak's delegation with consent

## Decision Outcome

Chosen option: "Exchange the person's token for one issued to the runtime, per turn; nothing
unattended runs the model", because it is the standard way for a service to act for the person
calling it, it carries the person's own credential through as `SOC1-25` asks, and it leaves no
person's credential stored anywhere.

> The chat window sends the person's access token with their message. The runtime exchanges it
> (RFC 8693) for an access token issued to its own confidential client, with CFOKit's API as the
> audience, and uses that token for every tool and API call in the turn. The server sees the agent
> `client:cfokit-runtime` acting for that person, allowed per company like any agent. The runtime
> acts only while a person's request is open; unattended work leaves its questions in the
> conversation for the person's next turn.

### 1. Per turn

The web client's tokens carry the runtime's client in their audience, so the issuer will exchange
them. At the start of a turn the runtime makes one exchange and holds the result in memory for the
turn only. It never stores a token, and never sees a password (`IAM-10`). The exchanged token's
audience is CFOKit's API (`NFR-06`), so it is validated exactly as every other token is.

The runtime is an agent like any other: the first time a person uses the chat in a company, the
server refuses with `agent_not_allowed` and its link, and the chat window offers that link, where
the person allows it as `bookkeeper` or `reader` (ADR-0066). What it may do is the intersection of
that grant and the person's own.

### 2. Nothing unattended runs the model

A run in the work queue that leaves something for the person appends it to the company's
conversation itself, through core's own module (ADR-0076), and the person meets it when they next
open the chat. The model works on it then, in that person's turn and with their token.

Running the model with nobody there, as managed bookkeeping will want, takes the same shape as any
unattended work: a schedule in core's work queue (ADR-0061), whose run calls the runtime, which
uses the model and reaches the ledger through MCP like a turn does. What that run lacks is a
person's token to exchange. Whether it holds one through the owner's offline consent, or acts as
CFOKit's bookkeeping service with a role the owner grants, is decided with managed bookkeeping,
against the issuer's delegation support as it then stands.

### Consequences

* Good, because the conflict between `SOC1-25` and ADR-0032 is resolved for the runtime: the
  person's credential flows through, and the runtime is visibly the actor.
* Good, because the server's authority checks are unchanged; the runtime is one more client.
* Good, because a breach of the runtime exposes no stored credential, only tokens of turns in
  flight.
* Bad, because the issuer conformance contract gains standard token exchange, narrowing the issuers
  that qualify, and the realm gains a confidential client and an audience on the web client's
  tokens.
* Bad, because nothing the model does happens while the person is away, so a question waits for
  them to open the chat.
* Neutral, because components other than the runtime, such as Slack (ADR-0021), still use the
  client credentials grant, and the conflict stands for them.

### Confirmation

* The issuer conformance contract (ADR-0019) lists standard token exchange, and the realm test
  that holds the web client's settings holds the runtime's client and the audience too.
* An integration test makes an exchange against the compose stack's issuer and calls the API with
  the result, asserting the audit row names the runtime acting for the person, and that a company
  where the runtime is not allowed refuses with `agent_not_allowed`.
* Review: the runtime writes no token to storage or logs.

## Pros and Cons of the Options

### Exchange the person's token for one issued to the runtime, per turn; nothing unattended runs the model

* Good, because it meets every driver.
* Bad, because the model does nothing unattended.

### Offline tokens: the runtime stores each person's refresh token and acts whenever needed

The strongest alternative for unattended work: the person consents once, and the runtime can act
for them at any hour, which managed bookkeeping will eventually want.

* Good, because the model can work while the person is away.
* Bad, because every person's refresh token would be stored, a long-lived credential whose theft
  acts for them until revoked, and the runtime holds no storage (ADR-0075), so they would sit in
  core.
* Bad, because no use case needs it yet.

### Client credentials, with the person named in each request

What other components do (ADR-0032).

* Good, because it needs nothing beyond the grant already in the conformance contract.
* Bad, because it is the shape `SOC1-25` forbids: a shared credential with the real actor passed as
  a parameter.

### Forward the web client's own token

* Good, because it is the least work: the runtime calls the API with the token it was sent.
* Bad, because the server would see the person acting, not an agent, so the agent's grant, the
  intersection, and the record of who acted would all be wrong (ADR-0066).
* Bad, because the token's audience is the web client's, not the API's alone.

### Keycloak's delegation with consent

* Good, because it marks the runtime with an `act` claim the server already reads (ADR-0033).
* Bad, because it is a preview in Keycloak 26.8.0, and a preview in one issuer cannot go into a
  conformance contract that any issuer must meet.

## More Information

**Follow-on obligations.**

* The realm adds the runtime's confidential client and the audience on the web client's tokens;
  its secret is a container populated out of band (ADR-0016).

This record adds standard token exchange to ADR-0019's conformance contract, and replaces ADR-0075
§ 1's unattended start with § 2 here.

**Reversal cost.** Low. The token is held for a turn and never stored, so moving to another
mechanism changes how the runtime obtains it and nothing the server keeps.

Related: ADR-0019 (the issuer), ADR-0032 (components' credentials), ADR-0033 (delegation), ADR-0066
(an agent acts for a person), ADR-0075 (the runtime), ADR-0076 (conversations).

## Revisit when

* A use case needs the model to work while the person is away, such as a scheduled run for
  managed bookkeeping.
* Keycloak's delegation with consent is fully supported, and a second issuer offers the same.
* An issuer CFOKit must support lacks standard token exchange.
