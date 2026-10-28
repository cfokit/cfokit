#!/usr/bin/env bash
# Once, on a project whose secrets predate the secrets key (secrets.tf): moves every secret under
# it. A secret's encryption cannot change in place, so OpenTofu replaces each one, and a replaced
# secret has no value. This reads each value first and adds it back after, so nothing is
# regenerated: no database password changes, and nothing is pasted again. The values stay in this
# shell's memory, are never printed or written to a file, and reach Secret Manager on stdin.
#
# Until a value is back, a service instance that starts cannot read it; ones already running hold
# theirs. Safe to run again: a secret already under the key is left alone.
#
#   secrets-cmek.sh
# shellcheck source=env.sh
. "$(dirname "$0")/env.sh"

secrets=(database-url-owner database-url-app keycloak-db-password keycloak-admin-password
  agent-client-secret anthropic-api-key)
key="projects/${CFOKIT_PROJECT}/locations/${CFOKIT_REGION}/keyRings/cfokit/cryptoKeys/secrets"

under_key() {
  gcloud secrets describe "$1" --format=json 2>/dev/null | grep -q "\"kmsKeyName\": \"$key\""
}

step "Secret Manager's service agent"
gcloud beta services identity create --service=secretmanager.googleapis.com --quiet >/dev/null
done_ "exists"

# Two arrays rather than one keyed by name: macOS's bash is 3.2, which has no associative arrays.
step "Read every value"
names=()
values=()
for s in "${secrets[@]}"; do
  if under_key "$s"; then
    done_ "$s already under the key"
    continue
  fi
  v=$(gcloud secrets versions access latest --secret "$s") ||
    { need "$s has no value; fill it with database.sh first"; exit 1; }
  names+=("$s")
  values+=("$v")
  unset v
  done_ "$s read"
done
[ "${#names[@]}" -gt 0 ] || { done_ "every secret is under the key"; exit 0; }

# What OpenTofu will do, read before it does it: the key, its grant, and each secret not yet under
# it replaced, with its readers.
step "The plan"
tf plan -input=false -target=google_secret_manager_secret_iam_member.reader
read -r -p "Replace these secrets, putting each value back? [y/N] " answer
[ "$answer" = y ] || { need "nothing changed"; exit 1; }

step "Replace the secrets"
tf apply -input=false -auto-approve -target=google_secret_manager_secret_iam_member.reader
done_ "applied"

step "Put every value back"
for i in "${!names[@]}"; do
  printf '%s' "${values[$i]}" | gcloud secrets versions add "${names[$i]}" --data-file=- --quiet >/dev/null
  done_ "${names[$i]}"
done
unset values

step "Check"
for s in "${secrets[@]}"; do
  under_key "$s" || { need "$s is not under the key"; exit 1; }
done
done_ "every secret is under the project's own key"
