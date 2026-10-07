#!/bin/bash
# Applies the settings an existing deployment's realms must hold, without replacing either realm
# and so without removing an account (infra/keycloak/README.md, "Settings on a running issuer").
#
# Keycloak reads cfokit-realm.json only when it creates the realm. This sets the same values on a
# realm that already exists, and the one setting the master realm needs, as a temporary
# administrator that Keycloak's own recovery command creates and this script deletes. No password
# is read or printed: the temporary client's secret is generated here and never leaves the
# container, and the script proves the client is gone before it reports success.
#
# Runs in the issuer's image, against the issuer's database, with Keycloak started inside the
# same container on localhost. Reads KC_DB, KC_DB_URL, KC_DB_USERNAME, KC_DB_PASSWORD, and:
#
#   CFOKIT_ACCESS_TOKEN_LIFESPAN   seconds; what the realm file reads at import
#   CFOKIT_MASTER_FRONTEND_URL     where the admin console is served, e.g. https://admin.example.com
set -euo pipefail
: "${CFOKIT_ACCESS_TOKEN_LIFESPAN:?}" "${CFOKIT_MASTER_FRONTEND_URL:?}"

kc=/opt/keycloak/bin/kc.sh
adm=/opt/keycloak/bin/kcadm.sh

# This Keycloak answers only kcadm, on localhost; the deployment's own hostnames do not apply.
unset KC_HOSTNAME KC_HOSTNAME_ADMIN KC_PROXY_HEADERS

CFOKIT_OPS_ID="cfokit-settings-$(date -u +%Y%m%d%H%M%S)"
CFOKIT_OPS_SECRET="$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')"
export CFOKIT_OPS_ID CFOKIT_OPS_SECRET

"$kc" bootstrap-admin service --client-id:env CFOKIT_OPS_ID --client-secret:env CFOKIT_OPS_SECRET --no-prompt

"$kc" start --http-enabled=true --http-port=8080 --hostname=http://localhost:8080 --cache=local &
server=$!

ready() {
  exec 3<>/dev/tcp/127.0.0.1/8080 || return 1
  printf 'GET /realms/master HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n' >&3
  head -1 <&3 | grep -q ' 200'
}
for _ in $(seq 150); do ready 2>/dev/null && break; sleep 2; done
ready

login() {
  "$adm" config credentials --server http://localhost:8080 --realm master \
    --client "$CFOKIT_OPS_ID" --secret "$CFOKIT_OPS_SECRET" >/dev/null
}

fail() {
  echo "FAILED: $1. Delete every cfokit-settings-* client in the master realm by hand." >&2
  kill "$server" 2>/dev/null
  exit 1
}

# However the rest ends, the temporary client is deleted. A fresh sign-in first, because setting
# the master realm's frontend URL changes its issuer and so invalidates the token held until
# then. Clients an earlier run left behind go first, while this run's credential still works;
# this run's own goes last, and its credential being refused afterwards is the proof it is gone.
# One surviving would be a standing administrator credential. The image has no awk.
cleanup() {
  status=$?
  set +e
  login || fail "could not sign in to clean up"
  clients=$("$adm" get clients -r master --fields id,clientId --format csv --noquotes) ||
    fail "could not list clients"
  own=
  while IFS=, read -r id client; do
    case "$client" in
      "$CFOKIT_OPS_ID") own=$id ;;
      cfokit-settings-*) "$adm" delete "clients/$id" -r master || fail "could not delete $client" ;;
    esac
  done <<<"$clients"
  others=$("$adm" get clients -r master --fields clientId --format csv --noquotes) ||
    fail "could not list clients"
  if grep '^cfokit-settings-' <<<"$others" | grep -qvx "$CFOKIT_OPS_ID"; then
    fail "an earlier temporary admin client survived"
  fi
  [ -n "$own" ] || fail "this run's own client was not found"
  "$adm" delete "clients/$own" -r master || fail "could not delete this run's own client"
  if login 2>/dev/null; then fail "this run's own client still signs in"; fi
  kill "$server" 2>/dev/null
  echo "temporary admin client deleted, and its credential refused"
  exit "$status"
}

login
trap cleanup EXIT

# The values cfokit-realm.json holds; tests/test_issuer_realm.py asserts the two agree.
lockout=(-s bruteForceProtected=true -s permanentLockout=false -s failureFactor=10
  -s waitIncrementSeconds=60 -s maxFailureWaitSeconds=900 -s maxDeltaTimeSeconds=43200
  -s quickLoginCheckMilliSeconds=1000 -s minimumQuickLoginWaitSeconds=60)
events=(-s eventsEnabled=true -s eventsExpiration=7776000 -s 'eventsListeners=["jboss-logging"]'
  -s adminEventsEnabled=true -s adminEventsDetailsEnabled=true)
password_policy='length(15) and maxLength(128) and notUsername and notEmail'

# Events first, so every change after them is an admin event.
"$adm" update events/config -r master "${events[@]}"
"$adm" update events/config -r cfokit "${events[@]}"

"$adm" update realms/cfokit "${lockout[@]}" \
  -s "accessTokenLifespan=${CFOKIT_ACCESS_TOKEN_LIFESPAN}" \
  -s "passwordPolicy=${password_policy}"
"$adm" update realms/master "${lockout[@]}"
# The admin console signs in to the master realm at that realm's frontend URL, from a hidden
# frame. Left at the issuer's public hostname, where Identity-Aware Proxy guards the master
# realm and cannot answer inside a frame, the console never finishes signing in. Last, because
# it changes the master realm's issuer, and with it which tokens are valid.
"$adm" update realms/master -s "attributes.frontendUrl=${CFOKIT_MASTER_FRONTEND_URL}"

login
echo "-- master"
"$adm" get realms/master --fields bruteForceProtected,failureFactor
"$adm" get realms/master | grep -i '"frontendUrl"' || fail "the master realm's frontend URL is not set"
echo "-- cfokit"
"$adm" get realms/cfokit --fields accessTokenLifespan,bruteForceProtected,failureFactor,passwordPolicy
"$adm" get events/config -r cfokit \
  --fields eventsEnabled,eventsExpiration,eventsListeners,adminEventsEnabled,adminEventsDetailsEnabled
