#!/usr/bin/env bash
# Everything the database step needs, and nothing that reads a secret yet: Cloud Run refuses to
# create a revision naming a secret with no value, so the services wait for apply.sh.
# shellcheck source=env.sh
. "$(dirname "$0")/env.sh"

step "Network, database, secret containers, identities"
need "Creating a Cloud SQL instance takes 10 to 15 minutes the first time."
tf apply -input=false -auto-approve \
  -target=google_sql_database.cfokit \
  -target=google_sql_database.keycloak \
  -target=google_compute_subnetwork.run \
  -target=google_artifact_registry_repository.images \
  -target=google_secret_manager_secret_iam_member.reader
done_ "foundation applied"
