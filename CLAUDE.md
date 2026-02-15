# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CFOKit is an open-source AI CFO toolkit — an AI bookkeeper agent that categorizes transactions, generates reports, and posts automated financial summaries for a cash-basis consulting business. Built for the author's business (single-member Delaware LLC with S-corp election, registered in NY) but configurable for other entity types. Uses Anthropic Claude AI, QuickBooks integration via Model Context Protocol (MCP), and deploys to GCP.

**Status:** Greenfield project. `docs/PRD.md` defines the Phase 1 scope, architecture, and all stories. Treat it as the authoritative source of truth for implementation decisions.

**Phase 1 scope:** Single-business bookkeeper on GCP. Multi-business support, additional agents (tax preparer, compliance monitor, cashflow analyst), and additional cloud providers (AWS, Azure, OpenClaw) are deferred to Phase 2+.

## Tech Stack

- **Language:** Python 3.11+
- **Package manager:** uv (with `pyproject.toml` and `uv.lock`)
- **AI:** Anthropic Claude API
- **Integrations:** Intuit's official QuickBooks Online MCP server ([intuit/quickbooks-online-mcp-server](https://github.com/intuit/quickbooks-online-mcp-server)), TypeScript/Node.js, runs as subprocess
- **Cloud services:** GCP — Firestore, Secret Manager, Cloud Run, Cloud Scheduler
- **Testing:** pytest, pytest-asyncio
- **Infrastructure:** Terraform (GCP-specific), Docker
- **User interface:** Slack bot
- **Local dev:** Dev containers (Claude Code cloud containers)

## Architecture

The codebase follows a three-layer architecture: platform-agnostic core, cloud-agnostic handlers/jobs, and GCP-specific implementations.

```
core/                        # Shared business logic (platform-agnostic)
├── skills/                  # CFO domain knowledge as markdown
│   ├── consulting/          # Transaction categorization, cash basis accounting
│   ├── federal_tax/         # Meal deductions, home office
│   ├── s_corp/              # Reasonable compensation, payroll obligations
│   └── state/               # Delaware franchise tax, NY state obligations
├── agents/                  # Agent definitions in YAML (bookkeeper)
├── integrations/
│   └── quickbooks_mcp/      # Config + OAuth for Intuit's QBO MCP server (external)
├── models/                  # Pydantic data models (Transaction, BusinessConfig)
└── shared/                  # Cloud-agnostic utilities
    ├── claude_client.py     # Claude API wrapper with token budget tracking
    ├── skill_loader.py      # Entity-type-aware skill loading
    ├── mcp_manager.py       # MCP server lifecycle (spawns Intuit QBO server as Node.js subprocess over stdio)
    └── slack_client.py      # Slack message formatting and sending

deploy-cloud/                # Cloud deployment
├── shared/                  # Cloud-agnostic request handlers and jobs
│   ├── handlers/            # base_handler, categorize, report, setup, help
│   ├── middleware/          # slack_auth, rate_limit
│   ├── routes/              # slack events, health, oauth callback
│   ├── jobs/                # daily_summary, weekly_review, monthly_close
│   └── app_factory.py       # FastAPI app factory
├── gcp/                     # GCP implementation (Phase 1)
│   ├── adapters/            # Firestore storage, Secret Manager
│   ├── agents/
│   │   ├── cfo_bot/         # Cloud Run service (app.py, Dockerfile)
│   │   └── scheduled_jobs/  # Cloud Run Jobs entry point
│   └── terraform/           # GCP Terraform modules
├── aws/README.md            # Placeholder — Phase 2
└── azure/README.md          # Placeholder — Phase 3

deploy-openclaw/README.md    # Placeholder — Phase 2

tests/
├── unit/                    # Unit tests (mocked dependencies)
├── integration/             # Integration tests (TestClient, in-memory storage)
├── cloud/                   # GCP emulator tests
├── e2e/                     # Post-deploy smoke tests
├── fixtures/                # Sample data files
├── factories.py             # Test data factories
└── conftest.py              # Shared fixtures
```

**Key design principles:**
- Skills are universal markdown files containing domain knowledge (tax rules, categorization guidelines)
- Agent definitions are portable YAML (skills, tools, triggers)
- Phase 1 builds directly against GCP — no adapter protocol abstraction. Protocols will be extracted when adding AWS in Phase 2.
- `deploy-cloud/shared/` code must not import cloud-specific SDKs
- `core/` must remain platform-agnostic — no cloud-provider imports
- Scheduled job business logic lives in `deploy-cloud/shared/jobs/`, not in GCP-specific code
- Only `app.py` in the GCP directory wires concrete implementations via the app factory

**Data flow:** Slack -> FastAPI (Cloud Run) -> Claude AI + Skills + Intuit QBO MCP Server (subprocess) -> QuickBooks API -> Firestore (audit events, config)

## Build & Development Commands

```bash
# Dev container handles setup automatically (uv sync, Firestore emulator)

# Run all unit tests
uv run pytest tests/unit/ -x

# Run a single test file
uv run pytest tests/unit/test_handlers/test_categorize.py

# Run with coverage
uv run pytest tests/unit/ --cov --cov-report=term-missing

# Run integration tests
uv run pytest tests/integration/

# Run GCP cloud tests (requires Firestore emulator)
uv run pytest tests/cloud/ -m gcp

# Run all tests except cloud
uv run pytest tests/unit/ tests/integration/

# GCP deployment
cd deploy-cloud/gcp && ./deploy.sh
```

## Environment Variables

```
ANTHROPIC_API_KEY            # Required — Claude API key
SLACK_BOT_TOKEN              # Required — Slack bot token
SLACK_SIGNING_SECRET         # Required — Slack request signature verification
SLACK_CHANNEL_ID             # Required — Channel for bot messages and summaries
QUICKBOOKS_CLIENT_ID         # Required — QuickBooks OAuth app client ID
QUICKBOOKS_CLIENT_SECRET     # Required — QuickBooks OAuth app client secret
QUICKBOOKS_REDIRECT_URI      # Required — OAuth callback URL
ENTITY_TYPE                  # sole_prop | s_corp | llc (default: s_corp)
FORMATION_STATE              # State of formation (default: DE)
OPERATING_STATE              # State of registration/operations (default: NY)
FISCAL_YEAR_START            # e.g. 2026-01-01
CLAUDE_DAILY_TOKEN_LIMIT     # Daily token budget (default: 1000000)
CLAUDE_MONTHLY_TOKEN_LIMIT   # Monthly token budget (default: 20000000)
FIRESTORE_EMULATOR_HOST      # Local dev only — Firestore emulator address
```

## Conventions

- Python files use snake_case; classes use PascalCase
- `core/` must remain platform-agnostic — no cloud-provider imports
- `deploy-cloud/shared/` must not import GCP SDKs — depends on injected storage/secrets
- GCP-specific code belongs exclusively in `deploy-cloud/gcp/`
- `asyncio_mode = "auto"` — no `@pytest.mark.asyncio` needed
- Test factories in `tests/factories.py` — use `Factory.create(**overrides)` pattern
- Handler tests verify both return values AND storage side-effects
- GitHub Actions pinned to commit SHAs

### Security

- Handler error paths must never expose secrets, stack traces, or internal paths in responses
- All `/slack/*` endpoints require Slack signature verification with replay protection
- `skill_loader.py` must reject path traversal (`..`, absolute paths, null bytes)
- `claude_client.py` must enforce prompt construction safety (user input in user role only)
- Audit events must never contain secret values, tokens, or API keys
- MCP server URLs must enforce HTTPS — reject `http://` URLs
- QuickBooks OAuth tokens stored in Secret Manager, never in Firestore or logs
- Claude API usage tracked with configurable daily/monthly token budget caps
