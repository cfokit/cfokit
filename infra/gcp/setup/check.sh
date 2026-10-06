#!/usr/bin/env bash
# The deployment check: through the public hostnames, so the load balancer's routing is what is
# checked (ADR-0055, ADR-0060 Confirmation). Fails on the first thing that is wrong.
# shellcheck source=env.sh
. "$(dirname "$0")/env.sh"

app="https://app.$CFOKIT_DOMAIN"

# Every check runs, so one deploy reports everything that is wrong; any failure fails the script.
failed=0
check() {
  local name=$1
  shift
  printf '  %-58s' "$name"
  if "$@" >/dev/null 2>&1; then
    printf '\033[32mok\033[0m\n'
  else
    printf '\033[31mFAILED\033[0m\n'
    failed=1
  fi
}
redirects_to() { curl -s -o /dev/null -w '%{redirect_url}' "$1" | grep -q "^$2"; }
has_header() { curl -fsS -D - -o /dev/null "$1" | grep -qi "^$2"; }

step "Deployment check"

check "REST ready: $app/readyz" curl -fsS "$app/readyz"
check "MCP ready: https://mcp.$CFOKIT_DOMAIN/readyz" curl -fsS "https://mcp.$CFOKIT_DOMAIN/readyz"
check "Issuer discovery: https://auth.$CFOKIT_DOMAIN/realms/cfokit" \
  curl -fsS "https://auth.$CFOKIT_DOMAIN/realms/cfokit/.well-known/openid-configuration"
check "Web client carries its CSP: $app/app/" has_header "$app/app/" "content-security-policy:"
check "Web client is revalidated" has_header "$app/app/" "cache-control: no-cache"
check "A deep link answers with the client's page" curl -fsS "$app/app/companies/check/questions"
if [ -n "${CFOKIT_ASSET:-}" ]; then
  check "A hashed asset is immutable" \
    has_header "$app/app/$CFOKIT_ASSET" "cache-control: public, max-age=31536000, immutable"
fi
check "The admin console is behind IAP: https://admin.$CFOKIT_DOMAIN" \
  redirects_to "https://admin.$CFOKIT_DOMAIN/admin/" "https://accounts.google.com/"
check "The sign-in host does not serve it" \
  redirects_to "https://auth.$CFOKIT_DOMAIN/admin/" "https://admin.$CFOKIT_DOMAIN/"
check "A REST 404 stays a 404" \
  test "$(curl -s -o /dev/null -w '%{http_code}' "$app/no-such-route")" = 404

if [ "$failed" -ne 0 ]; then
  need "Something above is wrong; if DNS or the certificate is still settling, run check.sh again."
  exit 1
fi
done_ "https://app.$CFOKIT_DOMAIN is serving"
