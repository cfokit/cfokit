---
status: "proposed"
kind: "substrate"
date: 2026-10-05
decision-makers: [Geoff]
---

# ADR-0060: Production is one GCP project behind one load balancer, deployed on every merge

## Context and Problem Statement

[ADR-0017](0017-gcp-initial-cloud-target.md) makes Cloud Run and Cloud SQL the maintained cloud
target, [ADR-0016](0016-opentofu-single-cloud-target-iac.md) makes OpenTofu its language and
`infra/README.md` its contract, and [ADR-0055](0055-on-gcp-the-web-client-is-served-from-a-cdn.md)
puts the web client in a bucket behind a load balancer on the API's origin. What those leave open
is everything a first production deployment has to settle before it can exist: how many
environments, where the issuer runs, how the services reach the database, where the
infrastructure's state lives, and what turns a merged pull request into running code.

Three surfaces are public. The REST service and the web client share one origin. The MCP service
has its own, because an MCP client discovers its issuer from that service's own protected-resource
metadata. The issuer has a third, because a token's `iss` must be the same address from every side
(ADR-0019). The issuer the compose stack runs is Keycloak, built in this repository with the
client's sign-in theme.

Every pull request is generated, merged by label under a review policy
([ADR-0048](0048-merge-eligibility-is-policy.md)), and gated by CI that runs no cloud deployment
(ADR-0004). The team is one person.

## Decision Drivers

* The environment contract in `infra/README.md` is met as written; nothing in the application
  learns it is on GCP (ADR-0004).
* No long-lived credential exists for a machine to leak: not a service-account key in CI, not a
  database password in OpenTofu state (ADR-0016).
* One public address per surface, each with a managed certificate, and none reachable around it.
* A merged change reaches production without a person running anything, in an order that never
  serves code against a schema it was not built for.
* The fixed monthly cost is the smallest that serves a first customer, on a target chosen for
  scaling to zero.
* Infrastructure changes — networks, databases, permissions — are applied by a person, not by the
  pipeline that ships application code.

## Considered Options

* One project; one load balancer for all three hosts; Keycloak on Cloud Run; private IP; deploy
  on merge with Workload Identity Federation; OpenTofu applied by a person
* A staging project beside production
* A managed issuer instead of Keycloak
* Cloud Run's built-in Cloud SQL connection and IAM database authentication
* OpenTofu applied by the pipeline on every merge

## Decision Outcome

Chosen option: "One project; one load balancer for all three hosts; Keycloak on Cloud Run; private
IP; deploy on merge with Workload Identity Federation; OpenTofu applied by a person", because it
meets the contract with nothing new in the application, holds no long-lived credential, and keeps
the power to change infrastructure out of the pipeline that runs on every merge.

> Production is one GCP project in `us-central1`. One global external Application Load Balancer
> holds three hostnames — the API and web client, MCP, and the issuer — with one Google-managed
> certificate. Keycloak runs as a Cloud Run service with one instance, its database beside
> CFOKit's on one Cloud SQL instance reached over private IP. Every merge to `main` builds the
> images, runs the migration job, publishes the web build and rolls out new revisions, authenticated
> by Workload Identity Federation. OpenTofu declares everything else and a person applies it.

### 1. One project, one region

There is no staging environment. Nothing is deployed anywhere yet, and the compose stack is
production-shaped, so a second project buys a rehearsal of a deploy CI already rehearses locally
(ADR-0018), at twice the fixed cost. The project ID, region, zone and hostnames are values in
`infra/gcp/`, not in this record.

### 2. One load balancer, three hostnames

The URL map routes by host. The API host sends `/app/` to the backend bucket and everything else to
the REST service, as ADR-0055 decides. The MCP host and the issuer host each send every path to
their service. One Google-managed certificate covers the three names. Every Cloud Run service's
ingress is restricted to internal traffic and Cloud Load Balancing, so none has a second public
address a client or a token could be issued against.

DNS is held outside GCP. Each hostname is an A record to the load balancer's address, set by a
person once, and served without the DNS provider's proxy, so the managed certificate's domain
validation reaches the load balancer and no second proxy rewrites what clients send.

### 3. Keycloak on Cloud Run, one instance

The issuer is the image the compose stack already builds, started in production mode with the
realm imported on first start. It runs as exactly one instance — minimum and maximum one — with its
cache local. Keycloak's own clustering needs instances to discover each other, which Cloud Run does
not provide; one instance needs none, and sessions persist in its database, so a restart signs
nobody out. It never scales to zero, because a sign-in that waits for a JVM to start is a sign-in
that times out.

Its database is a second database on the same Cloud SQL instance, under its own role, owned by
nothing of CFOKit's.

### 4. The database: one instance, private IP, passwords never in state

Cloud SQL for PostgreSQL, the major version the compose stack runs, zonal, the smallest dedicated
tier, with automated backups and point-in-time recovery. It has a private IP only. The services and
jobs reach it through Direct VPC egress, by the plain connection string the contract already
describes, so `DATABASE_URL` means the same thing here as on a laptop.

OpenTofu creates the instance, the databases and the Secret Manager containers. It does not create
database roles: a role's password would be in state. The roles the contract names — the owner, the
`cfokit_app` application role, and the issuer's — are created once by a person with the passwords
generated into Secret Manager, and each entrypoint's `DATABASE_URL` is a secret whose value is
populated the same way, out of band (ADR-0016).

### 5. Deploy on merge

A deploy workflow runs after CI succeeds on `main`. It authenticates to GCP by Workload Identity
Federation, scoped to this repository's `main` branch, so no key exists to store or rotate. In
order:

1. Build the application image and the issuer image, tagged with the commit, into Artifact
   Registry.
2. Run the migration job from the new image, and stop if it fails. A schema migration is applied
   before any revision that needs it serves traffic, never by a service at startup.
3. Copy the web build out of the new image into the bucket as ADR-0055 § 3 orders it.
4. Roll out new revisions of the REST, MCP and issuer services.
5. Run the deployment check ADR-0055 names, through the public addresses.

The deploy identity can push images, run the job, write the bucket and deploy revisions of existing
services. It cannot change networks, databases, IAM or the load balancer.

### 6. OpenTofu is applied by a person

State is in a versioned Cloud Storage bucket in the same project, encrypted by OpenTofu's state
encryption with a Cloud KMS key, so a reader of the bucket alone reads nothing. A person runs `tofu
plan` and `tofu apply` from `infra/gcp/`. The pipeline that runs on every merge never holds the
permissions infrastructure changes need.

### Consequences

* Good, because nothing in the application changes: every value it reads arrives as the contract
  says it will.
* Good, because no service-account key or database password exists in the repository, in CI, or in
  state.
* Good, because a merged change is in production minutes later with its migration applied first,
  with no person in the loop.
* Good, because one load balancer, one certificate and one database instance serve everything.
* Bad, because a bad merge reaches production with no staging environment between, and the only
  gates before it are CI and the deployment check after it.
* Bad, because the issuer is a single instance: a restart is a short sign-in outage, and its JVM
  and minimum instance are the largest fixed cost after the database and the load balancer.
* Bad, because creating the database roles and populating secrets are manual first-time steps,
  documented in `infra/gcp/` rather than declared.
* Bad, because DNS is outside OpenTofu, so the three records are set by hand and not reviewed as
  code.
* Neutral, because ADR-0055's MCP service is now behind the same load balancer, which that record
  left open.

### Confirmation

* The infrastructure is OpenTofu in `infra/gcp/`, reviewed as infrastructure under the code-owner
  rule (ADR-0048).
* The deploy workflow is in `.github/workflows/`, and its federation binding admits only this
  repository's `main` branch.
* The deployment check runs after every deploy and fails the workflow if `/readyz` on the REST and
  MCP hosts, the issuer's discovery document, or ADR-0055's web client requests fail.
* Not gated: that no role password reaches state. That is review of `infra/gcp/`.

## Pros and Cons of the Options

### One project; one load balancer; Keycloak on Cloud Run; private IP; deploy on merge

* Good, because it meets every driver with resources the OpenTofu Google provider declares.
* Bad, because of the single-instance issuer and the manual first-time steps above.

### A staging project beside production

The strongest case: a deploy is rehearsed against real GCP before it reaches customers, and a
migration that is slow on Cloud SQL is found there first.

* Good, because the load balancer, the certificate and the deploy order are exercised before
  production.
* Bad, because it doubles the fixed cost — database, load balancer, issuer instance — before there
  is a customer to protect, and the compose stack already runs the same image, migrations and
  issuer on every pull request.

### A managed issuer instead of Keycloak

* Good, because there is no JVM to run, patch or keep warm.
* Bad, because the issuer contract asks for the client credentials grant, JWT access tokens and
  dynamic client registration or client metadata documents, and an issuer that fails any of them
  fails the conformance suite the compose stack's issuer passes. Keycloak is already built, themed
  and tested here; a second issuer is a second thing to qualify.

### Cloud Run's built-in Cloud SQL connection and IAM database authentication

* Good, because there is no password at all, and no VPC to declare.
* Bad, because IAM authentication presents a short-lived token as the password, which the
  application would have to fetch through a provider library, or a proxy sidecar would have to
  inject; either way `DATABASE_URL` stops being the whole story, and the contract says it is.

### OpenTofu applied by the pipeline on every merge

* Good, because the infrastructure in `main` is always the infrastructure running.
* Bad, because the identity that applies it must be able to change IAM, networks and databases, and
  that identity would run on every generated, label-merged change.

## More Information

**Follow-on obligations.** `infra/gcp/` with its README holding the first-time steps: the state
bucket and KMS key, the database roles, the secret values, and the DNS records. The deploy workflow.
The deployment check.

**Reversal cost.** Low for the pipeline and the issuer's placement, which are infrastructure and
touch no application code. Moderate for adding a staging project later: the OpenTofu is written per
project from the start, so a second one is a second set of values and a second state.

## Revisit when

* A paying customer depends on the deployment — then a staging project, or at least a second
  issuer instance with clustering, earns its cost.
* Keycloak gains clustering that works without instance discovery, or Cloud Run gains discovery.
* A migration is too slow to run before a rollout without downtime.
