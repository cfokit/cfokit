# CFOKit — Working Agreement

Loaded into every session. Package-specific rules live in `packages/*/CLAUDE.md` and
load when you work in those directories.

Rules are binding. Each cites the ADR holding its reasoning — read it before proposing
a change. Index: `docs/decisions/README.md`. If a task appears to require breaking a rule,
stop and ask rather than working around it.

## Repository map

Directories are organised by **artifact kind**, and packages are named for
**capabilities, not vendors**. (ADR-0021)

| Path | What it is | Boundary |
|---|---|---|
| `packages/ledger/` | The double-entry primitive, kept deliberately tiny | Accounts, postings, draft/posted, reversal, close. Knows nothing about customers, invoices, banks, email, or agents. |
| `packages/<module>/` | In-process modules — siblings of the ledger, same deployable | Depend on the ledger; never on each other; the ledger never depends on them. |
| `packages/connectors/` | Transaction feed ingestion. **Name is known-wrong and will be renamed** (ADR-0024) | Classification as module or component is not yet settled. |
| `skills/` | Shipped Agent Skills, as `SKILL.md` bundles | Talk to the ledger over HTTP only. Never import ledger code. |
| `infra/` | OpenTofu for the one maintained cloud target, plus the deployment contract | Supplies env vars only. No app coupling. |
| `docs/product/` | Vision and numbered requirements | The source for positioning; the README derives from it. |
| `docs/decisions/` | Decision records, MADR 4.0.0. Immutable once accepted. | Not auto-loaded. Read on demand. |
| `.claude/` | Tooling for developing *this repo* | Never shipped. Distinct from `skills/`. |

`packages/` holds Python distributions **only** — its members are globbed into the `uv`
workspace, so nothing non-installable goes there. A skill is not a distribution.

**The ledger stays tiny.** It owns the double-entry primitive and nothing else. If the ledger needs
to know what a customer is, the boundary has moved wrongly. There is no `core` module — the ledger
*is* the kernel, and modules are its siblings rather than its children. (ADR-0024)

**Everything else is exactly one of two things**, decided by the criteria in ADR-0024 § 3:
an **in-process module** (must commit atomically with a ledger write) or a **separate component**
(own runtime shape, isolated credentials, or something a third party could build against the API).
In-process is the default; separation must be earned.

**Name things for the capability they provide** — not for a vendor, and not for the mechanism.
`plaid-sync` named a vendor; `connectors` names a mechanism. Both are wrong.

**The hard boundary:** the skills and the ledger are separate systems with separate
dependency graphs that share a tool contract. Never add a code dependency between
them, in either direction, for any reason. (ADR-0015)

This is enforced, not merely asserted: `import-linter` contracts in `pyproject.toml`
fail the build on a layer violation, and on any import from `cfokit.connectors` to
`cfokit.ledger`. If a contract blocks you, that is the rule working — stop and ask.

Shared code between packages requires an ADR. Default to duplication.

## Documentation

`docs/decisions/` holds decision records in [MADR 4.0.0](https://adr.github.io/madr/).
`CLAUDE.md` files hold the rules; the records hold the reasoning. Read the cited record
before proposing a change to a rule. (ADR-0001)

**`CLAUDE.md` plus the decision records are the constitution.** A second rules document is a
second source of truth, and it diverges silently.

Requirements carry stable domain-prefixed ids in `docs/product/requirements.md`. Derivation runs vision →
requirements → decision records → these rules, and citation never runs against it. (ADR-0001)

There is no roadmap file and no specifications directory. Work sequencing lives in GitHub
Milestones and Projects. Whether CFOKit adopts a specification workflow is undecided and
needs its own record. (ADR-0001)

## Commands

```
uv sync                          # install, all packages
uv run task test                 # full suite
uv run task test <path>          # one package, e.g. packages/ledger
uv run task lint                 # ruff + mypy --strict + import-linter + async boundary
uv run task check-money          # CI gate 4: no floats touch money
uv run task migrate              # apply migrations (never runs on startup)
docker compose up                # local production stack, no cloud account needed
uv run task dev                  # compose.yaml + compose.dev.yaml
```

Run `lint` and the relevant tests before reporting work complete. Do not report
completion on a red suite.

## Stack — the non-obvious parts

Everything else is discoverable from `pyproject.toml`. These are the choices you would
otherwise get wrong, because absence isn't visible in a manifest:

- **No ORM.** Hand-written SQL in the repository module. Do not introduce SQLAlchemy,
  SQLModel, or a query builder. Auditability requirement. (ADR-0009)
- **`uv` only.** Not pip, not poetry.
- **The ledger is synchronous; the transport is not, and neither is anything outside it.** No
  `async def`, no `await`, no `asyncio`/`anyio`/`trio` import in the ledger's engine, repository,
  service, or REST `api` adapter. `cfokit.ledger.mcp` is exempt because the MCP SDK is async.
  **Modules and components choose their own execution model** — ingestion and delivery are
  I/O-bound and a component is a separate runtime anyway. The rule protects code holding a
  transaction and an advisory lock, and nothing else; it removes a footgun rather than supplying
  a concurrency guarantee, which comes from ADR-0006 and ADR-0012. `uv run task lint` fails on a
  violation inside the ledger. (ADR-0026)
- **REST is FastAPI with synchronous `def` handlers only.** The event loop lives in the
  server, not in our code. `async def` handlers are the normal way to write FastAPI and are
  forbidden here — the driver is blocking, so they would gain nothing and would make an
  `await` mid-transaction expressible. (ADR-0026)
- **Runtime dependencies are load-bearing and few.** Adding one is a decision, not a
  convenience. Ask before adding any. Currently **five**, all in `packages/ledger`, each with
  its reason and verified licence in a comment there: `psycopg[binary]` (driver), `fastapi`
  (REST + OpenAPI), `uvicorn` (ASGI server), `mcp` (tool surface), `pyjwt[crypto]` (audience
  validation). 54 packages resolved in total; the MCP SDK is most of it, accepted knowingly
  (ADR-0026).
- **Python 3.12+**, `ruff`, `mypy --strict`, `import-linter`.

## Money and correctness

Applies to any package that touches financial values.

- Use `decimal.Decimal` everywhere. Never `float`, including in tests and fixtures.
  All decimal columns are `NUMERIC(28,10)`. (ADR-0005)
- Financial records are append-only. No `UPDATE` on financial fields, no `DELETE`.
  Corrections are reversing entries. (ADR-0007)
- Postgres is the only storage backend. Do not add SQLite, DynamoDB, or any second
  store, including "just for local dev". (ADR-0003)

## Portability

Self-hosting is a product promise, not a convenience. (ADR-0004)

- Configuration is environment variables only. No cloud metadata lookups, no provider
  SDK imports at module scope.
- `PUBLIC_BASE_URL` is authoritative for anything a service says about itself. Never
  derive external URLs from request headers — behind a proxy or tunnel they lie.
- Provider-specific code sits behind a protocol with a local default requiring no
  cloud account.
- Migrations run as an explicit command, never on startup.

## Observability

Rules, not tooling. What you log matters more than where it goes.

- **Never log token values, posting amounts, account numbers, or payee names at info
  level.** Log identifiers and counts instead.
- Structured JSON logs. One request id per inbound call, propagated into `audit_log`.
- Every state-changing service call writes exactly one `audit_log` row. If a code path
  mutates state without one, that is a bug.
- Errors carry a stable machine-readable `code`. Callers depend on it. (ADR-0016)
- `/healthz` is liveness only. `/readyz` checks database reachability and that
  migrations are current.

## CI gates

These define "done". Do not write code that assumes an environment they forbid.

1. `lint` clean — ruff, `mypy --strict`, import-linter layer rules.
2. Full suite green against `compose.yaml` (without the dev overlay) **with no cloud credentials
   present**. (ADR-0004)
3. Differential test against the Beancount oracle passes, with every divergence
   matching a documented entry. (ADR-0011)
4. No float storage types anywhere in the schema. (ADR-0005)
5. Generated OpenAPI and MCP tool descriptions match what's committed — a diff means a
   contract change and needs review. (ADR-0016)

## Licensing

Scope the question by **what triggers the obligation**, not by the licence name.

- **Things we ship to a user's machine** — skills, plugins, apps: **no copyleft.** This is
  genuine distribution of our artifact, and it is the case the rule exists for.
- **Anything AGPL or network-copyleft in the server stack: excluded.** AGPL triggers on
  network interaction rather than distribution, so it reaches a hosted service.
  (ADR-0020)
- **Ordinary server-side runtime dependencies: licence is not a constraint.** They are
  resolved from an index at install time; GPL and LGPL obligations trigger on
  distribution, and CFOKit is hosted or self-hosted under a licence we choose. LGPL
  dependencies are fine.
- **CI-only tooling: fine**, including copyleft. (ADR-0011)
- Check the licence before adding any dependency, and verify it currently rather than
  from memory — but weigh it against the scope above rather than reflexively.
- OpenTofu, not Terraform — Terraform 1.6+ is BUSL. (ADR-0017)

## Authentication

- The issuer is a swappable dependency. **No issuer-specific code anywhere.** The app
  reads `AUTH_ISSUER_URL` and `AUTH_AUDIENCE` and nothing else. (ADR-0020)
- Do not write an OAuth server, a token minter, or a login flow. Delegate to the issuer.
- Audience validation is mandatory on every request. Entity grants are validated
  server-side regardless of token contents. (ADR-0012, ADR-0020)
- Changes here need human review before you proceed.

## Infrastructure

- **OpenTofu**, not Terraform. `tofu`, not `terraform`. (ADR-0017)
- GCP is the only maintained cloud target. Do not add AWS or Azure configurations —
  including placeholder directories. (ADR-0017, ADR-0018)
- Local development and local production both run from `compose.yaml`; the dev overlay is
  applied explicitly. Never provision a laptop with OpenTofu. (ADR-0019)
- **IaC creates secret containers, never secret values.** State stores secrets in
  plaintext. Values are populated out of band. (ADR-0017)
- Adding anything to the environment surface in `infra/README.md` requires an ADR — that
  document is the portability contract. (ADR-0017)

## Scope discipline

Do not build, and do not propose without an ADR: a web UI or admin console, a plugin
system, a custom query language, a caching or rollup layer, read replicas, GraphQL,
websockets, SSE transport, or an event bus. (ADR-0013)

## Working style

- Write tests alongside the code, not after.
- Changes touching booking semantics, auth, or the write path need human review before
  you proceed.
- If you make a decision future work should be bound by, propose an ADR rather than
  burying it in a code comment.
