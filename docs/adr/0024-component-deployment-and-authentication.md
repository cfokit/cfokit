# ADR-0024: Components ship as one image with many entrypoints, and authenticate as OAuth clients

- **Status:** Accepted
- **Date:** 2026-08-18
- **Deciders:** Geoff

## Context

[ADR-0023](0023-tiny-ledger-modules-and-components.md) established that anything which is not the
ledger is either an in-process module or a **separate component** reaching the ledger through the
published API. It deliberately left three questions open, and a component cannot ship until they are
answered:

1. How is a component built and shipped?
2. How does it **authenticate**? It is a machine caller with no interactive user, but every request
   requires audience validation ([ADR-0019](0019-identity-provider-conformance-contract.md)) and
   entity access is checked server-side ([ADR-0011](0011-entity-advisory-lock-idempotency-keys.md)).
3. What runtime shapes exist, and how do they map to both the local compose stack
   ([ADR-0018](0018-local-compose-dev-and-production.md)) and the maintained cloud target
   ([ADR-0017](0017-gcp-initial-cloud-target.md))?

Two existing constraints narrow the answer sharply and are worth stating before the decision.

**Portability is a build gate.** Configuration is environment variables only, no provider SDKs at
module scope, and CI runs the stack with no cloud credentials present
([ADR-0003](0003-portability-as-a-build-gate.md)). Anything decided here must survive that gate.

**There is no event bus.** It is a binding non-goal
([ADR-0012](0012-binding-non-goals-and-scope-discipline.md)), which removes the entire
queue-and-worker category from consideration without further argument.

## Decision

### 1. One image, many entrypoints

All components build from **one image**, differing only in the command they run.

```
service   python -m cfokit.ledger.api          request-serving
job       python -m cfokit.ledger.migrations   one-shot, explicit
job       python -m cfokit.<component>         one-shot or scheduled
```

The decisive reason is **version skew**. Separate images mean a component can run last week's code
against this week's API, and the failure surfaces as a contract violation rather than a deployment
error. One image makes that structurally impossible. It also means the portability gate exercises
one artifact rather than several.

### 2. Two runtime shapes, and only two

| Shape | What it is | Local | Cloud |
|---|---|---|---|
| **Service** | Request-serving, scale-to-zero, HTTP ingress | compose service | Cloud Run service |
| **Job** | One-shot, invoked explicitly, no request timeout | compose profile, run on demand | Cloud Run job |

A **scheduled** component is a job with a trigger attached — Cloud Scheduler in the cloud, and
nothing by default locally, because a laptop deployment has no reason to poll on a timer. Scheduling
is infrastructure, not application behaviour; the component itself only knows how to run once.

**There are no long-running workers.** That shape requires a queue, and an event bus is a binding
non-goal (ADR-0012). If work genuinely needs queueing, that is an ADR against the non-goals list,
not an implementation detail.

### 3. Components authenticate as OAuth clients

A component obtains a token via the **client credentials grant** against the same issuer the
application already uses, and calls the API like any other client. Audience validation applies
unchanged.

This follows directly from ADR-0018's rejection of a static bearer token for local mode: a second
authentication path is a path exercised by fewer people, and auth is where divergence is least
acceptable. Components use the path that already exists.

**Entity access is a grant, not a claim.** A component's client is granted access to specific
entities exactly as a user is, validated server-side regardless of token contents (ADR-0011). A
component holds least privilege — an ingestion component that writes drafts needs neither posting
rights nor access to entities it does not serve.

### 4. Configuration surface

Components read three variables beyond the shared auth settings. This record is the ADR that
ADR-0016 requires for extending the deployment contract:

| Variable | Purpose |
|---|---|
| `CFOKIT_API_URL` | Where the API is reachable **from this component**. Distinct from `PUBLIC_BASE_URL`, which is what the service says about *itself* and may be a tunnel or public hostname. |
| `AUTH_CLIENT_ID` | Component's OAuth client identity |
| `AUTH_CLIENT_SECRET` | Populated out of band; IaC creates the container, never the value (ADR-0016) |

`infra/README.md` is updated accordingly.

## Alternatives rejected

### A separate image per component

The conventional container practice: each component gets a minimal image with only its own
dependencies, reducing size and attack surface. Genuinely better on both counts.

Rejected primarily on **version skew**, which is a correctness problem rather than an efficiency one:
independently built and deployed images drift, and a component running against an API it was not
built for fails as a contract violation at runtime. It also multiplies CI build time and the number
of artifacts the portability gate must exercise.

The size objection is real and will grow. A provider SDK needed only by an ingestion component ships
in the serving image too — mitigated but not eliminated by the rule that provider SDKs are imported
inside functions rather than at module scope (ADR-0003). **This is the named revisit trigger:** when
dependency sets diverge enough that the serving image carries meaningful weight it never uses, split
using multi-stage build targets from the same Dockerfile, which preserves version lockstep.

### A separate repository per component

Clean ownership and independent release cadence.

Rejected because ADR-0023 keeps components in one repository, and splitting repositories makes the
version-skew problem worse rather than better while adding cross-repository contract testing.

### A long-lived API key or shared secret for components

By far the simplest thing that works. No token exchange, no issuer round trip, no client
registration.

Rejected on the precedent already set in ADR-0018, which rejected a static bearer token for local
mode by name: it is a second authentication path in the application, and auth is the component where
divergence between what we develop against and what users run is least acceptable. A machine caller
is not a good enough reason to reintroduce it.

### Cloud workload identity — a GCP service account with implicit credentials

Idiomatic on the target platform, and it removes secret handling entirely: no client secret to store
or rotate.

Rejected because it is provider coupling of exactly the kind the portability gate exists to prevent.
The component would authenticate one way in the cloud and another way everywhere else, so the
self-hosted path becomes the one nobody exercises. It also fails CI gate 2 outright, which runs with
no cloud credentials present.

### Components connect to the database directly instead of using the API

Faster, avoids the auth round trip entirely, and they are our own code in our own repository.

Rejected because it is precisely what makes something a component rather than a module. Row-level
security and service-layer filtering on `entity_id` both sit *above* the database, so a direct
connection bypasses grant validation, the audit trail, and idempotency handling. This is the same
reasoning that rejected direct database reads for skills (ADR-0014), and it applies with equal force
to first-party code.

### A queue with long-running worker components

The standard shape for ingestion and background work, with real benefits: backpressure, retries,
and decoupling.

Rejected because an event bus is a binding non-goal (ADR-0012), and because the workload does not
need it — ingestion is periodic rather than continuous, and idempotency keys already make retries
safe (ADR-0011). Revisit through the scope gate if that changes.

### Components as sidecars in the same container or pod

Would keep deployment simple and let components share a network namespace with the service.

Rejected because it forfeits the isolation that justified making them components at all. If a
component is co-located and shares a lifecycle, the criteria in ADR-0023 § 3 say it should have been
a module.

### Always-on services for scheduled work

Simpler than jobs: one deployment shape, an internal timer, no scheduler to configure.

Rejected because it pays for idle compute on a workload that is mostly idle by assumption
(ADR-0002), and because an internal timer makes the run schedule application behaviour that cannot
be changed without a deploy. Cloud Run jobs plus a scheduler keep timing in infrastructure where it
belongs.

## Consequences

**Accepted costs.**
- The serving image carries dependencies only some entrypoints use, and that will worsen as
  components are added. Named as the revisit trigger above.
- Each component needs an OAuth client registered and a secret populated out of band, so onboarding
  a component is more than deploying it.
- Local scheduled execution is manual. A self-hoster wanting periodic sync configures it themselves,
  and `infra/README.md` must say so rather than implying it happens automatically.

**Follow-on obligations.**
- `infra/README.md` documents `CFOKIT_API_URL`, `AUTH_CLIENT_ID`, and `AUTH_CLIENT_SECRET`, and
  states the two runtime shapes any target must provide — a request-serving runtime and a one-shot
  job runtime with no request timeout.
- The issuer must support the client credentials grant. This is an addition to the conformance
  contract in ADR-0019 and the conformance suite covers it.
- Entity grants are issuable to component clients, not only to users.
- `compose.yaml` defines component entrypoints behind profiles so they never run by default — the
  same discipline applied to seeding in ADR-0018.
- A component started without credentials **fails immediately with a stable error code**, rather than
  hanging or retrying. CI gate 2 runs with no credentials present and must not hang.
- Because the local default ingestion provider requires no cloud account (REQ-C2), ingestion is
  exercisable locally and in CI without any third-party credential.

**Reversal cost. Low.** Splitting images is a Dockerfile change with no application impact. Changing
the authentication mechanism is contained in the component's client, though it would touch the
conformance contract.

## Revisit when

- **Dependency sets diverge** enough that the serving image carries meaningful unused weight. The
  remedy is multi-stage build targets from one Dockerfile, not separate builds.
- Work appears that genuinely needs queueing and backpressure, which is a scope-gate question
  (ADR-0012) before it is a deployment one.
- A second cloud target is added, which is when the two-runtime-shape abstraction is first tested
  against a platform that may not offer both.
