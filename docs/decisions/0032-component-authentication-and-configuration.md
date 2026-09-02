---
status: "draft"
kind: "requirement-driven"
date: 2026-08-18
decision-makers: [Geoff]
---

# ADR-0032: Components authenticate as OAuth clients

**Requirements served:** `IAM-11`, `NFR-11`.

## Context and Problem Statement

[ADR-0022](0022-tiny-ledger-modules-and-components.md) established the separate component: its own
runtime, reaching the ledger through the published API.
[ADR-0023](0023-one-image-many-entrypoints.md) settled how one is built and deployed. What remains is
how it proves who it is.

A component is a machine caller with no interactive user. Every request still requires audience
validation ([ADR-0019](0019-identity-provider-conformance-contract.md)), and entity access is checked
server-side regardless of what the caller asserts ([ADR-0011](0011-entity-advisory-lock.md)). So the
question is not whether a component is authenticated, but by what mechanism — and every convenient
answer introduces a second authentication path.

**Portability constrains this sharply.** Configuration is environment variables only, with no provider
SDKs at module scope, and CI runs the stack with no cloud credentials present
([ADR-0004](0004-portability-as-a-build-gate.md)). A mechanism that works only in the cloud fails the
gate outright.

## Decision Drivers

* One authentication path. Auth is where divergence between what we develop against and what users
  run is least acceptable (ADR-0018).
* The mechanism must work identically with no cloud account, or CI gate 2 cannot run it.
* A component should hold least privilege, not ambient access to every entity.
* Credentials should never appear in infrastructure state (ADR-0016).

## Considered Options

* Components authenticate as OAuth clients via the client credentials grant
* A long-lived API key or shared secret for components
* Cloud workload identity — a provider service account with implicit credentials
* Components connect to the database directly instead of using the API

## Decision Outcome

Chosen option: "Components authenticate as OAuth clients via the client credentials grant", because
it is the only mechanism that reuses the path every other caller already takes, and the only one that
behaves identically with and without a cloud account.

> A component obtains a token via the client credentials grant against the same issuer the application
> already uses, and calls the API like any other client. Audience validation applies unchanged.

This follows directly from ADR-0018's rejection of a static bearer token for local mode: a second
authentication path is a path exercised by fewer people, and auth is where divergence is least
acceptable. Components use the path that already exists.

**Entity access is a grant, not a claim.** A component's client is granted access to specific entities
exactly as a user is, validated server-side regardless of token contents (ADR-0011). A component holds
least privilege — an ingestion component that writes drafts needs neither posting rights nor access to
entities it does not serve.

### Configuration

A component reads its API location and its client credentials from the environment, like everything
else (ADR-0004). Two properties are decided here rather than left to implementation:

- **The API location a component dials is distinct from `PUBLIC_BASE_URL`.** `PUBLIC_BASE_URL` is what
  the service says about *itself* and may be a tunnel or a public hostname; a component needs where the
  API is reachable *from where it runs*, which is often neither.
- **The client secret is populated out of band.** Infrastructure code creates the secret container,
  never the value, because state stores secrets in plaintext (ADR-0016).

**`infra/README.md` is the authoritative list of variable names.** It is not repeated here: variable
names are specification, they change, and a record that enumerates them becomes wrong the first time
one is renamed — which cannot be corrected without violating immutability. ADR-0016 § "The deployment
contract" holds the rule that a change to the *shape* of the contract needs a record while a variable
within that shape does not.

### Consequences

* Good, because there is one authentication path, exercised by every caller in every topology.
* Good, because a component's reach is a server-side grant, so a compromised component secret does not
  imply access to every entity.
* Good, because it works identically on a laptop with no cloud account, so CI gate 2 exercises it.
* Bad, because each component needs an OAuth client registered and a secret populated out of band, so
  onboarding a component is more than deploying it.
* Bad, because it adds a requirement to the issuer conformance contract, narrowing the set of issuers
  that qualify.

### Confirmation

CI gate 2 runs with no cloud credentials present, which is what rejects any mechanism depending on
ambient cloud identity. A component started without credentials **fails immediately with a stable
error code** (ADR-0015) rather than hanging or retrying — that behaviour is required precisely so the
gate cannot hang.

The client credentials grant is part of the issuer conformance contract (ADR-0019), and the
conformance suite covers it. Absent that suite, support rests on the chosen issuer offering the
grant rather than on a check.

## Pros and Cons of the Options

### Components authenticate as OAuth clients via the client credentials grant

* Good, because it is the same path users take, so it is exercised by everyone.
* Good, because grants are per-entity and server-side, giving least privilege for free.
* Bad, because it requires client registration and secret rotation per component.
* Bad, because it adds a requirement to the issuer conformance contract.

### A long-lived API key or shared secret for components

By far the simplest thing that works. No token exchange, no issuer round trip, no client registration.

* Good, because it is trivial to implement, trivial to configure, and has no issuer dependency at all.
* Bad, because it is a second authentication path in the application, which ADR-0018 rejected by name
  for local mode. A machine caller is not a good enough reason to reintroduce it.
* Bad, because a long-lived secret with no audience binding is replayable against any resource server
  that trusts it.

### Cloud workload identity — a provider service account with implicit credentials

Idiomatic on the target platform, and it removes secret handling entirely: no client secret to store
or rotate.

* Good, because it eliminates the secret, which is the most operationally annoying part of the chosen
  option.
* Bad, because it is provider coupling of exactly the kind the portability gate exists to prevent. The
  component would authenticate one way in the cloud and another way everywhere else, so the
  self-hosted path becomes the one nobody exercises.
* Bad, because it fails CI gate 2 outright, which runs with no cloud credentials present.

### Components connect to the database directly instead of using the API

Faster, avoids the auth round trip entirely, and they are our own code in our own repository.

* Good, because it is the lowest-latency option and needs no credentials beyond the database's.
* Bad, because it is precisely what makes something a component rather than a module. Row-level
  security and service-layer filtering on `entity_id` both sit *above* the database, so a direct
  connection bypasses grant validation, the audit trail, and idempotency handling.
* Bad, because it is the same failure rejected for skills in ADR-0014, and it applies with equal force
  to first-party code.

## More Information

**Follow-on obligations.**

- The issuer must support the client credentials grant. This is an addition to the conformance
  contract in ADR-0019, and the conformance suite covers it.
- Entity grants are issuable to component clients, not only to users.
- A component started without credentials fails immediately with a stable error code (ADR-0015).
- `infra/README.md` documents the component variables and keeps them current.

**Reversal cost. Low.** Changing the authentication mechanism is contained in the component's client,
though it would touch the conformance contract.

Related: [ADR-0023](0023-one-image-many-entrypoints.md) decides how a component is built and deployed;
[ADR-0016](0016-opentofu-single-cloud-target-iac.md) holds the deployment contract this extends.

## Revisit when

- An issuer we want to support lacks the client credentials grant, which would be a conformance-contract
  question before it is an authentication one.
- Component secret rotation becomes an operational burden, at which point workload identity is worth
  re-examining — but only if it can be made to work identically without a cloud account.
