#!/usr/bin/env bash
# Once, on a project deployed while the sign-in service was named cfokit-issuer: moves it to
# cfokit-identity. A Cloud Run service cannot be renamed, so a new one is created beside the old,
# the load balancer moves to it, and only then is the old one deleted; sign-in stays up. Accounts
# are untouched: they are in Cloud SQL, whose database and role keep their names. Run it before
# the deploy that follows the rename reaches the project, which otherwise fails at a service that
# does not exist yet. Safe to run again after a failure.
#
#   rename-identity.sh
# shellcheck source=env.sh
. "$(dirname "$0")/env.sh"

exists() { gcloud run services describe "$1" --region "$CFOKIT_REGION" >/dev/null 2>&1; }

if ! exists cfokit-identity; then
  # The new service starts from the identity image's `latest` tag (run.tf).
  "$(dirname "$0")/images.sh" --latest

  # What OpenTofu will do, read before it does it (moved.tf): cfokit-issuer forgotten, the
  # identity-named resources created before the ones they replace are removed, and what points
  # at them updated in place.
  step "The plan"
  tf plan -input=false
  read -r -p "Apply it? [y/N] " answer
  [ "$answer" = y ] || { need "nothing changed"; exit 1; }

  "$(dirname "$0")/apply.sh"
fi

"$(dirname "$0")/check.sh"

# OpenTofu no longer manages the old service, and the load balancer no longer sends it anything.
if exists cfokit-issuer; then
  step "Delete cfokit-issuer"
  gcloud run services delete cfokit-issuer --region "$CFOKIT_REGION" --quiet
fi
done_ "sign-in runs as cfokit-identity"
