# Production on GCP

OpenTofu for the maintained cloud target ([ADR-0017](../../docs/decisions/0017-gcp-initial-cloud-target.md),
[ADR-0055](../../docs/decisions/0055-on-gcp-the-web-client-is-served-from-a-cdn.md),
[ADR-0060](../../docs/decisions/0060-production-is-one-gcp-project-deployed-on-merge.md)). It
meets the contract in [`infra/README.md`](../README.md) and nothing more: the application does
not know it is on GCP.

| File | What it declares |
|---|---|
| `versions.tf` | The provider, the state backend, and state encryption with Cloud KMS |
| `variables.tf` | Project, region, zone, the three hostnames, the repository allowed to deploy |
| `main.tf` | APIs, and the image repository |
| `network.tf` | The VPC, the subnet services egress into, and private services access |
| `database.tf` | The Cloud SQL instance and its two databases |
| `secrets.tf` | Secret containers. Never values |
| `iam.tf` | One identity per runtime, the deploy identity, and GitHub federation |
| `run.tf` | The REST, MCP and issuer services, and the migration job |
| `loadbalancer.tf` | The web bucket and CDN, the load balancer, the certificate |
| `outputs.tf` | What the first-time steps and the deploy workflow need |

**A person applies this; the deploy pipeline never does** (ADR-0060 § 6). The pipeline,
`.github/workflows/deploy.yml`, ships application code on every merge to `main`.

## First time

Once per project, in this order. Every command runs from the repository root unless it says
otherwise, as someone holding Owner on the project.

### 1. The project, and where state lives

State exists before `tofu init` can, so its bucket and key are made by hand. Give yourself the
key's encrypt and decrypt role: Owner does not include it.

```sh
P=cfokit-prod R=us-central1
gcloud config set project $P
gcloud services enable cloudkms.googleapis.com storage.googleapis.com
gcloud storage buckets create gs://$P-tofu-state --location $R \
  --uniform-bucket-level-access --public-access-prevention
gcloud storage buckets update gs://$P-tofu-state --versioning
gcloud kms keyrings create tofu --location $R
gcloud kms keys create state --keyring tofu --location $R --purpose encryption
gcloud kms keys add-iam-policy-binding state --keyring tofu --location $R \
  --member "user:$(gcloud config get account)" --role roles/cloudkms.cryptoKeyEncrypterDecrypter
gcloud auth application-default login
```

### 2. Everything but the services

The services read secrets that have no value yet, and Cloud Run refuses to create a revision
that names an empty secret. So the first apply stops short of them.

```sh
cd infra/gcp
tofu init
tofu apply \
  -target=google_sql_database.cfokit -target=google_sql_database.keycloak \
  -target=google_compute_subnetwork.run \
  -target=google_secret_manager_secret.this -target=google_artifact_registry_repository.images
```

### 3. Database roles and secret values

No role is declared in OpenTofu, because its password would be in state (ADR-0016). The owner and
the issuer's role are Cloud SQL users. `cfokit_app` is created with SQL, so it is an ordinary role
— not a member of `cloudsqlsuperuser`, and with `NOBYPASSRLS` — and row-level security applies to
it (`infra/README.md`, "Two database roles").

```sh
P=cfokit-prod R=us-central1
HOST=$(cd infra/gcp && tofu output -raw database_private_ip)
OWNER_PW=$(openssl rand -hex 24) APP_PW=$(openssl rand -hex 24)
KC_PW=$(openssl rand -hex 24) ADMIN_PW=$(openssl rand -hex 24)

gcloud sql users create cfokit --instance cfokit --password "$OWNER_PW"
gcloud sql users create keycloak --instance cfokit --password "$KC_PW"

printf '%s' "postgresql://cfokit:$OWNER_PW@$HOST:5432/cfokit?sslmode=require" \
  | gcloud secrets versions add database-url-owner --data-file=-
printf '%s' "postgresql://cfokit_app:$APP_PW@$HOST:5432/cfokit?sslmode=require" \
  | gcloud secrets versions add database-url-app --data-file=-
printf '%s' "$KC_PW" | gcloud secrets versions add keycloak-db-password --data-file=-
printf '%s' "$ADMIN_PW" | gcloud secrets versions add keycloak-admin-password --data-file=-
```

The database has a private IP only, so `cfokit_app` is created from inside the network, by a
one-off job that runs `psql` and is deleted afterwards. It uses the default compute identity,
which `cfokit-migrate` will replace once it exists, so grant that one the owner secret here.

```sh
gcloud secrets add-iam-policy-binding database-url-owner \
  --member "serviceAccount:$(gcloud projects describe $P --format='value(projectNumber)')-compute@developer.gserviceaccount.com" \
  --role roles/secretmanager.secretAccessor
printf '%s' "$APP_PW" | gcloud secrets create cfokit-app-password --data-file=-
gcloud run jobs create cfokit-bootstrap-role --region $R --image postgres:18-alpine \
  --network cfokit --subnet cfokit-run --vpc-egress private-ranges-only \
  --set-secrets OWNER_URL=database-url-owner:latest,APP_PW=cfokit-app-password:latest \
  --command sh --args=-c,'psql "$OWNER_URL" -v ON_ERROR_STOP=1 -c "CREATE ROLE cfokit_app LOGIN PASSWORD '"'"'$APP_PW'"'"' NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS"'
gcloud run jobs execute cfokit-bootstrap-role --region $R --wait
gcloud run jobs delete cfokit-bootstrap-role --region $R --quiet
gcloud secrets delete cfokit-app-password --quiet
gcloud secrets remove-iam-policy-binding database-url-owner \
  --member "serviceAccount:$(gcloud projects describe $P --format='value(projectNumber)')-compute@developer.gserviceaccount.com" \
  --role roles/secretmanager.secretAccessor
unset OWNER_PW APP_PW KC_PW ADMIN_PW
```

The issuer's first administrator is `admin`, with the password in `keycloak-admin-password`.
Sign in at `https://auth.cfokit.ai/admin` once the issuer is up and replace it with a named
administrator.

### 4. The rest

```sh
cd infra/gcp && tofu apply
```

### 5. DNS

At Cloudflare, one A record per hostname to `tofu output load_balancer_ip`, with the proxy **off**
(DNS only). The Google-managed certificate validates each name by reaching the load balancer, and
stays `PROVISIONING` until all three resolve to it; that can take up to an hour.

### 6. The deploy workflow

Four repository variables, from `tofu output`:

```sh
cd infra/gcp
gh variable set GCP_WORKLOAD_IDENTITY_PROVIDER --body "$(tofu output -raw workload_identity_provider)"
gh variable set GCP_DEPLOY_SERVICE_ACCOUNT --body "$(tofu output -raw deploy_service_account)"
gh variable set GCP_IMAGE_REPOSITORY --body "$(tofu output -raw image_repository)"
gh variable set GCP_WEB_BUCKET --body "$(tofu output -raw web_bucket)"
```

Then run it once by hand (`gh workflow run Deploy`) rather than waiting for a merge. Until these
are set the workflow is skipped, so `main` stays green.

## Afterwards

* **Infrastructure changes** are pull requests to this directory, reviewed under the code-owner
  rule, then `tofu plan` and `tofu apply` by a person.
* **A secret rotates** by adding a version and redeploying the services that read it; nothing in
  OpenTofu changes.
* **A rollback** is `gcloud run services update-traffic` to the previous revision. A migration is
  not rolled back: migrations are written forward-only.
