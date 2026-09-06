---
status: "accepted"
kind: "requirement-driven"
date: 2026-09-06
decision-makers: [Geoff]
---

# ADR-0019: Identity provider is a swappable dependency behind a conformance contract

**Requirements served:** `IAM-06`, `IAM-10`, `NFR-06`, `NFR-14`.

## Context and Problem Statement

ADR-0018 requires an OAuth 2.1 issuer that runs in the local compose stack with no cloud
account. That turns "self-hostable, light, permissively licensed" from a preference into a hard
constraint, and it eliminates the entire managed-IdP category — Auth0, WorkOS, Clerk, Stytch,
Descope — none of which can be self-hosted at all.

Two requirements then decide what remains, and they are stronger than they look:

- **`IAM-10`:** "Identity is delegated to the identity provider the organisation already uses.
  CFOKit never issues credentials, stores passwords, or operates a login flow."
- **`IAM-06`:** "A running deployment is usable as it stands, with nothing provisioned into it
  first."

Together they mean the default issuer must be a **complete identity provider** — a user store
and a login flow included — because anything less leaves the self-hoster to supply the missing
half, and the half missing is precisely the one `IAM-10` forbids CFOKit from writing.

Licence and capability are also not stable inputs. Zitadel moved from Apache 2.0 to AGPL 3.0 at
v3, putting network copyleft in scope for a candidate that had been eliminated on other grounds
anyway. Ory markets an Enterprise License for self-hosted production alongside its Apache 2.0
build and provides no security SLA on the open-source version. The registration mechanism is
mid-transition too: MCP 2026-07-28 deprecated RFC 7591 Dynamic Client Registration in favour of
Client ID Metadata Documents, retaining DCR for at least twelve months.

So the conclusion to draw is not only which issuer to pick. It is that **the issuer's licence
and capabilities are not stable inputs**, which makes the swap cost the thing worth engineering.

## Decision Drivers

* The issuer must run in the local compose stack with no cloud account (ADR-0018).
* **A deployment must authenticate a person on the strength of what it ships** (`IAM-06`),
  without CFOKit writing a login flow or storing a password (`IAM-10`).
* **The audience of an issued token must be bindable to this deployment**, because `NFR-06`
  refuses a request meant for somewhere else. *How* the issuer binds it is not a driver — see
  § 2.
* No AGPL or other network-copyleft component in the default stack (`NFR-14`, ADR-0026).
* Licence and capability volatility is the observed condition, so the cost of swapping matters
  more than the merits of any single candidate.
* Light enough to run on a laptop alongside the rest of the stack.

## Considered Options

* A swappable dependency behind a written conformance contract, defaulting to Keycloak
* A bare OAuth 2.1 authorization server, with identity supplied separately
* Supabase Auth
* Auth0 and other managed IdPs
* Zitadel
* Building our own issuer

## Decision Outcome

Chosen option: "A swappable dependency behind a written conformance contract, defaulting to
Keycloak", because a default that cannot log a person in fails `IAM-06` on the day it ships, and
because every candidate's licence and capabilities proved unstable during selection itself —
which makes the swap cost the thing worth engineering rather than the choice.

> The identity provider is a swappable dependency behind a written conformance contract,
> documented in `infra/README.md` and verified by an automated conformance suite. The default in
> the compose stack is Keycloak (Apache 2.0). It is a default, not a coupling.

**No AGPL or other network-copyleft component ships in the default stack.** This follows the
same reasoning already applied to Beancount (ADR-0010): copyleft stays out of the distributed
artifact.

### 1. The contract

Any conforming issuer must provide:

- A complete identity provider: a user store and a login flow it operates itself
- OIDC Discovery **and** OAuth 2.0 Authorization Server Metadata at the RFC 8414 path
- A JWKS endpoint with key rotation
- JWT access tokens, validatable against that JWKS
- An audience on an issued token that can be bound to a stated value (§ 2)
- RFC 9207 issuer identifier in the authorization response
- Declared, configurable claim names for subject and scopes
- RFC 7591 Dynamic Client Registration **or** Client ID Metadata Documents
- The **client credentials grant**, for separate components authenticating as machine callers
  (ADR-0032)

The application reads `AUTH_ISSUER_URL` and `AUTH_AUDIENCE` and nothing else. No issuer-specific
code exists anywhere in the codebase.

### 2. Audience binding is the requirement; RFC 8707 is one mechanism

`NFR-06` requires every request to be validated as intended for this deployment, which the
application does by checking `aud` against `AUTH_AUDIENCE`. What it needs is a token whose `aud`
can be made to contain that value. It does not need any particular way of arranging it.

Requiring RFC 8707 resource indicators specifically would be a requirement no issuer meets.
Hydra ignores `resource` and returns `aud: []`; Keycloak ignores it and returns its own default;
Microsoft Entra ID **rejects** the parameter at the authorization endpoint and signals the
audience through scope instead. RFC 6749 obliges a server to ignore parameters it does not
recognise, so ignoring it is conformant behaviour rather than a defect, and the MCP
specification's own `MUST` is under challenge for exactly this reason.

Binding the audience by issuer configuration is therefore not a workaround at the security
layer. It is the mechanism the ecosystem actually uses, it is configuration rather than code,
and the property `NFR-06` depends on — that a token issued for somewhere else is refused — is
identical either way. Prefer `resource` where an issuer honours it.

**Audience validation is not the tenancy boundary.** It stops a token issued for another
resource server being replayed here. What separates entities is the entity grant, validated
server-side on every call regardless of anything in the token (ADR-0011, `IAM-01`).

### Consequences

* Good, because a deployment can authenticate a person on the strength of `docker compose up`,
  which is what `IAM-06` asks for and what a product promise of self-hosting has to mean.
* Good, because a licence change or capability gap becomes a configuration swap plus a
  conformance run, rather than a rebuild.
* Good, because the contract states what "supported issuer" means, so the claim is testable
  rather than a marketing sentence.
* Good, because delegating identity entirely keeps a security-critical component out of our
  codebase (ADR-0002's thesis applied to auth) — and delegating it to something that actually
  holds identities is what makes that true rather than nominal.
* Bad, because Keycloak is the heaviest option: a 691 MB image against 70 MB for a bare
  authorization server, and JVM startup lands in every CI run of gate 2.
* Bad, because the audience is bound by realm configuration, so a deployment has a
  configuration step whose omission is an authentication failure rather than a visible error.
* Neutral, because no issuer implements RFC 8707. Nothing is given up by not requiring it.

### Confirmation

`tests/integration/test_issuer_conformance.py` drives the configured issuer over HTTP and
asserts each contract line, in CI gate 2. It knows nothing about which issuer it is measuring:
every request goes to an endpoint the issuer itself advertises, which is the same discipline the
contract demands of the application. A suite reaching for a vendor's admin API would prove the
default works and nothing about the swap.

A contract line the configured issuer does not meet is a strict expected failure carrying the
measurement as its reason, so a gap is visible in the suite's output and the marker must come
off the moment it closes.

Because the application reads only `AUTH_ISSUER_URL` and `AUTH_AUDIENCE`, an issuer-specific
import would also be visible to review as a new dependency.

## Pros and Cons of the Options

### A swappable dependency behind a conformance contract, defaulting to Keycloak

* Good, because it is a complete identity provider: a user store, login and account pages, and
  an admin console, so a deployment satisfies `IAM-06` with nothing provisioned into it.
* Good, because it is mature, widely deployed, and under a foundation rather than a vendor,
  which makes a Zitadel-style relicence unlikely. Apache 2.0.
* Good, because it meets every other contract line as it ships — RFC 8414 metadata, an
  advertised registration endpoint, RFC 9207, and JWT access tokens by default.
* Bad, because it is the heaviest option by an order of magnitude, and a laptop deployment
  feels it.
* Bad, because the audience is bound by a protocol mapper rather than by the request, so it is
  realm configuration a deployment can get wrong silently.

### A bare OAuth 2.1 authorization server, with identity supplied separately

Ory Hydra is the case. Attractive on every axis that is easy to measure: Apache 2.0, 70 MB, fast
to start, and single-purpose in a way that reads as good engineering.

* Good, because it is a tenth the size and does one job.
* Good, because a deployment that *already has* an identity layer would find it the smaller
  dependency.
* Bad, and decisively, because it has no user database, no login page and no consent UI, and
  requires the operator to supply all three. A deployment cannot authenticate anybody as it
  ships, which fails `IAM-06`; and the missing component is a login flow, which `IAM-10`
  forbids CFOKit from writing. Choosing it means either shipping a second identity product
  beside it or writing the one thing the requirements rule out.
* Bad, because it does not implement RFC 8707 either. It ignores `resource` and returns
  `aud: []`, so it offers no advantage on the driver that would once have selected it.
* Bad, because Ory's open-core pressure is real — an Enterprise License exists for exactly this
  deployment shape, and the open-source build carries no security SLA.

### Supabase Auth

* Good, because it is open source, self-hostable, and the fastest path when managed convenience
  is the priority.
* Bad, because the supported self-host path is the full platform stack rather than a standalone
  auth service, which is far too much to ask of a laptop deployment.

### Auth0 and other managed IdPs

* Good, because they are the most capable and best-operated options available, with nothing to
  maintain.
* Bad, because they are hosted-only and cannot run in the local compose stack. Fails ADR-0018
  outright, regardless of merit.

### Zitadel

* Good, because its multi-tenant model is the closest conceptual fit to the user-scoped-token
  plus per-call-entity design, and it is a complete identity provider.
* Bad, because it is AGPL 3.0, which puts network copyleft in the default stack and is excluded
  by `NFR-14`.

### Building our own issuer

* Good, because it would fit the contract exactly and could never be relicensed out from under
  us.
* Bad, because it is security-critical code with no differentiating value. CFOKit's thesis is
  that software value is zero; writing an OAuth server contradicts it directly, and `IAM-10`
  forbids it in as many words.

## More Information

**Follow-on obligations.**

* A realm definition ships with the compose stack, carrying the client registrations and the
  audience mapping. Without it the default is configured but not usable, which is the failure
  `IAM-06` names.
* Tokens from a shared issuer can otherwise be replayed across resource servers. Audience
  validation against `AUTH_AUDIENCE` is mandatory on every request, and entity grants are
  validated server-side regardless (ADR-0011).
* DCR support now, CIMD support before DCR's removal window closes. Track SEP-991.

**Reversal cost.** Low by construction — that is the point of the record. A licence change or
capability gap makes the default a config swap plus a conformance run.

## Revisit when

* Keycloak relicenses, or its governance moves under a single vendor.
* Any conforming issuer implements RFC 8707, which would let the contract prefer the request
  parameter over realm configuration and remove the silent-misconfiguration risk above.
* CIMD support appears in any conforming issuer.
* The image size becomes the binding constraint on a laptop deployment, at which point a
  lighter complete identity provider is worth measuring against the same suite.
