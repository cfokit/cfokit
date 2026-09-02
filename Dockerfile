# syntax=docker/dockerfile:1.7
#
# One image, many entrypoints (ADR-0023). The REST service, the MCP surface, the
# migration job, and any component all run from this image and differ only in the
# command. That is what makes it structurally impossible for a component to run
# against an API version it was not built for.
#
#   docker run … python -m cfokit.ledger.migrations    migrations, explicit only
#   docker run … python -m cfokit.ledger.api           REST service (default)
#   docker run … python -m cfokit.ledger.bootstrap     first administrator, once
#
# There is deliberately no MCP entrypoint yet: the adapter exists and is tested, but
# nothing authenticates an MCP caller, and a runnable server that booked for an
# unidentified principal would be worse than none (LED-20).
#
# Migrations never run at startup (ADR-0004). There is deliberately no entrypoint
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
# README.md comes too: [project] readme names it, so the build backend needs it present.
COPY pyproject.toml uv.lock README.md ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

COPY src/ ./src/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

# ---------------------------------------------------------------------------
# The suite, in an image built from the same source as production. Used by the `test`
# compose profile so integration tests run inside the network, where Postgres is reachable
# without compose.yaml publishing a database port (ADR-0018, ADR-0023).
FROM builder AS test

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked

COPY tests/ ./tests/

# Only the integration tests. The unit and documentation tests run on the host in the same
# CI job and need the full checkout — `test_documentation.py` walks the repository at import
# time — while these need a database and nothing else. Naming the path rather than filtering
# by marker keeps the rest out of collection entirely.
CMD ["uv", "run", "--no-sync", "pytest", "tests/integration"]

# ---------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS runtime

RUN groupadd --system cfokit && useradd --system --gid cfokit --create-home cfokit

WORKDIR /app
COPY --from=builder --chown=cfokit:cfokit /app /app

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Nothing here selects a cloud, a region, or a provider. The entire coupling to the
# environment is the variable surface in infra/README.md (ADR-0004, ADR-0016).
USER cfokit
EXPOSE 8080

CMD ["python", "-m", "cfokit.ledger.api"]
