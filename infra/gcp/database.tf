# One Cloud SQL instance holding CFOKit's database and the issuer's (ADR-0060 § 3, § 4).
#
# **No database role is declared here.** A role's password would be in state, and IaC creates
# secret containers, never values (ADR-0016). The owner, `cfokit_app` and the issuer's role are
# created once by a person; README.md has the steps.

# The database is encrypted with a key CFOKit holds, not only Google's: its rotation is ours, every
# use of it is in the audit log, and disabling it makes the data unreadable (SOC2-14). Cloud SQL
# takes a customer-managed key only when an instance is created.
resource "google_kms_key_ring" "data" {
  name       = "cfokit"
  location   = var.region
  depends_on = [google_project_service.this]
}

resource "google_kms_crypto_key" "database" {
  name            = "database"
  key_ring        = google_kms_key_ring.data.id
  rotation_period = "7776000s" # 90 days; older versions stay to decrypt what they encrypted

  lifecycle {
    prevent_destroy = true
  }
}

data "google_project" "this" {}

# Cloud SQL's service agent encrypts and decrypts with it, and nothing else does.
resource "google_kms_crypto_key_iam_member" "sql" {
  crypto_key_id = google_kms_crypto_key.database.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:service-${data.google_project.this.number}@gcp-sa-cloud-sql.iam.gserviceaccount.com"
}

resource "google_sql_database_instance" "this" {
  name                = "cfokit-pg"
  database_version    = "POSTGRES_18" # what compose.yaml runs
  region              = var.region
  encryption_key_name = google_kms_crypto_key.database.id

  depends_on = [google_service_networking_connection.sql, google_kms_crypto_key_iam_member.sql]

  settings {
    # PostgreSQL 16 and later default to Enterprise Plus, which has no small machine. Until
    # there are customers, a shared core: $25.55 a month against $49.31 for the smallest
    # dedicated one, at the price of an SLA nobody yet depends on. f1-micro's 0.6 GB is too
    # little for CFOKit and Keycloak together (ADR-0060 § 4).
    edition           = "ENTERPRISE"
    tier              = "db-g1-small"
    availability_type = "ZONAL"
    disk_autoresize   = true

    location_preference {
      zone = var.zone
    }

    ip_configuration {
      ipv4_enabled    = false
      private_network = google_compute_network.this.id
      ssl_mode        = "ENCRYPTED_ONLY"
    }

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
      start_time                     = "07:00"
      backup_retention_settings {
        retained_backups = 14
      }
    }

    maintenance_window {
      day  = 7
      hour = 8
    }

    insights_config {
      query_insights_enabled = true
    }

    # Who connected and when, kept with the project's other logs (SOC2-24). Statement text is
    # not logged: a role's password is set as a verifier, but a statement can still carry data.
    database_flags {
      name  = "log_connections"
      value = "on"
    }
    database_flags {
      name  = "log_disconnections"
      value = "on"
    }
  }

  deletion_protection = true
}

resource "google_sql_database" "cfokit" {
  name     = "cfokit"
  instance = google_sql_database_instance.this.name
}

resource "google_sql_database" "keycloak" {
  name     = "keycloak"
  instance = google_sql_database_instance.this.name
}
