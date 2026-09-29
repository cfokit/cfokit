---
status: "draft"
kind: "requirement-driven"
date: 2026-08-17
decision-makers: [Geoff]
---

# ADR-0004: Portability is a build gate, and configuration is environment variables only

**Requirements served:** `NFR-10`, `NFR-11`, `NFR-17`.

## Context and Problem Statement

Self-hosting is a product promise, not a convenience. CFOKit must run in three topologies —
managed cloud, self-hosted cloud, and self-hosted local — and the local one is a real deployment
holding real books, not a demo (ADR-0018).

Portability is not a property you can hold by intention. It erodes one convenience at a time: a
cloud SDK imported for secrets, a metadata lookup for the project id, a URL derived from a request
header because it was to hand. Each is individually reasonable and none announces that it has
broken the self-hosted tier. The failure is discovered by a user, months later, when the container
will not start without credentials nobody realized it needed.

So the question is not what configuration mechanism to use. It is what makes portability
**checkable**, because a promise that is only documented is a promise that decays.

## Decision Drivers

* Portability must be a property CI can prove, not a claim review must protect.
* One source of truth for every setting — "what is this service configured with?" must not
  require knowing precedence rules.
* No path by which the package becomes unimportable without a cloud account.
* Attacker-controlled input must never determine what the service says about itself
  (ADR-0019).
* The variable surface must stay small enough for a human to hold in mind.

## Considered Options

* Environment variables only, with portability enforced as a CI gate
* Configuration files, with environment variables as overrides
* Cloud metadata for configuration
* Provider SDK for secret retrieval at module scope
* Deriving external URLs from `Host` or `X-Forwarded-*`
* Running migrations at container startup
* Documenting portability without testing it
* Supporting a configuration surface per cloud

## Decision Outcome

Chosen option: **the application's entire coupling to its environment is a set of environment
variables**, and **CI proves it.**

- Configuration is environment variables only. No configuration files, no cloud metadata lookups,
  no provider SDK imports at module scope.
- `PUBLIC_BASE_URL` is authoritative for anything the service says about itself. External URLs are
  **never** derived from request headers.
- Migrations run as an explicit command, never at container startup.
- Provider-specific code sits behind a protocol with a **local default requiring no cloud account**.

The complete variable surface is documented in `infra/README.md`, and adding to it requires an ADR
(ADR-0016 records why that document is the portability contract).

### Consequences

* Good, because portability becomes a property the build asserts rather than a claim the team
  defends.
* Good, because there is exactly one place to look to learn how a deployment is configured.
* Bad, because every deployment must supply four variables explicitly. There is no
  zero-configuration path.
* Bad, because secrets pass through the environment in the managed tier rather than being fetched
  directly.
* Bad, because the connector layer must ship a credential-free default provider so the gate can
  run — work that exists solely to keep the promise true (BKP-03).
* Bad, because adding a variable is deliberately slow, requiring an ADR.

### Confirmation

**CI gate 2:** the full suite runs against `compose.yaml`, without the dev overlay, **with no
cloud credentials present in the environment**. The workflow asserts their absence rather than
assuming it. Already in place in `.github/workflows/ci.yml`. `config.py` is the only place
environment variables are read; also already in place.

## Pros and Cons of the Options

### Environment variables only, enforced as a CI gate

* Good, because it is the only option in this list where breaking portability fails the build
  rather than reaching a user.
* Good, because the surface is small — four required variables — so the ergonomic argument for
  layering does not apply.
* Bad, because it offers no zero-configuration path, and no mechanism for configuration too
  large or structured to express as flat variables.

### Configuration files, with environment variables as overrides

The conventional layered approach: a committed default file, an environment-specific file, and
variables on top.

* Good, because of better ergonomics for large configuration surfaces.
* Good, because the file documents itself.
* Bad, because it creates two sources of truth for every setting, so "what is this service
  actually configured with?" requires knowing the precedence rules.
* Bad, because it invites secrets into files, which invites them into git — for a financial
  application that is the wrong default to make convenient.
* Bad, because the surface here is small enough that layering solves a problem we do not have.

### Cloud metadata for configuration

Reading project id, region, or instance identity from the provider's metadata endpoint.

* Good, because it removes configuration entirely on the target cloud, which is genuinely
  pleasant.
* Bad, because it is invisible coupling. The code has no import to grep for and no dependency in
  the manifest; it simply fails on any environment that is not that provider. This is exactly the
  class of erosion the build gate exists to catch — and it would catch it, but only after someone
  wrote it.

### Provider SDK for secret retrieval at module scope

Fetching secrets directly from Secret Manager at import time, so the container never receives them
as variables.

* Good, because it is a genuinely better security posture in the managed tier: secrets never
  appear in the environment or in `docker inspect`.
* Bad, because it makes the package unimportable without cloud credentials — so the test suite,
  the CLI, and `--help` all require a cloud account.
* Neutral, because the security benefit is recoverable in the managed tier by having the platform
  inject secrets from its store into the environment, which Cloud Run does natively (ADR-0016).
  Where a provider SDK is genuinely required, it is imported **inside the function that needs it**,
  never at module scope.

### Deriving external URLs from `Host` or `X-Forwarded-*`

The obvious way to make a service work at whatever address it is reached on, with no configuration.

* Good, because it requires no configuration at all.
* Bad, because behind a proxy or a tunnel those headers lie, so OAuth redirect URIs and resource
  identifiers come out wrong in exactly the deployments self-hosters use.
* Bad, because they are attacker-controlled: host-header injection is a real class of
  vulnerability, and in a system where the resource identifier participates in audience validation
  (ADR-0019), trusting them is a security defect rather than a portability one.

### Running migrations at container startup

Very common, and appealing because the service is always schema-current with no operational step.

* Good, because it removes an operational step.
* Bad, because with more than one instance starting concurrently they race.
* Bad, because a failed migration takes the service down rather than failing a job you can inspect.
* Bad, because on a scale-to-zero runtime migrations would run on cold start — repeatedly,
  unpredictably, in the request path.

### Documenting portability without testing it

Write the deployment contract, review changes carefully, trust the team.

* Good, because it costs nothing to adopt.
* Bad, because it is the status quo ante of every project that lost portability. Nobody decides to
  break it; it breaks between reviews. The gate is what converts a claim into a property, and it is
  the reason this is a *build gate* rather than a coding standard.

### Supporting a configuration surface per cloud

Letting each target contribute its own variables, so each can be configured idiomatically.

* Good, because each target is configured in its own idiom.
* Bad, because the shared surface **is** the portability artifact. Once targets have their own
  variables, the application knows which cloud it is on, and moving becomes a code change rather
  than new infrastructure (ADR-0016, ADR-0017).

## More Information

**Follow-on obligations.**

- `infra/README.md` documents the complete surface and stays current.
- CI gate 2 runs `compose.yaml` without the dev overlay and asserts no cloud credentials are
  present. **Already in place.**
- `config.py` is the only place environment variables are read. **Already in place.**
- An import-linter contract forbidding provider SDKs at module scope is added when the first
  provider SDK arrives — import-linter cannot reference modules that are not installed.
- The local compose stack requires no cloud account, including its OAuth issuer (ADR-0018,
  ADR-0019).

**Reversal cost. Low to abandon, high to regain.** Relaxing the rule is deleting a CI job. Getting
portability back after it has eroded means finding every implicit dependency, which is precisely
the work this gate exists to avoid ever needing.

## Revisit when

- A capability genuinely cannot be expressed as an environment variable. The remedy is then an ADR
  extending the contract, not an exception to it.
- The variable surface grows past what a human can hold in mind, which would suggest the
  application has taken on configuration that belongs to infrastructure.
