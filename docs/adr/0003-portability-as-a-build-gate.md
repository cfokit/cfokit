# ADR-0003: Portability is a build gate, and configuration is environment variables only

- **Status:** Accepted
- **Date:** 2026-08-17
- **Deciders:** Geoff

## Context

Self-hosting is a product promise, not a convenience. CFOKit must run in three topologies —
managed cloud, self-hosted cloud, and self-hosted local — and the local one is a real deployment
holding real books, not a demo (ADR-0018).

Portability is not a property you can hold by intention. It erodes one convenience at a time: a
cloud SDK imported for secrets, a metadata lookup for the project id, a URL derived from a request
header because it was to hand. Each is individually reasonable and none announces that it has
broken the self-hosted tier. The failure is discovered by a user, months later, when the container
will not start without credentials nobody realised it needed.

So the question is not what configuration mechanism to use. It is what makes portability
**checkable**, because a promise that is only documented is a promise that decays.

## Decision

**The application's entire coupling to its environment is a set of environment variables**, and
**CI proves it.**

- Configuration is environment variables only. No configuration files, no cloud metadata lookups,
  no provider SDK imports at module scope.
- `PUBLIC_BASE_URL` is authoritative for anything the service says about itself. External URLs are
  **never** derived from request headers.
- Migrations run as an explicit command, never at container startup.
- Provider-specific code sits behind a protocol with a **local default requiring no cloud account**.
- **CI gate 2:** the full suite runs against `compose.yaml`, without the dev overlay, **with no
  cloud credentials present in the environment**. The workflow asserts their absence rather than
  assuming it.

The complete variable surface is documented in `infra/README.md`, and adding to it requires an ADR
(ADR-0016 records why that document is the portability contract).

## Alternatives rejected

### Configuration files, with environment variables as overrides

The conventional layered approach: a committed default file, an environment-specific file, and
variables on top. Better ergonomics for large configuration surfaces, and the file documents itself.

Rejected because it creates two sources of truth for every setting, so "what is this service
actually configured with?" requires knowing the precedence rules. It also invites secrets into
files, which invites them into git — and for a financial application that is the wrong default to
make convenient. The surface here is small enough (four required variables) that layering solves a
problem we do not have.

### Cloud metadata for configuration

Reading project id, region, or instance identity from the provider's metadata endpoint. Removes
configuration entirely on the target cloud, which is genuinely pleasant.

Rejected because it is invisible coupling. The code has no import to grep for and no dependency in
the manifest; it simply fails on any environment that is not that provider. This is exactly the
class of erosion the build gate exists to catch, and it would catch it — but only after someone
wrote it.

### Provider SDK for secret retrieval at module scope

Fetching secrets directly from Secret Manager at import time, so the container never receives them
as variables. Genuinely better security posture in the managed tier: secrets never appear in the
environment or in `docker inspect`.

Rejected because it makes the package unimportable without cloud credentials — so the test suite,
the CLI, and `--help` all require a cloud account. The security benefit is recoverable in the
managed tier by having the platform inject secrets from its store into the environment, which
Cloud Run does natively (ADR-0016). Where a provider SDK is genuinely required, it is imported
**inside the function that needs it**, never at module scope.

### Deriving external URLs from `Host` or `X-Forwarded-*`

The obvious way to make a service work at whatever address it is reached on, with no configuration.

Rejected twice over. Behind a proxy or a tunnel those headers lie, so OAuth redirect URIs and
resource identifiers come out wrong in exactly the deployments self-hosters use. And they are
attacker-controlled: host-header injection is a real class of vulnerability, and in a system where
the resource identifier participates in audience validation (ADR-0019), trusting them is a security
defect rather than a portability one.

### Running migrations at container startup

Very common, and appealing because the service is always schema-current with no operational step.

Rejected on three counts. With more than one instance starting concurrently they race. A failed
migration takes the service down rather than failing a job you can inspect. And on a scale-to-zero
runtime, migrations would run on cold start — repeatedly, unpredictably, in the request path.
Migrations are a deliberate act with a deliberate command.

### Documenting portability without testing it

Write the deployment contract, review changes carefully, trust the team.

Rejected because it is the status quo ante of every project that lost portability. Nobody decides
to break it; it breaks between reviews. The gate is what converts a claim into a property, and it
is the reason this is a *build gate* rather than a coding standard.

### Supporting a configuration surface per cloud

Letting each target contribute its own variables, so each can be configured idiomatically.

Rejected because the shared surface is the portability artifact. Once targets have their own
variables, the application knows which cloud it is on, and moving becomes a code change rather than
new infrastructure (ADR-0016, ADR-0017).

## Consequences

**Accepted costs.**
- Every deployment must supply four variables explicitly. There is no zero-configuration path.
- Secrets pass through the environment in the managed tier rather than being fetched directly.
- The connector layer must ship a credential-free default provider so the gate can run, which is
  work that exists solely to keep the promise true (REQ-C2).
- Adding a variable is deliberately slow, requiring an ADR.

**Follow-on obligations.**
- `infra/README.md` documents the complete surface and stays current.
- CI gate 2 runs `compose.yaml` without the dev overlay and asserts no cloud credentials are
  present. **Already in place** in `.github/workflows/ci.yml`.
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
