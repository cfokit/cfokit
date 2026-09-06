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

**`Trusted Hosts`, matching on the client's URIs rather than the caller's address.** Keycloak
restricts anonymous client registration, and ships with the list empty — so registration is
refused until a deployment says what may be registered. Keeping the policy is the point; what
changes here is which half of it applies.

Matching on the *caller's* address is what Keycloak does by default, and it does not survive
containers, proxies or NAT — every service behind one shares an address, so the check either
admits everything or nothing. Matching on the *client's URIs* is the check that stops the attack
worth stopping: registering a client whose redirect URI points somewhere else, so that an
authorization code is delivered to a stranger. A client with no redirect URI at all — a machine
caller under the client credentials grant — has nothing to redirect and nothing to check.

**Adding a client that lives elsewhere means adding its host here.** A remote MCP client
redirects to its own vendor's domain, so an operator who wants it to register itself adds that
domain to this list, deliberately. Otherwise the client is added through the admin console.

The remaining policies are Keycloak's own defaults, restated because listing `components`
replaces them wholesale rather than merging.

## What it deliberately does not contain

**No users, and no credentials.** The first person signs in through the admin console the
issuer ships with, which is the whole reason a complete identity provider is the default
(ADR-0019). A realm carrying a known password would be a credential in the repository.

**No client registrations.** A client either registers itself, or an operator adds it. Naming
one here would be provisioning a deployment we cannot see.
