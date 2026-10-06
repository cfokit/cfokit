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
| `TLS_CERT_FILE` | no | Serve HTTPS from this certificate. Set with `TLS_KEY_FILE`, where nothing in front of the service terminates TLS, as in the local stack; leave both unset behind an ingress that does. |
| `TLS_KEY_FILE` | no | The private key for `TLS_CERT_FILE`. Both are set, or neither. |
| `MCP_PUBLIC_BASE_URL` | no | REST service only: the MCP service's `PUBLIC_BASE_URL`, which the web client shows a person connecting their agent. Unset, it says it does not know. |

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

`infra/postgres/init-app-role.sh` does this for the compose stack, on first initialization of
an empty data directory.

Verified rather than assumed: `tests/integration/test_entity_isolation.py` asserts the
property from the outside, as the application role, and CI gate 2 runs it inside the compose
network on every pull request.

### 3. An OAuth 2.1 issuer meeting the conformance contract

The issuer is a **swappable dependency**, not a chosen product. The default in the compose
stack is Keycloak (Apache 2.0); it is a default, not a coupling. No issuer-specific code exists
anywhere in the codebase. (ADR-0019)

It is a *complete* identity provider — user store, login pages, admin console — because `IAM-10`
delegates authentication: CFOKit issues no credentials and does not store or verify passwords,
and `IAM-06` requires a running deployment to be usable as it stands. An issuer that issues tokens but holds no
identities leaves a self-hoster to supply exactly the half we may not write.

Any conforming issuer must provide:

- OIDC Discovery **or** OAuth 2.0 Authorization Server Metadata
- A JWKS endpoint with key rotation
- **JWT access tokens.** Signatures are validated locally against cached JWKS and the audience
  and subject are read from the claims. An opaque token carries neither and would need an
  introspection call per request — which is an issuer-specific API, so a deployment doing that
  has coupled itself to one issuer, which is the thing this contract exists to prevent.
- **RFC 8707 Resource Indicators** — the `resource` parameter must bind the token audience
- **RFC 9207** issuer identifier in the authorization response
- Declared, configurable claim names for subject and scopes
- RFC 7591 Dynamic Client Registration **or** Client ID Metadata Documents
- The **client credentials grant**, for separate components authenticating as machine callers
  (ADR-0032 — an extension to the contract originally set in ADR-0019)

**A deployment operated as a service requires a second factor of every person** (`SOC2-19`), and
that is the issuer's configuration rather than the application's, so it is not in the table
above. The default issuer requires one when `CFOKIT_REQUIRE_SECOND_FACTOR` is `true`, read when
the realm is imported; unset, a second factor is the person's choice. `infra/keycloak/README.md`
says what each setting does.

**One identity, and one port, from every side.** A client is handed the issuer's address in the
ledger's protected-resource metadata and goes to it directly, so a port mapped to a different
number outside the network makes that address wrong for exactly one side — and on a network
where the mapped-from port belongs to another service, the wrong service answers rather than
nothing answering. The issuer listens on the port it advertises, and publishes the same one.

**One identity, from every side.** Whatever an issuer calls itself is what it must be called by
everyone — the application validates a token's `iss` against `AUTH_ISSUER_URL`, so an issuer
advertising one hostname while services reach it at another rejects every token it issues. In
the compose stack that name is `keycloak.localhost:8443`, chosen because `*.localhost` resolves to
loopback without a hosts entry (RFC 6761) and a network alias makes the same name reach the
container from inside. A deployment reachable by more than one machine uses a public hostname.

### What the suite measures

`tests/integration/test_issuer_conformance.py` drives the configured issuer and asserts each
line above. It runs in CI gate 2, against whatever issuer the stack is pointed at, and it knows
nothing about which one that is — every request goes to an endpoint the issuer advertises.

The default meets every line as it ships. One preference it does not meet, recorded as a strict
expected failure so the marker comes off when it closes: **no issuer implements RFC 8707**.
Keycloak ignores the `resource` parameter and returns its own configured audience, Ory Hydra
returns none, and Microsoft Entra ID rejects the parameter outright. RFC 6749 obliges a server
to ignore parameters it does not recognize, so this is conformant behavior rather than a
defect, and ADR-0019 § 2 makes the contract line audience binding rather than any one mechanism
for it.

The audience is therefore bound by realm configuration, which ships in
`infra/keycloak/cfokit-realm.json`. Its omission is an authentication failure rather than a
visible error, which is why it ships rather than being a setup instruction.

**No AGPL or other network-copyleft component ships in the default stack.** (ADR-0019)

### 4. HTTPS ingress

Terminating TLS and forwarding to the container port. Cross-device access requires a tunnel
and `PUBLIC_BASE_URL` set to the public hostname.

**The issuer is always HTTPS, including on a laptop.** OAuth clients refuse to send credentials
to a plain-HTTP token endpoint unless its host is literally `localhost`, `127.0.0.1` or `::1`.
The services themselves may be reached over `http://localhost` on the same machine.

On a deployment the ingress's certificate does this and nothing is configured. The compose stack
has no ingress, so its `tls` step generates a local CA and the issuer's certificate into
`.local/tls/` (git-ignored), and every process that talks to the issuer trusts that CA through
`SSL_CERT_FILE` — a standard OpenSSL variable, not part of the configuration surface above, and
set nowhere but `compose.yaml`.

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
| `python -m cfokit.server rest` | REST, with the OpenAPI document |
| `python -m cfokit.server mcp` | MCP over streamable HTTP at `/mcp`, stateless |

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

The configuration is in [`infra/gcp/`](gcp/README.md): one project, one load balancer for the
API and web client, MCP and the issuer, and a deploy on every merge to `main` (ADR-0055,
ADR-0060). Its README holds the first-time steps.

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
