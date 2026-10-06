#!/usr/bin/env bash
# Replace the running issuer's realm with the one in the issuer image.
#
#   realm.sh --replace [COMMIT]     default: the image production's issuer runs
#
# Keycloak imports a realm only when it does not exist, so a change to
# infra/keycloak/cfokit-realm.json reaches a running deployment only this way. **Replacing a realm
# removes every account in it**, which is why it takes --replace and asks again: right before a
# deployment has users, never casually after.
# shellcheck source=env.sh
. "$(dirname "$0")/env.sh"

if [ "${1:-}" != "--replace" ]; then
  echo "usage: $0 --replace [COMMIT]   (replaces the realm and removes its accounts)" >&2
  exit 2
fi
shift

repository="${CFOKIT_REGION}-docker.pkg.dev/${CFOKIT_PROJECT}/cfokit"
if [ -n "${1:-}" ]; then
  image="${repository}/issuer:$1"
else
  image=$(gcloud run services describe cfokit-issuer --region "$CFOKIT_REGION" \
    --format='value(spec.template.spec.containers[0].image)')
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

# The running issuer caches realms in memory; a new revision starts from the database.
step "Restart the issuer"
gcloud run services update cfokit-issuer --region "$CFOKIT_REGION" --image "$image" \
  --revision-suffix "realm-$(date -u +%Y%m%d%H%M%S)" --quiet >/dev/null
done_ "restarted on ${image##*/}"
