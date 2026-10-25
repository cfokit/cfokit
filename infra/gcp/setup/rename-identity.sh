#!/usr/bin/env bash
# Once, on a project deployed while the sign-in service was named cfokit-issuer: moves it to
# cfokit-identity. A Cloud Run service cannot be renamed, so the old one is replaced, and sign-in
# is down for the few minutes Keycloak takes to start. Accounts are untouched: they are in Cloud
# SQL, whose database and role keep their names. Run it before the deploy that follows the rename
# reaches the project, which otherwise fails at a service that does not exist yet.
#
#   rename-identity.sh
# shellcheck source=env.sh
. "$(dirname "$0")/env.sh"

if gcloud run services describe cfokit-identity --region "$CFOKIT_REGION" >/dev/null 2>&1; then
  done_ "cfokit-identity exists; nothing to rename"
  exit 0
fi

# The new service starts from the identity image's `latest` tag (run.tf).
"$(dirname "$0")/images.sh" --latest

# What OpenTofu will do, read before it does it: replacements of the identity-named resources
# (moved.tf), and in-place updates of what points at them.
step "The plan"
tf plan -input=false
read -r -p "Apply it, with sign-in down for a few minutes? [y/N] " answer
[ "$answer" = y ] || { need "nothing changed"; exit 1; }

# Deletion protection is what stops OpenTofu replacing the live service; lifted on the old one
# only, which the apply removes.
step "Let cfokit-issuer be replaced"
gcloud run services update cfokit-issuer --region "$CFOKIT_REGION" --no-deletion-protection \
  --quiet >/dev/null
done_ "deletion protection lifted"

"$(dirname "$0")/apply.sh"
"$(dirname "$0")/check.sh"
