---
status: "draft"
kind: "requirement-driven"
date: 2026-08-17
decision-makers: [Geoff]
---

# ADR-0019: Identity provider is a swappable dependency behind a conformance contract

**Requirements served:** `IAM-10`, `NFR-06`, `NFR-14`.

## Context

ADR-0018 requires an OAuth 2.1 issuer that runs in the local compose stack with no cloud
account. That turned "self-hostable, light, permissively licensed" from a preference
into a hard constraint, and it eliminated the entire managed-IdP category — Auth0,
WorkOS, Clerk, Stytch, Descope — none of which can be self-hosted at all.

Two things then destabilized the remaining shortlist:

- **Zitadel is relicensing from Apache 2.0 to AGPL 3.0 starting with v3.** A candidate
  moved out of scope on license grounds after selection would have been made.
- **Ory markets an Enterprise License for self-hosted production** alongside the Apache
  2.0 build, and provides no security SLA on the open-source version with patches only
  for the latest release. The same open-core pressure that produced Zitadel's move
  exists here.

Separately, the MCP 2026-07-28 revision deprecated RFC 7591 Dynamic Client Registration
in favour of Client ID Metadata Documents, retaining DCR for backward compatibility for
at least twelve months. The registration mechanism is therefore mid-transition, and any
issuer choice made today will need to accommodate a change.

The conclusion to draw is not which issuer to pick. It is that **the issuer's license and
capabilities are not stable inputs**, so coupling to a specific one is the mistake.

## Decision

The identity provider is a **swappable dependency behind a written conformance
contract**, documented in `infra/README.md` alongside the deployment contract and
verified by an automated conformance suite.

The default in the compose stack is **Ory Hydra** (Apache 2.0). It is a default, not a
coupling.

**No AGPL or other network-copyleft component ships in the default stack.** This follows
the same reasoning already applied to Beancount (ADR-0010): copyleft stays out of the
distributed artifact.

## The contract

Any conforming issuer must provide:

- OIDC Discovery or OAuth 2.0 Authorization Server Metadata
- A JWKS endpoint with key rotation
- RFC 8707 Resource Indicators — the `resource` parameter must bind the token audience
- RFC 9207 issuer identifier in the authorization response
- Declared, configurable claim names for subject and scopes
- RFC 7591 DCR **or** Client ID Metadata Documents

The application reads `AUTH_ISSUER_URL` and `AUTH_AUDIENCE` and nothing else. No
issuer-specific code exists anywhere in the codebase.

## Alternatives rejected

### Supabase Auth

The prior working assumption, carried over from planning that predated the local
self-hosting requirement. Open source and self-hostable, but the supported self-host
path is the full platform stack rather than a standalone auth service. Selected when
managed convenience was the priority; that priority inverted with ADR-0018.

### Auth0 and other managed IdPs

Hosted-only. Cannot run in the local compose stack. Fails ADR-0018 outright, regardless
of merit.

### Keycloak

Apache 2.0, CNCF, the most capable self-hostable option, and it stays on the shortlist as
the fallback. Not the default because it does not natively support RFC 8707 — it
disregards the `resource` parameter, producing tokens with a missing or wrong `aud`
claim, and the documented fix is custom protocol mappers injecting the audience. For a
system whose tenancy boundary is enforced by audience and scope validation, a workaround
at that layer is the wrong default. Also the heaviest option for a laptop.

### Zitadel

Strong multi-tenant model, closest conceptual fit to the user-scoped-token plus
per-call-entity design. Excluded on the AGPL 3.0 transition at v3.

### Building our own issuer

Rejected. Security-critical code with no differentiating value, and CFOKit's thesis is
that software value is zero — writing an OAuth server contradicts it directly.

## Consequences

**Accepted costs.**
- A conformance suite to build and maintain — roughly a day's work, and it is what makes
  the swap claim true rather than aspirational.
- No security SLA on the Apache 2.0 Hydra build. Track releases actively; patches land
  only on latest.

**Follow-on obligations.**
- The conformance suite runs in CI against the default issuer, and against any
  additional issuer we claim to support.
- Hydra does not manage users. Identity and consent are delegated to our own user
  records and entity-grants model rather than adding a second component.
- Tokens from a shared issuer can otherwise be replayed across resource servers. Audience
  validation against `AUTH_AUDIENCE` is mandatory on every request, and entity grants are
  validated server-side regardless (ADR-0011).
- DCR support now, CIMD support before DCR's removal window closes. Track SEP-991.

**Reversal cost.** Low by construction — that is the point of the ADR. A license change
or capability gap makes the default a config swap plus a conformance run.

## Revisit when

- Ory relicenses, or the Enterprise License becomes required for our use. Fall back to
  Keycloak with the audience-mapper workaround, or reassess.
- Keycloak ships native RFC 8707 support, which would make it a stronger default given
  its maturity.
- CIMD support appears in any conforming issuer.
