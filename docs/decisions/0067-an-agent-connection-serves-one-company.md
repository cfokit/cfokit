---
status: "proposed"
kind: "requirement-driven"
date: 2026-10-10
decision-makers: [Geoff]
---

# ADR-0067: An agent's connection serves one company, named in its address

**Requirements served:** `IAM-08`, `IAM-12`.

## Context and Problem Statement

A person may hold several companies' books, and `IAM-08` makes an advisor across many the
ordinary case. Every tool takes an `entity_id`, so which company a call reaches is an argument
the model writes on every call. A model is not deterministic. Over a long conversation it can
carry the wrong ID forward, or pick another company it judges a better fit, and the person
sees a figure from the wrong books presented as theirs. Mixing two companies' books is the
worst failure the bookkeeper skill names.

Every answer now names its company, and the skill tells the model to keep to the one the
person chose. That makes a switch visible. It does not prevent one, because both the switch
and the check are the model's own.

ADR-0066 allows an agent per company. That bounds which companies a switch can reach. It does
not stop a switch among the companies the person allowed.

The MCP surface is reached at one address, `${PUBLIC_BASE_URL}/mcp`. A client connects to an
address, and Claude lets a person turn each connector on or off in a conversation.

## Decision Drivers

* Which company a call reaches is decided by something the model cannot change.
* The person chooses the company in a way they can see, and switching is their act.
* The published tool surface stays one surface (ADR-0014, ADR-0015).
* An advisor with many companies is not made to repeat work per company without need.

## Considered Options

* Name the company in the connection's address
* Leave the choice to the model, checked by the named answers
* Remove `entity_id` and add a tool that selects the company for the session
* One issuer client per company

## Decision Outcome

Chosen option: "Name the company in the connection's address", because it is the only option
where the server, not the model, holds which company a conversation is about.

> An agent connects to `${PUBLIC_BASE_URL}/companies/<slug>/mcp`. That connection serves that
> company and no other. A call naming another `entity_id` is refused with
> `other_company`, and `list_entities` answers with that company alone.

The tool surface is unchanged. Every tool still takes `entity_id`, so one published contract
serves every connection. A bound connection checks the argument rather than replacing it, and
the named answers still show it.

The person connects once per company. In Claude that is one connector per company, named for
it, such as "CFOKit · Acme LLC". Switching companies is turning one connector off and another on,
which is the person's act and visible in the conversation.

`${PUBLIC_BASE_URL}/mcp`, serving every company, remains for the person's own clients. An agent
reaching it is refused with `connect_per_company`, which names the address to use.

### Consequences

* Good, because a switch the person did not make cannot happen: the server refuses it.
* Good, because the protected-resource metadata, the authorization and the grant from ADR-0066 all
  name one company, so what the person allowed and what the connection reaches are the same.
* Bad, because an advisor with many companies adds a connector for each. Each connector also
  registers its own client, so each is allowed once, in its company.
* Bad, because the server serves protected-resource metadata per company address (RFC 9728 § 3.1,
  the path appended to the well-known path), and the MCP transport is reached at many paths.
* Neutral, because `entity_id` stays in every tool's input. It is redundant on a bound connection,
  and dropping it would split one contract into two.

### Confirmation

* An integration test calls a bound connection with its own company, another company, and
  `list_entities`, and asserts the answer, `other_company` and the one company listed.
* A probe, recorded in More Information before this record is accepted, adds two custom
  connectors on one host with different paths in Claude, and confirms each registers, signs in
  and is listed separately.

## Pros and Cons of the Options

### Name the company in the connection's address

* Good, because the binding lives in the server, outside the model's reach.
* Good, because Claude already presents connectors as things a person turns on and off.
* Bad, because one connector per company is more setup for someone holding many.

### Leave the choice to the model, checked by the named answers

* Good, because it needs nothing beyond what exists.
* Bad, because the model both makes the choice and checks it. A defect in one is likely a defect
  in the other.

### Remove `entity_id` and add a tool that selects the company for the session

The model calls `use_company` once, and every call after it reaches that company.

* Bad, because the MCP transport here is stateless, so a session is state the server would add
  to hold.
* Bad, because selecting is still a tool the model calls. A switch is one more call, and nothing
  the person does.
* Bad, because it changes every tool's published input at once (ADR-0015).

### One issuer client per company

Bind the company to the client registration, so the token itself names the company.

* Bad, because clients register themselves (ADR-0064), and what a client registers is the
  client's choice, not CFOKit's.
* Bad, because the token's audience stays the ledger's (ADR-0019), so the company would ride in a
  claim the issuer has to be configured to add, which is issuer-specific.

## More Information

**Unverified.** That Claude accepts two custom connectors on one host with different paths, and
runs RFC 9728 discovery per path, is not yet probed. The Confirmation's probe settles it before
this record is accepted.

**Reversal cost.** Low. The unbound address remains, and removing the binding is a routing
change. Connectors people added would keep working, at the cost of the guarantee.

## Revisit when

* Claude can bind a conversation or a Project to one connector's configuration, such as a
  parameter that the server receives on every call. The binding could then live there.
* An advisor holds enough companies that a connector each is the main complaint. A per-person
  connection with a server-held choice, set in the web client, would then be weighed.
