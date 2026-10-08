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
it is a binding non-goal ([ADR-0012](0012-binding-non-goals-and-scope-discipline.md)). A work queue is
not one, and passed that gate in [ADR-0061](0061-unattended-work-is-a-queue-in-postgres.md), which
also decides what drains it.

## Decision Drivers

* Version skew between a component and the API is a correctness problem, not an efficiency one.
* The portability gate should exercise the artifact users actually run, and preferably only one.
* The workload is mostly idle by assumption (ADR-0003), so paying for idle compute is a real cost.
* A schedule is never application behavior that requires a deploy to change.
* Code that runs unattended is deployed with the code that serves requests, in the same step.

## Considered Options

* One image with many entrypoints, in three runtime shapes
* A separate image per component
* A separate repository per component
* A broker-backed queue with worker components
* Components as sidecars in the same container or pod
* Two shapes only, with the worker as one more job

## Decision Outcome

Chosen option: "One image with many entrypoints, in three runtime shapes", because it makes version
skew between a component and the API structurally impossible, which is the only failure in this set
that costs correctness rather than money.

### 1. One image, many entrypoints

All components build from **one image**, differing only in the command they run.

```
service   python -m cfokit.ledger.api          request-serving
worker    python -m cfokit.server work         drains the work queue, no ingress
job       python -m cfokit.ledger.migrations   one-shot, explicit
```

The decisive reason is **version skew**. Separate images mean a component can run last week's code
against this week's API, and the failure surfaces as a contract violation rather than a deployment
error. One image makes that structurally impossible. It also means the portability gate exercises one
artifact rather than several.

### 2. Three runtime shapes, and only three

| Shape | What it is | Local | Cloud |
|---|---|---|---|
| **Service** | Request-serving, scale-to-zero, HTTP ingress | compose service | Cloud Run service |
| **Worker** | No ingress, drains the work queue a pass at a time | compose service, on by default, a pass after each | Cloud Run job, started on a tick and when a person waits |
| **Job** | One-shot, invoked explicitly, no request timeout | compose profile, run on demand | Cloud Run job |

**There is one worker**, and it runs everything unattended: what is due is the entity's stored
schedule and the causes enqueued with their writes, held in a queue in Postgres
([ADR-0061](0061-unattended-work-is-a-queue-in-postgres.md)). What is due is the database's to say,
so what starts a pass knows only that one should start. It is rolled out with the services, from the
same image, in the same step. On GCP it runs as a Cloud Run job until the queue is busy enough to
keep one instance always running, which changes the infrastructure and not the code (ADR-0061 § 3).

**A job is never scheduled.** It is a one-shot command a person or the deploy runs, such as a
migration. Anything that must happen on a schedule is a kind of work for the worker. That GCP runs
the worker with a Cloud Run job is the worker's runtime, not a job's shape: the tick starts a pass,
and the schedule stays in the database.

### Consequences

* Good, because a component cannot run against an API version it was not built for.
* Good, because the portability gate exercises one artifact rather than several.
* Good, because a schedule is data, so changing one is not a deploy, and unattended code is deployed
  with the rest of the code, so it never runs a different version.
* Bad, because the serving image carries dependencies only some entrypoints use, and that will worsen
  as components are added. A provider SDK needed only by an ingestion component ships in the serving
  image too — mitigated but not eliminated by the rule that provider SDKs are imported inside
  functions rather than at module scope (ADR-0004).
* Bad, because the worker is a fourth thing to run, and on GCP two triggers start it: a tick and a
  person's request. ADR-0061 states the cost and when it becomes always running instead.
* Bad, because a local deployment runs one service more than the API, the worker, so that scheduled
  work happens there as it does in the cloud (`NFR-17`).

### Confirmation

CI gate 2 runs the full suite against `compose.yaml` with no cloud credentials present, against the
same image every entrypoint uses. A component that reached for a provider SDK at module scope, or
that hung waiting for credentials, fails there.

Version lockstep is confirmed by construction rather than by a check: there is one image, so there is
no second version to skew against.

## Pros and Cons of the Options

### One image with many entrypoints, in three runtime shapes

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

### A broker-backed queue with worker components

The standard shape for background work — Redis or a managed queue, with workers per component —
with real benefits: backpressure, retries, and decoupling.

* Good, because backpressure and retry semantics come free, and it is the shape most engineers expect.
* Bad, because a broker is a second store (ADR-0003), and work published to it cannot commit with the
  write that caused it. ADR-0061 holds the queue in Postgres for that reason, with one worker
  draining every kind of work.
* Bad, because a worker per component multiplies always-running processes for a workload that is
  periodic rather than continuous.

### Components as sidecars in the same container or pod

Would keep deployment simple and let components share a network namespace with the service.

* Good, because there is one deployment unit and no service discovery.
* Bad, because it forfeits the isolation that justified making them components at all. If a component
  is co-located and shares a lifecycle, the criteria in ADR-0022 § 3 say it should have been a module.

### Two shapes only, with the worker as one more job

On GCP the worker runs as a Cloud Run job (ADR-0061 § 3), so it could be stated as a job and the
shapes kept to two.

* Good, because it is one fewer shape to state, and matches the resource GCP runs it as.
* Bad, because a job's contract is to run once, when a person or the deploy chooses, and nothing in
  it says a target must run anything unattended. A target that provided only services and jobs would
  meet the contract and never sync a feed or send a recurring invoice.
* Bad, because the worker's contract is its own: started repeatedly with no person, safe to run more
  than once at the same time, and on a laptop running continuously. Stated as a job, those are
  obligations of one job among several rather than of a shape every target supplies. That GCP meets
  them with a job resource is the worker's runtime there, not its shape.

## More Information

**Follow-on obligations.**

- `infra/README.md` states the three runtime shapes any target must provide — a request-serving
  runtime, a way to run the worker unattended (a job it can start on a timer and on request, or one
  always-running process with no ingress), and a one-shot job runtime with no request timeout.
- `compose.yaml` defines component entrypoints behind profiles so they never run by default — the same
  discipline applied to seeding in ADR-0018.
  The worker is the exception: it runs by default, because scheduled work is a capability every
  deployment has (ADR-0061).
- Because the local default ingestion provider requires no cloud account (`BKP-03`), ingestion is
  exercisable locally and in CI without any third-party credential.

**Reversal cost. Low.** Splitting images is a Dockerfile change with no application impact.

Related: [ADR-0032](0032-component-authentication-and-configuration.md) decides how a component
authenticates and what it reads from the environment.

## Revisit when

- **Dependency sets diverge** enough that the serving image carries meaningful unused weight. The
  remedy is multi-stage build targets from one Dockerfile, not separate builds.
- One worker cannot keep up, or a kind of work needs isolation from the others — the case for a
  second worker shape, which is a change to this record.
- A second cloud target is added, which is when the three-runtime-shape abstraction is first tested
  against a platform that may not offer all three.
