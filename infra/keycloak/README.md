# The realm CFOKit's issuer serves

`cfokit-realm.json` is imported by the `keycloak` service at startup and is what makes the
default deployment usable as it stands (`IAM-06`, ADR-0019).

**Hand-written, not exported.** A Keycloak realm export is several thousand lines of defaults
and generated identifiers, which is unreviewable and would hide a meaningful change inside
noise. This file states only what CFOKit needs; Keycloak supplies its own defaults for
everything omitted, which is also what keeps the file working across Keycloak versions.

## What it does, and why each part is here

**`cfokit-audience`, a default client scope.** The ledger validates every token's audience
against `AUTH_AUDIENCE` (`NFR-06`, ADR-0011), so a token has to carry it. No issuer honors the
RFC 8707 `resource` parameter, so the audience is bound here instead — ADR-0019 § 2 records why
that is the mechanism rather than a workaround.

It is a **default** scope rather than one a client opts into, which is the load-bearing part: a
client that registers itself through RFC 7591 receives the audience without anyone configuring
it afterwards. That is what lets an MCP client connect without a manual step.

**A registered client can still end up with it as optional.** Keycloak's registration takes the
`scope` field of an RFC 7591 request as the set a client may use, and assigns those as
*optional* rather than honoring the realm's defaults — so a client that names its scopes gets
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
token, and **CFOKit authorizes on none of them**. What a caller may do is decided by the entity
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

**`cfokit-web`, the web client's own client.** CFOKit ships the web client, so its client ships
with the realm: public, because a browser cannot keep a secret; authorization code with PKCE
(S256) and nothing else; redirects and sign-out returns only to `${PUBLIC_BASE_URL}/app/`, which
Keycloak fills from the environment at import, so the client follows the deployment's address
rather than naming one (ADR-0049 §§ 1-2). `webOrigins` `+` lets the page's own origin, and only
it, call the token endpoint.

**People sign themselves up**, by email, and reset their own passwords (`IAM-22`, ADR-0049 § 3).
No mail relay ships, so an address is not verified; a deployment with one turns `verifyEmail` on.

**Every person signs in with a second factor** (`SOC2-19`), an authenticator app or a security
key, whichever they have set up (`IAM-23`). No session is issued on a password alone. Three parts
do it, and each closes a different way in:

- **`CONFIGURE_TOTP` is a default required action**, so an account created on the sign-up page
  sets up an authenticator app before its first session exists. Registration does not run the
  browser flow, so this is the only part that reaches a new account.
- **`cfokit browser` is the browser flow.** After the password, `cfokit second factor` asks for
  whichever factor the person has — a code, or their security key — and a person with both can
  switch on the page. If they have neither, because an administrator created the account or
  they removed their last factor, `cfokit second factor setup` runs instead and makes them set up
  an authenticator app before the sign-in completes. This is the shape Keycloak's documentation
  gives as "Conditional 2FA sub-flow with OTP default".
- **`cfokit direct grant` is the password grant's flow.** The password grant is off for
  `cfokit-web`, but a client registering itself can ask for it, and Keycloak's own flow skips
  the code for a person with no authenticator app. Here the code is required, and a person
  without an app — one who signs in with a security key alone — is refused, since a key cannot
  be presented to a token endpoint.

The choice between the two is made after the first sign-in, not at it: Keycloak has one required
action per credential type and no built-in step that offers both, so a new account sets up an
app, and adds a security key from the account console if they prefer one. Both remain enough on
their own afterwards. A sign-in with a passkey, if a deployment turns passkeys on, already proves
two factors, and both second-factor sub-flows skip themselves for it, as Keycloak's own browser
flow does.

Only the flows that differ from Keycloak's are declared. `authenticationFlows` does not replace
the built-in set the way `clientScopes` does — Keycloak adds whichever built-in flows a realm
lacks at import — so registration, password reset and the rest stay Keycloak's own.
`requiredActions` is restated in full for the same reason `clientScopes` is: declaring it
replaces Keycloak's list.

**Two ways in this does not cover.** Neither is open in the realm as it ships:

- **A sign-in through another identity provider** — a Google or Microsoft account — does not run
  the browser flow. The first one creates the account, which takes the default required action
  and so sets up an app; later ones do not ask for it. Keycloak cannot see whether the other
  provider asked for a second factor. A deployment that adds one decides between setting that
  provider's post-login flow to ask for the second factor here, and trusting the provider's own.
  No provider ships with the realm.
- **A password reset by email** replaces the authenticator app rather than asking for it, so it
  rests on the mailbox alone. No mail relay ships, so the reset email is never sent; a deployment
  that adds one makes this a way in.

## What it deliberately does not contain

**No users, and no credentials.** People create their own accounts on the sign-up page the
issuer serves, which is the whole reason a complete identity provider is the default
(ADR-0019). A realm carrying a known password would be a credential in the repository.

**No clients but CFOKit's own.** An agent's client registers itself (RFC 7591), and anything
else an operator adds. Naming one here would be provisioning a deployment we cannot see.
