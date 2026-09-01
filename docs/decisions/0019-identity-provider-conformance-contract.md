---
status: "draft"
kind: "requirement-driven"
date: 2026-08-17
decision-makers: [Geoff]
---

# ADR-0019: Identity provider is a swappable dependency behind a conformance contract

**Requirements served:** `IAM-10`, `NFR-06`, `NFR-14`.

## Context and Problem Statement

ADR-0018 requires an OAuth 2.1 issuer that runs in the local compose stack with no cloud
account. That turned "self-hostable, light, permissively licensed" from a preference into a
hard constraint, and it eliminated the entire managed-IdP category — Auth0, WorkOS, Clerk,
Stytch, Descope — none of which can be self-hosted at all.

Two things then destabilized the remaining shortlist:

- **Zitadel is relicensing from Apache 2.0 to AGPL 3.0 starting with v3.** A candidate moved
  out of scope on licence grounds after selection would have been made.
- **Ory markets an Enterprise License for self-hosted production** alongside the Apache 2.0
  build, and provides no security SLA on the open-source version with patches only for the
  latest release. The same open-core pressure that produced Zitadel's move exists here.

Separately, the MCP 2026-07-28 revision deprecated RFC 7591 Dynamic Client Registration in
favour of Client ID Metadata Documents, retaining DCR for backward compatibility for at
least twelve months. The registration mechanism is therefore mid-transition, and any issuer
choice made today will need to accommodate a change.

The conclusion to draw is not which issuer to pick. It is that **the issuer's licence and
capabilities are not stable inputs**, so coupling to a specific one is the mistake.

## Decision Drivers

* The issuer must run in the local compose stack with no cloud account (ADR-0018).
* No AGPL or other network-copyleft component in the default stack (`NFR-14`, ADR-0026).
* Native RFC 8707 resource indicators, because the tenancy boundary is enforced by audience
  validation and a workaround at that layer is the wrong default.
* Licence and capability volatility is the observed condition, so the cost of swapping
  matters more than the merits of any single candidate.
* Light enough to run on a laptop alongside the rest of the stack.

## Considered Options

* A swappable dependency behind a written conformance contract, defaulting to Ory Hydra
* Supabase Auth
* Auth0 and other managed IdPs
* Keycloak
* Zitadel
* Building our own issuer

## Decision Outcome

Chosen option: "A swappable dependency behind a written conformance contract, defaulting to
Ory Hydra", because every candidate's licence and capabilities proved unstable during
selection itself, which makes the swap cost the thing worth engineering rather than the
choice.

> The identity provider is a swappable dependency behind a written conformance contract,
> documented in `infra/README.md` and verified by an automated conformance suite. The
> default in the compose stack is Ory Hydra (Apache 2.0). It is a default, not a coupling.

**No AGPL or other network-copyleft component ships in the default stack.** This follows the
same reasoning already applied to Beancount (ADR-0010): copyleft stays out of the distributed
artifact.

### The contract

Any conforming issuer must provide:

- OIDC Discovery or OAuth 2.0 Authorization Server Metadata
- A JWKS endpoint with key rotation
- RFC 8707 Resource Indicators — the `resource` parameter must bind the token audience
- RFC 9207 issuer identifier in the authorization response
- Declared, configurable claim names for subject and scopes
- RFC 7591 DCR **or** Client ID Metadata Documents

The application reads `AUTH_ISSUER_URL` and `AUTH_AUDIENCE` and nothing else. No
issuer-specific code exists anywhere in the codebase.

### Consequences

* Good, because a licence change or capability gap becomes a configuration swap plus a
  conformance run, rather than a rebuild.
* Good, because the contract states what "supported issuer" means, so the claim is testable
  rather than a marketing sentence.
* Good, because delegating identity entirely keeps a security-critical component out of our
  codebase (ADR-0002's thesis applied to auth).
* Bad, because there is a conformance suite to build and maintain — roughly a day's work,
  and it is what makes the swap claim true rather than aspirational.
* Bad, because there is no security SLA on the Apache 2.0 Hydra build. Releases must be
  tracked actively; patches land only on latest.

### Confirmation

The conformance suite runs in CI against the default issuer, and against any additional
issuer we claim to support. Because the application reads only `AUTH_ISSUER_URL` and
`AUTH_AUDIENCE`, an issuer-specific import would also be visible to review as a new
dependency.

**The suite is not yet written.** Until it is, "swappable" is a design property argued here
rather than a verified one, and the contract above is enforced by review. This is the same
gap ADR-0001 names for the decision corpus, and it is stated rather than implied.

## Pros and Cons of the Options

### A swappable dependency behind a conformance contract, defaulting to Ory Hydra

* Good, because Hydra is Apache 2.0, natively supports RFC 8707, and is light enough for a
  laptop.
* Good, because the contract makes the default replaceable without application changes.
* Bad, because Ory's open-core pressure is real — an Enterprise License exists for exactly
  this deployment shape, and the open-source build carries no security SLA.
* Bad, because Hydra does not manage users, so identity and consent fall to our own records.

### Supabase Auth

The prior working assumption, carried over from planning that predated the local
self-hosting requirement.

* Good, because it is open source, self-hostable, and the fastest path when managed
  convenience is the priority.
* Bad, because the supported self-host path is the full platform stack rather than a
  standalone auth service, which is far too much to ask of a laptop deployment. The priority
  that selected it inverted with ADR-0018.

### Auth0 and other managed IdPs

* Good, because they are the most capable and best-operated options available, with nothing
  to maintain.
* Bad, because they are hosted-only and cannot run in the local compose stack. Fails
  ADR-0018 outright, regardless of merit.

### Keycloak

Apache 2.0, CNCF, and the most capable self-hostable option. It stays on the shortlist as
the fallback.

* Good, because it is mature, widely deployed, and under a foundation rather than a vendor,
  which makes a Zitadel-style relicence unlikely.
* Bad, because it does not natively support RFC 8707 — it disregards the `resource`
  parameter, producing tokens with a missing or wrong `aud` claim, and the documented fix is
  custom protocol mappers injecting the audience. For a system whose tenancy boundary is
  enforced by audience and scope validation, a workaround at that layer is the wrong default.
* Bad, because it is the heaviest option for a laptop.

### Zitadel

* Good, because its multi-tenant model is the closest conceptual fit to the
  user-scoped-token plus per-call-entity design.
* Bad, because of the AGPL 3.0 transition at v3, which puts network copyleft in the default
  stack and is excluded by `NFR-14`.

### Building our own issuer

* Good, because it would fit the contract exactly and could never be relicensed out from
  under us.
* Bad, because it is security-critical code with no differentiating value. CFOKit's thesis is
  that software value is zero; writing an OAuth server contradicts it directly.

## More Information

**Follow-on obligations.**

* The conformance suite runs in CI against the default issuer, and against any additional
  issuer we claim to support.
* Hydra does not manage users. Identity and consent are delegated to our own user records
  and entity-grants model rather than adding a second component.
* Tokens from a shared issuer can otherwise be replayed across resource servers. Audience
  validation against `AUTH_AUDIENCE` is mandatory on every request, and entity grants are
  validated server-side regardless (ADR-0011).
* DCR support now, CIMD support before DCR's removal window closes. Track SEP-991.

**Reversal cost.** Low by construction — that is the point of the record. A licence change or
capability gap makes the default a config swap plus a conformance run.

## Revisit when

* Ory relicenses, or the Enterprise License becomes required for our use. Fall back to
  Keycloak with the audience-mapper workaround, or reassess.
* Keycloak ships native RFC 8707 support, which would make it a stronger default given its
  maturity.
* CIMD support appears in any conforming issuer.
