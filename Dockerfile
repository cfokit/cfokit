# syntax=docker/dockerfile:1.7
#
# One image, many entrypoints (ADR-0023). The REST service, the MCP surface, the
# migration job, and any component all run from this image and differ only in the
# command. That is what makes it structurally impossible for a component to run
# against an API version it was not built for.
#
#   docker run … python -m cfokit.ledger.migrations    migrations, explicit only
#   docker run … python -m cfokit.server rest         REST service (default)
#   docker run … python -m cfokit.server mcp          MCP service, streamable HTTP
#
# The REST service also serves the web client's static build at /app/ (ADR-0049 § 5). It is
# built from web/ in a Node stage below; the final image carries the files and no Node.
#
# Both surfaces validate bearer tokens against the same issuer and the same audience
# (ADR-0019). They listen on PORT, so a deployment runs one per service.
#
# Migrations never run at startup (ADR-0004). There is deliberately no entrypoint
# script that applies them before starting the service.

# ---------------------------------------------------------------------------
# The web client (ADR-0054). Node and pnpm at the versions web/.nvmrc and web/package.json pin;
# keep the tag in step with web/.nvmrc. Only web/ is copied in, which is the whole of what the
# client may read, apart from the contract it is typed against.
FROM node:24.21.0-slim@sha256:0e0ff40c39bc087845bfb27465a0df4ea419520094bc35842ff83dd8cbe6f9b6 AS web

ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0
WORKDIR /web

COPY web/package.json web/pnpm-lock.yaml web/pnpm-workspace.yaml ./
# The optional build CA, as for the Python stages: Node reads it from NODE_EXTRA_CA_CERTS.
RUN --mount=type=cache,target=/root/.local/share/pnpm/store \
    --mount=type=secret,id=build_ca,required=false \
    if [ -s /run/secrets/build_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/build_ca; fi; \
    corepack pnpm install --frozen-lockfile

COPY web/ ./
RUN corepack pnpm build

# ---------------------------------------------------------------------------
# The issuer's sign-in theme (ADR-0054 § 1), built by Keycloakify from the same project into a
# JAR. That needs Maven and a JDK beside Node, taken from the Maven image into the client's stage.
# The `issuer` target below puts the JAR into Keycloak's image.
FROM maven:3.9.16-eclipse-temurin-21@sha256:99e61abcff91a9b1333463bd8451fb18495d6eba9250ac66a338b518f8278320 AS maven

FROM web AS sign-in-theme
COPY --from=maven /opt/java/openjdk /opt/java/openjdk
COPY --from=maven /usr/share/maven /usr/share/maven
ENV JAVA_HOME=/opt/java/openjdk \
    MAVEN_HOME=/usr/share/maven \
    PATH=/opt/java/openjdk/bin:/usr/share/maven/bin:$PATH
RUN --mount=type=cache,target=/root/.m2 corepack pnpm exec keycloakify build

FROM quay.io/keycloak/keycloak:26.7.4@sha256:82a77884f3af238beab1e7afd63b5f530e1b5c0590bd7aa60b40a40463e29b2c AS issuer
COPY --from=sign-in-theme /web/dist_keycloak/cfokit-theme.jar /opt/keycloak/providers/

# ---------------------------------------------------------------------------
FROM python:3.14.7-slim@sha256:51dafde81dbdb6ebde285137a295cf18a47ca95234fe388a343719cb97305b3d AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11.33@sha256:77280f2f771df71f90786c314fe1bbc1e023feac652969bbf139c280babf2eb7 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Manifests first, so the dependency layer is cached independently of source.
# README.md comes too: [project] readme names it, so the build backend needs it present.
COPY pyproject.toml uv.lock README.md ./

# Every `uv sync` below mounts `build_ca`, an optional extra certificate authority for a build
# whose network re-terminates TLS, such as a Claude Code cloud session. Empty everywhere else
# (compose.yaml sources it from /dev/null), and a secret mount never reaches an image layer.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=secret,id=build_ca,required=false \
    if [ -s /run/secrets/build_ca ]; then export SSL_CERT_FILE=/run/secrets/build_ca; fi; \
    uv sync --locked --no-dev --no-install-project

COPY src/ ./src/

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=secret,id=build_ca,required=false \
    if [ -s /run/secrets/build_ca ]; then export SSL_CERT_FILE=/run/secrets/build_ca; fi; \
    uv sync --locked --no-dev

# ---------------------------------------------------------------------------
# The suite, in an image built from the same source as production. Used by the `test`
# compose profile so integration tests run inside the network, where Postgres is reachable
# without compose.yaml publishing a database port (ADR-0018, ADR-0023).
FROM builder AS test

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=secret,id=build_ca,required=false \
    if [ -s /run/secrets/build_ca ]; then export SSL_CERT_FILE=/run/secrets/build_ca; fi; \
    uv sync --locked

COPY tests/ ./tests/

# Only the integration tests. The unit and documentation tests run on the host in the same
# CI job and need the full checkout — `test_documentation.py` walks the repository at import
# time — while these need a database and nothing else. Naming the path rather than filtering
# by marker keeps the rest out of collection entirely.
CMD ["uv", "run", "--no-sync", "pytest", "tests/integration"]

# ---------------------------------------------------------------------------
FROM python:3.14.7-slim@sha256:51dafde81dbdb6ebde285137a295cf18a47ca95234fe388a343719cb97305b3d AS runtime

RUN groupadd --system cfokit && useradd --system --gid cfokit --create-home cfokit

WORKDIR /app
COPY --from=builder --chown=cfokit:cfokit /app /app
# Where cfokit.server looks for it (WEB_ROOT); read-only to the service.
COPY --from=web /web/dist /app/web

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Nothing here selects a cloud, a region, or a provider. The entire coupling to the
# environment is the variable surface in infra/README.md (ADR-0004, ADR-0016).
USER cfokit
EXPOSE 8080

CMD ["python", "-m", "cfokit.server", "rest"]
