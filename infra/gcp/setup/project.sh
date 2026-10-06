#!/usr/bin/env bash
# Check the project can be built in: signed in, the project exists, billing is linked.
# Changes nothing but enabling the two APIs the next step needs.
# shellcheck source=env.sh
. "$(dirname "$0")/env.sh"

step "Signed in"
account=$(gcloud config get account 2>/dev/null || true)
if [ -z "$account" ] || ! gcloud auth print-access-token >/dev/null 2>&1; then
  need "Sign in first: gcloud auth login --update-adc"
  exit 1
fi
if ! gcloud auth application-default print-access-token >/dev/null 2>&1; then
  need "OpenTofu needs application-default credentials: gcloud auth application-default login"
  exit 1
fi
done_ "$account"

step "Project $CFOKIT_PROJECT"
if ! gcloud projects describe "$CFOKIT_PROJECT" --format='value(projectId)' >/dev/null 2>&1; then
  need "No such project, or no access to it. Create it: gcloud projects create $CFOKIT_PROJECT"
  exit 1
fi
done_ "exists"

step "Billing"
if [ "$(gcloud billing projects describe "$CFOKIT_PROJECT" --format='value(billingEnabled)')" != "True" ]; then
  need "Link a billing account. Yours:"
  gcloud billing accounts list --filter=open=true --format='table(name,displayName)'
  need "gcloud billing projects link $CFOKIT_PROJECT --billing-account ACCOUNT_ID"
  exit 1
fi
done_ "linked"

step "APIs OpenTofu needs before it can enable the rest"
gcloud services enable cloudresourcemanager.googleapis.com serviceusage.googleapis.com cloudkms.googleapis.com storage.googleapis.com --quiet
done_ "enabled"
