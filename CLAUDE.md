# CFOKit — Working Agreement

Loaded into every session. Capability-specific rules live in `src/cfokit/*/CLAUDE.md`, and the
web client's in `web/CLAUDE.md`; each loads when you work in that directory.

Rules are binding. Each cites the ADR holding its reasoning — read it before proposing
a change. Index: `docs/decisions/README.md`. If a task appears to require breaking a rule,
stop and ask rather than working around it.

## Repository map

Directories are organized by **artifact kind**, and packages are named for
**capabilities, not vendors**. (ADR-0020, ADR-0031)

| Path | What it is | Boundary |
|---|---|---|
| `src/cfokit/ledger/` | The double-entry primitive, kept deliberately tiny | Accounts, postings, draft/posted, reversal, close. Knows nothing about customers, invoices, banks, email, or agents. |
| `src/cfokit/<module>/` | In-process modules — siblings of the ledger, same deployable | Depend on the ledger; never on each other; the ledger never depends on them. |
| `skills/` | Shipped Agent Skills, as `SKILL.md` bundles — their own kind of artifact, carrying whatever code the agent's runtime runs | Talk to the ledger over HTTP only. Never import ledger code. |
| `web/` | The web client: a React single-page application in TypeScript, served at `/app/` (ADR-0049, ADR-0054) | Reads only `docs/contracts/openapi.json` from outside itself, and `docs/design/` to publish the design system; never imported from. The product's only Node tooling; a skill may carry its own. |
| `infra/` | OpenTofu for the one maintained cloud target, plus the deployment contract | Supplies env vars only. No app coupling. |
| `docs/product/` | Vision and numbered requirements | The source for positioning; the README derives from it. |
| `docs/design/` | The design system's prose: the brand book, the marks' notes, a guide per component (ADR-0049 § 10) | The source; the Design System artifact is published from it and `web/design/`, never edited in its page. |
| `docs/decisions/` | Decision records, MADR 4.0.0. Corrected in place when wrong; nothing is final. | Not auto-loaded. Read on demand. |
| `.claude/` | Tooling for developing *this repo* | Never shipped. Distinct from `skills/`. |

**One distribution, rooted at `src/cfokit/`.** Every capability is a sibling package inside
it, because ADR-0023 ships one image with many entrypoints — so nothing is ever versioned,
installed, or released separately, which is the whole of what a multi-distribution workspace
buys. Boundaries between capabilities are enforced by `import-linter` on module paths, which
works the same either way. `src/cfokit/` is a PEP 420 namespace package: **do not add
`src/cfokit/__init__.py`**. A skill is not a package and never goes here (ADR-0014, ADR-0020).

**Five capabilities exist**: `ledger`, `imports` (ADR-0040), `receivables`, `assignment`
(ADR-0045), and `activity` (ADR-0046). `server` is not one — it is the composition point, the
only place that knows the module list, and a file in it that decides something about
accounting is in the wrong place.

There was a `connectors` package holding no code; it was removed rather than renamed, because
a package that exists before its capability is known is a boundary drawn around a guess
(ADR-0012, ADR-0022 § 5, ADR-0031). **Create a package when the capability it provides is
known and there is code to put in it** — which is why there is none for payables. Getting
transactions in is `activity`, named for the account activity it receives rather than for the
statement upload that is its first producer.

**The ledger stays tiny.** It owns the double-entry primitive and nothing else. If the ledger needs
to know what a customer is, the boundary has moved wrongly. There is no `core` module — the ledger
*is* the kernel, and modules are its siblings rather than its children. (ADR-0022)

**Everything else is exactly one of two things**, decided by the criteria in ADR-0022 § 3:
an **in-process module** (must commit atomically with a ledger write) or a **separate component**
(own runtime shape, isolated credentials, or something a third party could build against the API).
In-process is the default; separation must be earned.

**Name things for the capability they provide** — not for a vendor, and not for the mechanism.
`plaid-sync` named a vendor; `connectors` names a mechanism. Both are wrong. So is naming a
capability after one of its mechanisms: getting transactions in has three — an uploaded
statement, a fetched one, and an unattended feed — and `upload`, `fetch` and `sync` are each
the name of one of them.

**`migration` means a change to the database schema, and nothing else.** Moving a company's books
between accounting systems is import and export (`IMP-`, `EXP-`). One word held both senses once;
keeping them apart costs a line here, and separating them again cost a corpus-wide rename.

**`import` means landing a company's existing books from the system it already runs (`IMP-`),
and nothing else.** Transactions arriving from a bank feed, an uploaded statement or a
downloaded one are account activity (`BKP-`), and calling that an import is how the line
above came to be needed. Written now, while the word still holds one sense.

**The hard boundary:** the skills and the ledger are separate systems with separate
dependency graphs that share a tool contract. Never add a code dependency between
them, in either direction, for any reason. (ADR-0014)

This one is structural rather than gated: a skill is not Python, so there is no import path
to cross in either direction and nothing for a linter to check. What `import-linter` does
enforce, in `pyproject.toml` and failing `uv run task lint`, is the ledger's internal layering
and the purity of its engine. If a contract blocks you, that is the rule working — stop and ask.

Shared code between packages requires an ADR. Default to duplication.

## Documentation

`docs/decisions/` holds decision records in [MADR 4.0.0](https://adr.github.io/madr/).
`CLAUDE.md` files hold the rules; the records hold the reasoning. Read the cited record
before proposing a change to a rule. (ADR-0001)

**`CLAUDE.md` plus the decision records are the constitution.** A second rules document is a
second source of truth, and it diverges silently.

Requirements carry stable domain-prefixed ids in `docs/product/requirements.md`. Derivation runs vision →
requirements → decision records → these rules, and citation never runs against it. (ADR-0001)

There is no roadmap file and no specifications directory. **Where work sequencing lives is
undecided** — no milestones, projects or issues exist, and none is assumed. Whether CFOKit
adopts a specification workflow is undecided and needs its own record. (ADR-0001)

## Commands

```
uv sync                          # install everything
uv run task test                 # the tests needing no infrastructure; integration skips
uv run task test <path>          # scope it, e.g. tests/test_migrations.py
uv run task lint                 # ruff + mypy --strict + import-linter + async boundary
uv run task check-money          # CI gate 4: no floats touch money
uv run task check-decisions      # CI gate 6: decision corpus is well-formed
uv run task migrate              # apply migrations (never runs on startup)
docker compose up                # local production stack, no cloud account needed
uv run task dev                  # compose.yaml + compose.dev.yaml
docker compose --profile test run --rm test   # the whole suite, the way CI gate 2 runs it
docker compose --profile test build <service>  # after any source change, or the above runs a cache
```

The web client has its own commands, run from `web/`; `web/CLAUDE.md` lists them.

**Rebuild before you run.** Every service copies the source into an image rather than mounting
it, so `test` runs the previous copy after an edit and `migrate` reports "no migrations to apply"
for a migration that is on disk. Both have cost real debugging time.

**Cloud sessions are provisioned by `.claude/hooks/session-start.sh`** — CI's uv, Python 3.14,
`uv sync --locked`, and a running Docker daemon. The commands above are unchanged there.

**`uv run task test` is not the whole suite.** Every test of row-level security, the entity lock
and the write path needs a database and an issuer, and skips without them — which is most of the
tests. Row-level security is only in force for a non-superuser that does not own the tables, so
the suite runs *inside* the compose network as `cfokit_app` rather than against it from the host;
Postgres publishes no port, deliberately (ADR-0003, ADR-0018).

Run `lint` and the relevant tests before reporting work complete. A green `task test` alone is not
that. Do not report completion on a red suite.

## Stack — the non-obvious parts

Everything else is discoverable from `pyproject.toml`. These are the choices you would
otherwise get wrong, because absence isn't visible in a manifest:

- **No ORM.** Hand-written SQL in the repository module. Do not introduce SQLAlchemy,
  SQLModel, or a query builder. Auditability requirement. (ADR-0028)
- **`uv` only.** Not pip, not poetry.
- **The ledger is synchronous; the transport is not, and neither is anything outside it.** No
  `async def`, no `await`, no `asyncio`/`anyio`/`trio` import in the ledger's engine, repository,
  service, or REST `api` adapter. `cfokit.ledger.mcp` is exempt because the MCP SDK is async.
  **Modules and components choose their own execution model** — ingestion and delivery are
  I/O-bound and a component is a separate runtime anyway. The rule protects code holding a
  transaction and an advisory lock, and nothing else; it removes a footgun rather than supplying
  a concurrency guarantee, which comes from ADR-0006, ADR-0011 and ADR-0029. `uv run task lint` fails on a
  violation inside the ledger. (ADR-0024)
- **REST is FastAPI with synchronous `def` handlers only.** The event loop lives in the
  server, not in our code. `async def` handlers are the normal way to write FastAPI and are
  forbidden here. Not because the driver blocks — psycopg 3 is dual-mode and an `async def`
  handler would genuinely await the database, so that option is faster in principle. It is
  forbidden because it makes an `await` inside a transaction expressible, and the workload has
  almost no concurrency to reclaim in exchange. (ADR-0024)
- **Runtime dependencies are load-bearing and few.** Adding one is a decision, not a
  convenience. Ask before adding any. Currently **six**, in the root `pyproject.toml`, each
  with its reason and verified license in a comment there: `psycopg[binary]` (driver), `fastapi`
  (REST + OpenAPI), `uvicorn` (ASGI server), `mcp` (tool surface), `pyjwt[crypto]` (audience
  validation), `cryptography` (Web Push encryption, ADR-0057; already installed as PyJWT's
  extra, declared because we call into it). Those six pull **36** packages in total — `uv export
  --no-dev --no-emit-project --no-hashes | grep -c '^[a-z]'` — and the MCP SDK is most of it,
  accepted knowingly (ADR-0024). Accounting exports are parsed in the person's browser, never
  by the server, so no spreadsheet library is a dependency of any kind (ADR-0041, ADR-0058).
- **Python 3.14**, `ruff`, `mypy --strict`, `import-linter`, and the image and CI run it.

## Money and correctness

Applies to any package that touches financial values.

- Use `decimal.Decimal` everywhere. Never `float`, including in tests and fixtures.
  All decimal columns are `NUMERIC(28,10)`. (ADR-0005)
- Financial records are append-only. No `UPDATE` on financial fields, no `DELETE`.
  Corrections are reversing entries. (ADR-0007)
- Postgres is the only storage backend. Do not add SQLite, DynamoDB, or any second
  store, including "just for local dev". (ADR-0003)
- **Rounding happens once, at presentation.** Never to an intermediate, never stored back. A
  rounding call in `engine`, `repository`, or `service` means the boundary has been misplaced.
  Allocation lives in the pure engine and is property-tested. (ADR-0025)
- **The ledger is intrinsically accrual, and accounting basis is a presentation property.** Every
  obligation and every settlement is a posting whatever basis the entity declared; the cash view
  is derived from the stored link between them. **No posting path branches on the declared
  basis.** (ADR-0037)

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
- Errors carry a stable machine-readable `code`. Callers depend on it. (ADR-0015)
- `/healthz` is liveness only. `/readyz` checks database reachability and that
  migrations are current.

## CI gates

These define "done". Do not write code that assumes an environment they forbid.

1. `lint` clean — ruff, `mypy --strict`, import-linter layer rules.
2. Full suite green against `compose.yaml` (without the dev overlay) **with no cloud credentials
   present**. (ADR-0004)
3. **Deferred, not running.** The Beancount differential oracle activates with `LED-18`; until
   then correctness rests on the layers below. (ADR-0010, ADR-0036)
4. No float storage types anywhere in the schema. (ADR-0005)
5. Generated OpenAPI and MCP tool descriptions match what's committed — a diff means a
   contract change and needs review. (ADR-0015)
6. `check-decisions` clean — every record carries a valid `status` and `kind`, cites only live
   requirement ids, follows the MADR template, and matches the index. Requirements and the vision
   cite no record. (ADR-0001)

## Testing

Four layers, and only the top one needs a model. (ADR-0036)

1. Unit and property tests over the engine and service — no protocol, no model, no database.
2. A conformance corpus of published worked examples. **This is where independence comes from**,
   and every case cites its source. A case with no citation is a unit test that has been misfiled.
3. Protocol integration against REST and MCP as a client would, deterministic.
4. Evals, which assert on records — the transaction and its status, the postings, the audit row —
   never on prose.

Layers 1 to 3 gate every commit; layer 4 does not. **An assertion's expected value comes from
outside the implementation** — a published worked example, a requirement's stated acceptance, a
domain invariant, or a second enforcement point. Never write one by running the code and recording
what it returned: that pins current behavior including its defects, which is the blind spot layer 2
exists to close. Authorship is not the control here and cannot be, because every commit is
generated; provenance is, which is why a layer 2 case without a citation is refused.

## Licensing

Scope the question by **what triggers the obligation**, not by the license name.

- **Things we ship to a user's machine** — skills, plugins, apps: **no copyleft.** This is
  genuine distribution of our artifact, and it is the case the rule exists for.
- **Anything AGPL or network-copyleft in the server stack: excluded.** AGPL triggers on
  network interaction rather than distribution, so it reaches a hosted service.
  (ADR-0019)
- **Ordinary server-side runtime dependencies: license is not a constraint.** They are
  resolved from an index at install time; GPL and LGPL obligations trigger on
  distribution, and CFOKit is hosted or self-hosted under a license we choose. LGPL
  dependencies are fine.
- **CI-only tooling: fine**, including copyleft. (ADR-0010)
- Check the license before adding any dependency, and verify it currently rather than
  from memory — but weigh it against the scope above rather than reflexively.
- OpenTofu, not Terraform — Terraform 1.6+ is BUSL. (ADR-0016)

## Authentication

- The issuer is a swappable dependency. **No issuer-specific code anywhere.** The app
  reads `AUTH_ISSUER_URL` and `AUTH_AUDIENCE` and nothing else. (ADR-0019)
- Do not write an OAuth server, a token minter, or a login flow. Delegate to the issuer.
- Audience validation is mandatory on every request carrying an issuer token. Entity grants are
  validated server-side regardless of token contents. (ADR-0011, ADR-0019)
- **Without an issuer token, an entity's data is reached in two ways only:** a link of the kind
  `IAM-20` defines — one artifact, unguessable, revocable — such as an issued invoice's (ADR-0053),
  and the relay's signed event webhook, which writes delivery events and reads nothing across
  entities (ADR-0052). Every other route without the issuer serves no entity data, as `/healthz`,
  `/readyz` and the protected-resource metadata do. A new way in needs its own record.
- Changes here need human review before you proceed.

## Infrastructure

- **OpenTofu**, not Terraform. `tofu`, not `terraform`. (ADR-0016)
- GCP is the only maintained cloud target. Do not add AWS or Azure configurations —
  including placeholder directories. (ADR-0016, ADR-0017)
- Local development and local production both run from `compose.yaml`; the dev overlay is
  applied explicitly. Never provision a laptop with OpenTofu. (ADR-0018)
- **IaC creates secret containers, never secret values.** State stores secrets in
  plaintext. Values are populated out of band. (ADR-0016)
- Changing the **shape** of the environment contract requires an ADR — env-vars-only, secrets as
  containers populated out of band, nothing from cloud metadata. Adding a variable within that
  shape does not; `infra/README.md` is authoritative for the names. (ADR-0016)

## Scope discipline

Do not build, and do not propose without an ADR: an admin console, a plugin system, a custom query language, a caching or rollup layer, read replicas, GraphQL,
websockets, SSE transport, or an event bus. (ADR-0012) The web client has passed this gate
(ADR-0049); it is not a license for an admin console.

## Working style

- Write tests alongside the code, not after.
- Changes touching booking semantics, auth, or the write path need human review before
  you proceed.
- If you make a decision future work should be bound by, propose an ADR rather than
  burying it in a code comment.
- **Merge by labeling, not by `gh pr merge`.** Add the `merge` label and stop. That label
  runs the reviewer, which approves and auto-merges only what `scripts/review_policy.py`
  allows, and marks everything else `needs-human`. Paths in `.github/CODEOWNERS` always need
  a person. Use `--admin` only when the user tells you to merge a pull request the reviewer
  escalated. (ADR-0048)
