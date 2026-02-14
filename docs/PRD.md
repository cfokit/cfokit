# CFOKit — Phase 1 Product Requirements Document

**Product:** CFOKit — The Open Source CFO Toolkit
**Phase:** 1 — Single-Business Bookkeeper on GCP
**Target Audience:** The author (single-member Delaware LLC with S-corp election, registered in NY, cash-basis consulting), and technically sophisticated open-source enthusiasts who want AI-assisted bookkeeping
**Date:** 2026-02-14

CFOKit is an open-source AI CFO toolkit. Phase 1 delivers a working bookkeeper agent for the author's business — a single-member Delaware LLC that elects S-corp taxation, registered in New York, operating on a cash basis as a consulting practice. The bookkeeper handles transaction categorization, report generation, and scheduled summaries — all driven by Claude AI with QuickBooks integration via MCP, deployed to GCP, and operated through Slack.

Multi-business support, additional agents (tax preparer, compliance monitor, cashflow analyst), and additional cloud providers are deferred to Phase 2+. This repository is the open-source project; operational concerns (monitoring, alerting, dashboards) for production deployment belong in a separate private infrastructure repository.

---

## Interaction Flows

Before defining stories, these sequence diagrams establish how the system actually works. All flows go through Claude AI, which uses QuickBooks MCP tools to read and write financial data.

### Transaction Categorization (On-Demand)

The core interaction. The user asks CFOKit to categorize recent transactions. Claude fetches uncategorized transactions from QuickBooks, applies domain knowledge from skills, categorizes each one, and updates QuickBooks.

```mermaid
sequenceDiagram
    actor User
    participant Slack
    participant FastAPI
    participant Handler as CategorizeHandler
    participant Claude as Claude AI
    participant MCP as QuickBooks MCP
    participant QB as QuickBooks API

    User->>Slack: "@cfokit categorize recent transactions"
    Slack->>FastAPI: POST /slack/events
    FastAPI->>FastAPI: Verify Slack signature
    FastAPI->>Handler: route("categorize", request)
    Handler->>Handler: Load bookkeeper skills
    Handler->>Claude: invoke(user_msg, skills, mcp_tools=[quickbooks])

    Claude->>MCP: tool: list_transactions(status="uncategorized", since="2026-02-01")
    MCP->>QB: GET /v3/company/{id}/query?query=SELECT * FROM Purchase WHERE ...
    QB-->>MCP: transactions[]
    MCP-->>Claude: transactions[]

    Claude->>MCP: tool: get_chart_of_accounts()
    MCP->>QB: GET /v3/company/{id}/query?query=SELECT * FROM Account
    QB-->>MCP: accounts[]
    MCP-->>Claude: accounts[]

    loop Each uncategorized transaction
        Claude->>Claude: Apply skills (deduction rules, category mapping)
        Claude->>MCP: tool: update_transaction(id, account_id, memo)
        MCP->>QB: POST /v3/company/{id}/purchase?operation=update
        QB-->>MCP: updated
        MCP-->>Claude: confirmed
    end

    Claude-->>Handler: "Categorized 12 transactions: 5 consulting revenue, 3 software, 2 meals, 1 travel, 1 office"
    Handler->>Firestore: save_audit_event(categorize, 12 transactions)
    Handler->>Slack: formatted summary message
    Slack-->>User: Summary with categories and any flagged items
```

### Report Generation

The user asks for a financial report. Claude pulls the data from QuickBooks and adds analysis.

```mermaid
sequenceDiagram
    actor User
    participant Slack
    participant FastAPI
    participant Handler as ReportHandler
    participant Claude as Claude AI
    participant MCP as QuickBooks MCP
    participant QB as QuickBooks API

    User->>Slack: "@cfokit January P&L"
    Slack->>FastAPI: POST /slack/events
    FastAPI->>Handler: route("report", request)
    Handler->>Claude: invoke(user_msg, skills, mcp_tools=[quickbooks])

    Claude->>MCP: tool: get_profit_and_loss(start="2026-01-01", end="2026-01-31")
    MCP->>QB: GET /v3/company/{id}/reports/ProfitAndLoss?...
    QB-->>MCP: P&L data
    MCP-->>Claude: P&L data

    Claude->>Claude: Analyze using skills (tax implications, trends)
    Claude-->>Handler: Formatted P&L with insights

    Handler->>Firestore: save_audit_event(report, "january_pl")
    Handler->>Slack: Formatted report
    Slack-->>User: P&L report with analysis
```

### Initial Setup

First-time configuration: the user connects QuickBooks via OAuth and sets business parameters.

```mermaid
sequenceDiagram
    actor User
    participant Slack
    participant FastAPI
    participant Handler as SetupHandler
    participant QB as QuickBooks OAuth
    participant SecretMgr as Secret Manager

    User->>Slack: "@cfokit setup"
    Slack->>FastAPI: POST /slack/events
    FastAPI->>Handler: route("setup", request)
    Handler->>Slack: "Configure your business: entity type, formation state, operating state, fiscal year"
    User->>Slack: "Single-member LLC with S-corp election, formed in DE, operating in NY, Jan 1"
    Slack->>FastAPI: POST /slack/events
    Handler->>Firestore: save_config(entity_type=s_corp, formation_state=DE, operating_state=NY, fiscal_year_start=01-01)

    Handler->>Slack: "Connect QuickBooks: [Authorize Link]"
    User->>QB: Click authorize link, grant access
    QB->>FastAPI: GET /oauth/callback?code=AUTH_CODE
    FastAPI->>QB: Exchange code for tokens
    QB-->>FastAPI: access_token, refresh_token
    FastAPI->>SecretMgr: Store tokens
    FastAPI->>Slack: "QuickBooks connected successfully!"
    Slack-->>User: Confirmation
```

### Daily Summary (Scheduled)

Automated daily job. Cloud Scheduler triggers a Cloud Run Job that reviews the previous day's activity.

```mermaid
sequenceDiagram
    participant Scheduler as Cloud Scheduler
    participant Job as Cloud Run Job
    participant Logic as DailySummaryJob
    participant Claude as Claude AI
    participant MCP as QuickBooks MCP
    participant QB as QuickBooks API
    participant Slack

    Scheduler->>Job: Trigger daily_summary
    Job->>Logic: run()
    Logic->>MCP: Start QuickBooks MCP server
    Logic->>Claude: invoke("Summarize yesterday's transactions", skills, mcp_tools)

    Claude->>MCP: tool: list_transactions(date=yesterday)
    MCP->>QB: GET /v3/company/{id}/query
    QB-->>MCP: transactions[]
    MCP-->>Claude: transactions[]

    Claude->>Claude: Generate summary with skills
    Claude-->>Logic: Summary with categories, totals, flagged items

    Logic->>Firestore: save_audit_event(daily_summary)
    Logic->>Slack: Post summary to configured channel
```

### Transaction Reclassification

The user asks to change a transaction's category. Claude finds and updates it.

```mermaid
sequenceDiagram
    actor User
    participant Slack
    participant FastAPI
    participant Handler as CategorizeHandler
    participant Claude as Claude AI
    participant MCP as QuickBooks MCP
    participant QB as QuickBooks API

    User->>Slack: "@cfokit move the Uber charge on Feb 3 from travel to meals"
    Slack->>FastAPI: POST /slack/events
    FastAPI->>Handler: route("categorize", request)
    Handler->>Claude: invoke(user_msg, skills, mcp_tools=[quickbooks])

    Claude->>MCP: tool: list_transactions(vendor="Uber", date="2026-02-03")
    MCP->>QB: GET /v3/company/{id}/query
    QB-->>MCP: matching transaction
    MCP-->>Claude: transaction details

    Claude->>MCP: tool: get_chart_of_accounts()
    MCP-->>Claude: accounts (finds "Meals & Entertainment")

    Claude->>MCP: tool: update_transaction(id, account_id=meals_account, memo="Reclassified per user request")
    MCP->>QB: POST /v3/company/{id}/purchase?operation=update
    QB-->>MCP: updated
    MCP-->>Claude: confirmed

    Claude-->>Handler: "Moved Uber charge ($24.50) from Travel to Meals & Entertainment"
    Handler->>Firestore: save_audit_event(reclassify, transaction_id)
    Handler->>Slack: Confirmation
    Slack-->>User: Confirmation with details
```

---

## Success Criteria

Phase 1 is **done** when:

- A user can message CFOKit in Slack and get transactions categorized in QuickBooks
- A user can request P&L and transaction summary reports via Slack
- QuickBooks OAuth connect flow works end-to-end
- QuickBooks MCP server reads and writes transactions via the QuickBooks API
- Scheduled jobs (daily summary, weekly review, monthly close) run automatically and post to Slack
- Business configuration (entity type, state, fiscal year) is persisted in Firestore
- Claude API usage is tracked and budget-capped
- Slack signature verification rejects unsigned/forged/replayed requests
- Sensitive data (OAuth tokens, API keys) is stored in Secret Manager, never in Firestore or logs
- GCP infrastructure deploys via `deploy.sh` with Terraform
- CI pipeline passes: lint, unit tests, integration tests
- Local development works in a dev container with zero manual setup
- Directory structure includes placeholder READMEs for AWS, Azure, and OpenClaw adapters

---

## Sub-phases

### Foundation (Weeks 1-3)

Build the repository, dev environment, data models, QuickBooks MCP server, skills, and shared utilities. At exit, a developer can clone the repo, open it in Claude Code or a dev container, and run `uv run pytest` with all tests passing.

**Exit criteria:**
- Dev container starts with all dependencies, emulators, and tooling pre-installed
- Transaction and BusinessConfig models pass validation tests
- QuickBooks MCP server exposes tools and passes tests against mock API
- Bookkeeper skills exist for consulting/cash-basis categorization
- Claude client, skill loader, MCP manager, and Slack client have tests
- `uv run pytest tests/unit/ -x` passes

### Core (Weeks 4-6)

Implement request handlers, GCP storage, and the FastAPI application with security. At exit, the application runs locally with the Firestore emulator and handles Slack webhook requests end-to-end.

**Exit criteria:**
- Categorize, report, setup, and help handlers pass unit tests
- Firestore storage layer passes tests against emulator
- Secret Manager wrapper works for token storage
- FastAPI app routes Slack events to handlers
- Slack signature verification rejects invalid requests
- Rate limiting and Claude API budget caps are enforced
- QuickBooks OAuth callback endpoint stores tokens in Secret Manager
- Integration tests pass with TestClient + in-memory storage + mocked Claude

### Deploy (Weeks 7-9)

GCP infrastructure via Terraform, scheduled jobs, and documentation. At exit, `deploy-cloud/gcp/deploy.sh` provisions infrastructure and deploys a working service.

**Exit criteria:**
- Terraform provisions Cloud Run, Firestore, Cloud Scheduler, and Secret Manager
- `deploy.sh` performs end-to-end deployment
- Daily summary, weekly review, and monthly close jobs run on Cloud Run Jobs
- README, getting started guide, and GCP deployment guide are complete
- Placeholder READMEs exist for AWS, Azure, and OpenClaw directories

---

## Epics

### Epic 1: Repository Scaffolding & Dev Environment

> Set up the project structure, tooling, CI pipeline, and dev container that all subsequent work depends on.

**Sub-phase:** Foundation
**Dependencies:** None

#### Story 1.1: Initialize repository with uv and pyproject.toml

Create the Python project with `uv init`, configure `pyproject.toml` with project metadata, Python 3.11+ requirement, and dependency groups.

**Acceptance criteria:**
- `pyproject.toml` exists with project name `cfokit`, Python `>=3.11`
- Dev dependencies: pytest, pytest-asyncio, pytest-cov, pytest-timeout, ruff, mypy
- Runtime dependencies: anthropic, fastapi, uvicorn, pydantic, slack-sdk, mcp, google-cloud-firestore, google-cloud-secret-manager, httpx, python-quickbooks
- `uv sync` succeeds and creates `uv.lock`
- `.python-version` specifies 3.11
- `pyproject.toml` includes `[tool.pytest.ini_options]` with `asyncio_mode = "auto"`, `timeout = 30`
- `pyproject.toml` includes `[tool.coverage.run]` and `[tool.coverage.report]`

**Key files:** `pyproject.toml`, `uv.lock`, `.python-version`
**Labels:** `epic:scaffolding`, `sub-phase:foundation`
**blocks:** `[1.2, 1.3, 1.4, 1.5]`

---

#### Story 1.2: Create directory structure

Create all directories and `__init__.py` files. Include placeholder `README.md` files in future-phase directories (AWS, Azure, OpenClaw) describing what will be added.

**Acceptance criteria:**
- `core/` tree: `skills/`, `agents/`, `integrations/quickbooks_mcp/`, `models/`, `shared/`
- `deploy-cloud/shared/handlers/`, `deploy-cloud/shared/middleware/`, `deploy-cloud/shared/routes/`, `deploy-cloud/shared/jobs/`
- `deploy-cloud/gcp/adapters/`, `deploy-cloud/gcp/agents/cfo_bot/`, `deploy-cloud/gcp/agents/scheduled_jobs/`, `deploy-cloud/gcp/terraform/`
- `deploy-cloud/aws/README.md` — "AWS adapters (DynamoDB, Secrets Manager, SNS+SQS) planned for Phase 2"
- `deploy-cloud/azure/README.md` — "Azure adapters (Cosmos DB, Key Vault, Service Bus) planned for Phase 3"
- `deploy-openclaw/README.md` — "OpenClaw integration planned for Phase 2"
- `tests/unit/`, `tests/integration/`, `tests/cloud/`, `tests/e2e/`, `tests/fixtures/`
- Every Python package directory has an `__init__.py`

**Key files:** All `__init__.py` files, placeholder READMEs
**Labels:** `epic:scaffolding`, `sub-phase:foundation`
**blocks:** `[2.1, 3.1, 4.1, 5.1]`

---

#### Story 1.3: Configure linting and type checking

Set up ruff and mypy in `pyproject.toml`. Expand `.gitignore` for Python projects.

**Acceptance criteria:**
- `pyproject.toml` includes `[tool.ruff]` and `[tool.ruff.lint]` configuration
- `pyproject.toml` includes `[tool.mypy]` configuration targeting `core/` and `deploy-cloud/shared/`
- `uv run ruff check .` and `uv run ruff format --check .` pass
- `.gitignore` covers Python artifacts (`.venv`, `__pycache__`, `*.pyc`), `.env`, IDE files, cloud credential files

**Key files:** `pyproject.toml` (ruff/mypy sections), `.gitignore`
**Labels:** `epic:scaffolding`, `sub-phase:foundation`

---

#### Story 1.4: Set up CI pipeline with GitHub Actions

Create the CI workflow with lint, unit test, and integration test jobs.

**Acceptance criteria:**
- `.github/workflows/test.yml` exists with jobs: `lint`, `unit`, `integration`
- `lint` job runs ruff check, ruff format --check, and mypy
- `unit` job runs pytest with coverage reporting
- `integration` job runs integration tests
- All `uses:` actions reference commit SHAs, not tags

**Key files:** `.github/workflows/test.yml`
**Labels:** `epic:scaffolding`, `sub-phase:foundation`

---

#### Story 1.5: Create dev container for Claude Code

Create `.devcontainer/devcontainer.json` and supporting scripts for zero-friction local development. The container must work in Claude Code cloud containers.

**Acceptance criteria:**
- `.devcontainer/devcontainer.json` specifies Python 3.11+ base image
- Container installs `uv`, Google Cloud SDK, and Firestore emulator
- `postCreateCommand` runs `uv sync` to install all dependencies
- `postStartCommand` starts Firestore emulator in background
- Firestore emulator is accessible at `localhost:8080`
- `.env.example` lists all required environment variables with descriptions and placeholder values
- Developer can open repo in Claude Code, wait for container setup, and immediately run `uv run pytest`

**Key files:** `.devcontainer/devcontainer.json`, `.devcontainer/setup.sh`, `.env.example`
**Labels:** `epic:scaffolding`, `sub-phase:foundation`

---

### Epic 2: Data Models

> Define the Pydantic models for the domain entities.

**Sub-phase:** Foundation
**Dependencies:** Epic 1

#### Story 2.1: Implement Transaction model

Create the `Transaction` Pydantic model for cash-basis consulting transactions. Fields: id, date, amount, vendor, description, account_name, account_id, transaction_type (income/expense), source (bank_feed/manual), quickbooks_id, categorized_by (ai/manual), categorized_at, raw_data (dict for original QuickBooks payload).

**Acceptance criteria:**
- `core/models/transaction.py` defines `Transaction` as a Pydantic `BaseModel`
- `TransactionType` enum: `income`, `expense`
- `CategorizationSource` enum: `ai`, `manual`, `uncategorized`
- Validators: amount must be positive (refunds modeled as negative-amount income), date must not be in the future
- Model serializes to/from dict for Firestore compatibility
- Unit tests cover validators (not Pydantic builtins)

**Key files:** `core/models/transaction.py`, `tests/unit/test_models/test_transaction.py`
**Labels:** `epic:models`, `sub-phase:foundation`
**blocks:** `[2.2]`

---

#### Story 2.2: Implement BusinessConfig model

Create the `BusinessConfig` model for single-business configuration. This replaces the multi-client `Client` model — Phase 1 supports one business only. The primary configuration is the author's business: a single-member Delaware LLC with S-corp election, registered in NY.

**Acceptance criteria:**
- `core/models/business_config.py` defines `BusinessConfig` with fields: entity_type (enum: sole_prop, s_corp, llc), formation_state (str, e.g. "DE"), operating_state (str, e.g. "NY"), fiscal_year_start (date), slack_channel_id, quickbooks_company_id, quickbooks_connected (bool), created_at, updated_at
- `EntityType` enum: `sole_prop`, `s_corp`, `llc` — note that `s_corp` covers both direct S-corps and LLCs electing S-corp taxation (the tax treatment, not the legal form, determines which skills load)
- `formation_state` and `operating_state` are tracked separately because they determine different tax obligations (e.g., Delaware franchise tax vs. NY state income tax)
- Entity type determines which skills are loaded (S-corp loads reasonable compensation skill)
- Unit tests cover entity type validation, state validation, and fiscal year constraints

**Key files:** `core/models/business_config.py`, `tests/unit/test_models/test_business_config.py`
**Labels:** `epic:models`, `sub-phase:foundation`
**blocks:** `[2.3]`

---

#### Story 2.3: Create test factories and conftest

Implement `tests/factories.py` with factories for Transaction and BusinessConfig. Wire into `tests/conftest.py`.

**Acceptance criteria:**
- `TransactionFactory.create(**overrides)` returns a valid Transaction with sensible defaults (consulting income, recent date, categorized)
- `BusinessConfigFactory.create(**overrides)` returns a valid BusinessConfig — defaults to `entity_type=s_corp, formation_state="DE", operating_state="NY"` matching the author's business
- `create_batch(n)` returns `n` instances with unique IDs
- `tests/conftest.py` provides `transaction_factory` and `config_factory` fixtures
- `tests/conftest.py` provides `fixtures_dir` path fixture
- `tests/fixtures/` contains `sample_transactions.json` with representative consulting business transactions: client consulting income, payroll (owner reasonable compensation), software subscriptions, meals, travel, office supplies, Delaware franchise tax payment, NY state tax payment

**Key files:** `tests/factories.py`, `tests/conftest.py`, `tests/fixtures/sample_transactions.json`
**Labels:** `epic:models`, `sub-phase:foundation`

---

### Epic 3: QuickBooks MCP Integration

> Implement the MCP server that gives Claude AI access to QuickBooks data. This is the bridge between Claude's intelligence and the user's actual financial data.

**Sub-phase:** Foundation
**Dependencies:** Epic 1

#### Story 3.1: Implement QuickBooks MCP server

Create the QuickBooks MCP server in `core/integrations/quickbooks_mcp/`. The server exposes tools that Claude can call to read and write QuickBooks data.

**MCP tools to implement:**
- `list_transactions(start_date, end_date, account_id?, status?)` — List transactions with optional filters
- `get_transaction(transaction_id)` — Get a single transaction
- `update_transaction(transaction_id, account_id, memo?)` — Update a transaction's account/category
- `get_profit_and_loss(start_date, end_date, accounting_method="Cash")` — P&L report
- `get_chart_of_accounts()` — List accounts for category mapping
- `get_company_info()` — Basic company details

**Acceptance criteria:**
- `core/integrations/quickbooks_mcp/server.py` uses the MCP SDK to define tools
- Each tool translates to the corresponding QuickBooks Online API call
- All QuickBooks API calls use the `python-quickbooks` library
- OAuth access token is retrieved from Secret Manager (via injected callback)
- Token refresh is handled automatically when access token expires
- All API URLs use HTTPS — reject HTTP
- Unit tests mock the QuickBooks API and verify: correct API endpoints called, proper query construction, error handling for API failures (rate limit, auth expired, not found)

**Key files:** `core/integrations/quickbooks_mcp/server.py`, `core/integrations/quickbooks_mcp/tools.py`, `tests/unit/test_quickbooks_mcp/test_server.py`, `tests/unit/test_quickbooks_mcp/test_tools.py`
**Labels:** `epic:quickbooks`, `sub-phase:foundation`
**blocks:** `[3.2]`

---

#### Story 3.2: Implement QuickBooks OAuth flow

Create the OAuth 2.0 flow for connecting QuickBooks. The flow is initiated from Slack and completed via a browser redirect.

**Acceptance criteria:**
- `core/integrations/quickbooks_mcp/oauth.py` provides:
  - `get_authorization_url()` — Generate QuickBooks OAuth URL with state parameter
  - `exchange_code(code, realm_id)` — Exchange authorization code for tokens
  - `refresh_access_token(refresh_token)` — Refresh expired access token
  - `get_valid_token()` — Return a valid access token, refreshing if needed
- State parameter uses a cryptographic random value to prevent CSRF
- Tokens are stored/retrieved via an injected secrets callback (for Secret Manager in prod, dict in tests)
- Access token expiry is tracked; refresh happens before expiry
- Refresh token expiry (100 days) is tracked with warning
- Unit tests mock QuickBooks OAuth endpoints and verify: authorization URL generation, code exchange, token refresh, CSRF state validation, error handling

**Key files:** `core/integrations/quickbooks_mcp/oauth.py`, `tests/unit/test_quickbooks_mcp/test_oauth.py`
**Labels:** `epic:quickbooks`, `sub-phase:foundation`

---

#### Story 3.3: Create QuickBooks MCP integration tests

Integration tests that verify the MCP server works end-to-end with a mock QuickBooks API. These tests exercise the full MCP tool → QuickBooks API → response pipeline.

**Acceptance criteria:**
- `tests/integration/test_quickbooks_mcp.py` starts the MCP server with mocked QuickBooks API
- Tests verify: list_transactions returns parsed Transaction-compatible data, update_transaction sends correct payload, get_profit_and_loss returns structured report, token refresh triggers automatically on 401, rate limit handling (retry with backoff)
- Tests do NOT call the real QuickBooks API

**Key files:** `tests/integration/test_quickbooks_mcp.py`
**Labels:** `epic:quickbooks`, `sub-phase:foundation`

---

### Epic 4: CFO Skills & Agent Definition

> Author the domain knowledge and agent configuration that power the bookkeeper's financial intelligence.

**Sub-phase:** Foundation
**Dependencies:** Epic 1

#### Story 4.1: Author bookkeeper skills for cash-basis consulting

Create markdown skill files with domain knowledge relevant to categorizing transactions for a cash-basis consulting business.

**Skills to author:**
- `core/skills/consulting/transaction_categorization.md` — Common consulting expense categories (professional services income, software/SaaS subscriptions, meals & entertainment, travel, office expenses, professional development, insurance), how to identify them, categorization rules for ambiguous transactions
- `core/skills/consulting/cash_basis_accounting.md` — Cash basis rules, when to recognize revenue and expenses, implications for a consulting business (retainers, milestone payments, prepaid expenses)
- `core/skills/federal_tax/meal_deductions.md` — 50% deduction rules, documentation requirements, business meal vs. personal
- `core/skills/federal_tax/home_office.md` — Home office deduction rules for consultants (simplified method vs. regular method)
- `core/skills/s_corp/reasonable_compensation.md` — IRS reasonable compensation rules for S-corp owner-employees, salary vs. distribution split, payroll tax implications, how this applies to single-member LLCs with S-corp election
- `core/skills/s_corp/payroll_obligations.md` — Payroll categorization for owner-employee: salary, employer payroll taxes (FICA, FUTA, SUI), how to categorize payroll service fees
- `core/skills/state/delaware_franchise_tax.md` — Delaware LLC annual franchise tax ($300 flat fee), due date (June 1), how to categorize the payment
- `core/skills/state/ny_state_obligations.md` — NY state filing requirements for a Delaware LLC registered as a foreign LLC in NY, NY state income tax, NYC considerations if applicable

**Acceptance criteria:**
- Each skill file is well-structured markdown with clear headings
- Content is accurate and actionable for Claude (not just reference material — includes decision rules)
- Skills are scoped to the author's specific situation: single-member LLC with S-corp election, cash basis, consulting
- Each skill is under 50KB

**Key files:** `core/skills/consulting/*.md`, `core/skills/federal_tax/*.md`, `core/skills/s_corp/*.md`, `core/skills/state/*.md`
**Labels:** `epic:skills`, `sub-phase:foundation`
**blocks:** `[4.3]`

---

#### Story 4.2: Create bookkeeper agent YAML definition

Create the YAML agent definition for the bookkeeper agent. This defines which skills, tools, and triggers the bookkeeper uses.

**Acceptance criteria:**
- `core/agents/bookkeeper.yaml` defines:
  - `name`: bookkeeper
  - `description`: AI bookkeeper for cash-basis consulting businesses
  - `skills`: list of skill file paths — consulting and federal tax skills always loaded; S-corp skills loaded when entity_type is s_corp; state skills loaded based on formation_state and operating_state
  - `tools`: quickbooks_mcp
  - `triggers`: on-demand (Slack), daily-summary, weekly-review, monthly-close
- YAML parses without errors

**Key files:** `core/agents/bookkeeper.yaml`
**Labels:** `epic:skills`, `sub-phase:foundation`
**blocks:** `[4.3]`

---

#### Story 4.3: Create skill and agent tests

Tests for skill structure and agent YAML validation.

**Acceptance criteria:**
- Parameterized test auto-discovers all `core/skills/**/*.md` files and verifies: non-empty, under 50KB
- Bookkeeper agent YAML is tested for: valid YAML parse, required fields present, listed skill files exist on disk
- New skill files are auto-discovered without test code changes

**Key files:** `tests/unit/test_skills/test_skill_files.py`, `tests/unit/test_skills/test_agent_yaml.py`
**Labels:** `epic:skills`, `sub-phase:foundation`

---

### Epic 5: Shared Utilities

> Implement the cloud-agnostic utilities that handlers and agents depend on.

**Sub-phase:** Foundation
**Dependencies:** Epics 1, 3, 4

#### Story 5.1: Implement Claude API client

Create `core/shared/claude_client.py` wrapping the Anthropic Claude API. Includes token budget tracking to prevent runaway API costs.

**Acceptance criteria:**
- Async client for Claude API invocation
- User input goes exclusively in user-role messages
- Skill content goes in system context only
- MCP tools are passed through for Claude to use
- Token budget tracking: configurable daily/monthly token limits, raises `BudgetExceededError` when limit is reached
- Token usage is logged per invocation (input tokens, output tokens, total)
- Client is injectable (constructor takes API key and budget config)
- Unit tests verify: prompt construction safety (user input not in system prompt), skill content not in user role, budget enforcement, error handling for API failures

**Key files:** `core/shared/claude_client.py`, `tests/unit/test_claude_client.py`
**Labels:** `epic:utilities`, `sub-phase:foundation`

---

#### Story 5.2: Implement skill loader

Create `core/shared/skill_loader.py` that loads markdown skill files. Entity-type-aware: loads different skills based on the business configuration.

**Acceptance criteria:**
- `load_skills(agent_name, entity_type?)` loads the skills listed in the agent's YAML definition
- Entity type filtering: loads S-corp skills when entity_type is s_corp, state-specific skills based on formation_state and operating_state
- Path traversal protection: rejects `..`, absolute paths, and null bytes
- Returns dict mapping skill name → content string
- Unit tests: valid loading, entity-type filtering, path traversal rejection, nonexistent skill handling

**Key files:** `core/shared/skill_loader.py`, `tests/unit/test_skill_loader.py`
**Labels:** `epic:utilities`, `sub-phase:foundation`

---

#### Story 5.3: Implement MCP manager

Create `core/shared/mcp_manager.py` for managing MCP server connections. In Phase 1 this manages the QuickBooks MCP server only.

**Acceptance criteria:**
- `MCPManager` handles MCP server lifecycle (start, connect, disconnect)
- Rejects `http://` URLs with `ValueError` — HTTPS only
- Provides method to get the MCP tools list for passing to Claude
- Connection health checking
- Unit tests: HTTPS enforcement, lifecycle management, tool listing

**Key files:** `core/shared/mcp_manager.py`, `tests/unit/test_mcp_manager.py`
**Labels:** `epic:utilities`, `sub-phase:foundation`

---

#### Story 5.4: Implement Slack client

Create `core/shared/slack_client.py` for sending messages and formatting responses for Slack.

**Acceptance criteria:**
- Async methods for sending messages and responding to slash commands
- Message formatting supports Slack markdown blocks (headers, code blocks, bullet lists)
- Constructor takes bot token (injectable)
- Unit tests mock Slack API: message payload structure, channel targeting, error handling

**Key files:** `core/shared/slack_client.py`, `tests/unit/test_slack_client.py`
**Labels:** `epic:utilities`, `sub-phase:foundation`

---

### Epic 6: Request Handlers

> Implement the cloud-agnostic request handlers that process user commands. These live in `deploy-cloud/shared/` and depend on injected storage and utilities.

**Sub-phase:** Core
**Dependencies:** Epics 2, 3, 5

#### Story 6.1: Implement base handler

Create `deploy-cloud/shared/handlers/base_handler.py` with shared functionality for all handlers.

**Acceptance criteria:**
- `BaseHandler.__init__` accepts storage, secrets, claude_client, mcp_manager, slack_client, skill_loader
- `_emit_audit_event(action, details)` writes to `audit_events` collection — never includes secret values, tokens, or API keys
- `_format_error(error)` returns a user-friendly message with correlation ID — never includes stack traces, file paths, or internal details
- Unit tests verify: audit event structure, audit events do not contain secrets, error formatting excludes sensitive data

**Key files:** `deploy-cloud/shared/handlers/base_handler.py`, `tests/unit/test_handlers/test_base_handler.py`
**Labels:** `epic:handlers`, `sub-phase:core`
**blocks:** `[6.2, 6.3, 6.4, 6.5]`

---

#### Story 6.2: Implement categorize handler

The primary handler. Invokes Claude with bookkeeper skills and QuickBooks MCP tools to categorize transactions.

**Acceptance criteria:**
- `CategorizeHandler` extends `BaseHandler`
- `handle(request)` invokes Claude with:
  - User's message as the user prompt
  - Loaded bookkeeper skills as system context
  - QuickBooks MCP tools available for Claude to use
- Claude autonomously fetches transactions, categorizes them, and updates QuickBooks
- Handler captures Claude's summary response and sends to Slack
- Emits audit event with transaction count and categories
- Handles errors: QuickBooks connection failure, Claude API failure, budget exceeded
- Unit tests use mocked Claude client and mocked MCP; verify handler orchestration and error paths

**Key files:** `deploy-cloud/shared/handlers/categorize.py`, `tests/unit/test_handlers/test_categorize.py`
**Labels:** `epic:handlers`, `sub-phase:core`

---

#### Story 6.3: Implement report handler

Generates financial reports by invoking Claude with QuickBooks MCP tools.

**Acceptance criteria:**
- `ReportHandler` extends `BaseHandler`
- Supports report types: `monthly_pl`, `transaction_summary`
- Claude fetches data from QuickBooks and generates analysis
- Reports are sent to Slack and optionally saved to Firestore
- Emits audit event
- Unit tests verify report request routing and response formatting

**Key files:** `deploy-cloud/shared/handlers/report.py`, `tests/unit/test_handlers/test_report.py`
**Labels:** `epic:handlers`, `sub-phase:core`

---

#### Story 6.4: Implement setup handler

Guides business configuration and triggers QuickBooks OAuth connection.

**Acceptance criteria:**
- `SetupHandler` extends `BaseHandler`
- `handle(request)` creates or updates BusinessConfig in storage
- Validates entity type, state, fiscal year start
- Generates QuickBooks OAuth authorization URL when user requests connection
- Emits audit event for configuration changes
- Unit tests verify: config creation, validation errors, OAuth URL generation

**Key files:** `deploy-cloud/shared/handlers/setup.py`, `tests/unit/test_handlers/test_setup.py`
**Labels:** `epic:handlers`, `sub-phase:core`

---

#### Story 6.5: Implement help handler

Returns usage information and available commands.

**Acceptance criteria:**
- `HelpHandler` extends `BaseHandler`
- Returns available commands (categorize, report, setup, help) with usage examples
- Response formatted for Slack markdown
- Stateless — no storage access needed
- Unit test verifies response contains expected command names

**Key files:** `deploy-cloud/shared/handlers/help.py`, `tests/unit/test_handlers/test_help.py`
**Labels:** `epic:handlers`, `sub-phase:core`

---

### Epic 7: GCP Storage & Secrets

> Implement the GCP-specific storage and secrets layers. These are direct implementations against GCP services, not Protocol-based abstractions. The adapter pattern will be extracted when adding AWS in Phase 2.

**Sub-phase:** Core
**Dependencies:** Epic 1

#### Story 7.1: Implement Firestore storage layer

Create `deploy-cloud/gcp/adapters/storage.py` with typed methods for reading and writing domain objects to Firestore.

**Acceptance criteria:**
- `FirestoreStorage` provides async methods:
  - `save_transaction(transaction)` / `get_transaction(id)` / `list_transactions(date_from, date_to, account_id?)`
  - `save_config(config)` / `get_config()`
  - `save_audit_event(event)`
  - `query_transactions(filters)` for flexible querying
- Uses `google-cloud-firestore` async client
- All data is stored under a single project namespace (no multi-tenant namespacing for Phase 1)
- Documents are serialized/deserialized to/from Pydantic models
- Firestore indexes are defined in `deploy-cloud/gcp/firestore-indexes.json`

**Key files:** `deploy-cloud/gcp/adapters/storage.py`, `deploy-cloud/gcp/firestore-indexes.json`
**Labels:** `epic:gcp`, `sub-phase:core`
**blocks:** `[7.3]`

---

#### Story 7.2: Implement Secret Manager wrapper

Create `deploy-cloud/gcp/adapters/secrets.py` for reading and writing secrets (QuickBooks tokens, API keys).

**Acceptance criteria:**
- `SecretManagerClient` provides async methods:
  - `get_secret(name)` — Get latest version of a secret
  - `set_secret(name, value)` — Create or add new version
- Used by QuickBooks OAuth for token storage/retrieval
- `__repr__` and `__str__` never expose secret values
- Unit tests mock Secret Manager API

**Key files:** `deploy-cloud/gcp/adapters/secrets.py`, `tests/unit/test_gcp/test_secrets.py`
**Labels:** `epic:gcp`, `sub-phase:core`

---

#### Story 7.3: Create GCP cloud tests

Tests that run against the Firestore emulator to verify the storage layer works with real Firestore behavior.

**Acceptance criteria:**
- `tests/cloud/test_firestore_storage.py` tests all `FirestoreStorage` methods against emulator
- Tests cover: save/get round-trip, list with date filters, query operations, audit event storage, config persistence
- Session-scoped emulator fixture, function-scoped data cleanup
- Tests skip if `FIRESTORE_EMULATOR_HOST` is not set
- Tests marked with `@pytest.mark.gcp`

**Key files:** `tests/cloud/conftest.py`, `tests/cloud/test_firestore_storage.py`
**Labels:** `epic:gcp`, `sub-phase:core`

---

### Epic 8: FastAPI Application & Security

> Build the FastAPI application with security middleware and wire everything together.

**Sub-phase:** Core
**Dependencies:** Epics 5, 6, 7

#### Story 8.1: Create FastAPI application factory and GCP wiring

Create the app factory and the GCP-specific `app.py` that wires concrete implementations.

**Acceptance criteria:**
- `deploy-cloud/shared/app_factory.py` provides `create_app(storage, secrets, claude_client, mcp_manager, slack_client, skill_loader)` returning a FastAPI instance
- Routes registered: `/slack/events` (POST), `/slack/commands` (POST), `/oauth/quickbooks/callback` (GET), `/health` (GET)
- `deploy-cloud/gcp/agents/cfo_bot/app.py` imports GCP implementations, instantiates them, and passes to `create_app()`
- `deploy-cloud/gcp/agents/cfo_bot/Dockerfile` builds a production container
- Application starts with `uvicorn`

**Key files:** `deploy-cloud/shared/app_factory.py`, `deploy-cloud/gcp/agents/cfo_bot/app.py`, `deploy-cloud/gcp/agents/cfo_bot/Dockerfile`
**Labels:** `epic:fastapi`, `sub-phase:core`
**blocks:** `[8.2, 8.3, 8.4, 8.5]`

---

#### Story 8.2: Implement Slack signature verification middleware

Verify Slack request signatures on all `/slack/*` endpoints.

**Acceptance criteria:**
- Middleware validates `X-Slack-Signature` using HMAC-SHA256 with signing secret
- Requests without signature headers return 401
- Requests with invalid signatures return 401
- Requests with timestamps older than 5 minutes return 401 (replay protection)
- Valid signatures pass through to handlers
- Unit tests: missing signature, invalid signature, expired timestamp, valid signature

**Key files:** `deploy-cloud/shared/middleware/slack_auth.py`, `tests/unit/test_middleware/test_slack_auth.py`
**Labels:** `epic:fastapi`, `sub-phase:core`

---

#### Story 8.3: Implement rate limiting and Claude API budget caps

Rate limiting for Slack requests and budget enforcement for Claude API usage.

**Acceptance criteria:**
- Request rate limiter: configurable threshold and window, returns 429 on breach
- Claude API budget: daily and monthly token limits (configurable via environment variables)
- Budget state persisted in Firestore (survives restarts)
- When budget is exceeded, handler returns a friendly "budget limit reached" message to Slack instead of processing the request
- Unit tests: rate limit enforcement, budget tracking, budget exceeded behavior

**Key files:** `deploy-cloud/shared/middleware/rate_limit.py`, `tests/unit/test_middleware/test_rate_limit.py`
**Labels:** `epic:fastapi`, `sub-phase:core`

---

#### Story 8.4: Implement Slack event routing and health endpoint

Route incoming Slack events to the appropriate handler. Health endpoint for load balancer probes.

**Acceptance criteria:**
- `/slack/events` handles Slack event callbacks (URL verification challenge, message events)
- `/slack/commands` handles slash command payloads
- Command parser extracts intent (categorize, report, setup, help) from message text
- Unknown commands route to help handler
- Invalid payloads return appropriate error responses (no stack traces, no internal paths)
- GET `/health` returns `{"status": "healthy"}` — no version numbers, no internal IPs
- Health response includes security headers (X-Content-Type-Options, X-Frame-Options)
- Unit tests and integration tests verify routing logic

**Key files:** `deploy-cloud/shared/routes/slack.py`, `deploy-cloud/shared/routes/health.py`, `tests/unit/test_routes/test_slack.py`, `tests/integration/test_fastapi_app.py`
**Labels:** `epic:fastapi`, `sub-phase:core`

---

#### Story 8.5: Implement QuickBooks OAuth callback endpoint

Handle the OAuth redirect after the user authorizes QuickBooks access.

**Acceptance criteria:**
- GET `/oauth/quickbooks/callback` receives authorization code and realm_id from QuickBooks
- Validates CSRF state parameter against stored state
- Exchanges code for access + refresh tokens via `quickbooks_oauth.exchange_code()`
- Stores tokens in Secret Manager
- Updates BusinessConfig with `quickbooks_connected=True` and `quickbooks_company_id`
- Redirects to a success page or returns success HTML
- Error handling: invalid state, expired code, QuickBooks API errors
- Unit tests mock QuickBooks OAuth and verify token storage

**Key files:** `deploy-cloud/shared/routes/oauth.py`, `tests/unit/test_routes/test_oauth.py`
**Labels:** `epic:fastapi`, `sub-phase:core`

---

#### Story 8.6: Create integration test suite

Integration tests using FastAPI TestClient with mocked storage and Claude client.

**Acceptance criteria:**
- `tests/integration/conftest.py` creates TestClient via `create_app()` with in-memory storage mock and mocked Claude/MCP
- Tests cover: Slack signature verification end-to-end, command routing (categorize/report/setup/help), handler invocation and response format, health endpoint
- Multi-step flow test: setup → categorize → report
- All integration tests pass without external services

**Key files:** `tests/integration/conftest.py`, `tests/integration/test_fastapi_app.py`, `tests/integration/test_handler_flows.py`
**Labels:** `epic:fastapi`, `sub-phase:core`

---

### Epic 9: Scheduled Jobs

> Implement automated scheduled jobs. Business logic lives in `deploy-cloud/shared/jobs/` (cloud-agnostic). The GCP-specific entry point in `deploy-cloud/gcp/` is a thin wrapper.

**Sub-phase:** Deploy
**Dependencies:** Epics 5, 6, 7, 8

#### Story 9.1: Implement daily summary job

Review the previous day's transactions and post a summary to Slack.

**Acceptance criteria:**
- `deploy-cloud/shared/jobs/daily_summary.py` contains the business logic
- Invokes Claude with QuickBooks MCP tools to fetch yesterday's transactions
- Generates summary: transaction count, total income, total expenses, categories breakdown, flagged items
- Posts formatted summary to configured Slack channel
- Emits audit event
- Unit tests verify summary generation and Slack message structure

**Key files:** `deploy-cloud/shared/jobs/daily_summary.py`, `tests/unit/test_jobs/test_daily_summary.py`
**Labels:** `epic:jobs`, `sub-phase:deploy`

---

#### Story 9.2: Implement weekly review job

Generate a weekly financial summary with trends.

**Acceptance criteria:**
- `deploy-cloud/shared/jobs/weekly_review.py` contains the business logic
- Fetches the week's data via Claude + QuickBooks MCP
- Includes: total income/expenses, top spending categories, week-over-week comparison, action items
- Posts to Slack
- Emits audit event
- Unit tests verify metrics and message format

**Key files:** `deploy-cloud/shared/jobs/weekly_review.py`, `tests/unit/test_jobs/test_weekly_review.py`
**Labels:** `epic:jobs`, `sub-phase:deploy`

---

#### Story 9.3: Implement monthly close job

Generate month-end close package.

**Acceptance criteria:**
- `deploy-cloud/shared/jobs/monthly_close.py` contains the business logic
- Generates: P&L summary, expense breakdown by category, uncategorized transaction alerts, reconciliation checklist
- Posts close package to Slack and persists to Firestore
- Emits audit event
- Unit tests verify close package structure

**Key files:** `deploy-cloud/shared/jobs/monthly_close.py`, `tests/unit/test_jobs/test_monthly_close.py`
**Labels:** `epic:jobs`, `sub-phase:deploy`

---

#### Story 9.4: Create Cloud Run Jobs entry point

GCP-specific entry point that instantiates dependencies and dispatches to the cloud-agnostic job logic.

**Acceptance criteria:**
- `deploy-cloud/gcp/agents/scheduled_jobs/main.py` accepts job name as argument (`daily_summary`, `weekly_review`, `monthly_close`)
- Instantiates Firestore storage, Secret Manager, Claude client, MCP manager, Slack client
- Calls the appropriate shared job function
- `deploy-cloud/gcp/agents/scheduled_jobs/Dockerfile` builds the container
- Exit code reflects success (0) or failure (non-zero)

**Key files:** `deploy-cloud/gcp/agents/scheduled_jobs/main.py`, `deploy-cloud/gcp/agents/scheduled_jobs/Dockerfile`
**Labels:** `epic:jobs`, `sub-phase:deploy`

---

### Epic 10: GCP Infrastructure & Deployment

> Terraform modules and deployment automation.

**Sub-phase:** Deploy
**Dependencies:** Epics 7, 8, 9

#### Story 10.1: Create Terraform modules

Create Terraform modules for all GCP resources.

**Acceptance criteria:**
- `deploy-cloud/gcp/terraform/modules/cloud_run/` — Cloud Run service (cfo_bot) and Cloud Run Jobs (scheduled jobs)
- `deploy-cloud/gcp/terraform/modules/firestore/` — Firestore database and indexes
- `deploy-cloud/gcp/terraform/modules/scheduler/` — Cloud Scheduler jobs (daily/weekly/monthly triggers)
- `deploy-cloud/gcp/terraform/modules/secrets/` — Secret Manager secrets (API keys, OAuth tokens)
- Each module has `main.tf`, `variables.tf`, `outputs.tf`
- `terraform validate` passes for each module
- Secret Manager configuration includes IAM bindings (Cloud Run service account can read secrets)

**Key files:** `deploy-cloud/gcp/terraform/modules/*/`
**Labels:** `epic:infra`, `sub-phase:deploy`
**blocks:** `[10.2]`

---

#### Story 10.2: Create root Terraform configuration

Compose all modules into a deployable configuration.

**Acceptance criteria:**
- `deploy-cloud/gcp/terraform/main.tf` composes cloud_run, firestore, scheduler, and secrets modules
- `variables.tf` defines all required variables with descriptions and validation (project_id, region, slack_channel, etc.)
- `outputs.tf` exposes Cloud Run service URL, Firestore database name, OAuth callback URL
- `terraform.tfvars.example` documents all variables
- `terraform validate` passes

**Key files:** `deploy-cloud/gcp/terraform/main.tf`, `variables.tf`, `outputs.tf`, `terraform.tfvars.example`
**Labels:** `epic:infra`, `sub-phase:deploy`
**blocks:** `[10.3]`

---

#### Story 10.3: Create deploy script

One-click deployment script.

**Acceptance criteria:**
- `deploy-cloud/gcp/deploy.sh` automates: prerequisite checks (gcloud, terraform, docker), Docker image build and push to Artifact Registry, `terraform init && terraform apply`, secret configuration (prompts for values or reads from env), outputs the Cloud Run service URL and OAuth callback URL
- Script is idempotent (safe to re-run)
- `--dry-run` flag previews changes without applying
- Script does not contain hardcoded secrets

**Key files:** `deploy-cloud/gcp/deploy.sh`
**Labels:** `epic:infra`, `sub-phase:deploy`

---

#### Story 10.4: Create GCP configuration files

Supporting configuration files for the GCP deployment.

**Acceptance criteria:**
- `deploy-cloud/gcp/slack/app-manifest.yaml` — Slack app configuration (OAuth scopes, event subscriptions, slash commands)
- `deploy-cloud/gcp/slack/setup-guide.md` — Step-by-step Slack app setup
- `deploy-cloud/gcp/cloud-run-service.yaml` — Cloud Run service config (scaling, resources, env)
- `deploy-cloud/gcp/cloud-run-jobs.yaml` — Cloud Run Jobs config for 3 scheduled tasks

**Key files:** `deploy-cloud/gcp/slack/`, `deploy-cloud/gcp/cloud-run-*.yaml`
**Labels:** `epic:infra`, `sub-phase:deploy`

---

#### Story 10.5: Configure encryption and IAM

Ensure sensitive data is encrypted and access is minimized.

**Acceptance criteria:**
- Firestore data encrypted at rest (GCP default, documented)
- All secrets stored in Secret Manager, never in Firestore, environment variables in production, or application logs
- Cloud Run service account has minimum required IAM roles (Firestore read/write, Secret Manager accessor, Pub/Sub publisher)
- Scheduled jobs service account is scoped to required permissions only
- OAuth tokens stored in Secret Manager with restricted access
- Documented in `deploy-cloud/gcp/terraform/README.md`: IAM roles, encryption configuration, secret rotation procedure

**Key files:** `deploy-cloud/gcp/terraform/README.md`, IAM configuration in Terraform modules
**Labels:** `epic:infra`, `sub-phase:deploy`

---

### Epic 11: Documentation

> Minimum viable documentation for the open-source release.

**Sub-phase:** Deploy
**Dependencies:** All previous epics

#### Story 11.1: Write README

The project's front door. Should communicate what CFOKit does, how to get started, and what's coming next.

**Acceptance criteria:**
- Tagline and value proposition
- Feature summary (bookkeeper agent, QuickBooks integration, Slack interface, scheduled summaries)
- Quick start (link to getting started guide)
- Architecture overview (link to architecture section)
- Current limitations (single business, GCP only, cash basis only)
- Roadmap: multi-business, AWS/Azure, OpenClaw, additional agents
- Contributing section
- License (MIT)

**Key files:** `README.md`
**Labels:** `epic:docs`, `sub-phase:deploy`

---

#### Story 11.2: Write getting started guide

End-to-end guide from zero to working deployment.

**Acceptance criteria:**
- Prerequisites: GCP account, Slack workspace, QuickBooks Online account, Anthropic API key
- Dev container setup (clone, open in Claude Code, automatic environment)
- GCP deployment walkthrough (deploy.sh)
- Slack app setup (reference setup-guide.md)
- QuickBooks connection (OAuth flow walkthrough)
- First interaction walkthrough (setup → categorize → report)
- Troubleshooting common issues

**Key files:** `docs/getting-started.md`
**Labels:** `epic:docs`, `sub-phase:deploy`

---

#### Story 11.3: Write GCP deployment guide

Detailed deployment reference beyond the quick start.

**Acceptance criteria:**
- Terraform variable reference table
- IAM and security configuration
- Cost estimation for a single business
- Secret rotation procedures
- Updating and redeploying

**Key files:** `docs/deployment-guide-gcp.md`
**Labels:** `epic:docs`, `sub-phase:deploy`

---

## Epic Dependency Graph

```
                    ┌─────────────────────────────────────┐
                    │  Epic 1: Scaffolding & Dev Env       │
                    │        (no dependencies)             │
                    └──────┬──────────┬──────────┬─────────┘
                           │          │          │
                    ┌──────▼──┐  ┌────▼────┐  ┌──▼──────────┐
                    │ Epic 2  │  │ Epic 3  │  │   Epic 4    │
                    │ Models  │  │QuickBooks│  │Skills/Agent │
                    │         │  │  MCP    │  │             │
                    └────┬────┘  └────┬────┘  └──────┬──────┘
                         │            │              │
                         │            └──────┬───────┘
                         │                   │
                         │           ┌───────▼───────┐
                         │           │   Epic 5      │
                         │           │  Utilities    │
                         │           └───────┬───────┘
                         │                   │
                    ┌────▼───────────────────▼──┐  ┌──────────────┐
                    │       Epic 6              │  │   Epic 7     │
                    │    Request Handlers       │  │  GCP Storage │
                    └──────────┬────────────────┘  └──────┬───────┘
                               │                          │
                           ┌───▼──────────────────────────▼──┐
                           │         Epic 8                  │
                           │   FastAPI App + Security        │
                           └───┬─────────────────────────┬───┘
                               │                         │
                        ┌──────▼──────┐          ┌───────▼──────┐
                        │  Epic 9     │          │   Epic 10    │
                        │Sched. Jobs  │          │  GCP Infra   │
                        └──────┬──────┘          └───────┬──────┘
                               │                         │
                           ┌───▼─────────────────────────▼──┐
                           │          Epic 11               │
                           │       Documentation            │
                           └────────────────────────────────┘
```

---

## Parallel Execution Tracks

### Track 1: After Epic 1 completes (3 agents in parallel)

```
Agent A: Epic 2 (Data Models) ─────────────────────┐
Agent B: Epic 3 (QuickBooks MCP) ──────────────────┤──> Epic 5 (Utilities)
Agent C: Epic 4 (Skills & Agent Definition) ───────┘
```

### Track 2: After Foundation completes (2 agents in parallel)

```
Agent A: Epic 6 (Request Handlers) ─────┐
                                         ├──> Epic 8 (FastAPI App)
Agent B: Epic 7 (GCP Storage & Secrets) ┘
```

### Track 3: After Core completes (2 agents in parallel)

```
Agent A: Epic 9 (Scheduled Jobs) ──────────┐
                                            ├──> Epic 11 (Documentation)
Agent B: Epic 10 (GCP Infrastructure) ─────┘
```

---

## Non-Goals (Phase 1)

The following are explicitly **out of scope** for Phase 1:

- **Multi-business support** — Phase 1 supports a single business only. Multi-business with per-business agent instances is deferred to Phase 2.
- **Additional agents** — Tax preparer, compliance monitor, and cashflow analyst agents are deferred to Phase 2.
- **Adapter protocol abstraction** — Phase 1 builds directly against GCP. Protocol-based abstractions will be extracted when adding AWS in Phase 2.
- **AWS deployment** — Deferred to Phase 2.
- **Azure deployment** — Deferred to Phase 3.
- **OpenClaw integration** — Deferred to Phase 2. Placeholder README only.
- **Accrual basis accounting** — Cash basis only in Phase 1.
- **Wave and Stripe integrations** — QuickBooks only in Phase 1.
- **Nonprofit entity types** (501(c)(3), 501(c)(6)) — Deferred to Phase 2. Phase 1 supports sole_prop, s_corp (including LLCs with S-corp election), and llc.
- **E-filing integration** — Deferred to Phase 4.
- **Web dashboard** — All interaction is via Slack.
- **Multi-currency** — USD only.
- **State tax expansion** — Federal + Delaware + NY only in Phase 1. Additional states deferred.
- **Operational automation** (monitoring, alerting, dashboards) — Belongs in a separate private infrastructure repository, not this open-source project.
- **CLI interface** — Slack is the primary interface for Phase 1. CLI may be added in Phase 2 for developer convenience.

---

## Story Summary

| Sub-phase | Epic | Stories |
|-----------|------|---------|
| Foundation | 1. Repository Scaffolding & Dev Environment | 5 |
| Foundation | 2. Data Models | 3 |
| Foundation | 3. QuickBooks MCP Integration | 3 |
| Foundation | 4. CFO Skills & Agent Definition | 3 |
| Foundation | 5. Shared Utilities | 4 |
| Core | 6. Request Handlers | 5 |
| Core | 7. GCP Storage & Secrets | 3 |
| Core | 8. FastAPI Application & Security | 6 |
| Deploy | 9. Scheduled Jobs | 4 |
| Deploy | 10. GCP Infrastructure & Deployment | 5 |
| Deploy | 11. Documentation | 3 |
| **Total** | | **44** |
