locals {
  app_host  = "app.${var.domain}"
  mcp_host  = "mcp.${var.domain}"
  auth_host = "auth.${var.domain}"

  # What the issuer calls itself, and so what every token's `iss` is (ADR-0019).
  issuer_url    = "https://${local.auth_host}/realms/cfokit"
  issuer_origin = "https://${local.auth_host}"
  audience      = "cfokit-ledger"

  services = toset([
    "artifactregistry.googleapis.com",
    "cloudkms.googleapis.com",
    "compute.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "servicenetworking.googleapis.com",
    "sqladmin.googleapis.com",
    "sts.googleapis.com",
  ])
}

resource "google_project_service" "this" {
  for_each           = local.services
  service            = each.value
  disable_on_destroy = false
}

# ---------------------------------------------------------------------------------------------
# Images. One repository: the application image and the issuer image, tagged by commit.
# ---------------------------------------------------------------------------------------------
resource "google_artifact_registry_repository" "images" {
  repository_id = "cfokit"
  location      = var.region
  format        = "DOCKER"
  description   = "The application and issuer images, tagged by commit (ADR-0023, ADR-0060)."

  # Keep the most recent images, so a rollback has somewhere to go, and nothing older.
  cleanup_policies {
    id     = "keep-recent"
    action = "KEEP"
    most_recent_versions {
      keep_count = 20
    }
  }
  cleanup_policies {
    id     = "delete-older"
    action = "DELETE"
    condition {
      tag_state = "ANY"
    }
  }

  depends_on = [google_project_service.this]
}
