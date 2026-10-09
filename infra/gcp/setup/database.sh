#!/usr/bin/env bash
# The database roles, and every secret's value (ADR-0016, ADR-0060 § 4).
#
# Credentials are handled as SOC 2 asks of a secret (SOC2-17): **no password is ever printed,
# written to a file, put in a command's arguments, or sent to the database in a statement.**
#
# * Each is generated in this shell and reaches Secret Manager on stdin.
# * Cloud SQL users are made through the Admin API with the password in the request body, on
#   stdin, and the access token through a pipe — never as an argument, because gcloud writes
#   every command's arguments to its log on disk and `ps` shows them to every local user.
# * `cfokit_app` is given a SCRAM-SHA-256 verifier computed here, so the plaintext never reaches
#   Postgres, whose logs can record a statement's text.
#
# Safe to run again: a secret that already has a value is left alone.
# shellcheck source=env.sh
. "$(dirname "$0")/env.sh"

has_value() {
  [ -n "$(gcloud secrets versions list "$1" --filter=state=enabled --limit=1 --format='value(name)')" ]
}
put() { gcloud secrets versions add "$1" --data-file=- --quiet >/dev/null; }
password() { openssl rand -hex 24; }

# POST or PUT to the Cloud SQL Admin API, body on stdin, and wait for the operation.
sqladmin() {
  local method=$1 path=$2 response operation
  response=$(curl -fsS -X "$method" \
    -H @<(printf 'Authorization: Bearer %s\n' "$(gcloud auth print-access-token)") \
    -H 'Content-Type: application/json' --data-binary @- \
    "https://sqladmin.googleapis.com/v1/projects/${CFOKIT_PROJECT}/instances/${instance}/${path}")
  operation=$(python3 -c 'import json,sys; print(json.load(sys.stdin)["name"])' <<<"$response")
  gcloud sql operations wait "$operation" --timeout=300 --quiet >/dev/null
}

# Create a Cloud SQL user, or set its password if it exists. The password is read from stdin.
# Pipes throughout, never here-strings: older bash writes a here-string to a temporary file.
sql_user() {
  local name=$1 body
  body=$(python3 -c 'import json,sys; print(json.dumps({"name": sys.argv[1], "password": sys.stdin.read()}))' "$name")
  if gcloud sql users list --instance "$instance" --format='value(name)' | grep -qx "$name"; then
    printf '%s' "$body" | sqladmin PUT "users?name=${name}"
  else
    printf '%s' "$body" | sqladmin POST users
  fi
}

# A SCRAM-SHA-256 verifier for a password read from stdin, as Postgres stores it (RFC 7677).
scram() {
  # shellcheck disable=SC2016 # Python, not shell: nothing here is meant to expand.
  python3 -c '
import base64, hashlib, hmac, os, sys
pw = sys.stdin.read().encode()
salt = os.urandom(16)
salted = hashlib.pbkdf2_hmac("sha256", pw, salt, 4096)
client = hmac.new(salted, b"Client Key", hashlib.sha256).digest()
server = hmac.new(salted, b"Server Key", hashlib.sha256).digest()
b64 = lambda b: base64.b64encode(b).decode()
print(f"SCRAM-SHA-256$4096:{b64(salt)}${b64(hashlib.sha256(client).digest())}:{b64(server)}", end="")'
}

host=$(tf output -raw database_private_ip)
instance=$(tf output -raw database_instance)

step "Owner role, and the migration job's DATABASE_URL"
if has_value database-url-owner; then
  done_ "already set"
else
  pw=$(password)
  printf '%s' "$pw" | sql_user cfokit
  printf 'postgresql://cfokit:%s@%s:5432/cfokit?sslmode=require' "$pw" "$host" | put database-url-owner
  unset pw
  done_ "created"
fi

step "The issuer's role"
if has_value keycloak-db-password; then
  done_ "already set"
else
  pw=$(password)
  printf '%s' "$pw" | sql_user keycloak
  printf '%s' "$pw" | put keycloak-db-password
  unset pw
  done_ "created"
fi

step "The issuer's first administrator"
if has_value keycloak-admin-password; then
  done_ "already set"
else
  password | tr -d '\n' | put keycloak-admin-password
  done_ "generated; read it with: gcloud secrets versions access latest --secret keycloak-admin-password"
fi

# `cfokit_app` is an ordinary role made with SQL, so it is not a member of cloudsqlsuperuser and
# row-level security applies to it (infra/README.md, "Two database roles"). The database has a
# private IP only, so the SQL runs from a one-off job inside the network, as the migration
# job's identity, which already reads the owner's connection string.
step "The application role, cfokit_app"
if has_value database-url-app; then
  done_ "already set"
else
  # Whatever an interrupted run left behind.
  gcloud run jobs delete cfokit-bootstrap-role --region "$CFOKIT_REGION" --quiet >/dev/null 2>&1 || true
  gcloud secrets delete cfokit-app-verifier --quiet >/dev/null 2>&1 || true

  pw=$(password)
  printf '%s' "$pw" | scram | gcloud secrets create cfokit-app-verifier --data-file=- --quiet >/dev/null
  gcloud secrets add-iam-policy-binding cfokit-app-verifier --quiet >/dev/null \
    --member "serviceAccount:cfokit-migrate@${CFOKIT_PROJECT}.iam.gserviceaccount.com" \
    --role roles/secretmanager.secretAccessor

  # Base64, because gcloud splits --args on commas. Creates the role only if it is absent.
  script=$(base64 <<'SH' | tr -d '\n'
psql "$OWNER_URL" -v ON_ERROR_STOP=1 -v verifier="$APP_VERIFIER" <<'SQL'
SELECT 'CREATE ROLE cfokit_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS'
 WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'cfokit_app') \gexec
ALTER ROLE cfokit_app PASSWORD :'verifier';
SQL
SH
)
  gcloud run jobs deploy cfokit-bootstrap-role --region "$CFOKIT_REGION" --quiet \
    --image postgres:18.6-alpine@sha256:77f585114c32fbca283dc835b0596f4e52b51b4c6662d7810b2f4084f60a1873 \
    --service-account "cfokit-migrate@${CFOKIT_PROJECT}.iam.gserviceaccount.com" \
    --network cfokit --subnet cfokit-run --vpc-egress private-ranges-only \
    --set-secrets OWNER_URL=database-url-owner:latest,APP_VERIFIER=cfokit-app-verifier:latest \
    --command sh --args="-c,echo $script | base64 -d | sh" --max-retries 0 >/dev/null
  gcloud run jobs execute cfokit-bootstrap-role --region "$CFOKIT_REGION" --wait --quiet >/dev/null
  gcloud run jobs delete cfokit-bootstrap-role --region "$CFOKIT_REGION" --quiet >/dev/null
  gcloud secrets delete cfokit-app-verifier --quiet >/dev/null

  printf 'postgresql://cfokit_app:%s@%s:5432/cfokit?sslmode=require' "$pw" "$host" | put database-url-app
  unset pw
  done_ "created"
fi

# pgaudit, in both databases (infra/gcp/database.tf): the instance's flag loads it, and each
# database audits only once the extension exists in it. Run every time, because it is idempotent.
# As the migration job's identity, whose owner role may create the extension in either database.
step "pgaudit in both databases"
gcloud run jobs delete cfokit-bootstrap-pgaudit --region "$CFOKIT_REGION" --quiet >/dev/null 2>&1 || true
script=$(base64 <<'SH' | tr -d '\n'
set -e
for db in cfokit keycloak; do
  psql "$(printf '%s' "$OWNER_URL" | sed "s#/cfokit?#/${db}?#")" -v ON_ERROR_STOP=1 \
    -c 'CREATE EXTENSION IF NOT EXISTS pgaudit' >/dev/null
done
SH
)
gcloud run jobs deploy cfokit-bootstrap-pgaudit --region "$CFOKIT_REGION" --quiet \
  --image postgres:18.6-alpine@sha256:77f585114c32fbca283dc835b0596f4e52b51b4c6662d7810b2f4084f60a1873 \
  --service-account "cfokit-migrate@${CFOKIT_PROJECT}.iam.gserviceaccount.com" \
  --network cfokit --subnet cfokit-run --vpc-egress private-ranges-only \
  --set-secrets OWNER_URL=database-url-owner:latest \
  --command sh --args="-c,echo $script | base64 -d | sh" --max-retries 0 >/dev/null
gcloud run jobs execute cfokit-bootstrap-pgaudit --region "$CFOKIT_REGION" --wait --quiet >/dev/null
gcloud run jobs delete cfokit-bootstrap-pgaudit --region "$CFOKIT_REGION" --quiet >/dev/null
done_ "pgaudit created in cfokit and keycloak"
