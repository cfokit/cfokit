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
# Who may open the issuer's admin console through IAP: whoever runs the setup, unless set. Read
# at run time so no address is kept in the repository.
if [ -z "${TF_VAR_admin_members:-}" ]; then
  TF_VAR_admin_members=$(printf '["user:%s"]' "$(gcloud config get account 2>/dev/null)")
fi
export TF_VAR_admin_members
# Where alerts go (monitoring.tf): the same person, unless set.
if [ -z "${TF_VAR_alert_emails:-}" ]; then
  TF_VAR_alert_emails=$(printf '["%s"]' "$(gcloud config get account 2>/dev/null)")
fi
export TF_VAR_alert_emails

export CLOUDSDK_CORE_PROJECT="$CFOKIT_PROJECT"
# A person's application-default credentials carry a quota project of their own, often some other
# project, so their API calls are billed and checked against this one instead. Not in GitHub
# Actions: the deploy identity is a service account, which needs no quota project, and naming one
# would require it to hold serviceusage.services.use on the project for nothing.
if [ -z "${GITHUB_ACTIONS:-}" ]; then
  export GOOGLE_CLOUD_QUOTA_PROJECT="$CFOKIT_PROJECT"
fi

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
