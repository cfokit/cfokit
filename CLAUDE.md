# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CFOKit is an open-source AI CFO toolkit — AI agents that handle bookkeeping, tax preparation, cash flow monitoring, and compliance tracking for small businesses, solo founders, and fractional CFOs. It uses Anthropic Claude AI, Model Context Protocol (MCP), and deploys to GCP, AWS, Azure, or OpenClaw.

**Status:** Greenfield project. `docs/PRD.md` defines the Phase 1 scope, architecture, and all stories. Treat it as the authoritative source of truth for implementation decisions.

## Planned Tech Stack

- **Language:** Python 3.11+
- **Package manager:** uv (with `pyproject.toml` and `uv.lock`)
- **AI:** Anthropic Claude API
- **Integrations:** MCP servers for QuickBooks, Wave, Stripe
- **Cloud services:** GCP (Phase 1), AWS (Phase 2), Azure (Phase 3) — all serverless
- **Testing:** pytest, pytest-asyncio
- **Infrastructure:** Terraform (provider-specific per cloud), Docker Compose (for OpenClaw)
- **User interface:** Slack bot

## Architecture

The codebase follows a three-layer architecture: platform-agnostic core, cloud-agnostic handlers, and cloud-specific adapters.

```
core/                        # Shared business logic (platform-agnostic)
├── skills/                  # CFO domain knowledge as markdown (S-corp, 501c3, tax rules)
├── agents/                  # Agent definitions in YAML (bookkeeper, tax_preparer, compliance_monitor, cashflow_analyst)
├── integrations/            # MCP servers (QuickBooks, Wave, Stripe)
├── models/                  # Pydantic data models (transaction, client, tax_form, compliance_rule)
├── adapters/                # Protocol-based cloud abstractions (PEP 544)
│   ├── base.py              # StorageAdapter, SecretsAdapter, MessagingAdapter, SchedulerAdapter
│   └── exceptions.py
└── shared/                  # Cloud-agnostic utilities
    ├── claude_client.py
    ├── skill_loader.py
    ├── mcp_manager.py
    └── slack_client.py

deploy-cloud/                # Cloud deployment adapters
├── shared/                  # Cloud-agnostic request handlers (use adapter interfaces only)
│   └── handlers/
│       ├── base_handler.py
│       ├── categorize.py
│       ├── cashflow.py
│       ├── report.py
│       ├── compliance.py
│       ├── setup.py
│       └── help.py
├── gcp/                     # GCP adapter (Phase 1)
│   ├── adapters/            # Firestore, Secret Manager, Pub/Sub, Cloud Scheduler
│   ├── agents/              # Cloud Run service + Cloud Run Jobs
│   └── terraform/           # GCP-specific Terraform with modules
├── aws/                     # AWS adapter (Phase 2)
│   ├── adapters/            # DynamoDB, Secrets Manager, SNS+SQS, EventBridge
│   ├── agents/              # Fargate + ALB service + scheduled tasks
│   └── terraform/           # AWS-specific Terraform with modules
└── azure/                   # Azure adapter (Phase 3)
    ├── adapters/            # Cosmos DB, Key Vault, Service Bus, Logic Apps
    ├── agents/              # Container Apps service + scheduled jobs
    └── terraform/           # Azure-specific Terraform with modules

deploy-openclaw/            # OpenClaw deployment (separate paradigm, not a cloud adapter)
├── agents/                  # OpenClaw agent configs (YAML)
├── skills/                  # Skills manifests (YAML)
└── workflows/               # Scheduled workflow definitions (YAML)
```

**Key design principles:**
- Skills are universal markdown files that work across all deployment targets
- Agent definitions are portable YAML
- Adapter interfaces use Python Protocols (PEP 544) — duck typing, no inheritance required
- Request handlers depend only on adapter protocols, never on concrete cloud implementations
- Only `app.py` in each cloud directory wires concrete adapters via a factory
- OpenClaw is a separate paradigm, not a cloud adapter

**Data flow (cloud — all providers):** Slack -> Containerized FastAPI Service -> Claude AI + Skills -> QuickBooks/Wave (via MCP) -> Document DB (via StorageAdapter)

**Data flow (OpenClaw):** Slack -> OpenClaw Agent Router -> Claude AI + Skills -> QuickBooks/Wave (via MCP) -> OpenClaw State

## Build & Development Commands

Once the project is scaffolded:

```bash
# Install dependencies
uv sync

# Run all tests
uv run pytest

# Run a single test file
uv run pytest tests/unit/test_categorize.py

# Run a single test function
uv run pytest tests/unit/test_categorize.py::test_function_name

# Cloud deployment
cd deploy-cloud/gcp && ./deploy.sh     # GCP (Phase 1)
cd deploy-cloud/aws && ./deploy.sh     # AWS (Phase 2)
cd deploy-cloud/azure && ./deploy.sh   # Azure (Phase 3)

# OpenClaw deployment
cd deploy-openclaw && ./install.sh

# Local dev setup
./scripts/local-dev-setup.sh

# Run unit tests only (fast, no external deps)
uv run pytest tests/unit/ -x

# Run with coverage report
uv run pytest tests/unit/ --cov --cov-report=term-missing

# Run cloud adapter tests (requires emulators running)
uv run pytest tests/cloud/ -m gcp
uv run pytest tests/cloud/ -m aws
uv run pytest tests/cloud/ -m azure

# Run all tests except cloud
uv run pytest tests/unit/ tests/integration/
```

## Multi-Client Architecture

CFOKit supports fractional CFOs managing multiple clients. Each client gets:
- A dedicated Slack channel
- Isolated data storage (cloud document DB namespace or OpenClaw namespace)
- Per-client skills and configuration
- Independent entity type settings (S-corp, LLC, 501c3, 501c6)

## Environment Variables

```
ANTHROPIC_API_KEY        # Required — Claude API key
QUICKBOOKS_COMPANY_ID    # Required — QuickBooks company ID
SLACK_BOT_TOKEN          # Required — Slack bot token
ENTITY_TYPE              # s-corp | llc | 501c3 | 501c6
STATE                    # State of incorporation (NY, CA, etc.)
FISCAL_YEAR_START        # e.g. 2024-01-01
QUARTERLY_SALARY         # For S-corps — quarterly salary amount
```

## Conventions

- Skills are markdown files containing domain knowledge (tax rules, compliance requirements)
- Agent definitions are YAML files specifying skills, tools, and triggers
- Python files use snake_case; classes use PascalCase
- The `core/` directory must remain platform-agnostic — no cloud-provider or OpenClaw imports
- `deploy-cloud/shared/handlers/` must use only adapter interfaces — no cloud-provider imports
- Cloud-specific code belongs exclusively in `deploy-cloud/{gcp,aws,azure}/`
- OpenClaw-specific code belongs exclusively in `deploy-openclaw/`
- Adapter interfaces use Python Protocols (PEP 544), not ABCs
- Terraform is provider-specific per cloud — no shared Terraform abstractions
- Unit tests use in-memory adapter fixtures — never import cloud SDKs
- Adapter conformance tests define the behavioral contract; new adapters inherit them
- `tests/adapters/` contains reference implementations, not production code
- `asyncio_mode = "auto"` — no `@pytest.mark.asyncio` needed
- Test factories in `tests/factories.py` — use `Factory.create(**overrides)` pattern
- Handler tests verify both return values AND storage side-effects
- Coverage floor: 85% for unit, 80% combined

### Security Testing

- Adapter conformance tests must include tenant isolation scenarios (data under tenant A's namespace must not be visible to tenant B)
- Handler error paths must never expose secrets, stack traces, internal paths, or other-tenant data in responses
- All internet-facing endpoints must have authentication tests (Slack signature verification, replay protection)
- `skill_loader.py` must have path traversal tests; `claude_client.py` must have prompt construction safety tests
- State-changing handlers must emit audit events (tested for presence and for absence of secrets)
- CI must include `bandit` (SAST), `pip-audit` (dependency vulnerabilities), and `detect-secrets` (committed secrets)
- GitHub Actions pinned to commit SHAs, Docker service images pinned to digest hashes
- MCP server URLs must enforce HTTPS — reject `http://` URLs
- Test factories should include adversarial data variants (empty strings, unicode, injection payloads, boundary values)
