#!/bin/bash
# Prepares a Claude Code cloud session to run the gates CI runs (CLAUDE.md § CI gates).
#
# Host: uv at the version CI pins, which fetches Python 3.14 into its own cache, then
# `uv sync --locked`. That covers lint, money, decisions, contracts and the unit tests.
# Node: the version web/.nvmrc pins, and the web client's dependencies through pnpm, so the
# web client's lint, tests and build run as its CI job runs them (ADR-0054).
# Docker: the daemon, so the integration suite runs the documented way, inside the compose
# network. Images are built on first use rather than here, to keep session start fast.
#
# Cloud only. A laptop is provisioned by its owner, not by this script.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-$(dirname "$0")/../..}"

# Keep in step with UV_VERSION in .github/workflows/ci.yml.
UV_VERSION="0.11.33"
# From the GitHub release, which is what the installer fetches too; `uv self update` resolves
# versions through a host this environment's network policy does not allow.
if [ "$(uv --version 2>/dev/null | awk '{print $2}')" != "$UV_VERSION" ]; then
  mkdir -p "$HOME/.local/bin"
  curl -fsSL "https://github.com/astral-sh/uv/releases/download/$UV_VERSION/uv-x86_64-unknown-linux-gnu.tar.gz" \
    | tar -xz --strip-components=1 -C "$HOME/.local/bin"
  hash -r
fi

uv python install --quiet 3.14
uv sync --locked --quiet

# Node's own CA store does not include the session proxy's, so corepack and pnpm need it named.
if [ -f /root/.ccr/ca-bundle.crt ]; then
  export NODE_EXTRA_CA_CERTS=/root/.ccr/ca-bundle.crt
fi
# From nodejs.org, the only host that publishes Node's release builds.
NODE_VERSION="$(cat web/.nvmrc)"
if [ "$(node --version 2>/dev/null)" != "v$NODE_VERSION" ]; then
  mkdir -p "$HOME/.local/node"
  curl -fsSL "https://nodejs.org/dist/v$NODE_VERSION/node-v$NODE_VERSION-linux-x64.tar.xz" \
    | tar -xJ --strip-components=1 -C "$HOME/.local/node"
  export PATH="$HOME/.local/node/bin:$PATH"
  hash -r
fi
# corepack fetches the pnpm that web/package.json pins, from the npm registry, without asking.
export COREPACK_ENABLE_DOWNLOAD_PROMPT=0
(cd web && corepack pnpm install --frozen-lockfile --silent)

if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  echo 'export UV_PYTHON=3.14' >> "$CLAUDE_ENV_FILE"
  echo 'export COREPACK_ENABLE_DOWNLOAD_PROMPT=0' >> "$CLAUDE_ENV_FILE"
  if [ -d "$HOME/.local/node/bin" ]; then
    echo "export PATH=\"$HOME/.local/node/bin:\$PATH\"" >> "$CLAUDE_ENV_FILE"
  fi
  # Container traffic here is TLS-intercepted by the session's proxy, so image builds need its
  # CA to reach PyPI. compose.yaml passes it to the build as the optional `build_ca` secret.
  if [ -f /root/.ccr/ca-bundle.crt ]; then
    echo 'export BUILD_CA_FILE=/root/.ccr/ca-bundle.crt' >> "$CLAUDE_ENV_FILE"
    echo 'export NODE_EXTRA_CA_CERTS=/root/.ccr/ca-bundle.crt' >> "$CLAUDE_ENV_FILE"
  fi
fi

if ! docker info >/dev/null 2>&1; then
  nohup dockerd >/tmp/dockerd.log 2>&1 &
  for _ in $(seq 1 30); do
    docker info >/dev/null 2>&1 && break
    sleep 1
  done
  docker info >/dev/null 2>&1 || { echo "dockerd did not start; see /tmp/dockerd.log" >&2; exit 1; }
fi
