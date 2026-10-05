# One Cloud SQL instance holding CFOKit's database and the issuer's (ADR-0060 § 3, § 4).
#
# **No database role is declared here.** A role's password would be in state, and IaC creates
# secret containers, never values (ADR-0016). The owner, `cfokit_app` and the issuer's role are
# created once by a person; README.md has the steps.

resource "google_sql_database_instance" "this" {
  name             = "cfokit"
  database_version = "POSTGRES_18" # what compose.yaml runs
  region           = var.region

  depends_on = [google_service_networking_connection.sql]

  settings {
    # PostgreSQL 16 and later default to Enterprise Plus, which has no small machine. The
    # smallest dedicated Enterprise tier serves a first customer (ADR-0060 § 4).
    edition           = "ENTERPRISE"
    tier              = "db-custom-1-3840"
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
