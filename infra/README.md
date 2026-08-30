# CFOKit Deployment Contract

**This document is the portability artifact, not the modules beside it.** (ADR-0017)

CFOKit runs in three topologies: managed cloud, self-hosted cloud, and self-hosted local.
Portability is a product promise and a CI gate, not a convenience (ADR-0004). What makes it
true is that the application's entire coupling to its environment is the variable list below
— so infrastructure code for any particular cloud is thin glue rather than a port.

**Adding anything to the environment surface below requires an ADR.** That is what makes
this document a contract instead of documentation. (ADR-0017)

## What any target must provide

### 1. Environment variables

The complete configuration surface. The application reads these and nothing else — no cloud
metadata lookups, no provider SDK imports at module scope.

| Variable | Required | Purpose |
|---|---|---|
| `DATABASE_URL` | yes | PostgreSQL connection string. The only storage backend (ADR-0003). |
| `PUBLIC_BASE_URL` | yes | Authoritative for anything the service says about itself. **Never derived from request headers** — behind a proxy or tunnel they lie (ADR-0004). |
| `AUTH_ISSUER_URL` | yes | OAuth 2.1 issuer base URL (ADR-0020). |
| `AUTH_AUDIENCE` | yes | Expected token audience. Validated on every request (ADR-0012, ADR-0020). |
| `LOG_LEVEL` | no | Defaults to `info`. |
| `PORT` | no | Defaults to `8080`. |

There is deliberately no variable selecting a cloud, a region, or a provider.

**Separate components** — anything running in its own runtime and reaching the API rather than the
database (ADR-0024) — read three more (ADR-0025):

| Variable | Required | Purpose |
|---|---|---|
| `CFOKIT_API_URL` | yes | Where the API is reachable **from this component**. Not the same as `PUBLIC_BASE_URL`, which is what the service says about *itself* and may be a tunnel or public hostname. |
| `AUTH_CLIENT_ID` | yes | The component's OAuth client identity. |
| `AUTH_CLIENT_SECRET` | yes | Populated out of band. IaC creates the container, never the value. |

A component started without credentials fails immediately with a stable error code. It does not hang
or retry, because the CI portability gate runs with no credentials present.

### 2. A PostgreSQL database

Reachable at `DATABASE_URL`, supporting deferred constraint triggers (ADR-0006), advisory
locks (ADR-0012), and row-level security. These requirements are why Aurora DSQL is deferred
rather than chosen (ADR-0003).

### 3. An OAuth 2.1 issuer meeting the conformance contract

The issuer is a **swappable dependency**, not a chosen product. The default in the compose
stack is Ory Hydra (Apache 2.0); it is a default, not a coupling. No issuer-specific code
exists anywhere in the codebase. (ADR-0020)

Any conforming issuer must provide:

- OIDC Discovery **or** OAuth 2.0 Authorization Server Metadata
- A JWKS endpoint with key rotation
- **RFC 8707 Resource Indicators** — the `resource` parameter must bind the token audience
- **RFC 9207** issuer identifier in the authorization response
- Declared, configurable claim names for subject and scopes
- RFC 7591 Dynamic Client Registration **or** Client ID Metadata Documents
- The **client credentials grant**, for separate components authenticating as machine callers
  (ADR-0025 — an extension to the contract originally set in ADR-0020)

An automated conformance suite verifies this. It runs in CI against the default issuer and
against any additional issuer we claim to support — that suite is what makes the swap claim
true rather than aspirational.

**No AGPL or other network-copyleft component ships in the default stack.** (ADR-0020)

### 4. HTTPS ingress

Terminating TLS and forwarding to the container port. Same-machine access over
`http://localhost` needs no TLS; cross-device access requires a tunnel and
`PUBLIC_BASE_URL` set to the public hostname.

### 5. Two runtime shapes

Any target must provide both (ADR-0025):

| Shape | Requirement |
|---|---|
| **Service** | Request-serving with HTTPS ingress. May scale to zero. |
| **Job** | One-shot execution, invoked explicitly, **with no request timeout**. |

All entrypoints run from the **same image**, differing only in command — this is what prevents a
component running against an API version it was not built for. Scheduling a job is the target's
concern, not the application's: the component only knows how to run once. Locally there is no
scheduler, so periodic work is run on demand.

There are no long-running worker processes, because there is no queue (ADR-0013).

### 6. A compute path without a request timeout

`rebook` holds an entity lock and can run for minutes on a large ledger. It must not run on
the request path. On the maintained target it is a Cloud Run job. (ADR-0012, ADR-0018)

### 7. An explicit migration step

Migrations run as a command, **never at container startup** (ADR-0004):

```
python -m cfokit.ledger.migrations
```

The deployment must invoke this deliberately — a job, a task, a manual step. If your target
makes migrations a startup hook, it does not satisfy this contract.

### 8. Secret storage

Values are populated **out of band**. Infrastructure code creates secret *containers* only,
never secret values: state stores secrets in plaintext, so treat state as sensitive and
enable OpenTofu state encryption. (ADR-0017)

## Health endpoints

| Endpoint | Meaning |
|---|---|
| `/healthz` | Liveness only. Does not touch the database. |
| `/readyz` | Database reachable **and** migrations current. |

Point your platform's liveness probe at `/healthz` and its readiness probe at `/readyz`.
Getting these the wrong way round will restart a healthy container during a migration.

## Tooling

**OpenTofu, not Terraform** — `tofu`, not `terraform`. Terraform 1.6+ ships under BUSL,
which is source-available rather than open source, and shipping infrastructure code our users
cannot freely use would contradict the anti-lock-in promise that motivates the self-host
tier. (ADR-0017)

## Maintained targets

**GCP — Cloud Run plus Cloud SQL for PostgreSQL.** The first and only maintained cloud
target. (ADR-0018)

Configuration is not yet written; it arrives with REQ-E2 and will live
in `infra/gcp/`. There is no placeholder directory, deliberately: module sets nobody runs and
CI never exercises rot silently, and the first user to try an unmaintained module concludes
the project is abandoned. That is worse than shipping nothing for a cloud. (ADR-0017)

**We do not maintain AWS or Azure configurations, including placeholder directories.** Users
on another cloud write their own infrastructure code against the contract above — that is why
the contract is written down. Additional targets are added when someone actually needs one and
are expected to be contributed. (ADR-0017, ADR-0018)

## Local deployment

`compose.yaml` at the repository root is a production-shaped local deployment needing no
cloud account. It is not a demo — it holds real books. `compose.dev.yaml` is applied
explicitly and never automatically. (ADR-0019)

```
docker compose up          # local production
uv run task dev            # with the development overlay
```

Data lives in a named volume. **`docker compose down -v` destroys it.**

Never provision a laptop with OpenTofu. (ADR-0019)
