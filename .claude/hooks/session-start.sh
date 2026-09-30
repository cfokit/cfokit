#!/bin/bash
# Prepares a Claude Code cloud session to run the gates CI runs (CLAUDE.md § CI gates).
#
# Host: uv at the version CI pins, which fetches Python 3.14 and 3.11 into its own cache, then
# `uv sync --locked`. That covers lint, money, decisions, contracts and the unit tests.
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

uv python install --quiet 3.14 3.11
uv sync --locked --quiet

if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  echo 'export UV_PYTHON=3.14' >> "$CLAUDE_ENV_FILE"
  # Container traffic here is TLS-intercepted by the session's proxy, so image builds need its
  # CA to reach PyPI. compose.yaml passes it to the build as the optional `build_ca` secret.
  if [ -f /root/.ccr/ca-bundle.crt ]; then
    echo 'export BUILD_CA_FILE=/root/.ccr/ca-bundle.crt' >> "$CLAUDE_ENV_FILE"
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
