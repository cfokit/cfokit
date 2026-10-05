#!/usr/bin/env bash
# Everything else: the services, the migration job, the load balancer and the web bucket.
# The services start on a placeholder image until the first deploy.
# shellcheck source=env.sh
. "$(dirname "$0")/env.sh"

step "Services, load balancer, web bucket"
tf apply -input=false -auto-approve
done_ "applied"
