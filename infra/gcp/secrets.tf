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
  }
}

resource "google_secret_manager_secret" "this" {
  for_each  = local.secrets
  secret_id = each.key
  labels    = { purpose = "cfokit" }

  annotations = { description = each.value }

  replication {
    auto {}
  }

  depends_on = [google_project_service.this]
}
