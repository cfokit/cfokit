#!/usr/bin/env bash
# Everything else: the services, the migration job, the load balancer and the web bucket.
# The services start from the `latest` images setup/images.sh pushed.
# shellcheck source=env.sh
. "$(dirname "$0")/env.sh"

# A service whose creation failed is left tainted, and deletion protection stops OpenTofu replacing
# it, so a re-run cannot recover. One that never served a request is safe to remove and recreate;
# one that ever became ready is never touched.
for key in 'api["rest"]' 'api["mcp"]' issuer; do
  address="google_cloud_run_v2_service.$key"
  if tf state show "$address" 2>/dev/null | head -1 | grep -q tainted; then
    name=$(tf state show "$address" | sed -n 's/^ *name *= *"\(.*\)"$/\1/p' | head -1)
    if [ -z "$(gcloud run services describe "$name" --region "$CFOKIT_REGION" \
      --format='value(status.latestReadyRevisionName)' 2>/dev/null)" ]; then
      step "Recreating $name, whose creation failed"
      gcloud run services delete "$name" --region "$CFOKIT_REGION" --quiet >/dev/null 2>&1 || true
      tf state rm "$address" >/dev/null
      done_ "removed"
    fi
  fi
done

step "Services, load balancer, web bucket"
tf apply -input=false -auto-approve
done_ "applied"
