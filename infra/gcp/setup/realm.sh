#!/usr/bin/env bash
# Bring the running issuer's realms up to what the issuer image holds.
#
#   realm.sh --settings [COMMIT]    apply the realms' settings in place; every account stays
#   realm.sh --replace [COMMIT]     replace the cfokit realm with the image's; every account goes
#
# COMMIT defaults to the image production's issuer runs.
#
# Keycloak imports a realm only when it does not exist, so a change to
# infra/keycloak/cfokit-realm.json does not reach a running deployment by itself.
#
# --settings sets the values infra/keycloak/realm-settings.sh lists (lockout, password policy,
# events, token lifetime) on the realm that exists, and points the master realm's frontend URL at
# the admin console's host, without which the console cannot finish signing in. Run it once after
# the first deploy, and again whenever those values change. Safe to repeat.
#
# --replace re-imports the whole realm file, and **removing the realm removes every account in
# it**, which is why it asks again: right before a deployment has users, never casually after.
# shellcheck source=env.sh
. "$(dirname "$0")/env.sh"

mode="${1:-}"
case "$mode" in
  --settings | --replace) shift ;;
  *)
    echo "usage: $0 --settings [COMMIT]   (applies settings; keeps every account)" >&2
    echo "       $0 --replace [COMMIT]    (replaces the realm and removes its accounts)" >&2
    exit 2
    ;;
esac

repository="${CFOKIT_REGION}-docker.pkg.dev/${CFOKIT_PROJECT}/cfokit"
if [ -n "${1:-}" ]; then
  image="${repository}/issuer:$1"
else
  image=$(gcloud run services describe cfokit-issuer --region "$CFOKIT_REGION" \
    --format='value(spec.template.spec.containers[0].image)')
fi

# The running issuer caches realms in memory; a new revision starts from the database.
restart() {
  step "Restart the issuer"
  gcloud run services update cfokit-issuer --region "$CFOKIT_REGION" --image "$image" \
    --revision-suffix "realm-$(date -u +%Y%m%d%H%M%S)" --quiet >/dev/null
  done_ "restarted on ${image##*/}"
}

if [ "$mode" = "--settings" ]; then
  step "Apply the realms' settings from ${image##*/}"
  gcloud run jobs update cfokit-issuer-settings --region "$CFOKIT_REGION" --image "$image" \
    --quiet >/dev/null
  status=0
  execution=$(gcloud run jobs execute cfokit-issuer-settings --region "$CFOKIT_REGION" --wait \
    --quiet --format='value(metadata.name)') || status=$?

  # What the job read back, and whether its temporary administrator is gone. Its own output only:
  # Keycloak's log lines start with a date. Cloud Logging can trail the job by a few seconds.
  filter="resource.type=\"cloud_run_job\" AND resource.labels.job_name=\"cfokit-issuer-settings\""
  [ -n "$execution" ] && filter="$filter AND labels.\"run.googleapis.com/execution_name\"=\"$execution\""
  for _ in $(seq 12); do
    output=$(gcloud logging read "$filter" --order asc --limit 1000 --freshness 1h \
      --format='value(textPayload)' | grep -vE '^[0-9]{4}-|^WARNING|^\s*$|^Logging into|Changes detected|Updating the|Server configuration|show-config|Next time' || true)
    grep -qE 'temporary admin client deleted|FAILED' <<<"$output" && break
    sleep 5
  done
  printf '%s\n' "$output"

  if [ "$status" != 0 ] || ! grep -q 'temporary admin client deleted' <<<"$output"; then
    need "The job did not finish cleanly. Read its log, and check the master realm for any cfokit-settings-* client."
    exit 1
  fi
  done_ "applied"
  restart
  exit 0
fi

if [ "${CFOKIT_CONFIRM:-}" != "replace-realm" ]; then
  need "This removes every account in the cfokit realm of https://auth.$CFOKIT_DOMAIN."
  printf 'Type "replace-realm" to go on: '
  read -r answer
  [ "$answer" = "replace-realm" ] || { echo "Nothing changed."; exit 1; }
fi

step "Import the realm from ${image##*/}"
gcloud run jobs update cfokit-issuer-import --region "$CFOKIT_REGION" --image "$image" --quiet >/dev/null
gcloud run jobs execute cfokit-issuer-import --region "$CFOKIT_REGION" --wait --quiet >/dev/null
done_ "imported"

restart
