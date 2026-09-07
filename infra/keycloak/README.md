# The realm CFOKit's issuer serves

`cfokit-realm.json` is imported by the `keycloak` service at startup and is what makes the
default deployment usable as it stands (`IAM-06`, ADR-0019).

**Hand-written, not exported.** A Keycloak realm export is several thousand lines of defaults
and generated identifiers, which is unreviewable and would hide a meaningful change inside
noise. This file states only what CFOKit needs; Keycloak supplies its own defaults for
everything omitted, which is also what keeps the file working across Keycloak versions.

## What it does, and why each part is here

**`cfokit-audience`, a default client scope.** The ledger validates every token's audience
against `AUTH_AUDIENCE` (`NFR-06`, ADR-0011), so a token has to carry it. No issuer honours the
RFC 8707 `resource` parameter, so the audience is bound here instead — ADR-0019 § 2 records why
that is the mechanism rather than a workaround.

It is a **default** scope rather than one a client opts into, which is the load-bearing part: a
client that registers itself through RFC 7591 receives the audience without anyone configuring
it afterwards. That is what lets an MCP client connect without a manual step.

**Keycloak's own client scopes, restated in full.** Declaring `clientScopes` **replaces** the
set Keycloak would otherwise create rather than adding to it — the same replace-semantics as
`components` below, and the reason `basic`, `profile`, `email` and `roles` were absent until
this file named them. A realm missing them issues tokens without standard claims and refuses
every client that asks for one, which is how a conforming MCP client came to be rejected at
registration.

So this file is longer than a hand-written file wants to be. The alternative is a provisioning
step after startup, which `IAM-06` rules out: a running deployment is usable as it stands.
These definitions are Keycloak's own; they are reproduced because the platform gives no way to
add to them.

**No anonymous client-registration policies beyond Keycloak's harmless defaults.** Two of them
refuse a standards-conforming client outright:

- `Allowed Client Scopes` rejects `openid`, which is not a Keycloak client scope at all but the
  OIDC marker every conforming client sends under RFC 7591.
- `Trusted Hosts` checks *every* client URI, not only redirect URIs, so it rejects any client
  that advertises a homepage — `https://github.com/modelcontextprotocol/mcp-cli` was the one
  that surfaced it. Its other mode, matching the caller's address, does not survive containers
  or proxies.

Neither is adjustable into something that admits a normal client and still means anything, so
both are gone and **anonymous registration is open to whoever can reach the issuer**.

**That is a deployment posture, and it holds only while the issuer is not reachable.** On a
laptop it costs nothing: anyone who can reach `localhost:8180` can already reach the ledger. A
deployment reachable by anything else must close it — by registering clients deliberately
instead, which `mcp-remote --static-oauth-client-info` and Claude's connector settings both
support.

## What it deliberately does not contain

**No users, and no credentials.** The first person signs in through the admin console the
issuer ships with, which is the whole reason a complete identity provider is the default
(ADR-0019). A realm carrying a known password would be a credential in the repository.

**No client registrations.** A client either registers itself, or an operator adds it. Naming
one here would be provisioning a deployment we cannot see.
