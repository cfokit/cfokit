---
status: "proposed"
kind: "requirement-driven"
date: 2026-10-10
decision-makers: [Geoff]
---

# ADR-0066: An agent is the client it signs in through, and acts in a company once the person allows it

**Requirements served:** `IAM-11`, `IAM-12`, `IAM-15`, `SOC1-25`.

## Context and Problem Statement

`IAM-11` requires an agent to act as itself on behalf of an identified person, with authority
equal to the intersection of its own and the person's. `IAM-12` requires the person to
authorize it separately in each entity, and to be able to revoke any one authorization alone.
`IAM-15` makes a revocation take effect at once.

The server derives the principal from the bearer token, and ADR-0033 reads delegation from an
RFC 8693 `act` claim. No client CFOKit supports sends one. Claude's custom connector and
`mcp-remote` both run the authorization-code flow against the issuer, as the person, through
a client they registered for themselves under RFC 7591. The token they receive names the
person in `sub` and carries no `act` claim. Token exchange, which would mint one, is
something the client starts, and neither does.

So every call Claude makes today is attributed to the person, with the person's whole
authority in every company they hold a role in. Neither `IAM-11` nor `IAM-12` holds. The
audit trail cannot tell what the person did from what Claude did for them, which is the
question `SOC1-25` exists to answer.

What the server does see is which client the token was issued to. OpenID Connect names it in
`azp`, and RFC 9068's access-token profile in `client_id`. Every issuer in ADR-0019's
contract issues one of them. The web client is one known client per deployment. Every other
client is software a person signed in through.

## Decision Drivers

* `IAM-11` and `IAM-12` are approved Musts, and nothing in the deployment meets them.
* Nothing issuer-specific (ADR-0019). The issuer remains swappable.
* No step that only Claude could perform. A client must not have to change for this to hold.
* The person authorizes, in a browser, signed in as themselves (`IAM-10`). A model does not
  grant itself authority.
* A revocation takes effect on the next call (`IAM-15`).

## Considered Options

* The token's client identifies the agent; the person allows it per company in the web client
* Require an `act` claim, minted by token exchange
* Keep treating every token as its person
* Grant the agent automatically wherever the person holds a role

## Decision Outcome

Chosen option: "The token's client identifies the agent; the person allows it per company in the
web client", because it is the one option the server can enforce with tokens that clients
already send.

> A token issued to the web client is its person. A token issued to any other client is an
> agent, `client:<client_id>`, acting for `sub`. An agent acts in a company only where the
> person has allowed it there, with a role the person chose, and then within the intersection
> `IAM-11` defines.

### 1. Which client is the person

`AUTH_WEB_CLIENT_ID` names the web client. A token whose `azp`, or failing that `client_id`,
equals it is the person themselves. Every other token is an agent. A token naming no client
is refused, because there is no truthful principal to record.

An `act` claim, where an issuer sends one, still means delegation as ADR-0033 reads it.

### 2. Allowing an agent in a company

An agent with no grant in the company it called is refused with `agent_not_allowed`. The
refusal carries a link to the web client's page for allowing it. The person opens the link,
signed in as themselves. The page names the company, the client, and when that client first
called, and offers a role: `reader`, which reads, or `bookkeeper`, which reads, records and
posts. Both join the role catalog now that something holds them (ADR-0039). Allowing writes the
agent's grant, under the person's authority and in their name, with one `audit_log` row. Only
a person who can grant roles in the company can allow an agent there.

The same page lists every agent allowed in the company, and revoking one ends its grant
(`IAM-15`). Revoking in one company leaves every other company alone (`IAM-12`).

### Consequences

* Good, because `IAM-11` and `IAM-12` hold for every client that connects today, with no change
  on Claude's side.
* Good, because each entry records the agent and the person it acted for, so the audit trail
  answers who did it (`SOC1-25`), and ADR-0034's coverage rule has the client to read.
* Good, because the authorization is a grant like any other, so the existing check, history and
  revocation apply unchanged (ADR-0039).
* Bad, because every new connection needs one visit to the web client before it can act, in
  each company.
* Bad, because a client's ID changes when it registers again, for example after a person
  removes and re-adds a connector. The new ID must be allowed again, and the old grant remains
  until it is revoked.
* Neutral, because the settings page is where the person manages this, so it is the same page
  that explains how to connect (ADR-0067).

### Confirmation

* Unit tests of `principal_from_claims` cover the web client, another client, `act`, and a
  token naming no client.
* An integration test shows an agent refused with `agent_not_allowed`, allowed and then served,
  and refused again once revoked, in one company while unaffected in another.
* `AUTH_WEB_CLIENT_ID` joins `AUTH_ISSUER_URL` and `AUTH_AUDIENCE` as the variables
  authentication reads. CLAUDE.md's Authentication section names all three.

## Pros and Cons of the Options

### The token's client identifies the agent; the person allows it per company in the web client

* Good, because `azp` and `client_id` are standard claims, so the rule is the same on every
  issuer.
* Good, because the authorization happens on CFOKit's own page, where the person is signed in.
* Bad, because the server learns only the client's ID. Its display name sits behind RFC 7592
  management, which needs the client's own registration token. The page shows when the client
  first called instead, which the person can match with what they just did.

### Require an `act` claim, minted by token exchange

The standard shape for delegation, and what ADR-0033 assumed.

* Bad, because neither Claude's connector nor `mcp-remote` performs token exchange, so every
  Claude connection would be refused. Nothing CFOKit controls changes that.
* Bad, because it still does not record a per-company authorization, which `IAM-12` needs
  whatever the token says.

### Keep treating every token as its person

* Good, because it costs nothing.
* Bad, because it fails `IAM-11` and `IAM-12` outright, and leaves an agent with the full
  authority of an owner in every company the owner holds.

### Grant the agent automatically wherever the person holds a role

The first call from a client would create its grant.

* Bad, because a grant nobody chose is not an authorization, so `IAM-12` is not met, only
  renamed.
* Bad, because a person who connects Claude for one company gives it every company.

## More Information

ADR-0033 § 2 says delegation is the `act` claim. It is corrected to name both sources, the
`act` claim and the token's client.

ADR-0064 keeps self-registered clients to Claude's callback and loopback, so a client named
in a token is one a person signed in through on their own machine or in Claude.

**Reversal cost.** Low. The rule is one function, and the grants are rows. Undoing it restores
the person's full authority to every client, which is the state this record replaces.

## Revisit when

* Claude, or another supported client, sends an `act` claim or performs token exchange. The
  `act` claim then identifies the agent more precisely than the client does.
* A supported client's ID stops being stable across a person's sessions, so that allowing it
  once no longer lasts.
