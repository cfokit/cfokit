# CFOKit — Phase 1 Product Requirements Document

**Product:** CFOKit — The Open Source CFO Toolkit
**Phase:** 1 — GCP Deployment + Core Adapter Pattern
**Target Audience:** Solo founders (S-corps/LLCs), small business owners, fractional CFOs, tech-savvy consultants
**Date:** 2026-02-14

CFOKit is an open-source AI CFO toolkit. Phase 1 delivers the bookkeeper agent, the platform-agnostic core, GCP cloud deployment, and the adapter pattern that enables future cloud providers. Tax preparer, compliance monitor, and cashflow analyst agents are deferred to Phase 2. OpenClaw integration is deferred to Phase 2 — Phase 1 creates placeholder directories only.

---

## Success Criteria

Phase 1 is **done** when:

- All core business logic (`core/`) is implemented and platform-agnostic
- Adapter protocol interfaces are defined and have in-memory reference implementations
- GCP adapters (Firestore, Secret Manager, Pub/Sub, Cloud Scheduler) pass conformance tests
- FastAPI application deploys to GCP Cloud Run via one-click `deploy.sh`
- Scheduled jobs (daily summary, weekly review, monthly close) run on Cloud Run Jobs
- CI pipeline passes: lint, security scanning, unit tests (85%+ coverage), integration tests, GCP cloud tests
- Combined test coverage meets 80% floor
- Bookkeeper agent is defined and functional; tax preparer, compliance monitor, and cashflow analyst agents deferred to Phase 2
- Bookkeeper-relevant skills authored (categorization-focused S-corp reasonable compensation, depreciation, meal deductions, sales tax)
- Slack webhook integration works end-to-end with signature verification
- `deploy-openclaw/` exists as a placeholder directory structure

---

## Sub-phases

### MVP (Weeks 1-4) — Foundation

Build the repository scaffolding, core data models, adapter protocols with in-memory implementations, CFO skills, and shared utilities. At exit, `uv run pytest tests/unit/ -x` passes with 85%+ coverage and the full adapter conformance suite runs against in-memory implementations.

**Exit criteria:**
- Repository structure matches architecture spec
- CI pipeline runs lint + security + unit tests on every push
- 2 Pydantic models (Transaction, Client) pass validation tests with factory-generated data
- All 4 adapter protocols have in-memory implementations passing 15+ conformance tests each
- Bookkeeper-relevant skill markdown files exist and pass structure/content regression tests
- Bookkeeper agent YAML definition exists
- Shared utilities (claude_client, skill_loader, mcp_manager, slack_client) are implemented with tests

### Beta (Weeks 5-8) — Handlers + GCP

Implement request handlers, GCP adapter implementations, and the FastAPI application with security middleware. At exit, the application runs locally with GCP emulators and handles Slack webhook requests.

**Exit criteria:**
- All 4 request handlers (categorize, report, setup, help) pass unit tests with mock adapters
- All 4 GCP adapters pass conformance tests against emulators
- FastAPI app starts, routes requests to handlers, and returns responses
- Slack signature verification rejects unsigned/forged/replayed requests
- Rate limiting returns 429 on threshold breach
- Health endpoint responds without leaking internal details
- Integration tests pass with TestClient

### GA (Weeks 9-12) — Deploy + Harden

GCP infrastructure via Terraform, scheduled jobs, documentation, and CI hardening. At exit, `deploy-cloud/gcp/deploy.sh` provisions infrastructure and deploys a working service.

**Exit criteria:**
- Terraform provisions all GCP resources (Cloud Run, Firestore, Pub/Sub, Cloud Scheduler, Secret Manager)
- `deploy.sh` performs end-to-end deployment
- All 3 scheduled jobs (daily summary, weekly review, monthly close) run on Cloud Run Jobs
- E2E smoke tests pass against staging
- Documentation covers getting started, deployment, architecture, adapter development, and skill development
- CI includes cloud adapter tests (GCP emulator), coverage gating, and security scanning
- `deploy-openclaw/` placeholder directories and READMEs exist

---

## Epics

### Epic 1: Repository Scaffolding & CI Foundation

> Set up the project structure, tooling configuration, and CI pipeline that all subsequent work depends on.

**Sub-phase:** MVP
**Dependencies:** None

#### Story 1.1: Initialize repository with uv and pyproject.toml

Create the Python project with `uv init`, configure `pyproject.toml` with project metadata, Python 3.11+ requirement, and dependency groups (runtime + dev).

**Acceptance criteria:**
- `pyproject.toml` exists with project name `cfokit`, Python `>=3.11`, and all dev dependencies (pytest, pytest-asyncio, pytest-cov, pytest-xdist, pytest-timeout, hypothesis, ruff, mypy, bandit, pip-audit, detect-secrets)
- `uv sync` succeeds and creates `uv.lock`
- `.python-version` specifies 3.11+
- `pyproject.toml` includes `[tool.pytest.ini_options]` with `asyncio_mode = "auto"`, `timeout = 30`, `strict_markers = true`, `filterwarnings = ["error"]`, and cloud marker definitions
- `pyproject.toml` includes `[tool.coverage.run]` and `[tool.coverage.report]` with `fail_under = 80`

**Key files:** `pyproject.toml`, `uv.lock`, `.python-version`
**Labels:** `epic:scaffolding`, `sub-phase:mvp`
**parallel-group:** `1.init`
**blocks:** `[1.2, 1.3, 1.4, 1.5]`

---

#### Story 1.2: Create directory structure with __init__.py files

Create all directories and `__init__.py` files for the three-layer architecture: `core/` (skills, agents, integrations, models, adapters, shared), `deploy-cloud/` (shared/handlers, gcp, aws, azure), `deploy-openclaw/`, `tests/`, `docs/`, `examples/`, `scripts/`.

**Acceptance criteria:**
- All directories from the architecture spec exist
- Every Python package directory has an `__init__.py`
- `deploy-openclaw/` contains placeholder subdirectories: `agents/`, `skills/`, `workflows/`
- `deploy-openclaw/README.md` exists with "Coming in Phase 2" placeholder content
- `core/integrations/` contains placeholder subdirectories: `quickbooks_mcp/`, `wave_mcp/`, `stripe_mcp/`, and `README.md`
- `tests/` directory has `unit/`, `integration/`, `cloud/`, `e2e/`, `adapters/`, `fixtures/` subdirectories

**Key files:** All `__init__.py` files, `deploy-openclaw/README.md`, `core/integrations/README.md`
**Labels:** `epic:scaffolding`, `sub-phase:mvp`
**parallel-group:** `1.init-seq`
**blocks:** `[2.1, 3.1, 4.1]`

---

#### Story 1.3: Configure linting and type checking

Set up ruff (linter + formatter) and mypy configuration in `pyproject.toml`. Add `.gitignore` for Python projects.

**Acceptance criteria:**
- `pyproject.toml` includes `[tool.ruff]` and `[tool.ruff.lint]` configuration
- `pyproject.toml` includes `[tool.mypy]` configuration targeting `core/` and `deploy-cloud/shared/`
- `uv run ruff check .` and `uv run ruff format --check .` pass on empty project
- `uv run mypy core/ deploy-cloud/shared/` passes on empty project
- `.gitignore` covers Python artifacts, `.env`, IDE files, cloud credential files

**Key files:** `pyproject.toml` (ruff/mypy sections), `.gitignore`
**Labels:** `epic:scaffolding`, `sub-phase:mvp`
**parallel-group:** `1.init-seq`
**blocks:** `[]`

---

#### Story 1.4: Set up CI pipeline with GitHub Actions

Create the CI workflow with jobs for lint, security scanning, unit tests, integration tests, and GCP cloud adapter tests. All GitHub Actions pinned to commit SHAs, all Docker service images pinned to digest hashes.

**Acceptance criteria:**
- `.github/workflows/test.yml` exists with jobs: `lint`, `security`, `unit`, `integration`, `cloud-gcp`, `coverage`
- `lint` job runs ruff check, ruff format --check, and mypy
- `security` job runs bandit, pip-audit, and detect-secrets
- `unit` job runs pytest with `--cov-fail-under=85`
- `cloud-gcp` job uses Firestore emulator service container
- `coverage` job enforces 80% combined floor
- All `uses:` actions reference commit SHAs, not tags
- `.secrets.baseline` file exists for detect-secrets

**Key files:** `.github/workflows/test.yml`, `.secrets.baseline`
**Labels:** `epic:scaffolding`, `sub-phase:mvp`
**parallel-group:** `1.init-seq`
**blocks:** `[]`

---

#### Story 1.5: Create project root files

Add standard open-source project files: LICENSE (MIT), README.md (abbreviated — full version in Epic 11), CONTRIBUTING.md, CODE_OF_CONDUCT.md, SECURITY.md, CHANGELOG.md, ROADMAP.md, `.env.example`.

**Acceptance criteria:**
- `LICENSE` contains MIT license text
- `README.md` has project name, tagline, brief description, and "under construction" note
- `CONTRIBUTING.md` has contribution guidelines referencing the adapter pattern and skill development
- `.env.example` lists all required and optional environment variables with placeholder values
- No file contains actual secrets or API keys

**Key files:** `LICENSE`, `README.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `CHANGELOG.md`, `ROADMAP.md`, `.env.example`
**Labels:** `epic:scaffolding`, `sub-phase:mvp`
**parallel-group:** `1.init-seq`
**blocks:** `[]`

---

### Epic 2: Core Data Models

> Define Pydantic data models for the domain entities that handlers, adapters, and agents operate on.

**Sub-phase:** MVP
**Dependencies:** Epic 1

#### Story 2.1: Implement Transaction model

Create the `Transaction` Pydantic model with fields for id, amount, vendor, date, category, description, tenant_id, and metadata. Include custom validators for amount (positive or zero), date format, and vendor string constraints.

**Acceptance criteria:**
- `core/models/transaction.py` defines `Transaction` as a Pydantic `BaseModel`
- Custom validators reject negative amounts (except refunds with explicit flag), empty vendor strings, and future dates beyond reasonable range
- Model serializes to/from dict for storage adapter compatibility
- Unit tests cover custom validators only (not Pydantic builtins)

**Key files:** `core/models/transaction.py`, `tests/unit/test_models/test_transaction.py`
**Labels:** `epic:models`, `sub-phase:mvp`
**parallel-group:** `2.models`
**blocks:** `[2.3]`

---

#### Story 2.2: Implement Client model

Create the `Client` Pydantic model with fields for id, name, entity_type (enum: s-corp, llc, 501c3, 501c6), state, fiscal_year_start, slack_channel_id, quickbooks_company_id, and configuration dict.

**Acceptance criteria:**
- `core/models/client.py` defines `Client` with an `EntityType` enum
- Entity type constrains which skills are loaded for the client
- `fiscal_year_start` validates as a date
- `slack_channel_id` and `quickbooks_company_id` are optional with validation
- Unit tests cover entity type enum validation and fiscal year constraints

**Key files:** `core/models/client.py`, `tests/unit/test_models/test_client.py`
**Labels:** `epic:models`, `sub-phase:mvp`
**parallel-group:** `2.models`
**blocks:** `[2.3]`

---

#### Story 2.3: Create test data factories

Implement `tests/factories.py` with `TransactionFactory` and `ClientFactory`. Each factory uses the `Factory.create(**overrides)` pattern with sensible defaults. Include `create_batch(n)` methods and adversarial data variants (`create_adversarial()`).

**Acceptance criteria:**
- `tests/factories.py` contains `TransactionFactory` and `ClientFactory`
- `Factory.create()` returns valid Pydantic model instances
- `Factory.create(**overrides)` applies keyword overrides
- `Factory.create_batch(n)` returns `n` instances with unique IDs (UUID suffixes)
- `Factory.create_adversarial()` produces boundary-value and adversarial variants (empty strings, unicode, injection payloads, very large values, negative amounts)

**Key files:** `tests/factories.py`
**Labels:** `epic:models`, `sub-phase:mvp`
**parallel-group:** `2.models-seq`
**blocks:** `[2.4]`

---

#### Story 2.4: Wire model fixtures into test conftest

Create root `tests/conftest.py` with factory fixtures and path fixtures. Create `tests/fixtures/` with sample JSON data files.

**Acceptance criteria:**
- `tests/conftest.py` provides `transaction_factory` and `client_factory` fixtures
- `tests/conftest.py` provides `skills_dir` and `fixtures_dir` path fixtures
- `tests/fixtures/sample_transactions.json` and `tests/fixtures/sample_clients.json` contain valid sample data
- All model unit tests pass when run via `uv run pytest tests/unit/test_models/`

**Key files:** `tests/conftest.py`, `tests/fixtures/sample_transactions.json`, `tests/fixtures/sample_clients.json`, `tests/fixtures/sample_skills.md`
**Labels:** `epic:models`, `sub-phase:mvp`
**parallel-group:** `2.models-seq`
**blocks:** `[]`

---

### Epic 3: Adapter Protocols & In-Memory Implementations

> Define the Protocol interfaces that decouple business logic from cloud providers, build reference in-memory implementations, and create conformance test suites that all adapter implementations must pass.

**Sub-phase:** MVP
**Dependencies:** Epic 1

#### Story 3.1: Define adapter protocol interfaces

Create `core/adapters/base.py` with Python Protocol classes (PEP 544) for `StorageAdapter`, `SecretsAdapter`, `MessagingAdapter`, and `SchedulerAdapter`. All methods are `async`.

**Acceptance criteria:**
- `core/adapters/base.py` defines 4 Protocol classes with all methods from the architecture spec
- `StorageAdapter`: `get`, `save`, `query`, `batch_write`, `delete`
- `SecretsAdapter`: `get`, `set`, `delete`, `list`
- `MessagingAdapter`: `publish`, `subscribe`, `create_topic`, `delete_topic`
- `SchedulerAdapter`: `create`, `update`, `pause`, `resume`, `delete`, `list`
- All methods use `async def` signatures
- Type hints use standard library types (no cloud SDK types)

**Key files:** `core/adapters/base.py`
**Labels:** `epic:adapters`, `sub-phase:mvp`
**parallel-group:** `3.protocols`
**blocks:** `[3.3, 3.4, 3.5, 3.6]`

---

#### Story 3.2: Define adapter exceptions

Create `core/adapters/exceptions.py` with `AdapterError` (base), `NotFoundError`, `ConflictError`, and `ValidationError`. Ensure exception `__repr__` never includes secret values.

**Acceptance criteria:**
- `core/adapters/exceptions.py` defines 4 exception classes with clear hierarchy
- `AdapterError` is the base; `NotFoundError`, `ConflictError`, `ValidationError` extend it
- `NotFoundError` includes collection and doc_id in message (but not document contents)
- Exception `__repr__` and `__str__` are tested to not leak sensitive data
- Unit tests verify exception hierarchy and message formatting

**Key files:** `core/adapters/exceptions.py`, `tests/unit/test_adapters/test_exceptions.py` (optional, can be part of conformance)
**Labels:** `epic:adapters`, `sub-phase:mvp`
**parallel-group:** `3.protocols`
**blocks:** `[3.3, 3.4, 3.5, 3.6]`

---

#### Story 3.3: Implement in-memory StorageAdapter

Create `tests/adapters/memory_storage.py` — a dict-backed `StorageAdapter` with collection/document semantics, deep-copy on save/get, `reset()` method, and `seed()` helper.

**Acceptance criteria:**
- `tests/adapters/memory_storage.py` implements all `StorageAdapter` Protocol methods
- `save` and `get` use deep-copy semantics (no shared references)
- `query` supports filters dict and `order_by`/`limit` parameters
- `get` on missing document raises `NotFoundError`
- `reset()` clears all data (for per-test isolation)
- `seed(collection, docs)` bulk-loads test data
- All methods are `async`

**Key files:** `tests/adapters/memory_storage.py`
**Labels:** `epic:adapters`, `sub-phase:mvp`
**parallel-group:** `3.in-memory`
**blocks:** `[3.7]`

---

#### Story 3.4: Implement in-memory SecretsAdapter

Create `tests/adapters/memory_secrets.py` — a dict-backed `SecretsAdapter` with version tracking. `__repr__` and `__str__` must never expose stored values.

**Acceptance criteria:**
- `tests/adapters/memory_secrets.py` implements all `SecretsAdapter` Protocol methods
- `get(name, version)` supports version parameter (defaults to latest)
- `set` increments version counter
- `list(prefix)` filters by prefix
- `get` on missing secret raises `NotFoundError`
- `repr()` and `str()` do not contain secret values
- `reset()` clears all data

**Key files:** `tests/adapters/memory_secrets.py`
**Labels:** `epic:adapters`, `sub-phase:mvp`
**parallel-group:** `3.in-memory`
**blocks:** `[3.8]`

---

#### Story 3.5: Implement in-memory MessagingAdapter

Create `tests/adapters/memory_messaging.py` — a list-backed `MessagingAdapter` with topic/message capture and a `get_messages(topic)` test helper.

**Acceptance criteria:**
- `tests/adapters/memory_messaging.py` implements all `MessagingAdapter` Protocol methods
- `publish` stores messages with topic, payload, and attributes
- `subscribe` registers handlers that receive published messages
- `create_topic` / `delete_topic` manage topic state
- `get_messages(topic)` returns all messages published to a topic (test helper)
- `reset()` clears all topics and messages

**Key files:** `tests/adapters/memory_messaging.py`
**Labels:** `epic:adapters`, `sub-phase:mvp`
**parallel-group:** `3.in-memory`
**blocks:** `[3.9]`

---

#### Story 3.6: Implement in-memory SchedulerAdapter

Create `tests/adapters/memory_scheduler.py` — a dict-backed `SchedulerAdapter` with job state tracking and a `get_jobs()` test helper.

**Acceptance criteria:**
- `tests/adapters/memory_scheduler.py` implements all `SchedulerAdapter` Protocol methods
- `create` stores job with name, schedule (cron expression), target, payload, and state (active/paused)
- `pause` / `resume` toggle job state
- `delete` removes job; `get` on missing job raises `NotFoundError`
- `list()` returns all jobs; `get_jobs()` is a test helper for assertions
- `reset()` clears all jobs

**Key files:** `tests/adapters/memory_scheduler.py`
**Labels:** `epic:adapters`, `sub-phase:mvp`
**parallel-group:** `3.in-memory`
**blocks:** `[3.10]`

---

#### Story 3.7: Create StorageAdapter conformance test suite

Create `tests/unit/test_adapters/test_storage_conformance.py` with a `StorageAdapterContract` class defining 15+ behavioral tests. Include CRUD operations, query with filters, batch writes, not-found behavior, collection isolation, and tenant isolation tests.

**Acceptance criteria:**
- `StorageAdapterContract` defines an `adapter` fixture that subclasses override
- Tests cover: save/get, get-not-found raises `NotFoundError`, query with filters, query with order_by/limit, batch_write, delete, collection isolation
- Tenant isolation tests: query across tenant boundary returns empty, get across tenant boundary raises `NotFoundError`, delete scoped to one tenant does not affect another
- In-memory adapter passes all conformance tests
- Contract class is importable by cloud adapter test modules

**Key files:** `tests/unit/test_adapters/test_storage_conformance.py`
**Labels:** `epic:adapters`, `sub-phase:mvp`
**parallel-group:** `3.conformance`
**blocks:** `[3.11]`

---

#### Story 3.8: Create SecretsAdapter conformance test suite

Create `tests/unit/test_adapters/test_secrets_conformance.py` with a `SecretsAdapterContract` class defining behavioral tests for get/set/delete, version behavior, list with prefix, not-found errors, and repr safety.

**Acceptance criteria:**
- `SecretsAdapterContract` defines 10+ behavioral tests
- Tests cover: set/get, get-not-found, version retrieval, list with prefix, delete, repr does not leak values
- In-memory adapter passes all conformance tests
- Contract class is importable by cloud adapter test modules

**Key files:** `tests/unit/test_adapters/test_secrets_conformance.py`
**Labels:** `epic:adapters`, `sub-phase:mvp`
**parallel-group:** `3.conformance`
**blocks:** `[3.11]`

---

#### Story 3.9: Create MessagingAdapter conformance test suite

Create `tests/unit/test_adapters/test_messaging_conformance.py` with a `MessagingAdapterContract` class defining behavioral tests for publish/subscribe, topic lifecycle, message attributes, and ordering.

**Acceptance criteria:**
- `MessagingAdapterContract` defines 10+ behavioral tests
- Tests cover: publish/subscribe round-trip, topic creation/deletion, message attributes preserved, publish to nonexistent topic behavior
- In-memory adapter passes all conformance tests
- Contract class is importable by cloud adapter test modules

**Key files:** `tests/unit/test_adapters/test_messaging_conformance.py`
**Labels:** `epic:adapters`, `sub-phase:mvp`
**parallel-group:** `3.conformance`
**blocks:** `[3.11]`

---

#### Story 3.10: Create SchedulerAdapter conformance test suite

Create `tests/unit/test_adapters/test_scheduler_conformance.py` with a `SchedulerAdapterContract` class defining behavioral tests for job CRUD, pause/resume, schedule validation, and list filtering.

**Acceptance criteria:**
- `SchedulerAdapterContract` defines 10+ behavioral tests
- Tests cover: create/get, update schedule, pause/resume state transitions, delete, list all jobs, create duplicate name behavior
- In-memory adapter passes all conformance tests
- Contract class is importable by cloud adapter test modules

**Key files:** `tests/unit/test_adapters/test_scheduler_conformance.py`
**Labels:** `epic:adapters`, `sub-phase:mvp`
**parallel-group:** `3.conformance`
**blocks:** `[3.11]`

---

#### Story 3.11: Wire adapter fixtures into test conftest

Update `tests/conftest.py` to provide function-scoped in-memory adapter fixtures with auto-reset. Create `tests/unit/test_adapters/conftest.py` to parameterize conformance tests against the in-memory implementations.

**Acceptance criteria:**
- `tests/conftest.py` provides `storage`, `secrets`, `messaging`, `scheduler` fixtures (function-scoped)
- Each fixture creates the in-memory adapter, yields it, then calls `reset()`
- `tests/unit/test_adapters/conftest.py` wires conformance test classes to in-memory adapters via the `adapter` fixture
- `uv run pytest tests/unit/test_adapters/` passes all conformance suites

**Key files:** `tests/conftest.py` (updated), `tests/unit/test_adapters/conftest.py`
**Labels:** `epic:adapters`, `sub-phase:mvp`
**parallel-group:** `3.wiring`
**blocks:** `[]`

---

### Epic 4: CFO Skills & Agent Definitions

> Author the domain knowledge (skills) and agent configuration (YAML) that power CFOKit's financial intelligence.

**Sub-phase:** MVP
**Dependencies:** Epic 1

#### Story 4.1: Author S-corp skills

Create markdown skill files for S-corp domain knowledge relevant to bookkeeping: reasonable compensation (informs salary/distribution categorization).

**Acceptance criteria:**
- `core/skills/s_corp/reasonable_compensation.md` covers IRS reasonable compensation rules, factors courts consider, salary-vs-distribution guidelines
- Each skill starts with `# ` heading, is non-empty, and is under 50KB
- Skills contain required keyword: "reasonable compensation"

**Key files:** `core/skills/s_corp/*.md`
**Labels:** `epic:skills`, `sub-phase:mvp`
**parallel-group:** `4.skills`
**blocks:** `[4.4]`

---

#### Story 4.2: Author federal tax and NY state skills

Create markdown skill files for bookkeeper-relevant federal tax rules (depreciation, meal deductions) and NY state tax rules (sales tax).

**Acceptance criteria:**
- `core/skills/federal_tax/depreciation.md` covers Section 179, MACRS, and bonus depreciation rules
- `core/skills/federal_tax/meal_deductions.md` covers 50% deduction rules, exceptions, and documentation requirements
- `core/skills/ny_state/sales_tax.md` covers NY sales tax collection and reporting
- Each skill starts with `# ` heading, is non-empty, and is under 50KB

**Key files:** `core/skills/federal_tax/*.md`, `core/skills/ny_state/*.md`
**Labels:** `epic:skills`, `sub-phase:mvp`
**parallel-group:** `4.skills`
**blocks:** `[4.4]`

---

#### Story 4.3: Create bookkeeper agent YAML definition

Create the YAML agent definition file for the bookkeeper agent. The agent definition specifies the agent's name, description, skills, tools, and triggers.

**Acceptance criteria:**
- `core/agents/bookkeeper.yaml` defines skills (transaction categorization, receipt processing), tools (quickbooks-mcp, wave-mcp), and triggers (daily-transaction-review, on-demand)
- YAML file parses without errors

**Key files:** `core/agents/bookkeeper.yaml`
**Labels:** `epic:skills`, `sub-phase:mvp`
**parallel-group:** `4.skills`
**blocks:** `[4.4]`

---

#### Story 4.4: Create skill and agent tests

Implement tests for skill file structure, content regression, and agent YAML validation. Use parameterized tests that auto-discover skill files via glob.

**Acceptance criteria:**
- `tests/unit/test_skills/test_skill_loader.py` parameterizes over all `core/skills/**/*.md` files and verifies: non-empty, starts with `# `, under 50KB
- `tests/unit/test_skills/test_s_corp_rules.py` verifies S-corp skills contain required keyword ("reasonable compensation")
- Bookkeeper agent YAML file is tested for valid YAML parse, required fields (name, description, skills, tools), and referential integrity (listed skills exist as files)
- New skill files are auto-discovered — no test code changes needed when adding skills

**Key files:** `tests/unit/test_skills/test_skill_loader.py`, `tests/unit/test_skills/test_s_corp_rules.py`
**Labels:** `epic:skills`, `sub-phase:mvp`
**parallel-group:** `4.tests`
**blocks:** `[]`

---

### Epic 5: Shared Utilities

> Implement the cloud-agnostic utility modules that handlers and agents depend on: Claude API client, skill loader, MCP manager, and Slack client.

**Sub-phase:** MVP
**Dependencies:** Epics 1, 3, 4

#### Story 5.1: Implement Claude API client

Create `core/shared/claude_client.py` wrapping the Anthropic Claude API. User input goes in user role only; skill content goes in system/assistant context only. All calls are async.

**Acceptance criteria:**
- `core/shared/claude_client.py` provides async methods for agent invocation
- User-provided input is placed exclusively in user-role messages
- Skill content is placed in system context, never in user role
- Client is injectable (constructor takes API key, not env var directly)
- Unit tests mock the API and verify: prompt construction safety (user input not in system prompt), skill content not in user role, error handling for API failures
- Tests use `claude_client_mock` fixture returning predictable responses

**Key files:** `core/shared/claude_client.py`, `tests/unit/test_claude_client.py`
**Labels:** `epic:utilities`, `sub-phase:mvp`
**parallel-group:** `5.utilities`
**blocks:** `[]`

---

#### Story 5.2: Implement skill loader

Create `core/shared/skill_loader.py` that loads markdown skill files from `core/skills/`. Enforce path traversal protection: reject `..`, absolute paths, and null bytes.

**Acceptance criteria:**
- `core/shared/skill_loader.py` provides `load_skill(name)` that returns skill content as string
- Rejects path traversal attempts (`../../etc/passwd`), absolute paths (`/etc/passwd`), and null bytes
- Raises `ValueError` or `PermissionError` on invalid paths
- Resolves skill names to `core/skills/{name}.md` paths
- Unit tests cover: valid skill loading, path traversal rejection, absolute path rejection, null byte rejection, nonexistent skill handling

**Key files:** `core/shared/skill_loader.py`, `tests/unit/test_skills/test_skill_loader.py` (extended)
**Labels:** `epic:utilities`, `sub-phase:mvp`
**parallel-group:** `5.utilities`
**blocks:** `[]`

---

#### Story 5.3: Implement MCP manager

Create `core/shared/mcp_manager.py` for MCP server lifecycle management. Enforce HTTPS-only URLs — reject `http://` URLs.

**Acceptance criteria:**
- `core/shared/mcp_manager.py` provides `MCPManager` class for server connection lifecycle
- Constructor rejects `http://` URLs with `ValueError` matching "HTTPS required"
- Accepts `https://` URLs
- Manages connection state (connect, disconnect, health check)
- Unit tests cover: HTTPS enforcement, HTTP rejection, connection lifecycle

**Key files:** `core/shared/mcp_manager.py`, `tests/unit/test_mcp_manager.py`
**Labels:** `epic:utilities`, `sub-phase:mvp`
**parallel-group:** `5.utilities`
**blocks:** `[]`

---

#### Story 5.4: Implement Slack client

Create `core/shared/slack_client.py` wrapping the Slack API for sending messages, responding to commands, and formatting responses.

**Acceptance criteria:**
- `core/shared/slack_client.py` provides async methods for sending messages and responding to slash commands
- Client is injectable (constructor takes bot token)
- Message formatting supports markdown blocks
- Unit tests mock the Slack API and verify: message payload structure, channel targeting, error handling
- No actual Slack API calls in tests

**Key files:** `core/shared/slack_client.py`, `tests/unit/test_slack_client.py`
**Labels:** `epic:utilities`, `sub-phase:mvp`
**parallel-group:** `5.utilities`
**blocks:** `[]`

---

### Epic 6: Request Handlers

> Implement the cloud-agnostic request handlers that process user commands. Handlers depend only on adapter Protocol interfaces via constructor injection.

**Sub-phase:** Beta
**Dependencies:** Epics 2, 3, 5

#### Story 6.1: Implement base handler

Create `deploy-cloud/shared/handlers/base_handler.py` with a `BaseHandler` class that receives adapters via constructor injection and provides shared functionality: audit logging, error formatting, and tenant context.

**Acceptance criteria:**
- `BaseHandler.__init__` accepts `storage`, `secrets`, `messaging` adapter parameters
- `BaseHandler` provides `_emit_audit_event(action, resource_id, tenant, details)` method that writes to `audit_log` collection
- Audit events include timestamp, actor, action, tenant, resource_id — never include secret values
- `BaseHandler` provides `_format_error(error)` that returns generic message + correlation ID, never stack traces or file paths
- Unit tests verify: audit event structure, audit events do not contain secrets, error formatting excludes stack traces

**Key files:** `deploy-cloud/shared/handlers/base_handler.py`, `tests/unit/test_handlers/test_base_handler.py`
**Labels:** `epic:handlers`, `sub-phase:beta`
**parallel-group:** `6.handlers-base`
**blocks:** `[6.2, 6.3, 6.4, 6.5]`

---

#### Story 6.2: Implement categorize handler

Create `deploy-cloud/shared/handlers/categorize.py` for transaction categorization. Uses Claude AI (via `claude_client`) to categorize transactions and persists results via `StorageAdapter`.

**Acceptance criteria:**
- `CategorizeHandler` extends `BaseHandler`, receives adapters via constructor
- `handle(request)` fetches transaction from storage, sends to Claude for categorization, saves result
- Emits audit event on successful categorization
- Handles missing transaction (returns error, does not crash)
- Error responses never contain secret values
- Unit tests use mocked `claude_client` returning predictable categories; verify both response AND storage side-effects

**Key files:** `deploy-cloud/shared/handlers/categorize.py`, `tests/unit/test_handlers/test_categorize.py`
**Labels:** `epic:handlers`, `sub-phase:beta`
**parallel-group:** `6.handlers`
**blocks:** `[]`

---

#### Story 6.3: Implement report handler

Create `deploy-cloud/shared/handlers/report.py` for bookkeeper report generation. Generates P&L and transaction summaries.

**Acceptance criteria:**
- `ReportHandler` extends `BaseHandler`
- `handle(request)` generates report based on report_type parameter
- Supports report types: monthly_pl, transaction_summary
- Persists generated reports to storage
- Emits audit event
- Unit tests verify report structure and storage persistence

**Key files:** `deploy-cloud/shared/handlers/report.py`, `tests/unit/test_handlers/test_report.py`
**Labels:** `epic:handlers`, `sub-phase:beta`
**parallel-group:** `6.handlers`
**blocks:** `[]`

---

#### Story 6.4: Implement setup handler

Create `deploy-cloud/shared/handlers/setup.py` for client onboarding. Guides new clients through entity type selection, QuickBooks connection, and initial configuration.

**Acceptance criteria:**
- `SetupHandler` extends `BaseHandler`
- `handle(request)` creates or updates client configuration in storage
- Validates entity type, state, fiscal year start
- Stores client configuration via `StorageAdapter`
- Emits audit event for client creation/update
- Unit tests verify: client creation, validation errors, duplicate setup handling

**Key files:** `deploy-cloud/shared/handlers/setup.py`, `tests/unit/test_handlers/test_setup.py`
**Labels:** `epic:handlers`, `sub-phase:beta`
**parallel-group:** `6.handlers`
**blocks:** `[]`

---

#### Story 6.5: Implement help handler

Create `deploy-cloud/shared/handlers/help.py` for usage information and command listing.

**Acceptance criteria:**
- `HelpHandler` extends `BaseHandler`
- `handle(request)` returns available commands, usage examples, and feature descriptions
- Response is formatted for Slack markdown
- Does not require storage access (stateless)
- Unit test verifies response contains expected command names

**Key files:** `deploy-cloud/shared/handlers/help.py`, `tests/unit/test_handlers/test_help.py`
**Labels:** `epic:handlers`, `sub-phase:beta`
**parallel-group:** `6.handlers`
**blocks:** `[]`

---

#### Story 6.6: Create handler test conftest

Create `tests/unit/conftest.py` with handler fixtures pre-wired with mock adapters and mocked `claude_client`. Create `tests/unit/test_handlers/conftest.py` with handler-specific fixtures.

**Acceptance criteria:**
- `tests/unit/conftest.py` provides `mocked_claude_client` fixture returning predictable responses
- Handler fixtures (`categorize_handler`, `report_handler`, `setup_handler`, `help_handler`) inject in-memory adapters and mocked claude_client
- `tests/unit/test_handlers/conftest.py` provides pre-seeded storage fixtures for handler tests
- All handler tests pass when run via `uv run pytest tests/unit/test_handlers/`

**Key files:** `tests/unit/conftest.py`, `tests/unit/test_handlers/conftest.py`
**Labels:** `epic:handlers`, `sub-phase:beta`
**parallel-group:** `6.handlers-base`
**blocks:** `[]`

---

### Epic 7: GCP Adapter Implementations

> Implement the GCP-specific adapter classes that fulfill the Protocol interfaces using GCP services: Firestore, Secret Manager, Pub/Sub, and Cloud Scheduler.

**Sub-phase:** Beta
**Dependencies:** Epic 3 (adapter protocols must exist; starts after MVP completes per Track 2)

#### Story 7.1: Implement Firestore StorageAdapter

Create `deploy-cloud/gcp/adapters/storage.py` implementing `StorageAdapter` using Google Cloud Firestore. Support collection/document semantics, query filters, batch writes, and tenant-namespaced collections.

**Acceptance criteria:**
- `FirestoreAdapter` implements all `StorageAdapter` Protocol methods
- Uses Firestore client from `google-cloud-firestore` SDK
- Collection paths support tenant namespacing (`clients/{tenant}/transactions`)
- Batch write uses Firestore batch/transaction API
- Query filters translate to Firestore query operators
- Raises `NotFoundError` for missing documents
- Passes `StorageAdapterContract` conformance suite against Firestore emulator

**Key files:** `deploy-cloud/gcp/adapters/storage.py`, `tests/cloud/test_gcp_adapters.py`
**Labels:** `epic:gcp`, `sub-phase:beta`
**parallel-group:** `7.gcp-adapters`
**blocks:** `[]`

---

#### Story 7.2: Implement Secret Manager SecretsAdapter

Create `deploy-cloud/gcp/adapters/secrets.py` implementing `SecretsAdapter` using Google Cloud Secret Manager.

**Acceptance criteria:**
- `SecretManagerAdapter` implements all `SecretsAdapter` Protocol methods
- Supports version retrieval (specific version or latest)
- `list` with prefix filters secrets by name prefix
- `__repr__` and `__str__` do not expose secret values
- Raises `NotFoundError` for missing secrets
- Passes `SecretsAdapterContract` conformance suite

**Key files:** `deploy-cloud/gcp/adapters/secrets.py`, `tests/cloud/test_gcp_adapters.py`
**Labels:** `epic:gcp`, `sub-phase:beta`
**parallel-group:** `7.gcp-adapters`
**blocks:** `[]`

---

#### Story 7.3: Implement Pub/Sub MessagingAdapter

Create `deploy-cloud/gcp/adapters/messaging.py` implementing `MessagingAdapter` using Google Cloud Pub/Sub.

**Acceptance criteria:**
- `PubSubAdapter` implements all `MessagingAdapter` Protocol methods
- Publish includes message attributes
- Subscribe registers push/pull handlers
- Topic create/delete manage Pub/Sub topic lifecycle
- Passes `MessagingAdapterContract` conformance suite

**Key files:** `deploy-cloud/gcp/adapters/messaging.py`, `tests/cloud/test_gcp_adapters.py`
**Labels:** `epic:gcp`, `sub-phase:beta`
**parallel-group:** `7.gcp-adapters`
**blocks:** `[]`

---

#### Story 7.4: Implement Cloud Scheduler SchedulerAdapter

Create `deploy-cloud/gcp/adapters/scheduler.py` implementing `SchedulerAdapter` using Google Cloud Scheduler.

**Acceptance criteria:**
- `CloudSchedulerAdapter` implements all `SchedulerAdapter` Protocol methods
- Cron expressions are passed through to Cloud Scheduler
- Pause/resume toggle job state
- Passes `SchedulerAdapterContract` conformance suite

**Key files:** `deploy-cloud/gcp/adapters/scheduler.py`, `tests/cloud/test_gcp_adapters.py`
**Labels:** `epic:gcp`, `sub-phase:beta`
**parallel-group:** `7.gcp-adapters`
**blocks:** `[]`

---

#### Story 7.5: Create GCP cloud test conftest and CI integration

Create `tests/cloud/conftest.py` with emulator fixtures (session-scoped setup, function-scoped adapter instances). Wire GCP conformance tests to inherit from contract classes. Update CI to run GCP cloud tests.

**Acceptance criteria:**
- `tests/cloud/conftest.py` provides session-scoped Firestore emulator fixture
- Function-scoped fixtures create fresh adapter instances per test
- Skip markers activate if emulator is not running (`FIRESTORE_EMULATOR_HOST` not set)
- `tests/cloud/test_gcp_adapters.py` has `TestFirestoreAdapter(StorageAdapterContract)`, `TestSecretManagerAdapter(SecretsAdapterContract)`, etc.
- All GCP adapter tests are marked with `@pytest.mark.gcp`
- CI `cloud-gcp` job runs these tests with emulator service container

**Key files:** `tests/cloud/conftest.py`, `tests/cloud/test_gcp_adapters.py`
**Labels:** `epic:gcp`, `sub-phase:beta`
**parallel-group:** `7.gcp-wiring`
**blocks:** `[]`

---

### Epic 8: FastAPI Application & Security

> Build the FastAPI application that receives Slack webhooks, routes to handlers, and enforces security: signature verification, rate limiting, and secure error responses.

**Sub-phase:** Beta
**Dependencies:** Epics 5, 6, 7

#### Story 8.1: Create FastAPI application factory

Create the `create_app()` factory function that accepts adapter instances and returns a configured FastAPI application with all routes registered.

**Acceptance criteria:**
- `deploy-cloud/shared/app_factory.py` provides `create_app(storage, secrets, messaging, scheduler)` returning a FastAPI instance
- Routes are registered for: `/slack/events` (POST), `/slack/commands` (POST), `/health` (GET)
- Handler instances are created with injected adapters
- Application can be instantiated with in-memory adapters for testing

**Key files:** `deploy-cloud/shared/app_factory.py`
**Labels:** `epic:fastapi`, `sub-phase:beta`
**parallel-group:** `8.app-base`
**blocks:** `[8.2, 8.3, 8.4, 8.5, 8.6]`

---

#### Story 8.2: Implement Slack signature verification middleware

Create middleware that verifies Slack request signatures (`X-Slack-Signature`, `X-Slack-Request-Timestamp`). Reject unsigned, forged, and replayed (stale timestamp) requests.

**Acceptance criteria:**
- Middleware validates `X-Slack-Signature` using HMAC-SHA256 with signing secret
- Requests without signature headers return 401/403
- Requests with invalid signatures return 401/403
- Requests with timestamps older than 5 minutes return 401/403 (replay protection)
- Valid signatures pass through to handlers
- Unit tests cover: missing signature, invalid signature, expired timestamp, valid signature
- Integration tests verify middleware with FastAPI TestClient

**Key files:** `deploy-cloud/shared/middleware/slack_auth.py`, `tests/unit/test_slack_auth.py`, `tests/integration/test_fastapi_app.py`
**Labels:** `epic:fastapi`, `sub-phase:beta`
**parallel-group:** `8.security`
**blocks:** `[]`

---

#### Story 8.3: Implement rate limiting middleware

Create per-tenant rate limiting middleware. One tenant's burst must not block another tenant.

**Acceptance criteria:**
- Rate limiter tracks requests per tenant (identified by Slack workspace/channel)
- Exceeding threshold returns 429 Too Many Requests
- Rate limits are scoped per tenant — one tenant exhausting quota does not affect others
- Configurable threshold and window
- Unit tests cover: threshold enforcement, per-tenant isolation, window reset

**Key files:** `deploy-cloud/shared/middleware/rate_limit.py`, `tests/unit/test_rate_limit.py`
**Labels:** `epic:fastapi`, `sub-phase:beta`
**parallel-group:** `8.security`
**blocks:** `[]`

---

#### Story 8.4: Implement health endpoint

Create `/health` endpoint that returns service status without leaking internal details (no version, no internal IPs, no stack info).

**Acceptance criteria:**
- GET `/health` returns 200 with `{"status": "healthy"}`
- Response does not include version numbers, internal IP addresses, or stack information
- Response includes appropriate security headers (HSTS, X-Content-Type-Options, X-Frame-Options)
- Unit test verifies response body and absence of leaked details

**Key files:** `deploy-cloud/shared/handlers/health.py`, `tests/unit/test_health.py`
**Labels:** `epic:fastapi`, `sub-phase:beta`
**parallel-group:** `8.endpoints`
**blocks:** `[]`

---

#### Story 8.5: Implement Slack event routing

Create the `/slack/events` and `/slack/commands` route handlers that parse Slack payloads, extract command intent, and route to the appropriate handler.

**Acceptance criteria:**
- `/slack/events` handles Slack event callbacks (URL verification, message events)
- `/slack/commands` handles slash command payloads
- Command parser extracts intent (categorize, report, setup, help) from message text
- Unknown commands route to help handler
- Invalid payloads return appropriate error responses (no stack traces)
- Integration tests verify routing with TestClient

**Key files:** `deploy-cloud/shared/routes/slack.py`, `tests/integration/test_fastapi_app.py`
**Labels:** `epic:fastapi`, `sub-phase:beta`
**parallel-group:** `8.endpoints`
**blocks:** `[]`

---

#### Story 8.6: Create GCP app.py wiring

Create `deploy-cloud/gcp/agents/cfo_bot/app.py` that imports GCP adapter implementations, instantiates them, and passes them to `create_app()`. Include Dockerfile and requirements.txt.

**Acceptance criteria:**
- `app.py` imports `FirestoreAdapter`, `SecretManagerAdapter`, `PubSubAdapter`, `CloudSchedulerAdapter`
- Instantiates each adapter and passes to `create_app()`
- `Dockerfile` builds a production-ready container image
- `requirements.txt` pins production dependencies
- Application starts successfully with `uvicorn`

**Key files:** `deploy-cloud/gcp/agents/cfo_bot/app.py`, `deploy-cloud/gcp/agents/cfo_bot/Dockerfile`, `deploy-cloud/gcp/agents/cfo_bot/requirements.txt`
**Labels:** `epic:fastapi`, `sub-phase:beta`
**parallel-group:** `8.gcp-wiring`
**blocks:** `[]`

---

#### Story 8.7: Create integration test suite

Create `tests/integration/` test suite using FastAPI TestClient with in-memory adapters wired via `create_app()` factory. Test multi-component flows end-to-end within the process.

**Acceptance criteria:**
- `tests/integration/conftest.py` creates TestClient via `create_app()` with in-memory adapters and pre-seeded data
- `tests/integration/test_fastapi_app.py` tests: Slack signature verification, command routing, handler invocation, response format
- `tests/integration/test_handler_flows.py` tests multi-step bookkeeper flow (setup → categorize → report)
- `tests/integration/test_skill_loading.py` tests real skill file loading from disk
- All integration tests pass without external services

**Key files:** `tests/integration/conftest.py`, `tests/integration/test_fastapi_app.py`, `tests/integration/test_handler_flows.py`, `tests/integration/test_skill_loading.py`
**Labels:** `epic:fastapi`, `sub-phase:beta`
**parallel-group:** `8.integration`
**blocks:** `[]`

---

### Epic 9: GCP Infrastructure & Deployment

> Create Terraform modules for GCP resources and the one-click deploy script.

**Sub-phase:** GA
**Dependencies:** Epics 7, 8

#### Story 9.1: Create Terraform Cloud Run module

Create `deploy-cloud/gcp/terraform/modules/cloud_run/` with Terraform configuration for Cloud Run service and Cloud Run Jobs.

**Acceptance criteria:**
- Module provisions Cloud Run service with configurable image, memory, CPU, concurrency
- Module provisions Cloud Run Jobs for scheduled tasks
- Service connects to VPC connector for private networking (optional)
- Environment variables are injected from Secret Manager references
- `terraform validate` passes

**Key files:** `deploy-cloud/gcp/terraform/modules/cloud_run/main.tf`, `variables.tf`, `outputs.tf`
**Labels:** `epic:gcp-infra`, `sub-phase:ga`
**parallel-group:** `9.terraform-modules`
**blocks:** `[9.5]`

---

#### Story 9.2: Create Terraform Firestore module

Create `deploy-cloud/gcp/terraform/modules/firestore/` with Terraform configuration for Firestore database and indexes.

**Acceptance criteria:**
- Module provisions Firestore database in native mode
- Module creates composite indexes from `firestore-indexes.json`
- Configurable location (region)
- `terraform validate` passes

**Key files:** `deploy-cloud/gcp/terraform/modules/firestore/main.tf`, `variables.tf`, `outputs.tf`
**Labels:** `epic:gcp-infra`, `sub-phase:ga`
**parallel-group:** `9.terraform-modules`
**blocks:** `[9.5]`

---

#### Story 9.3: Create Terraform Pub/Sub module

Create `deploy-cloud/gcp/terraform/modules/pubsub/` with Terraform configuration for Pub/Sub topics and subscriptions.

**Acceptance criteria:**
- Module provisions topics and push/pull subscriptions
- Dead-letter topic configuration for failed messages
- Configurable acknowledgment deadline and retention
- `terraform validate` passes

**Key files:** `deploy-cloud/gcp/terraform/modules/pubsub/main.tf`, `variables.tf`, `outputs.tf`
**Labels:** `epic:gcp-infra`, `sub-phase:ga`
**parallel-group:** `9.terraform-modules`
**blocks:** `[9.5]`

---

#### Story 9.4: Create Terraform Cloud Scheduler module

Create `deploy-cloud/gcp/terraform/modules/scheduler/` with Terraform configuration for Cloud Scheduler jobs.

**Acceptance criteria:**
- Module provisions Cloud Scheduler jobs targeting Cloud Run Jobs
- Cron schedule, timezone, and retry configuration are parameterized
- HTTP target points to Cloud Run Jobs execution endpoint
- `terraform validate` passes

**Key files:** `deploy-cloud/gcp/terraform/modules/scheduler/main.tf`, `variables.tf`, `outputs.tf`
**Labels:** `epic:gcp-infra`, `sub-phase:ga`
**parallel-group:** `9.terraform-modules`
**blocks:** `[9.5]`

---

#### Story 9.5: Create root Terraform configuration

Create `deploy-cloud/gcp/terraform/main.tf` that composes all modules, plus `variables.tf` and `outputs.tf`. Include project ID, region, and service account configuration.

**Acceptance criteria:**
- `main.tf` composes cloud_run, firestore, pubsub, and scheduler modules
- `variables.tf` defines all required variables with descriptions and validation
- `outputs.tf` exposes Cloud Run service URL, Firestore database name, project ID
- `terraform validate` passes
- README documents required variables and usage

**Key files:** `deploy-cloud/gcp/terraform/main.tf`, `variables.tf`, `outputs.tf`, `README.md`
**Labels:** `epic:gcp-infra`, `sub-phase:ga`
**parallel-group:** `9.terraform-root`
**blocks:** `[9.6]`

---

#### Story 9.6: Create deploy.sh one-click script

Create `deploy-cloud/gcp/deploy.sh` that automates the full deployment: build container, push to Artifact Registry, apply Terraform, configure secrets.

**Acceptance criteria:**
- Script checks prerequisites (gcloud, terraform, docker)
- Builds Docker image and pushes to GCP Artifact Registry
- Runs `terraform init && terraform apply`
- Configures secrets in Secret Manager (prompts for values or reads from env)
- Outputs the Cloud Run service URL
- Script is idempotent (safe to re-run)
- Includes `--dry-run` flag for previewing changes

**Key files:** `deploy-cloud/gcp/deploy.sh`
**Labels:** `epic:gcp-infra`, `sub-phase:ga`
**parallel-group:** `9.deploy`
**blocks:** `[]`

---

#### Story 9.7: Create GCP configuration files

Create supporting GCP configuration: `cloud-run-service.yaml`, `cloud-run-jobs.yaml`, `firestore-indexes.json`, and Slack app manifest.

**Acceptance criteria:**
- `cloud-run-service.yaml` defines Cloud Run service configuration (scaling, resources, env)
- `cloud-run-jobs.yaml` defines Cloud Run Jobs for 3 scheduled tasks (daily summary, weekly review, monthly close)
- `firestore-indexes.json` defines composite indexes for common queries
- `deploy-cloud/gcp/slack/app-manifest.yaml` defines Slack app configuration
- `deploy-cloud/gcp/slack/setup-guide.md` documents Slack app setup steps
- `deploy-cloud/gcp/slack/oauth-scopes.md` documents required OAuth scopes

**Key files:** `deploy-cloud/gcp/cloud-run-service.yaml`, `deploy-cloud/gcp/cloud-run-jobs.yaml`, `deploy-cloud/gcp/firestore-indexes.json`, `deploy-cloud/gcp/slack/app-manifest.yaml`, `deploy-cloud/gcp/slack/setup-guide.md`, `deploy-cloud/gcp/slack/oauth-scopes.md`
**Labels:** `epic:gcp-infra`, `sub-phase:ga`
**parallel-group:** `9.config`
**blocks:** `[]`

---

### Epic 10: Scheduled Jobs

> Implement the scheduled job handlers that run on Cloud Run Jobs: daily summary, weekly review, and monthly close.

**Sub-phase:** GA
**Dependencies:** Epics 5, 6, 7, 8 (starts after Beta completes per Track 3)

#### Story 10.1: Implement daily summary job

Create `deploy-cloud/gcp/agents/scheduled_jobs/daily_summary.py` that reviews the previous day's transactions, generates a summary, and posts to the client's Slack channel.

**Acceptance criteria:**
- Job queries transactions from the previous day via `StorageAdapter`
- Generates categorization summary (counts by category, flagged items)
- Posts summary to client's Slack channel via `slack_client`
- Handles multi-tenant: iterates over active clients
- Emits audit event
- Unit tests verify summary generation and Slack message structure

**Key files:** `deploy-cloud/gcp/agents/scheduled_jobs/daily_summary.py`, `tests/unit/test_scheduled_jobs/test_daily_summary.py`
**Labels:** `epic:scheduled-jobs`, `sub-phase:ga`
**parallel-group:** `10.jobs`
**blocks:** `[]`

---

#### Story 10.2: Implement weekly review job

Create `deploy-cloud/gcp/agents/scheduled_jobs/weekly_review.py` that generates a weekly financial summary including cash position, spending trends, and action items.

**Acceptance criteria:**
- Job queries the previous week's transactions and computes weekly metrics
- Includes cash position, top spending categories, week-over-week trends
- Posts formatted review to Slack
- Handles multi-tenant
- Emits audit event
- Unit tests verify metrics computation and message format

**Key files:** `deploy-cloud/gcp/agents/scheduled_jobs/weekly_review.py`, `tests/unit/test_scheduled_jobs/test_weekly_review.py`
**Labels:** `epic:scheduled-jobs`, `sub-phase:ga`
**parallel-group:** `10.jobs`
**blocks:** `[]`

---

#### Story 10.3: Implement monthly close job

Create `deploy-cloud/gcp/agents/scheduled_jobs/monthly_close.py` that generates a month-end close package: P&L, reconciliation checklist, and compliance status.

**Acceptance criteria:**
- Job generates month-end financial summary (P&L, expense breakdown)
- Includes reconciliation checklist items
- Reports compliance status for the client's entity type
- Posts close package to Slack and persists to storage
- Handles multi-tenant
- Emits audit event
- Unit tests verify close package structure and storage persistence

**Key files:** `deploy-cloud/gcp/agents/scheduled_jobs/monthly_close.py`, `tests/unit/test_scheduled_jobs/test_monthly_close.py`
**Labels:** `epic:scheduled-jobs`, `sub-phase:ga`
**parallel-group:** `10.jobs`
**blocks:** `[]`

---

#### Story 10.4: Create scheduled jobs Dockerfile and entry point

Create the Dockerfile and entry point for Cloud Run Jobs that dispatches to the correct job based on environment variable or argument.

**Acceptance criteria:**
- `deploy-cloud/gcp/agents/scheduled_jobs/Dockerfile` builds a container image with all job modules
- Entry point accepts job name as argument (`daily_summary`, `weekly_review`, `monthly_close`)
- `requirements.txt` pins production dependencies
- Container starts, executes the specified job, and exits
- Exit code reflects success (0) or failure (non-zero)

**Key files:** `deploy-cloud/gcp/agents/scheduled_jobs/Dockerfile`, `deploy-cloud/gcp/agents/scheduled_jobs/requirements.txt`, `deploy-cloud/gcp/agents/scheduled_jobs/__init__.py`
**Labels:** `epic:scheduled-jobs`, `sub-phase:ga`
**parallel-group:** `10.jobs-infra`
**blocks:** `[]`

---

### Epic 11: Documentation, Examples & CI Hardening

> Complete the documentation suite, create example configurations, and harden the CI pipeline for GA.

**Sub-phase:** GA
**Dependencies:** All previous epics

#### Story 11.1: Write architecture documentation

Create `docs/architecture.md` documenting the three-layer architecture, adapter pattern, handler injection, and data flow diagrams.

**Acceptance criteria:**
- Describes the three layers: platform-agnostic core, cloud-agnostic handlers, cloud-specific adapters
- Includes data flow diagrams for cloud deployment
- Documents the adapter Protocol pattern with code examples
- Documents handler dependency injection pattern
- References the multi-cloud strategy

**Key files:** `docs/architecture.md`
**Labels:** `epic:docs`, `sub-phase:ga`
**parallel-group:** `11.docs`
**blocks:** `[]`

---

#### Story 11.2: Write getting started guide

Create `docs/getting-started.md` with prerequisites, installation, GCP deployment, and first-use walkthrough.

**Acceptance criteria:**
- Lists prerequisites (Python 3.11+, uv, GCP account, Slack workspace, Anthropic API key, QuickBooks account)
- Step-by-step GCP deployment instructions
- First-use bookkeeper workflow walkthrough (setup → categorize → weekly review → monthly close)
- Troubleshooting section for common setup issues

**Key files:** `docs/getting-started.md`
**Labels:** `epic:docs`, `sub-phase:ga`
**parallel-group:** `11.docs`
**blocks:** `[]`

---

#### Story 11.3: Write adapter development guide

Create `docs/adapter-development.md` documenting how to add a new cloud provider: implement Protocol interfaces, inherit conformance tests, create Terraform, and wire into app.py.

**Acceptance criteria:**
- Step-by-step guide for implementing a new cloud adapter
- Shows how to inherit conformance test classes for instant test coverage
- Documents the factory/wiring pattern in `app.py`
- Includes Terraform module structure expectations
- References AWS (Phase 2) and Azure (Phase 3) as future examples

**Key files:** `docs/adapter-development.md`
**Labels:** `epic:docs`, `sub-phase:ga`
**parallel-group:** `11.docs`
**blocks:** `[]`

---

#### Story 11.4: Write skill development guide

Create `docs/skill-development.md` documenting how to author and test CFO skills.

**Acceptance criteria:**
- Documents skill file format (markdown, heading structure, size limit)
- Shows how to add a new skill and have it auto-discovered by tests
- Documents content regression testing approach
- Provides template for new skills

**Key files:** `docs/skill-development.md`
**Labels:** `epic:docs`, `sub-phase:ga`
**parallel-group:** `11.docs`
**blocks:** `[]`

---

#### Story 11.5: Write GCP deployment guide

Create `docs/deployment-guide-gcp.md` with detailed GCP deployment instructions, Terraform variable reference, and operational runbook.

**Acceptance criteria:**
- Complete GCP deployment instructions (beyond quick start)
- Terraform variable reference table
- Cost estimation for 1 client and 10 clients
- Operational runbook: monitoring, scaling, troubleshooting
- Secret rotation procedures

**Key files:** `docs/deployment-guide-gcp.md`
**Labels:** `epic:docs`, `sub-phase:ga`
**parallel-group:** `11.docs`
**blocks:** `[]`

---

#### Story 11.6: Create OpenClaw placeholder docs

Create placeholder documentation files for OpenClaw integration (coming in Phase 2).

**Acceptance criteria:**
- `docs/getting-started-openclaw.md` exists with "Coming in Phase 2" content and brief description of planned OpenClaw integration
- `docs/deployment-guide-openclaw.md` exists with "Coming in Phase 2" content
- `deploy-openclaw/README.md` exists with placeholder content describing what will be added in Phase 2
- Placeholder directories exist: `deploy-openclaw/agents/`, `deploy-openclaw/skills/`, `deploy-openclaw/workflows/`

**Key files:** `docs/getting-started-openclaw.md`, `docs/deployment-guide-openclaw.md`, `deploy-openclaw/README.md`
**Labels:** `epic:docs`, `sub-phase:ga`
**parallel-group:** `11.docs`
**blocks:** `[]`

---

#### Story 11.7: Create example configurations

Create example configurations for solo founder (S-corp) and fractional CFO (multi-client) use cases with GCP config files and README documentation. Examples focus on bookkeeping features.

**Acceptance criteria:**
- `examples/solo-founder-s-corp/README.md` documents the S-corp bookkeeping use case with Slack conversation examples
- `examples/solo-founder-s-corp/config-gcp.yaml` provides GCP configuration template
- `examples/fractional-cfo-multi-client/README.md` documents the multi-client bookkeeping use case with client onboarding flow
- `examples/fractional-cfo-multi-client/config-gcp.yaml` provides GCP multi-client configuration template

**Key files:** `examples/solo-founder-s-corp/`, `examples/fractional-cfo-multi-client/`
**Labels:** `epic:docs`, `sub-phase:ga`
**parallel-group:** `11.examples`
**blocks:** `[]`

---

#### Story 11.8: Write full README.md

Replace the abbreviated README from Epic 1 with the full README including feature descriptions, deployment options, use cases, architecture overview, cost comparison, and community links.

**Acceptance criteria:**
- README covers: tagline, value proposition, deployment options (GCP now, AWS/Azure/OpenClaw coming), features (leading with bookkeeper), quick start, use cases, architecture diagram, cost comparison, contributing, community links
- Includes badges (license, stars, deploy buttons)
- References OpenClaw as "coming in Phase 2"
- Includes "Tax preparer, compliance monitor, and cashflow analyst agents coming in Phase 2" messaging
- No broken internal links

**Key files:** `README.md`
**Labels:** `epic:docs`, `sub-phase:ga`
**parallel-group:** `11.readme`
**blocks:** `[]`

---

#### Story 11.9: Create helper scripts

Create development helper scripts for local setup, test data generation, and skill management.

**Acceptance criteria:**
- `scripts/local-dev-setup.sh` installs dependencies, starts emulators, seeds test data
- `scripts/generate-test-data.py` generates sample transactions, clients, and tax forms for development
- Scripts are executable and include usage instructions in comments
- Scripts do not contain hardcoded secrets

**Key files:** `scripts/local-dev-setup.sh`, `scripts/generate-test-data.py`
**Labels:** `epic:docs`, `sub-phase:ga`
**parallel-group:** `11.scripts`
**blocks:** `[]`

---

#### Story 11.10: Create E2E smoke tests

Create post-deploy smoke tests that verify a running deployment is healthy and secure. These run against staging environments, not in `uv run pytest`.

**Acceptance criteria:**
- `tests/e2e/test_smoke.py` tests: health endpoint returns 200, health response does not leak version/IPs/stack info, security headers present (HSTS, X-Content-Type-Options, X-Frame-Options), unauthenticated requests rejected, HTTPS enforcement
- `tests/e2e/test_slack_webhook.py` tests: basic Slack webhook round-trip (send command, receive response)
- Tests are marked to not run in standard `uv run pytest` (require `--e2e` flag or explicit path)
- Tests require `STAGING_URL` environment variable

**Key files:** `tests/e2e/test_smoke.py`, `tests/e2e/test_slack_webhook.py`
**Labels:** `epic:docs`, `sub-phase:ga`
**parallel-group:** `11.e2e`
**blocks:** `[]`

---

## Epic Dependency Graph

```
                    ┌─────────────────────────────────────────────┐
                    │           Epic 1: Scaffolding               │
                    │         (no dependencies)                   │
                    └──────┬──────────┬──────────┬────────────────┘
                           │          │          │
                    ┌──────▼──┐  ┌────▼────┐  ┌──▼──────────────┐
                    │ Epic 2  │  │ Epic 3  │  │    Epic 4       │
                    │ Models  │  │Adapters │  │ Skills/Agents   │
                    └─────────┘  └────┬────┘  └──┬──────────────┘
                         │            │          │
                         │            └─────┬────┘
                         │                  │
                         │          ┌───────▼───────┐
                         │          │   Epic 5      │
                         │          │  Utilities    │
                         │          └───┬───────┬───┘
                         │              │       │
                    ┌────▼───▼──┐  ┌────▼───────────┐
                    │  Epic 6   │  │    Epic 7      │
                    │ Handlers  │  │  GCP Adapters  │
                    └──────┬────┘  └────┬───────────┘
                           │            │
                       ┌───▼────────────▼───┐
                       │      Epic 8        │
                       │  FastAPI + Sec     │
                       └───┬────────────┬───┘
                           │            │
                    ┌──────▼──┐  ┌──────▼──────┐
                    │ Epic 9  │  │  Epic 10    │
                    │GCP Infra│  │Sched. Jobs  │
                    └──────┬──┘  └──────┬──────┘
                           │            │
                       ┌───▼────────────▼───┐
                       │     Epic 11        │
                       │   Docs + CI        │
                       └────────────────────┘

Notes:
- Epic 5 depends on Epics 3 and 4 (not Epic 2)
- Epic 6 depends on Epics 2, 3, and 5
- Epic 7 depends on Epic 3 (starts after MVP per Track 2)
- Epic 10 depends on Epics 5, 6, 7, 8 (starts after Beta per Track 3)
```

---

## Parallel Agent Tracks

### Track 1: After Epic 1 completes (3 agents in parallel)

```
Agent A: Epic 2 (Core Data Models) ──────────────────┐
Agent B: Epic 3 (Adapter Protocols + In-Memory) ─────┤──> Epic 5 (Shared Utilities)
Agent C: Epic 4 (CFO Skills + Agent Definitions) ────┘
```

**Agent A** works on Pydantic models + test factories + conftest (4 stories):
- Stories 2.1-2.2 (individual models) can run in parallel
- Story 2.3 (factories) runs after 2.1-2.2 complete
- Story 2.4 (conftest) runs after 2.3 completes

**Agent B** works on Protocol interfaces + in-memory adapters + conformance suites (11 stories):
- Stories 3.1-3.2 (protocols/exceptions) run first
- Stories 3.3-3.6 (4 in-memory implementations) run in parallel after 3.1-3.2
- Stories 3.7-3.10 (4 conformance suites) run in parallel after corresponding implementation
- Story 3.11 (conftest wiring) runs last

**Agent C** works on skill markdown files + agent YAML + tests (4 stories):
- Stories 4.1-4.2 (skills by domain) + 4.3 (agent YAML) run in parallel
- Story 4.4 (tests) runs after 4.1-4.3 complete

### Track 2: After MVP completes (2 agents in parallel)

```
Agent A: Epic 6 (Request Handlers) ─────┐
                                         ├──> Epic 8 (FastAPI App)
Agent B: Epic 7 (GCP Adapters) ─────────┘
```

**Agent A** works on base handler + 4 domain handlers + conftest (6 stories):
- Story 6.1 (base handler) + 6.6 (conftest) run first
- Stories 6.2-6.5 (domain handlers) run in parallel after 6.1

**Agent B** works on 4 GCP adapter implementations + cloud test wiring (5 stories):
- Stories 7.1-7.4 (GCP adapters) run in parallel
- Story 7.5 (cloud test conftest) runs after 7.1-7.4

### Track 3: After Beta completes (2 agents in parallel)

```
Agent A: Epic 9 (GCP Infrastructure) ───┐
                                         ├──> Epic 11 (Docs + CI)
Agent B: Epic 10 (Scheduled Jobs) ──────┘
```

**Agent A** works on Terraform modules + deploy script (7 stories):
- Stories 9.1-9.4 (Terraform modules) run in parallel
- Story 9.5 (root Terraform) runs after 9.1-9.4
- Story 9.6 (deploy.sh) runs after 9.5
- Story 9.7 (config files) runs in parallel with 9.1-9.4

**Agent B** works on 3 scheduled job handlers + Dockerfile (4 stories):
- Stories 10.1-10.3 (job implementations) run in parallel
- Story 10.4 (Dockerfile/entry point) runs after 10.1-10.3

### Track 4: After Epics 9 and 10 complete (1 agent)

**Agent A** works on documentation, examples, and CI hardening (9 stories):
- Stories 11.1-11.6 (docs) run in parallel
- Story 11.7 (examples) runs in parallel with docs
- Story 11.8 (README) runs after other docs are available for cross-referencing
- Story 11.9 (scripts) runs in parallel

---

## Non-Goals (Phase 1)

The following are explicitly **out of scope** for Phase 1:

- **Tax preparer agent** — deferred to Phase 2
- **Compliance monitor agent** — deferred to Phase 2
- **Cashflow analyst agent** — deferred to Phase 2
- **501(c)(3) and 501(c)(6) skills** — deferred to Phase 2
- **Quarterly tax prep scheduled job** — deferred to Phase 2
- **OpenClaw implementation** — Phase 1 creates placeholder directories only; OpenClaw agent configs, skill manifests, workflows, and `install.sh` are deferred to Phase 2
- **AWS deployment** — AWS adapters (DynamoDB, Secrets Manager, SNS+SQS, EventBridge), Fargate deployment, and AWS Terraform are deferred to Phase 2
- **Azure deployment** — Azure adapters (Cosmos DB, Key Vault, Service Bus, Logic Apps), Container Apps deployment, and Azure Terraform are deferred to Phase 3
- **E-filing integration** — IRS e-file, state e-file, EFTPS payment automation are deferred to Phase 4
- **Web dashboard** — No browser-based UI; all interaction is via Slack
- **Multi-currency support** — USD only in Phase 1
- **Wave and Stripe MCP integrations** — QuickBooks MCP integration only in Phase 1; Wave and Stripe MCP servers are placeholder directories
- **State tax expansion** — NY state only in Phase 1; additional states are deferred
- **Cash flow forecasting** — Basic cash position and burn rate only; ML-based forecasting is deferred to Phase 3
- **Board reporting templates** — Basic report generation only; templated board packages are deferred

---

## Story Summary

| Sub-phase | Epic | Stories |
|-----------|------|---------|
| MVP | 1. Repository Scaffolding & CI Foundation | 5 |
| MVP | 2. Core Data Models | 4 |
| MVP | 3. Adapter Protocols & In-Memory Implementations | 11 |
| MVP | 4. CFO Skills & Agent Definitions | 4 |
| MVP | 5. Shared Utilities | 4 |
| Beta | 6. Request Handlers | 6 |
| Beta | 7. GCP Adapter Implementations | 5 |
| Beta | 8. FastAPI Application & Security | 7 |
| GA | 9. GCP Infrastructure & Deployment | 7 |
| GA | 10. Scheduled Jobs | 4 |
| GA | 11. Documentation, Examples & CI Hardening | 10 |
| **Total** | | **67** |
