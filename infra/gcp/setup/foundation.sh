#!/usr/bin/env bash
# Everything the database step needs, and nothing that reads a secret yet: Cloud Run refuses to
# create a revision naming a secret with no value, so the services wait for apply.sh. The load
# balancer's address is reserved here too, so DNS can propagate while the rest is built.
# shellcheck source=env.sh
. "$(dirname "$0")/env.sh"

step "Service agents"
# Cloud SQL's encrypts the database with the project's own key, and IAP's reaches the issuer's
# admin console; each must exist before a policy can name it, and on a new project neither does.
gcloud services enable sqladmin.googleapis.com iap.googleapis.com --quiet
for service in sqladmin.googleapis.com iap.googleapis.com; do
  gcloud beta services identity create --service="$service" --quiet >/dev/null
done
done_ "exist"

step "Network, database, secret containers, identities"
need "Creating a Cloud SQL instance takes 10 to 15 minutes the first time."
tf apply -input=false -auto-approve \
  -target=google_sql_database.cfokit \
  -target=google_sql_database.keycloak \
  -target=google_compute_subnetwork.run \
  -target=google_artifact_registry_repository.images \
  -target=google_secret_manager_secret_iam_member.reader \
  -target=google_compute_global_address.lb \
  -target=google_project_iam_audit_config.this \
  -target=google_logging_project_bucket_config.default
done_ "foundation applied"
