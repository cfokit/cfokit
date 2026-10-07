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
laptop it costs nothing: anyone who can reach `keycloak.localhost:8443` can already reach the ledger.

## Clients that register themselves

On a deployment anyone can reach, open registration with no consent screen lets an attacker
register a client whose redirect is their own server, send a person a link to the genuine sign-in
page, and receive the code when they sign in, second factor and all (ADR-0064). So a deployment
reachable by others restricts where a client that registers itself may send a sign-in, set by one
variable read when the realm is imported:

| `CFOKIT_RESTRICT_REGISTERED_REDIRECTS` | Who uses it | A client that registers itself may redirect to |
|---|---|---|
| unset, or `false` | a laptop, where nothing else reaches the issuer | anywhere |
| `true` | CFOKit's hosted service, or any deployment reachable by others | Claude's callback, `https://claude.ai/api/mcp/auth_callback` or the same on `claude.com`; or a loopback address over http, `127.0.0.1`, `[::1]` or `localhost`, on any port |

Claude's custom connectors and local proxies, `mcp-remote` and Claude Code among them, register
exactly those, so connecting stays one step. A code sent to either reaches only the person:
Claude's callback completes only the connection that browser started, and a loopback address is
their own machine.

The rule is the client profile `cfokit-registered-redirects`: Keycloak's
`secure-client-uris-pattern` executor on the redirect URIs and no other field, so a client that
also names a homepage or a logo still registers, which is where the `Trusted Hosts` policy above
failed. It compares text. Keycloak's purpose-made `secure-redirect-uris-enforcer` decides whether
a host is loopback by resolving it when no port is given, and so admits a name that resolves to
`127.0.0.1` today and to someone's server tomorrow. The client policy of the same name applies the
profile only to a client that registers itself, or changes itself with its registration token; the
realm's own clients, and any an administrator registers, are unaffected.

Supporting another MCP client on such a deployment means adding its redirect to the patterns here
and in `realm-settings.sh`.

**Tokens that outlive a working session.** Keycloak's default access token lives five minutes,
and a desktop client runs several proxy instances that all re-authenticate the moment it
expires. They then race for one callback port, one wins, the stragglers report that
"authentication was completed by another instance", and the client cancels the whole server
before it ever asks for a tool list. Every five minutes.

Eight hours removes the trigger rather than the symptom: within one working session no instance
re-authenticates, so there is nothing to race. The refresh token already lasted thirty days, so
this lengthens how long a *bearer* token is worth stealing — which on a laptop, where the issuer
is not reachable and anyone who can reach it can reach the ledger anyway, is a trade worth
making. **A deployment reachable by anything else shortens it**, through one variable read when
the realm is imported, the same way as the second-factor setting below:

| `CFOKIT_ACCESS_TOKEN_LIFESPAN` | Who uses it | What it costs |
|---|---|---|
| unset: `28800`, eight hours | a laptop, or a self-hosted install that has not chosen otherwise | A stolen token is good for a working day. |
| `900`, fifteen minutes | CFOKit's hosted service, or any install claiming SOC 2 | A revoked session stops working within fifteen minutes (`SOC2-20`). A local server running several proxies, as Claude Desktop does through `mcp-remote`, re-authenticates every fifteen minutes and can trip over itself; a client that connects directly, as a Claude custom connector does, refreshes its token and does not. |

**Repeated failures lock an account for a while.** After ten failed sign-ins within twelve
hours, each further attempt waits a minute longer, up to fifteen minutes; a correct password
inside the wait is refused too. Never permanent, so nobody can lock a person out of their own
books for good by guessing at their address. It stops guessing one person's password; guessing
a few passwords across many accounts from one address is the load balancer's to stop, which on
GCP is Cloud Armor (`infra/gcp/armor.tf`).

**A password is at least fifteen characters, and nothing else is asked of it.** NIST SP
800-63B-4 § 3.1.1.2 sets fifteen for a password that is the only authenticator, which it can be
where a second factor is optional, and forbids composition rules. It allows up to 128, and
refuses one equal to the person's username or email address.

**Every sign-in and every administrative change is an event in the issuer's log** (`PLT-17`):
who, from which address, through which client, and on failure why. Kept in the database for
ninety days, where the admin console shows them, and in whatever collects the issuer's output for
as long as that keeps it. Keycloak logs successes at debug level unless told otherwise, so a
deployment collecting them sets `KC_SPI_EVENTS_LISTENER__JBOSS_LOGGING__SUCCESS_LEVEL` to `info`.
The log carries the sign-in name, which is an email address, and never a credential.

**`cfokit-web`, the web client's own client.** CFOKit ships the web client, so its client ships
with the realm: public, because a browser cannot keep a secret; authorization code with PKCE
(S256) and nothing else; redirects and sign-out returns only to `${PUBLIC_BASE_URL}/app/`, which
Keycloak fills from the environment at import, so the client follows the deployment's address
rather than naming one (ADR-0049 §§ 1-2). `webOrigins` `+` lets the page's own origin, and only
it, call the token endpoint.

**People sign themselves up**, by email, and reset their own passwords (`IAM-22`, ADR-0049 § 3).
No mail relay ships, so an address is not verified; a deployment with one turns `verifyEmail` on.

**A second factor is the person's choice, or the deployment's requirement.** Any person can
protect their sign-in with an authenticator app or a security key (`IAM-23`), and once they have
one they are asked for it every time. Whether a person may go without one is a property of the
deployment, set by one variable read when the realm is imported:

| `CFOKIT_REQUIRE_SECOND_FACTOR` | Who uses it | What a person sees |
|---|---|---|
| unset, or `false` | a laptop, or any self-hosted install that has not chosen otherwise | Signing up goes straight in. A second factor is added when the person chooses, and asked for from then on. |
| `true` | a deployment operated as a service — CFOKit's hosted service, or any install claiming SOC 2 (`SOC2-19`) | Signing up asks for an authenticator app before the first session exists. No session is issued on a password alone. |

The variable reaches the realm through Keycloak's own import: when the issuer starts with
`--import-realm`, it replaces every `${NAME}` and `${NAME:default}` in this file with that
environment variable, or the default when it is unset — the same mechanism that fills
`${PUBLIC_BASE_URL}`. The replacement is plain text, applied before the file is parsed, so it
reaches the two places the setting lives: `CONFIGURE_TOTP`'s `defaultAction` (written as a
string, which Keycloak reads as the boolean) and the `included` option of one flow condition.
**It is read once, when the realm is created.** An issuer whose realm already exists keeps the
setting it was created with; changing it means recreating the realm, or making the same two
changes in the admin console. The same holds for every setting in this file, the token
lifetime, lockout, password policy and events above included; the next section is how those
reach a realm that already exists.

Three parts do the work, and each closes a different way in:

- **`CONFIGURE_TOTP` is a default required action when the setting is `true`**, so an account
  created on the sign-up page sets up an authenticator app before its first session exists.
  Registration does not run the browser flow, so this is the only part that reaches a new
  account.
- **`cfokit browser` is the browser flow.** After the password, `cfokit second factor` asks for
  whichever factor the person has — a code, or their security key — and a person with both can
  switch on the page. That part holds whatever the setting. Under `true`, a person with neither,
  because an administrator created the account or they removed their last factor, meets
  `cfokit second factor setup` instead, which makes them set up an authenticator app before the
  sign-in completes: the shape Keycloak's documentation gives as "Conditional 2FA sub-flow with
  OTP default". Its condition is "a password was used, and the setting is `true`" — the
  condition's `included` option is the setting — so under `false` it never runs, and a sign-in
  with a passkey, which proves two factors itself, never meets it either way.
- **`cfokit direct grant` is the password grant's flow**, under either setting. The password grant
  is off for `cfokit-web`, but a client registering itself can ask for it, and Keycloak's own
  flow skips the code for a person with no authenticator app. Here a person with an app must send
  its code, and a person without one is refused — including one who signs in with a security key
  alone, since a key cannot be presented to a token endpoint. A person who has chosen no second
  factor signs in in a browser, as `cfokit-web` does.

The choice between app and key is made after the first sign-in, not at it: Keycloak has one
required action per credential type and no built-in step that offers both, so a new account under
`true` sets up an app, and adds a security key from the account console if they prefer one. Both
are enough on their own afterwards.

Only the flows that differ from Keycloak's are declared. `authenticationFlows` does not replace
the built-in set the way `clientScopes` does — Keycloak adds whichever built-in flows a realm
lacks at import — so registration, password reset and the rest stay Keycloak's own.
`requiredActions` is restated in full for the same reason `clientScopes` is: declaring it
replaces Keycloak's list.

**Two ways in the requirement does not cover.** Neither is open in the realm as it ships:

- **A sign-in through another identity provider** — a Google or Microsoft account — does not run
  the browser flow. The first one creates the account, which takes the default required action
  and so sets up an app; later ones do not ask for it. Keycloak cannot see whether the other
  provider asked for a second factor. A deployment that adds one decides between setting that
  provider's post-login flow to ask for the second factor here, and trusting the provider's own.
  No provider ships with the realm.
- **A password reset by email** replaces the authenticator app rather than asking for it, so it
  rests on the mailbox alone. No mail relay ships, so the reset email is never sent; a deployment
  that adds one makes this a way in.

## Settings on a running issuer

`realm-settings.sh` sets, on realms that already exist, the values a running deployment cannot
otherwise receive: the lockout, password policy, events and token lifetime this file holds, on
the `cfokit` realm, with the restriction on clients that register themselves, and the lockout
and events on `master`. It keeps every account, which re-importing the realm does not.
`tests/test_issuer_realm.py` asserts its values and this file's agree.

It also sets the one thing the master realm needs where the admin console has a host of its own
and the issuer's public host does not serve the master realm, as on GCP: the master realm's
**frontend URL**, pointed at the console's host. The console signs in to the master realm at that
realm's frontend URL, from a hidden frame, and by default that is the issuer's public hostname.
Behind Identity-Aware Proxy, which cannot answer inside a frame, the sign-in never completes and
the console reports a timeout waiting for the "3rd party check iframe".

It needs no administrator's password. Keycloak's own recovery command, `kc.sh bootstrap-admin`,
creates a temporary administrator client whose secret is generated inside the container and
never leaves it; the script signs in as that, applies the settings, deletes the client, and
proves it gone by being refused when it signs in again. Events are switched on first, so each
change after that is an admin event. It runs from the issuer image, against the issuer's
database, with Keycloak started inside the same container; on GCP, `setup/realm.sh --settings`
runs it as a job and then restarts the issuer, which caches realms.

## What it deliberately does not contain

**No users, and no credentials.** People create their own accounts on the sign-up page the
issuer serves, which is the whole reason a complete identity provider is the default
(ADR-0019). A realm carrying a known password would be a credential in the repository.

**No clients but CFOKit's own.** An agent's client registers itself (RFC 7591), and anything
else an operator adds. Naming one here would be provisioning a deployment we cannot see.
