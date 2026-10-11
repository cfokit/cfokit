---
status: "proposed"
kind: "requirement-driven"
date: 2026-10-11
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
* Allow the agent that connects next, without a click
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

### 3. Seeing which agents are connected

Each time an agent opens an MCP session, the server records the client, the person it acts for,
and the name and version the client reports in `initialize`, with one `audit_log` row. The
reported name is the client's own claim, shown beside its ID and never used to decide anything.

The web client shows, for each company, a light for the person viewing it:

* **Green**: an agent allowed in this company has connected. The list shows each, by its reported
  name, with when it last connected.
* **Amber**: an agent has connected for this person but is not allowed in this company. The light
  offers to allow it.
* **Red**: no agent has connected for this person.

Removing a connector on the agent's side tells the server nothing, so a light stays green after it.
The last-connected time is what shows an agent has gone quiet, and revoking is the person's act.

### 4. Allowing as part of connecting

Where the web client sends a person to connect an agent, from the end of getting started or from
Settings (ADR-0058), it then waits on the same page. When an agent opens its first session for that
person after they set off, the page shows it, by name and first-connected time, with **Allow** and
the role preselected as `bookkeeper`. The person's click writes the grant, as in § 2. Nothing is
allowed without it.

### 5. An agent that creates a company is allowed in it

When an agent creates a company for its person (`IAM-06`), the same act grants that agent
`bookkeeper` in it, with its own `audit_log` row. The person is the first owner (`IAM-05`), sees the
agent in the company's list, and may revoke it.

This is not the automatic grant rejected below, which opens companies that already exist, holding
books, to an agent the person never chose for them. A company an agent creates did not exist until the
person asked their agent to set it up, and holds nothing but what the two of them then put in it. The
request to create it is the person's authorization of that agent in that company (`IAM-12`), and the
grant is a row they see and revoke like any other (`IAM-15`). Requiring a click in the web client
instead would put a browser step in the middle of the conversation that ADR-0058's agent door keeps
them in, to authorize access to a company that is empty.

The risk is an agent that creates a company the person did not ask for. What it gains is a new, empty
company of its own making, held by the person, who can delete it (`PLT-13`). It gains nothing in any
company that existed before.

### Consequences

* Good, because `IAM-11` and `IAM-12` hold for every client that connects today, with no change
  on Claude's side.
* Good, because each entry records the agent and the person it acted for, so the audit trail
  answers who did it (`SOC1-25`), and ADR-0034's coverage rule has the client to read.
* Good, because the authorization is a grant like any other, so the existing check, history and
  revocation apply unchanged (ADR-0039).
* Bad, because every new connection needs one click in the web client before it can act in a
  company it did not create. Connecting from the web client puts that click on the same page.
* Bad, because a client's ID changes when it registers again, for example after a person
  removes and re-adds a connector. The new ID must be allowed again, and the old grant remains
  until it is revoked.
* Good, because a person can see at a glance whether an agent is connected, and which.
* Bad, because a company created through an agent has that agent in it without a click. The grant is
  limited to the company it created, which held nothing before.
* Bad, because a light shows that an agent connected, not that it still can: a connector removed
  on the agent's side stays green until the person revokes it.
* Neutral, because the settings page is where the person manages this, so it is the same page
  that explains how to connect.

### Confirmation

* Unit tests of `principal_from_claims` cover the web client, another client, `act`, and a
  token naming no client.
* An integration test shows an agent refused with `agent_not_allowed`, allowed and then served,
  and refused again once revoked, in one company while unaffected in another.
* An integration test shows an agent that creates a company holding `bookkeeper` there and nowhere
  else, and a session's `initialize` recorded with one audit row.
* Web client tests show each light from the recorded sessions and grants, and the waiting page
  showing a session that arrives after the person set off, and none from before.
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

### Allow the agent that connects next, without a click

The waiting page of § 4 would grant the first new agent to arrive.

* Good, because it saves one click.
* Bad, because whichever client reaches the server first is allowed, which may not be the one the
  person connected, and a grant nobody saw is not an authorization (`IAM-12`).

### Grant the agent automatically wherever the person holds a role

The first call from a client would create its grant.

* Bad, because a grant nobody chose is not an authorization, so `IAM-12` is not met, only
  renamed.
* Bad, because a person who connects Claude for one company gives it every company.

## More Information

**Follow-on obligations.** `AUTH_WEB_CLIENT_ID` is added to the variables authentication reads in
the same change that implements § 1: ADR-0019 § 1's "reads `AUTH_ISSUER_URL` and `AUTH_AUDIENCE` and
nothing else", CLAUDE.md's Authentication rule, and the table in `infra/README.md`. It names a client,
not an issuer, so ADR-0019's portability holds.

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
