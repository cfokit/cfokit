---
status: "proposed"
kind: "requirement-driven"
date: 2026-10-07
decision-makers: [Geoff]
---

# ADR-0064: A client that registers itself may send a sign-in only to a known redirect

**Requirements served:** `IAM-10`, `SOC2-21`.

## Context and Problem Statement

An agent's client connects to CFOKit by registering itself with the issuer under RFC 7591, with no
person or administrator involved, which is what lets an MCP client connect in one step (ADR-0019).
The realm CFOKit ships admits that registration anonymously and with none of Keycloak's
registration policies but its harmless defaults: each of the others refused a conforming client,
and the consent screen, shown on every connection by the proxies that force `prompt=consent`, was
removed with them (`infra/keycloak/README.md` gives the case for each).

That posture is safe only while nothing but the person's own machine can reach the issuer. A
deployment reachable by anyone else, such as CFOKit's hosted service, admits this:

1. An attacker registers a client whose redirect URI is a host they control.
2. They send a person a sign-in link to the deployment's real issuer.
3. The person signs in on the genuine page, with their second factor. No screen names the client.
4. The authorization code goes to the attacker's host, who exchanges it for an access token and a
   refresh token.

Every token the realm issues carries the ledger's audience, so the attacker then acts on the
person's books with that person's authority. The second factor does not stop it, because the
attacker never needs the password: the person authenticates and the code is delivered elsewhere.
Rate limits on the registration endpoint bound how many clients an address registers; they do
nothing about one.

`IAM-10` delegates sign-in to the identity provider so that a person's credential is handled in
one place. A sign-in that ends in someone else's hands defeats that as surely as a stolen
password. `SOC2-21` asks that a token's issuance be defined; one issued to whoever registered a
redirect is not.

The clients CFOKit supports reach the issuer in two ways. Claude's custom connectors register
with the redirect `https://claude.ai/api/mcp/auth_callback`, which Anthropic says may become
`https://claude.com/api/mcp/auth_callback`. A local proxy on the person's machine, such as
`mcp-remote` or Claude Code, registers a loopback redirect, `http://localhost:{port}/…` or
`http://127.0.0.1:{port}/…`. A code delivered to either reaches no one but the person: Claude's
callback completes only the connection the same browser started, and a loopback address is the
person's own machine.

The registration mechanism is moving. MCP 2026-07-28 deprecated RFC 7591 in favor of Client ID
Metadata Documents, under which a client is identified by a URL it controls, keeping RFC 7591 for
at least twelve months (ADR-0019). Claude supports both. Keycloak 26.7.4, the issuer CFOKit ships,
offers Client ID Metadata Documents as an experimental feature, off by default.

## Decision Drivers

* **A sign-in reaches only the client the person meant to connect.** Nothing an anonymous party
  registers can receive one.
* **Connecting an agent stays one step** for the clients CFOKit supports, with no administrator
  and no client to register by hand.
* **No issuer-specific code** in CFOKit (ADR-0019). Whatever enforces this is the issuer's
  configuration.
* **The check is literal.** A redirect is judged by its text, not by what a name resolves to today.
* **A laptop is unaffected.** Its issuer is reachable only from the same machine, and a
  self-hosted install keeps conventional defaults until it chooses otherwise.

## Considered Options

* Keep self-registration, and restrict a self-registered client's redirect URIs to a known list
  by regular expression, switched per deployment
* Keep self-registration, and restrict redirects with Keycloak's redirect-URI enforcer
* Keep self-registration, and restore the Trusted Hosts registration policy
* Close self-registration, and register every client deliberately
* Keep self-registration, and restore the consent screen
* Identify clients by Client ID Metadata Documents instead of registration

## Decision Outcome

Chosen option: "restrict a self-registered client's redirect URIs to a known list by regular
expression", because it closes the phishing path at registration while every supported client
still connects in one step, and it decides by the redirect's text alone.

> In a deployment reachable by anyone but the person's own machine, a client that registers or
> updates itself may name only Claude's callback, over https, or a loopback address, over http.

The realm declares a client profile whose one executor, Keycloak's `secure-client-uris-pattern`,
checks the `redirectUris` field and no other against two anchored patterns:

```
^https://claude\.(ai|com)/api/mcp/auth_callback$
^http://(127\.0\.0\.1|\[::1\]|localhost)(:[0-9]{1,5})?/[^?#*]*$
```

A client policy applies the profile when a client is created or changed `ByAnonymous` or
`ByRegistrationAccessToken`: registration without an administrator, and the registered client's
own later changes. Clients the realm declares itself, and clients an administrator registers, are
unaffected. The policy is enabled by `CFOKIT_RESTRICT_REGISTERED_REDIRECTS`, read when the realm is
imported, the same way as `CFOKIT_REQUIRE_SECOND_FACTOR`: `true` on CFOKit's hosted service,
unset and `false` on a laptop. `infra/keycloak/realm-settings.sh` applies the same profile and
policy to a realm that already exists.

### Consequences

* Good, because a code can no longer be delivered to a host an attacker registered, whatever
  their link looks like and whether or not the person has a second factor.
* Good, because Claude's custom connectors and local proxies connect exactly as before.
* Good, because a host that resolves to `127.0.0.1` without being literally a loopback address
  is refused, so registering one and later pointing it elsewhere gains nothing.
* Bad, because every other MCP client is refused on a deployment with the switch on until its
  redirect is added to the patterns, which is a change to the realm file and to
  `realm-settings.sh`.
* Neutral, because a self-hosted deployment reachable by others carries the same risk and the
  same remedy, which it turns on by setting the variable.

### Confirmation

`tests/test_issuer_realm.py` asserts the patterns, the field they apply to, and the conditions in
the realm file, and that `realm-settings.sh` sets the same. `tests/test_gcp_infrastructure.py`
asserts that the hosted deployment sets the switch to `true`. Whether Keycloak enforces the
policy as configured is not exercised by the suite, which runs the issuer with the switch off;
it was verified against Keycloak 26.7.4 by registering each accepted and refused form named under
`Pros and Cons of the Options`.

## Pros and Cons of the Options

### Restrict redirects by regular expression, switched per deployment

* Good, because it acts on the one field that carries a code and on no other, so a client that
  also names a homepage or a logo still registers.
* Good, because a regular expression compares text: no lookup, no time at which the answer
  differs from the time it was checked.
* Good, because it is configuration of the issuer's own executor, in the realm file, with no code
  in CFOKit.
* Bad, because the list is a list of products. A supported client is one whose redirect is in it.

### Restrict redirects with Keycloak's redirect-URI enforcer

`secure-redirect-uris-enforcer` was built for this. It takes a list of permitted domains, and
switches for IPv4 and IPv6 loopback and the http scheme, and checks a redirect at registration
and again at authorization.

* Good, because it is purpose-made and also enforces OAuth 2.0 and 2.1 redirect rules.
* Bad, because **it decides whether a host is loopback by resolving it when the URI names no
  port**. Under Keycloak 26.7.4, `http://localtest.me/cb`, `http://lvh.me/cb` and
  `http://127.0.0.1.nip.io/cb` were each accepted as loopback, because each resolves to
  `127.0.0.1`; the same names with a port were refused. An attacker registers a name of their own
  that resolves to `127.0.0.1`, and later points it at their server. That is the attack this
  record closes, reopened through DNS.
* Bad, because in OAuth 2.1 mode it refuses loopback over http altogether, which every local
  proxy uses.

### Restore the Trusted Hosts registration policy

* Good, because it is Keycloak's own policy for exactly this, enabled by default.
* Bad, because its "client URIs must match" check applies to every URI a client names, not only
  its redirects, so a conforming client that advertises a homepage is refused. That is why it was
  removed (`infra/keycloak/README.md`). Its other mode, matching the address the registration
  request comes from, identifies nothing behind a proxy or a container network.

### Close self-registration, and register every client deliberately

The strongest control: no client exists that someone did not create.

* Good, because nothing an outsider does creates a client at all.
* Good, because Claude's custom connectors accept a client ID and secret supplied by hand.
* Bad, because every person must have a client registered before they connect an agent, and
  CFOKit cannot do it for them: registering with an initial access token or through the
  administrative API is a credential CFOKit would hold on the issuer's behalf, and code written
  against one issuer's API (ADR-0019).
* Bad, because the step falls on the person or on an administrator, which is the friction
  self-registration exists to remove.

### Restore the consent screen

* Good, because it is the standard OAuth answer: the person sees what they are authorizing.
* Bad, because the screen shows what the client says about itself, and an attacker's client says
  it is Claude.
* Bad, because proxies that send `prompt=consent` show it on every connection, inside the
  desktop client's startup timeout, which teaches a person to click through it.

### Identify clients by Client ID Metadata Documents

* Good, because it is where MCP is going: the client is a URL its owner controls, and its
  redirects are published there rather than asserted by whoever registers.
* Good, because Claude supports it.
* Bad, because Keycloak 26.7.4 offers it only as an experimental feature, and an experimental
  feature of the identity provider is not a basis for the hosted service's authentication.

## More Information

**Follow-on obligations.** Supporting another MCP client on a deployment with the switch on means
adding its redirect to the patterns in `infra/keycloak/cfokit-realm.json` and
`infra/keycloak/realm-settings.sh`, as one reviewed change.

The policy checks a client's redirects when the client registers or changes itself, not when a
person signs in through it, so tightening the rule does not reach a client already registered.
A change that tightens it — removing a pattern, or turning the switch on for a deployment that has
admitted registration without it — also decides what happens to the clients registered before it.

**Reversal cost.** Low. The switch turns the policy off, and the profile and policy are two
entries in the realm file. Nothing in CFOKit depends on them.

Related: ADR-0019 sets the issuer contract this configures.

## Revisit when

* Keycloak supports Client ID Metadata Documents as a supported, non-experimental feature: move
  the hosted service to them, since a client's redirects then come from the client's own URL.
* MCP removes RFC 7591 registration.
* A client CFOKit supports registers a redirect neither pattern admits, or Anthropic moves
  Claude's callback to a host other than `claude.ai` or `claude.com`.
