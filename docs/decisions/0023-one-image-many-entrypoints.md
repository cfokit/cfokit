---
status: "draft"
kind: "requirement-driven"
date: 2026-08-18
decision-makers: [Geoff]
---

# ADR-0023: Components ship as one image with many entrypoints

**Requirements served:** `NFR-10`, `NFR-11`.

## Context and Problem Statement

[ADR-0022](0022-tiny-ledger-modules-and-components.md) established that anything which is not the
ledger is either an in-process module or a **separate component** reaching the ledger through the
published API. It deliberately left the deployment questions open, and a component cannot ship until
they are answered:

1. How is a component built and shipped?
2. What runtime shapes exist, and how do they map to both the local compose stack
   ([ADR-0018](0018-local-compose-dev-and-production.md)) and the maintained cloud target
   ([ADR-0017](0017-gcp-initial-cloud-target.md))?

How a component *authenticates* is a separate decision, held in
[ADR-0032](0032-component-authentication-and-configuration.md).

Two existing constraints narrow the answer sharply. **Portability is a build gate** — configuration
is environment variables only, no provider SDKs at module scope, and CI runs the stack with no cloud
credentials present ([ADR-0004](0004-portability-as-a-build-gate.md)). And **there is no event bus**;
it is a binding non-goal ([ADR-0012](0012-binding-non-goals-and-scope-discipline.md)), which removes
the entire queue-and-worker category from consideration without further argument.

## Decision Drivers

* Version skew between a component and the API is a correctness problem, not an efficiency one.
* The portability gate should exercise the artifact users actually run, and preferably only one.
* The workload is mostly idle by assumption (ADR-0003), so paying for idle compute is a real cost.
* Scheduling belongs to infrastructure, not to application behaviour that requires a deploy to
  change.

## Considered Options

* One image with many entrypoints, in two runtime shapes
* A separate image per component
* A separate repository per component
* A queue with long-running worker components
* Components as sidecars in the same container or pod
* Always-on services for scheduled work

## Decision Outcome

Chosen option: "One image with many entrypoints, in two runtime shapes", because it makes version
skew between a component and the API structurally impossible, which is the only failure in this set
that costs correctness rather than money.

### 1. One image, many entrypoints

All components build from **one image**, differing only in the command they run.

```
service   python -m cfokit.ledger.api          request-serving
job       python -m cfokit.ledger.migrations   one-shot, explicit
job       python -m cfokit.<component>         one-shot or scheduled
```

The decisive reason is **version skew**. Separate images mean a component can run last week's code
against this week's API, and the failure surfaces as a contract violation rather than a deployment
error. One image makes that structurally impossible. It also means the portability gate exercises one
artifact rather than several.

### 2. Two runtime shapes, and only two

| Shape | What it is | Local | Cloud |
|---|---|---|---|
| **Service** | Request-serving, scale-to-zero, HTTP ingress | compose service | Cloud Run service |
| **Job** | One-shot, invoked explicitly, no request timeout | compose profile, run on demand | Cloud Run job |

A **scheduled** component is a job with a trigger attached — Cloud Scheduler in the cloud, and nothing
by default locally, because a laptop deployment has no reason to poll on a timer. Scheduling is
infrastructure, not application behaviour; the component itself only knows how to run once.

**There are no long-running workers.** That shape requires a queue, and an event bus is a binding
non-goal (ADR-0012). If work genuinely needs queueing, that is a record against the non-goals list,
not an implementation detail.

### Consequences

* Good, because a component cannot run against an API version it was not built for.
* Good, because the portability gate exercises one artifact rather than several.
* Good, because scheduling lives in infrastructure, so changing a run schedule is not a deploy.
* Bad, because the serving image carries dependencies only some entrypoints use, and that will worsen
  as components are added. A provider SDK needed only by an ingestion component ships in the serving
  image too — mitigated but not eliminated by the rule that provider SDKs are imported inside
  functions rather than at module scope (ADR-0004).
* Bad, because local scheduled execution is manual. A self-hoster wanting periodic sync configures it
  themselves, and `infra/README.md` must say so rather than implying it happens automatically.

### Confirmation

CI gate 2 runs the full suite against `compose.yaml` with no cloud credentials present, against the
same image every entrypoint uses. A component that reached for a provider SDK at module scope, or
that hung waiting for credentials, fails there.

Version lockstep is confirmed by construction rather than by a check: there is one image, so there is
no second version to skew against.

## Pros and Cons of the Options

### One image with many entrypoints, in two runtime shapes

* Good, because version skew is impossible by construction.
* Good, because one artifact is built, scanned, and exercised.
* Bad, because the image carries every component's dependencies.

### A separate image per component

The conventional container practice: each component gets a minimal image with only its own
dependencies, reducing size and attack surface. Genuinely better on both counts.

* Good, because images are smaller and each has a narrower attack surface.
* Bad, because independently built and deployed images drift, and a component running against an API
  it was not built for fails as a contract violation at runtime. That is a correctness problem rather
  than an efficiency one.
* Bad, because it multiplies CI build time and the number of artifacts the portability gate must
  exercise.

The size objection is real and will grow. **It is the named revisit trigger:** when dependency sets
diverge enough that the serving image carries meaningful weight it never uses, split using
multi-stage build targets from the same Dockerfile, which preserves version lockstep.

### A separate repository per component

Clean ownership and independent release cadence.

* Good, because ownership and release cadence would be genuinely independent.
* Bad, because ADR-0022 keeps components in one repository, and splitting repositories makes the
  version-skew problem worse rather than better while adding cross-repository contract testing.

### A queue with long-running worker components

The standard shape for ingestion and background work, with real benefits: backpressure, retries, and
decoupling.

* Good, because backpressure and retry semantics come free, and it is the shape most engineers expect.
* Bad, because an event bus is a binding non-goal (ADR-0012).
* Bad, because the workload does not need it — ingestion is periodic rather than continuous, and
  idempotency keys already make retries safe (ADR-0029).

### Components as sidecars in the same container or pod

Would keep deployment simple and let components share a network namespace with the service.

* Good, because there is one deployment unit and no service discovery.
* Bad, because it forfeits the isolation that justified making them components at all. If a component
  is co-located and shares a lifecycle, the criteria in ADR-0022 § 3 say it should have been a module.

### Always-on services for scheduled work

Simpler than jobs: one deployment shape, an internal timer, no scheduler to configure.

* Good, because it removes a runtime shape and needs no external scheduler.
* Bad, because it pays for idle compute on a workload that is mostly idle by assumption (ADR-0003).
* Bad, because an internal timer makes the run schedule application behaviour that cannot be changed
  without a deploy.

## More Information

**Follow-on obligations.**

- `infra/README.md` states the two runtime shapes any target must provide — a request-serving runtime
  and a one-shot job runtime with no request timeout.
- `compose.yaml` defines component entrypoints behind profiles so they never run by default — the same
  discipline applied to seeding in ADR-0018.
- Because the local default ingestion provider requires no cloud account (`BKP-03`), ingestion is
  exercisable locally and in CI without any third-party credential.

**Reversal cost. Low.** Splitting images is a Dockerfile change with no application impact.

Related: [ADR-0032](0032-component-authentication-and-configuration.md) decides how a component
authenticates and what it reads from the environment.

## Revisit when

- **Dependency sets diverge** enough that the serving image carries meaningful unused weight. The
  remedy is multi-stage build targets from one Dockerfile, not separate builds.
- Work appears that genuinely needs queueing and backpressure, which is a scope-gate question
  (ADR-0012) before it is a deployment one.
- A second cloud target is added, which is when the two-runtime-shape abstraction is first tested
  against a platform that may not offer both.
