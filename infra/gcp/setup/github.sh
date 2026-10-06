#!/usr/bin/env bash
# What the deploy workflow needs to know, as repository variables. Names, never secrets: the
# workflow authenticates by Workload Identity Federation and holds no key (ADR-0060 § 5).
#
# Sets them with `gh` where it is signed in; otherwise prints them for the repository's
# Settings → Secrets and variables → Actions → Variables page.
# shellcheck source=env.sh
. "$(dirname "$0")/env.sh"

vars="GCP_PROJECT=$CFOKIT_PROJECT
GCP_REGION=$CFOKIT_REGION
CFOKIT_DOMAIN=$CFOKIT_DOMAIN
GCP_WORKLOAD_IDENTITY_PROVIDER=$(tf output -raw workload_identity_provider)
GCP_DEPLOY_SERVICE_ACCOUNT=$(tf output -raw deploy_service_account)"

step "Repository variables for github.com/$CFOKIT_REPOSITORY"
if command -v gh >/dev/null && gh auth status >/dev/null 2>&1; then
  while IFS='=' read -r name value; do
    gh variable set "$name" --repo "$CFOKIT_REPOSITORY" --body "$value"
    done_ "$name"
  done <<<"$vars"
else
  while IFS='=' read -r name value; do printf '  %-32s %s\n' "$name" "$value"; done <<<"$vars"
  need "Add each at https://github.com/$CFOKIT_REPOSITORY/settings/variables/actions"
fi
