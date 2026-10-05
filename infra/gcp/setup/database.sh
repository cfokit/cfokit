#!/usr/bin/env bash
# The database roles, and every secret's value (ADR-0016, ADR-0060 § 4).
#
# **No password is ever printed, written to a file, or shown to whoever runs this.** Each is
# generated here and piped straight into Secret Manager, or into the Cloud SQL API. Safe to run
# again: a secret that already has a value is left alone.
# shellcheck source=env.sh
. "$(dirname "$0")/env.sh"

has_value() {
  [ -n "$(gcloud secrets versions list "$1" --filter=state=enabled --limit=1 --format='value(name)')" ]
}
put() { gcloud secrets versions add "$1" --data-file=- --quiet >/dev/null; }
password() { openssl rand -hex 24; }

host=$(tf output -raw database_private_ip)

step "Owner role, and the migration job's DATABASE_URL"
if has_value database-url-owner; then
  done_ "already set"
else
  pw=$(password)
  if gcloud sql users list --instance cfokit --format='value(name)' | grep -qx cfokit; then
    gcloud sql users set-password cfokit --instance cfokit --password "$pw" --quiet
  else
    gcloud sql users create cfokit --instance cfokit --password "$pw" --quiet
  fi
  printf 'postgresql://cfokit:%s@%s:5432/cfokit?sslmode=require' "$pw" "$host" | put database-url-owner
  unset pw
  done_ "created"
fi

step "The issuer's role"
if has_value keycloak-db-password; then
  done_ "already set"
else
  pw=$(password)
  if gcloud sql users list --instance cfokit --format='value(name)' | grep -qx keycloak; then
    gcloud sql users set-password keycloak --instance cfokit --password "$pw" --quiet
  else
    gcloud sql users create keycloak --instance cfokit --password "$pw" --quiet
  fi
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
  pw=$(password)
  printf '%s' "$pw" | gcloud secrets create cfokit-app-password --data-file=- --quiet >/dev/null
  gcloud secrets add-iam-policy-binding cfokit-app-password --quiet >/dev/null \
    --member "serviceAccount:cfokit-migrate@${CFOKIT_PROJECT}.iam.gserviceaccount.com" \
    --role roles/secretmanager.secretAccessor

  # Base64, because gcloud splits --args on commas. Creates the role only if it is absent.
  script=$(base64 <<'SH' | tr -d '\n'
psql "$OWNER_URL" -v ON_ERROR_STOP=1 -v pw="$APP_PW" <<'SQL'
SELECT format('CREATE ROLE cfokit_app LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS', :'pw')
 WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'cfokit_app') \gexec
ALTER ROLE cfokit_app PASSWORD :'pw';
SQL
SH
)
  gcloud run jobs deploy cfokit-bootstrap-role --region "$CFOKIT_REGION" --quiet \
    --image postgres:18-alpine \
    --service-account "cfokit-migrate@${CFOKIT_PROJECT}.iam.gserviceaccount.com" \
    --network cfokit --subnet cfokit-run --vpc-egress private-ranges-only \
    --set-secrets OWNER_URL=database-url-owner:latest,APP_PW=cfokit-app-password:latest \
    --command sh --args="-c,echo $script | base64 -d | sh" --max-retries 0 >/dev/null
  gcloud run jobs execute cfokit-bootstrap-role --region "$CFOKIT_REGION" --wait --quiet >/dev/null
  gcloud run jobs delete cfokit-bootstrap-role --region "$CFOKIT_REGION" --quiet >/dev/null
  gcloud secrets delete cfokit-app-password --quiet >/dev/null

  printf 'postgresql://cfokit_app:%s@%s:5432/cfokit?sslmode=require' "$pw" "$host" | put database-url-app
  unset pw
  done_ "created"
fi
