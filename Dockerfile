# syntax=docker/dockerfile:1.7
#
# One image, many entrypoints (ADR-0024). The REST service, the MCP surface, the
# migration job, and any component all run from this image and differ only in the
# command. That is what makes it structurally impossible for a component to run
# against an API version it was not built for.
#
#   docker run … python -m cfokit.ledger.migrations    migrations, explicit only
#   docker run … python -m cfokit.ledger.api           REST service (default)
#   docker run … python -m cfokit.ledger.mcp           MCP surface
#
# Migrations never run at startup (ADR-0003). There is deliberately no entrypoint
# script that applies them before starting the service.

ARG PYTHON_VERSION=3.12

# ---------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Manifests first, so the dependency layer is cached independently of source.
COPY pyproject.toml uv.lock ./
COPY packages/ledger/pyproject.toml packages/ledger/
COPY packages/connectors/pyproject.toml packages/connectors/

# The workspace members are declared in the root `dev` group, so `--no-dev` alone
# would install nothing. `--package` resolves the member and its runtime deps.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-workspace --package cfokit-ledger

COPY packages/ ./packages/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --package cfokit-ledger

# ---------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS runtime

RUN groupadd --system cfokit && useradd --system --gid cfokit --create-home cfokit

WORKDIR /app
COPY --from=builder --chown=cfokit:cfokit /app /app

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Nothing here selects a cloud, a region, or a provider. The entire coupling to the
# environment is the variable surface in infra/README.md (ADR-0003).
USER cfokit
EXPOSE 8080

CMD ["python", "-m", "cfokit.ledger.api"]
