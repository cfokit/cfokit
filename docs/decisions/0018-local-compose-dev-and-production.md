---
status: "draft"
kind: "requirement-driven"
date: 2026-08-16
decision-makers: [Geoff]
---

# ADR-0018: One compose stack serving both local development and local production

**Requirements served:** `NFR-11`, `NFR-21`.

## Context and Problem Statement

ADR-0004 commits to three deployment topologies, one of which is self-hosted local. That
tier is a product promise: a user should be able to run CFOKit on a laptop, point an MCP
client at it, and have real books — not a demo.

Local development has overlapping but different needs: source reload, an inspectable
database, seed fixtures, verbose logs.

The failure mode to avoid is a "local mode" that quietly becomes a second product with its
own semantics. That is what collapsing the two backends (ADR-0014) was meant to prevent,
and a divergent compose file is the same mistake in a different place.

The genuinely hard part is not containers. It is authentication: the service is an
OAuth 2.1 resource server, and on a laptop with no cloud account there is no issuer.

## Decision Drivers

* What CI proves must be what users run, or the portability promise is untested.
* Development differences must be opt-in. For a financial application, a user who follows
  the quickstart must not silently get development configuration.
* Local deployment requires no cloud account and no signup (`NFR-11`).
* One authentication path. Auth is where divergence between what we develop against and
  what users run is least acceptable.

## Considered Options

* A production-shaped `compose.yaml` with an explicitly-applied `compose.dev.yaml` overlay
* `docker-compose.override.yml`, auto-loaded
* Separate compose files with no shared base
* Require an external OAuth issuer for local deployment
* A static bearer token for local mode

## Decision Outcome

Chosen option: "A production-shaped `compose.yaml` with an explicitly-applied
`compose.dev.yaml` overlay", because it is the only arrangement where the stack CI
exercises is the stack a self-hoster runs, and development convenience has to be asked for.

> We will ship `compose.yaml` as a production-shaped local deployment, with
> `compose.dev.yaml` as an explicitly-applied overlay containing only development
> differences.

Local deployment does not require an external identity provider. The specific issuer
arrangement is settled in ADR-0019; what this record fixes is that whatever it is, it runs
inside the compose stack and needs no cloud account.

### What a local issuer does and does not make identical

Running the issuer locally makes **token validation** identical in every topology: the
application reads `AUTH_ISSUER_URL` and `AUTH_AUDIENCE`, fetches JWKS, and validates
audience the same way whatever is on the other end.

It does not make the topologies identical issuer-side. Dynamic client registration, claim
shapes and scope encoding can still diverge between issuers, and the DCR shim is custom
code. Holding those constant is a conformance problem rather than a packaging one, and
ADR-0019 is where it is solved.

### Consequences

* Good, because the CI portability gate exercises the same file a self-hoster runs, so the
  self-host tier is tested rather than asserted.
* Good, because a user gets bind mounts, debug logging and an exposed database only by
  naming the overlay.
* Good, because there is one authentication path, exercised by everyone.
* Bad, because the local stack carries at least one additional container.
* Bad, because whatever ADR-0019 settles on must be pinned and tracked for security updates
  like any other dependency.

### Confirmation

CI gate 2 runs the full suite against `compose.yaml` **without** the dev overlay and with
no cloud credentials present (ADR-0004). That is what makes "what CI proves is what users
run" a gate rather than an intention.

What is not gated: nothing mechanically prevents `compose.dev.yaml` from altering the auth
path or the migrations. That constraint is stated below as an obligation and enforced by
review.

## Pros and Cons of the Options

### A production-shaped `compose.yaml` with an explicit `compose.dev.yaml` overlay

* Good, because the production path is the default path, so it is the one that gets
  exercised.
* Good, because a shared base means the development stack keeps proving something about
  the production one.
* Bad, because it is not the idiomatic Compose pattern, so contributors must be told the
  overlay exists.

### `docker-compose.override.yml`, auto-loaded

The idiomatic Compose pattern, and the one most contributors expect.

* Good, because it needs no extra flags and no documentation.
* Bad, because it applies silently, so `docker compose up` gives development configuration
  by default. A user who follows the quickstart and then keeps their real books in it gets
  bind mounts, debug logging and an exposed database without ever having chosen them. For a
  financial application, explicit beats idiomatic.

### Separate compose files with no shared base

* Good, because each file is readable on its own with no overlay semantics to understand.
* Bad, because it duplicates the service topology, so the two drift and the development
  stack stops proving anything about the production one.

### Require an external OAuth issuer for local deployment

* Good, because it is the simplest application code and removes a container from the stack.
* Bad, because local deployment then requires a cloud account and a provider project, which
  defeats the purpose of the tier and fails `NFR-11`.

### A static bearer token for local mode

Easiest thing for a user to get working, and tempting for exactly that reason.

* Good, because it removes the issuer from the local stack entirely.
* Bad, because it is a second authentication path in the application. Auth is the component
  where divergence between what we develop against and what users run is least acceptable,
  and a local-only code path would be exercised by nobody who could catch its bugs. ADR-0032
  reuses this reasoning for components.

## More Information

**Follow-on obligations.**

* The CI portability gate runs `compose.yaml` without the dev overlay (ADR-0004).
* `compose.dev.yaml` may not alter the image build target's runtime dependencies, the
  migrations, or the auth path. Divergence is limited to reload, exposed ports, log level,
  and opt-in fixtures.
* Seeding is behind a Compose profile and never runs by default. Seeding a ledger holding
  real books would corrupt it.
* Data lives in a named volume. Document that `docker compose down -v` destroys it, and
  ship a backup command.
* Cross-device access requires a tunnel and `PUBLIC_BASE_URL` set to the public hostname.
  Same-machine access over `http://localhost` needs no TLS.

**Reversal cost.** Low. Both files are configuration.

## Revisit when

* An MCP client we want to support cannot complete discovery against the local issuer.
* Local deployment demand justifies a packaged installer, at which point compose becomes an
  implementation detail behind it rather than the user-facing interface.
