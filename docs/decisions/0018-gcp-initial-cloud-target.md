---
status: "accepted"
kind: "substrate"
date: 2026-08-16
decision-makers: [Geoff]
---

# ADR-0018: GCP (Cloud Run + Cloud SQL) as the initial cloud target

## Context

ADR-0017 commits to one maintained cloud target at a time. This ADR picks it.

The service is a single container: HTTPS ingress, stateless, synchronous, backed by
Postgres (ADR-0003). Traffic is low and bursty — thousands of mostly-idle entities with
agent-driven writes. One long-running operation exists: `rebook`, which holds an entity
lock and can run for minutes on a large ledger (ADR-0012).

## Decision

We will target **Google Cloud Run** for compute and **Cloud SQL for PostgreSQL** for
storage as the first and only maintained cloud deployment.

## Alternatives rejected

### AWS Lambda + API Gateway

Attractive for scale-to-zero and pay-per-request. Rejected on two counts. MCP streamable
HTTP requires stateless mode plus a Lambda Web Adapter to be reachable by standard MCP
clients — the awslabs adapter needs a custom client transport that Claude Desktop's
connector flow cannot dial. And `rebook` can exceed Lambda's 15-minute ceiling, forcing
a second compute path for one operation.

### AWS ECS Fargate

Solves the runtime limit but is always-on, giving up scale-to-zero without giving back
operational simplicity — there is a cluster, a service, a load balancer, and a task
definition where Cloud Run has a container and a URL.

### AWS App Runner

Closest AWS analogue to Cloud Run. Less mature, smaller ecosystem, and does not fully
scale billing to zero. Not rejected on merit so much as not better enough to outweigh
existing GCP familiarity.

### Azure Container Apps

Comparable primitive to Cloud Run. No current reason to prefer it and no existing
familiarity. A reasonable contributed target later.

## Consequences

**Accepted costs.** Cloud SQL does not scale to zero, so there is an always-on database
bill from day one — tens of dollars per month at current scale. Aurora Serverless v2 or
Aurora DSQL would avoid this. We are buying a much simpler compute story with that
money, and the amount is small relative to a single customer.

**Follow-on obligations.**
- Cloud Run min instances stays at zero; the service must tolerate cold starts.
- Migrations run as a Cloud Run **job**, invoked explicitly, never at container startup
  (ADR-0004).
- `rebook` runs on a compute path without a request timeout — a Cloud Run job, not the
  request path.
- Secrets live in Secret Manager. IaC creates the secret containers; values are
  populated out of band and never appear in IaC state (ADR-0017).
- Nothing GCP-specific enters application code. The IaC supplies environment variables
  and that is the entire coupling (ADR-0004).

**Reversal cost.** Low by construction. Because the app reads only environment
variables and imports no provider SDKs, moving to another container runtime is new IaC
against the same image, not an application change. The CI portability gate keeps this
true rather than aspirational.

## Revisit when

- Idle Cloud SQL cost exceeds compute cost. At that point evaluate Aurora Serverless v2
  or DSQL — which is a database decision (ADR-0003), and would then likely pull compute
  to AWS with it.
- A customer requires a specific cloud for procurement or data-residency reasons.
