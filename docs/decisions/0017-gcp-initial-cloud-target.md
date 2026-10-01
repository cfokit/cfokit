---
status: "draft"
kind: "substrate"
date: 2026-08-16
decision-makers: [Geoff]
---

# ADR-0017: GCP (Cloud Run + Cloud SQL) as the initial cloud target

## Context and Problem Statement

ADR-0016 commits to one maintained cloud target at a time. This record picks it.

The service is a single container: HTTPS ingress, stateless, synchronous, backed by
Postgres (ADR-0003). Traffic is low and bursty — thousands of mostly-idle entities with
agent-driven writes. One long-running operation exists: `rebook`, which holds an entity
lock and can run for minutes on a large ledger (ADR-0011).

## Decision Drivers

* Scale to zero on compute, because the workload is thousands of mostly-idle entities.
* A single compute path. An operation that needs a second runtime shape because the first
  has a ceiling is a recurring tax, not a one-off.
* MCP streamable HTTP must be reachable by standard MCP clients without a custom transport
  (ADR-0009).
* Operational surface small enough for one maintainer.
* Existing familiarity, which is a real cost difference when there is one maintainer.

## Considered Options

* Google Cloud Run + Cloud SQL for PostgreSQL
* AWS Lambda + API Gateway
* AWS ECS Fargate
* AWS App Runner
* Azure Container Apps

## Decision Outcome

Chosen option: "Google Cloud Run + Cloud SQL for PostgreSQL", because it is the only
option that scales compute to zero while still running `rebook` and serving MCP over a
standard transport on one compute path.

> We will target Cloud Run for compute and Cloud SQL for PostgreSQL for storage, as the
> first and only maintained cloud deployment.

### Consequences

* Good, because compute scales to zero, which matches a workload of mostly-idle entities.
* Good, because compute is a container and a URL rather than a cluster, a service and a task
  definition. The load balancer the target does carry is for serving the web client from a CDN
  ([ADR-0055](0055-on-gcp-the-web-client-is-served-from-a-cdn.md)), not for compute.
* Good, because `rebook` runs as a job on the same image with no request timeout, so one
  long operation does not force a second compute stack.
* Bad, because Cloud SQL does not scale to zero, so there is an always-on database bill
  from day one — tens of dollars per month at current scale. Aurora Serverless v2 or
  Aurora DSQL would avoid it. That money buys a much simpler compute story, and the amount
  is small relative to a single customer.
* Neutral, because the choice is invisible to application code: the IaC supplies
  environment variables and that is the entire coupling (ADR-0004).

### Confirmation

CI gate 2 runs the full suite against `compose.yaml` with no cloud credentials present. A
provider SDK imported at module scope, or a cloud metadata lookup, fails there — which is
what keeps "nothing GCP-specific enters application code" true rather than aspirational.

The deployment shape itself is verified by deploying it; there is no gate asserting that
Cloud Run min instances stays at zero, and there does not need to be, because that setting
lives in IaC a reviewer reads.

## Pros and Cons of the Options

### Google Cloud Run + Cloud SQL for PostgreSQL

* Good, because it scales to zero on compute and bills per request.
* Good, because jobs and services are the same image with a different command, so
  `rebook` and migrations need no separate stack (ADR-0032).
* Good, because MCP streamable HTTP works over a standard transport, with no adapter.
* Bad, because Cloud SQL carries an always-on cost.

### AWS Lambda + API Gateway

Attractive for scale-to-zero and pay-per-request, and the most obvious serverless default.

* Good, because it bills only for invocations, with no idle compute cost at all.
* Bad, because MCP streamable HTTP requires stateless mode plus a Lambda Web Adapter to be
  reachable by standard MCP clients — the awslabs adapter needs a custom client transport
  that Claude Desktop's connector flow cannot dial. That is disqualifying for a published
  interface (ADR-0015).
* Bad, because `rebook` can exceed Lambda's 15-minute ceiling, forcing a second compute
  path for one operation.

### AWS ECS Fargate

* Good, because it solves the runtime limit — no request ceiling, no adapter.
* Bad, because it is always-on, giving up scale-to-zero without giving back operational
  simplicity: there is a cluster, a service, a load balancer, and a task definition where
  Cloud Run has a container and a URL.

### AWS App Runner

The closest AWS analogue to Cloud Run, and the option that would have made AWS viable.

* Good, because the deployment model is nearly the same as the chosen one.
* Bad, because it is less mature, has a smaller ecosystem, and does not fully scale billing
  to zero. Not rejected on merit so much as not better enough to outweigh existing GCP
  familiarity.

### Azure Container Apps

* Good, because it is a comparable primitive to Cloud Run and would serve equally well.
* Bad, because there is no current reason to prefer it and no existing familiarity. A
  reasonable contributed target later, under ADR-0016's rule that targets arrive with
  someone to maintain them.

## More Information

**Follow-on obligations.**

* Cloud Run min instances stays at zero; the service must tolerate cold starts.
* Migrations run as a Cloud Run **job**, invoked explicitly, never at container startup
  (ADR-0004).
* `rebook` runs on a compute path without a request timeout — a job, not the request path.
* Secrets live in Secret Manager. IaC creates the secret containers; values are populated
  out of band and never appear in IaC state (ADR-0016).
* Nothing GCP-specific enters application code. The IaC supplies environment variables and
  that is the entire coupling (ADR-0004).

**Reversal cost.** Low by construction. Because the app reads only environment variables
and imports no provider SDKs, moving to another container runtime is new IaC against the
same image, not an application change. The CI portability gate keeps this true rather than
aspirational.

## Revisit when

* Idle Cloud SQL cost exceeds compute cost. At that point evaluate Aurora Serverless v2 or
  DSQL — which is a database decision (ADR-0003), and would then likely pull compute to AWS
  with it.
* A customer requires a specific cloud for procurement or data-residency reasons.
* The MCP SDK or the connector ecosystem gains a Lambda-compatible transport, which would
  remove the specific objection to the serverless option but not the `rebook` ceiling.
