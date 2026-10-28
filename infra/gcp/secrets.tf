# Secret containers only. Every value is populated out of band, so none is in state (ADR-0016).
#
# Two connection strings for one database, because the migration job connects as the owner and
# every serving entrypoint as `cfokit_app`, and row-level security applies only to the second
# (infra/README.md, "Two database roles").

locals {
  secrets = {
    "database-url-owner"      = "DATABASE_URL for the migration job: the owner role."
    "database-url-app"        = "DATABASE_URL for the REST and MCP services: cfokit_app."
    "keycloak-db-password"    = "The issuer's database role's password."
    "keycloak-admin-password" = "The issuer's first administrator's password."
    "agent-client-secret"     = "CFOKit's agent's client secret at the issuer, read by both."
    "anthropic-api-key"       = "The agent's inference credential."
  }
}

# Every secret is encrypted with a key CFOKit holds, as the database is (database.tf): its rotation
# is ours, every use of it is in the audit log, and disabling it makes every secret unreadable
# (SOC2-14, SOC2-17).
resource "google_kms_crypto_key" "secrets" {
  name            = "secrets"
  key_ring        = google_kms_key_ring.data.id
  rotation_period = "7776000s" # 90 days; older versions stay to decrypt what they encrypted

  lifecycle {
    prevent_destroy = true
  }
}

# Secret Manager's service agent encrypts and decrypts with it, and nothing else does.
resource "google_kms_crypto_key_iam_member" "secrets" {
  crypto_key_id = google_kms_crypto_key.secrets.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:service-${data.google_project.this.number}@gcp-sa-secretmanager.iam.gserviceaccount.com"
}

resource "google_secret_manager_secret" "this" {
  for_each  = local.secrets
  secret_id = each.key
  labels    = { purpose = "cfokit" }

  annotations = { description = each.value }

  # In the deployment's region, under the key above: automatic replication is a global location,
  # which the resource locations policy refuses (orgpolicy.tf). Replication cannot change in place,
  # so changing it replaces the secret, and its values with it.
  replication {
    user_managed {
      replicas {
        location = var.region
        customer_managed_encryption {
          kms_key_name = google_kms_crypto_key.secrets.id
        }
      }
    }
  }

  depends_on = [google_project_service.this, google_kms_crypto_key_iam_member.secrets]
}
