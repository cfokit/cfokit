# CFOKit Deployment Contract

**This document is the portability artifact, not the modules beside it.** (ADR-0016)

CFOKit runs in three topologies: managed cloud, self-hosted cloud, and self-hosted local.
Portability is a product promise and a CI gate, not a convenience (ADR-0004). What makes it
true is that the application's entire coupling to its environment is the variable list below
— so infrastructure code for any particular cloud is thin glue rather than a port.

**This document is authoritative for the variable names.** Decision records do not enumerate
them: names are specification, they change, and a record that lists them becomes wrong the
first time one is renamed.

**Changing the *shape* of the contract requires a decision record. Adding a variable within
the existing shape does not.** The shape is what portability rests on — configuration is
environment variables only, secrets arrive as containers whose values are populated out of
band, and nothing is read from cloud metadata. Anything that breaks one of those is
architectural and needs its own record. (ADR-0016)

## What any target must provide

### 1. Environment variables

The complete configuration surface. The application reads these and nothing else — no cloud
metadata lookups, no provider SDK imports at module scope.

| Variable | Required | Purpose |
|---|---|---|
| `DATABASE_URL` | yes | PostgreSQL connection string. The only storage backend (ADR-0003). **The value differs per entrypoint** — see *Two database roles* below. |
| `PUBLIC_BASE_URL` | yes | Authoritative for anything the service says about itself. **Never derived from request headers** — behind a proxy or tunnel they lie (ADR-0004). |
| `AUTH_ISSUER_URL` | yes | OAuth 2.1 issuer base URL (ADR-0019). |
| `AUTH_AUDIENCE` | yes | Expected token audience. Validated on every request (ADR-0011, ADR-0019). |
| `LOG_LEVEL` | no | Defaults to `info`. |
| `PORT` | no | Defaults to `8080`. |

There is deliberately no variable selecting a cloud, a region, or a provider.

**Separate components** — anything running in its own runtime and reaching the API rather than the
database (ADR-0022) — read three more (ADR-0032):

| Variable | Required | Purpose |
|---|---|---|
| `CFOKIT_API_URL` | yes | Where the API is reachable **from this component**. Not the same as `PUBLIC_BASE_URL`, which is what the service says about *itself* and may be a tunnel or public hostname. |
| `AUTH_CLIENT_ID` | yes | The component's OAuth client identity. |
| `AUTH_CLIENT_SECRET` | yes | Populated out of band. IaC creates the container, never the value. |

A component started without credentials fails immediately with a stable error code. It does not hang
or retry, because the CI portability gate runs with no credentials present.

### 2. A PostgreSQL database

Reachable at `DATABASE_URL`, supporting deferred constraint triggers (ADR-0006), advisory
locks (ADR-0011), and row-level security. These requirements are why Aurora DSQL is deferred
rather than chosen (ADR-0003).

#### Two database roles

Row-level security does not apply to a superuser, and does not apply to a table's owner
unless the table is `FORCE`'d. So the role that applies migrations and the role the
application connects as **must be different**, or the policies are inert and entity isolation
rests on service-layer filtering alone. ADR-0003 asks for two layers precisely because "RLS
misconfiguration is silent" — nothing fails, and a bypassed policy is indistinguishable from
an enforced one unless something checks.

| Role | Used by | Needs |
|---|---|---|
| Owner | the `migrate` entrypoint | Ownership of the schema; DDL |
| `cfokit_app` | every serving entrypoint | `LOGIN`, **`NOSUPERUSER`**, **`NOBYPASSRLS`**, and no ownership of any table |

`DATABASE_URL` carries the owner connection for the migrate job and the `cfokit_app`
connection for everything else. It is one variable with a different value per entrypoint
rather than two variables, so the configuration surface is unchanged.

The application role's table privileges are granted by migration `0002`, which names
`cfokit_app` directly. **Creating the role is a deployment step, not a migration** — roles are
cluster-scoped and a managed provider may not grant `CREATEROLE`. Create it before applying
migrations; `0002` fails loudly if it does not exist, which is the right outcome, because a
deployment missing the role would otherwise run with isolation silently halved.

`infra/postgres/init-app-role.sh` does this for the compose stack, on first initialisation of
an empty data directory.

Verified rather than assumed: `tests/integration/test_entity_isolation.py` asserts the
property from the outside, as the application role, and CI gate 2 runs it inside the compose
network on every pull request.

### 3. An OAuth 2.1 issuer meeting the conformance contract

The issuer is a **swappable dependency**, not a chosen product. The default in the compose
stack is Ory Hydra (Apache 2.0); it is a default, not a coupling. No issuer-specific code
exists anywhere in the codebase. (ADR-0019)

Any conforming issuer must provide:

- OIDC Discovery **or** OAuth 2.0 Authorization Server Metadata
- A JWKS endpoint with key rotation
- **RFC 8707 Resource Indicators** — the `resource` parameter must bind the token audience
- **RFC 9207** issuer identifier in the authorization response
- Declared, configurable claim names for subject and scopes
- RFC 7591 Dynamic Client Registration **or** Client ID Metadata Documents
- The **client credentials grant**, for separate components authenticating as machine callers
  (ADR-0032 — an extension to the contract originally set in ADR-0019)

An automated conformance suite verifies this. It runs in CI against the default issuer and
against any additional issuer we claim to support — that suite is what makes the swap claim
true rather than aspirational.

**No AGPL or other network-copyleft component ships in the default stack.** (ADR-0019)

### 4. HTTPS ingress

Terminating TLS and forwarding to the container port. Same-machine access over
`http://localhost` needs no TLS; cross-device access requires a tunnel and
`PUBLIC_BASE_URL` set to the public hostname.

### 5. Two runtime shapes

Any target must provide both (ADR-0023):

| Shape | Requirement |
|---|---|
| **Service** | Request-serving with HTTPS ingress. May scale to zero. |
| **Job** | One-shot execution, invoked explicitly, **with no request timeout**. |

Two services run from this image, and each needs its own ingress and its own
`PUBLIC_BASE_URL`:

| Command | Surface |
|---|---|
| `python -m cfokit.ledger.api` | REST, with the OpenAPI document |
| `python -m cfokit.ledger.mcp` | MCP over streamable HTTP at `/mcp`, stateless |

Both validate bearer tokens against the same `AUTH_ISSUER_URL` and `AUTH_AUDIENCE`, so a
deployment configures one issuer and both surfaces accept its tokens (ADR-0019). The MCP
service publishes OAuth protected-resource metadata at
`/.well-known/oauth-protected-resource`, derived from its own `PUBLIC_BASE_URL` — an MCP
client reads it from the `WWW-Authenticate` challenge on an unauthenticated request to find
the issuer. Point `PUBLIC_BASE_URL` at the wrong host and clients are sent to the wrong place,
which is why it is never derived from a request header.

All entrypoints run from the **same image**, differing only in command — this is what prevents a
component running against an API version it was not built for. Scheduling a job is the target's
concern, not the application's: the component only knows how to run once. Locally there is no
scheduler, so periodic work is run on demand.

There are no long-running worker processes, because there is no queue (ADR-0012).

### 6. A compute path without a request timeout

`rebook` holds an entity lock and can run for minutes on a large ledger. It must not run on
the request path. On the maintained target it is a Cloud Run job. (ADR-0011, ADR-0017)

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
enable OpenTofu state encryption. (ADR-0016)

## Health endpoints

| Endpoint | Meaning |
|---|---|
| `/healthz` | Liveness only. Does not touch the database. |
| `/readyz` | Database reachable **and** migrations current. |

**Both services serve both endpoints**, so each is probed independently — one surface can be
ready while the other is not, and a deployment that probed only the REST service would not know.
Neither endpoint requires a token: a platform probe holds no credential, and a readiness check
that could fail for want of one would report the wrong thing.

Point your platform's liveness probe at `/healthz` and its readiness probe at `/readyz`.
Getting these the wrong way round will restart a healthy container during a migration.

## Tooling

**OpenTofu, not Terraform** — `tofu`, not `terraform`. Terraform 1.6+ ships under BUSL,
which is source-available rather than open source, and shipping infrastructure code our users
cannot freely use would contradict the anti-lock-in promise that motivates the self-host
tier. (ADR-0016)

## Maintained targets

**GCP — Cloud Run plus Cloud SQL for PostgreSQL.** The first and only maintained cloud
target. (ADR-0017)

Configuration is not yet written; it arrives with the first managed deployment and will live
in `infra/gcp/`. There is no placeholder directory, deliberately: module sets nobody runs and
CI never exercises rot silently, and the first user to try an unmaintained module concludes
the project is abandoned. That is worse than shipping nothing for a cloud. (ADR-0016)

**We do not maintain AWS or Azure configurations, including placeholder directories.** Users
on another cloud write their own infrastructure code against the contract above — that is why
the contract is written down. Additional targets are added when someone actually needs one and
are expected to be contributed. (ADR-0016, ADR-0017)

## Local deployment

`compose.yaml` at the repository root is a production-shaped local deployment needing no
cloud account. It is not a demo — it holds real books. `compose.dev.yaml` is applied
explicitly and never automatically. (ADR-0018)

```
docker compose up          # local production
uv run task dev            # with the development overlay
```

Data lives in a named volume. **`docker compose down -v` destroys it.**

Never provision a laptop with OpenTofu. (ADR-0018)
