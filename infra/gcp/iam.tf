# Who runs what, and who may deploy (ADR-0060 § 5, § 6).
#
# Each runtime has its own identity, holding the secrets it reads and nothing else. The deploy
# identity can push images, run the migration job, write the web bucket and roll out revisions of
# services that exist; it cannot change networks, databases, IAM or the load balancer.

resource "google_service_account" "service" {
  account_id   = "cfokit-service"
  display_name = "CFOKit REST and MCP services"
}

resource "google_service_account" "migrate" {
  account_id   = "cfokit-migrate"
  display_name = "CFOKit migration job"
}

resource "google_service_account" "issuer" {
  account_id   = "cfokit-issuer"
  display_name = "CFOKit issuer (Keycloak)"
}

resource "google_service_account" "deploy" {
  account_id   = "cfokit-deploy"
  display_name = "CFOKit deploy, from GitHub Actions on main"
}

locals {
  secret_readers = {
    "database-url-app"        = google_service_account.service.member
    "database-url-owner"      = google_service_account.migrate.member
    "keycloak-db-password"    = google_service_account.issuer.member
    "keycloak-admin-password" = google_service_account.issuer.member
  }
}

resource "google_secret_manager_secret_iam_member" "reader" {
  for_each  = local.secret_readers
  secret_id = google_secret_manager_secret.this[each.key].id
  role      = "roles/secretmanager.secretAccessor"
  member    = each.value
}

# ---------------------------------------------------------------------------------------------
# Workload Identity Federation: GitHub Actions on this repository's main branch, and nothing
# else, may act as the deploy identity. No key exists to store or rotate.
# ---------------------------------------------------------------------------------------------
resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "github"
  display_name              = "GitHub Actions"
  depends_on                = [google_project_service.this]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "cfokit"
  display_name                       = "cfokit main"

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
    "attribute.ref"        = "assertion.ref"
  }
  attribute_condition = "assertion.repository == '${var.github_repository}' && assertion.ref == 'refs/heads/main'"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account_iam_member" "deploy_federation" {
  service_account_id = google_service_account.deploy.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${var.github_repository}"
}

# Update revisions and run jobs; not change IAM on them, which run.admin would allow.
resource "google_project_iam_member" "deploy_run" {
  project = var.project_id
  role    = "roles/run.developer"
  member  = google_service_account.deploy.member
}

# A revision runs as its runtime identity, so deploying one requires acting as it.
resource "google_service_account_iam_member" "deploy_acts_as" {
  for_each = {
    service = google_service_account.service.name
    migrate = google_service_account.migrate.name
    issuer  = google_service_account.issuer.name
  }
  service_account_id = each.value
  role               = "roles/iam.serviceAccountUser"
  member             = google_service_account.deploy.member
}

resource "google_artifact_registry_repository_iam_member" "deploy_push" {
  repository = google_artifact_registry_repository.images.name
  location   = google_artifact_registry_repository.images.location
  role       = "roles/artifactregistry.writer"
  member     = google_service_account.deploy.member
}

resource "google_storage_bucket_iam_member" "deploy_web" {
  bucket = google_storage_bucket.web.name
  role   = "roles/storage.objectAdmin"
  member = google_service_account.deploy.member
}
