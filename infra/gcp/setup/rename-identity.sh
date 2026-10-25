#!/usr/bin/env bash
# Once, on a project deployed while the sign-in service was named cfokit-issuer: moves it to
# cfokit-identity. A Cloud Run service cannot be renamed, so a new one is created beside the old,
# the load balancer moves to it, and only then is the old one deleted; sign-in stays up. Accounts
# are untouched: they are in Cloud SQL, whose database and role keep their names. Run it before
# the deploy that follows the rename reaches the project, which otherwise fails at a service that
# does not exist yet. After a failure, run it again: it plans and applies until the old service
# is gone.
#
#   rename-identity.sh
# shellcheck source=env.sh
. "$(dirname "$0")/env.sh"

if ! gcloud run services describe cfokit-issuer --region "$CFOKIT_REGION" >/dev/null 2>&1; then
  done_ "cfokit-issuer is gone; nothing to rename"
  exit 0
fi

# The new service starts from the identity image's `latest` tag (run.tf).
"$(dirname "$0")/images.sh" --latest

# What OpenTofu will do, read before it does it (moved.tf): cfokit-issuer forgotten, the
# identity-named resources created before the ones they replace are removed, and what points at
# them updated in place. A run after a partial apply plans only what is left.
step "The plan"
tf plan -input=false
read -r -p "Apply it? [y/N] " answer
[ "$answer" = y ] || { need "nothing changed"; exit 1; }

"$(dirname "$0")/apply.sh"
"$(dirname "$0")/check.sh"

# The load balancer reaches a service only through its endpoint group, and the old group is
# removed only after the URL map has moved to the new backends. While it exists, the old service
# may still be serving sign-in.
if gcloud compute network-endpoint-groups describe cfokit-issuer --region "$CFOKIT_REGION" \
  >/dev/null 2>&1; then
  need "the load balancer still reaches cfokit-issuer; run this again"
  exit 1
fi
step "Delete cfokit-issuer"
gcloud run services delete cfokit-issuer --region "$CFOKIT_REGION" --quiet
done_ "sign-in runs as cfokit-identity"
