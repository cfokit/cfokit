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

**A registered client can still end up with it as optional.** Keycloak's registration takes the
`scope` field of an RFC 7591 request as the set a client may use, and assigns those as
*optional* rather than honouring the realm's defaults — so a client that names its scopes gets
the audience only if it asked. The observed clients do ask, and the failure mode if one did not
is closed rather than silent: a token with no audience is rejected by the ledger (`NFR-06`)
rather than accepted with a missing claim. Worth checking on a client's first connection all the
same, in the admin console under the client's **Client scopes** tab.

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

- `Full Scope Disabled` clears every realm role from a registered client's scope, and
  `offline_access` is a realm role. So a client asking for an offline token — which is how a
  desktop proxy keeps a connection alive without sending someone back to a login page — is
  refused with "Offline tokens not allowed for the user or client", naming neither the policy
  nor the role.

- `Consent Required` sets `consentRequired` on every registered client, and a proxy sends
  `prompt=consent` on every authorization request — which forces the screen again whatever was
  granted before. A consent screen shown on every connection is not a control: it teaches
  whoever sees it to click through without reading, and it puts a human round-trip inside the
  desktop client's startup timeout, where being slow means the connection never completes.
  Consent protects a person from a *third-party* client taking their resources; here the client
  is their own proxy, on their own machine, reaching their own ledger.

None is adjustable into something that admits a normal client and still means anything, so all
four are gone and **anonymous registration is open to whoever can reach the issuer**.

Losing `Full Scope Disabled` costs less than it appears: it controls which realm roles reach a
token, and **CFOKit authorises on none of them**. What a caller may do is decided by the entity
grant held against their `sub` (ADR-0011, `IAM-01`), read from this deployment's own database on
every request. The roles in a token are Keycloak's business, and `offline_access` is the only
one anything here consults.

**That is a deployment posture, and it holds only while the issuer is not reachable.** On a
laptop it costs nothing: anyone who can reach `keycloak.localhost:8443` can already reach the ledger. A
deployment reachable by anything else must close it — by registering clients deliberately
instead, which `mcp-remote --static-oauth-client-info` and Claude's connector settings both
support.

**Tokens that outlive a working session.** Keycloak's default access token lives five minutes,
and a desktop client runs several proxy instances that all re-authenticate the moment it
expires. They then race for one callback port, one wins, the stragglers report that
"authentication was completed by another instance", and the client cancels the whole server
before it ever asks for a tool list. Every five minutes.

Eight hours removes the trigger rather than the symptom: within one working session no instance
re-authenticates, so there is nothing to race. The refresh token already lasted thirty days, so
this lengthens how long a *bearer* token is worth stealing — which on a laptop, where the issuer
is not reachable and anyone who can reach it can reach the ledger anyway, is a trade worth
making. **A deployment reachable by anything else should shorten it**, and accept that a client
which cannot tolerate re-authentication is a client that needs static credentials instead.

## What it deliberately does not contain

**No users, and no credentials.** The first person signs in through the admin console the
issuer ships with, which is the whole reason a complete identity provider is the default
(ADR-0019). A realm carrying a known password would be a credential in the repository.

**No client registrations.** A client either registers itself, or an operator adds it. Naming
one here would be provisioning a deployment we cannot see.
