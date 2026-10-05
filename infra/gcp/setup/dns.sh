#!/usr/bin/env bash
# The three DNS records, and whether the certificate has seen them.
#
#   dns.sh          print the records to set
#   dns.sh --wait   then wait until all three resolve and the certificate is ACTIVE
# shellcheck source=env.sh
. "$(dirname "$0")/env.sh"

ip=$(tf output -raw load_balancer_ip)
hosts=("app.$CFOKIT_DOMAIN" "mcp.$CFOKIT_DOMAIN" "auth.$CFOKIT_DOMAIN")

step "Set these at your DNS provider"
for h in "${hosts[@]}"; do printf '  %-28s A  %s\n' "$h" "$ip"; done
need "Proxy off (Cloudflare: DNS only, grey cloud). The certificate validates by reaching the load balancer."

[ "${1:-}" = "--wait" ] || exit 0

step "Waiting for DNS"
for h in "${hosts[@]}"; do
  until [ "$(dig +short A "$h" @1.1.1.1 | tail -1)" = "$ip" ]; do sleep 15; done
  done_ "$h → $ip"
done

step "Waiting for the certificate (up to an hour)"
until [ "$(gcloud compute ssl-certificates describe cfokit --global --format='value(managed.status)')" = ACTIVE ]; do
  sleep 30
done
done_ "ACTIVE"
