#!/usr/bin/env bash
# The deployment check: through the public hostnames, so the load balancer's routing is what is
# checked (ADR-0055, ADR-0060 Confirmation). Fails on the first thing that is wrong.
# shellcheck source=env.sh
. "$(dirname "$0")/env.sh"

app="https://app.$CFOKIT_DOMAIN"

check() { printf '  %-58s' "$1"; }
ok() { printf '\033[32mok\033[0m\n'; }

step "Deployment check"

check "REST ready: $app/readyz"
curl -fsS "$app/readyz" >/dev/null && ok

check "MCP ready: https://mcp.$CFOKIT_DOMAIN/readyz"
curl -fsS "https://mcp.$CFOKIT_DOMAIN/readyz" >/dev/null && ok

check "Issuer discovery: https://auth.$CFOKIT_DOMAIN/realms/cfokit"
curl -fsS "https://auth.$CFOKIT_DOMAIN/realms/cfokit/.well-known/openid-configuration" >/dev/null && ok

check "Web client, with its CSP, revalidated: $app/app/"
headers=$(curl -fsS -D - -o /dev/null "$app/app/")
grep -qi '^content-security-policy:' <<<"$headers"
grep -qi '^cache-control: no-cache' <<<"$headers" && ok

check "A deep link answers with the client's page"
curl -fsS -o /dev/null "$app/app/companies/check/questions" && ok

if [ -n "${CFOKIT_ASSET:-}" ]; then
  check "A hashed asset is immutable"
  headers=$(curl -fsS -D - -o /dev/null "$app/app/$CFOKIT_ASSET")
  grep -qi '^cache-control: public, max-age=31536000, immutable' <<<"$headers" && ok
fi

check "A REST 404 stays a 404"
test "$(curl -s -o /dev/null -w '%{http_code}' "$app/no-such-route")" = 404 && ok

done_ "https://app.$CFOKIT_DOMAIN is serving"
