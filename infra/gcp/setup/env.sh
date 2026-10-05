# Sourced by every setup script: what this deployment is called, and the tools it uses.
#
# The values are names, never secrets. They come from the environment, then from the file
# `configure.sh` writes, then from CFOKit's own production defaults. A fork deploying to its own
# project runs `configure.sh` once and every later step reads the same values.
# shellcheck shell=bash

set -euo pipefail

CFOKIT_ENV_FILE="${CFOKIT_ENV_FILE:-$HOME/.config/cfokit/deploy.env}"
# shellcheck disable=SC1090
[ -f "$CFOKIT_ENV_FILE" ] && . "$CFOKIT_ENV_FILE"

export CFOKIT_PROJECT="${CFOKIT_PROJECT:-cfokit-prod}"
export CFOKIT_REGION="${CFOKIT_REGION:-us-central1}"
export CFOKIT_ZONE="${CFOKIT_ZONE:-${CFOKIT_REGION}-a}"
export CFOKIT_DOMAIN="${CFOKIT_DOMAIN:-cfokit.ai}"
export CFOKIT_REPOSITORY="${CFOKIT_REPOSITORY:-cfokit/cfokit}"

# What OpenTofu reads (variables.tf).
export TF_VAR_project_id="$CFOKIT_PROJECT"
export TF_VAR_region="$CFOKIT_REGION"
export TF_VAR_zone="$CFOKIT_ZONE"
export TF_VAR_domain="$CFOKIT_DOMAIN"
export TF_VAR_github_repository="$CFOKIT_REPOSITORY"

export CLOUDSDK_CORE_PROJECT="$CFOKIT_PROJECT"
# Application-default credentials carry a quota project of their own, often some other project.
# API calls OpenTofu makes are billed and checked against this one instead.
export GOOGLE_CLOUD_QUOTA_PROJECT="$CFOKIT_PROJECT"

CFOKIT_INFRA="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export CFOKIT_INFRA
CFOKIT_ROOT="$(cd "$CFOKIT_INFRA/../.." && pwd)"
export CFOKIT_ROOT

TOFU="${TOFU:-$(command -v tofu || echo "$HOME/.local/bin/tofu")}"
export TOFU

step() { printf '\n\033[1m== %s\033[0m\n' "$*"; }
done_() { printf '\033[32m✓ %s\033[0m\n' "$*"; }
need() { printf '\033[33m→ %s\033[0m\n' "$*"; }

tf() { (cd "$CFOKIT_INFRA" && "$TOFU" "$@"); }
