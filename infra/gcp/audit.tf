# The evidence a SOC 2 Type 2 examination samples over its review period.
#
# Admin Activity audit logs are always on and kept 400 days by Google. Data Access logs are off by
# default; these turn them on where a read is itself a security event: who read a secret, who
# used a key, who touched the database's configuration or an identity's credentials, and who
# opened the admin console.

resource "google_project_iam_audit_config" "this" {
  for_each = toset([
    "secretmanager.googleapis.com",
    "cloudkms.googleapis.com",
    # The audit-log name for Cloud SQL, not its API's.
    "cloudsql.googleapis.com",
    "iam.googleapis.com",
    "sts.googleapis.com",
    # Every request through Identity-Aware Proxy: who opened the issuer's admin console, and
    # when. Admin Activity logs record changes to IAP, not its use.
    "iap.googleapis.com",
  ])
  project = var.project_id
  service = each.value

  audit_log_config {
    log_type = "ADMIN_READ"
  }
  audit_log_config {
    log_type = "DATA_READ"
  }
  audit_log_config {
    log_type = "DATA_WRITE"
  }
}

# Everything else lands in _Default, which keeps 30 days unless told otherwise. 400 days covers a
# twelve-month review period and its lookback (SOC2-24).
resource "google_logging_project_bucket_config" "default" {
  project        = var.project_id
  location       = "global"
  bucket_id      = "_Default"
  retention_days = 400
}

# A copy of the evidence nobody can delete (SOC2-24). `_Required` already holds Admin Activity
# and System Event logs, locked, for 400 days. Everything else lands in `_Default`, which an
# Owner can shorten or empty. This bucket is locked: its retention cannot be reduced and it
# cannot be deleted, by anyone, until every entry in it is 400 days old. Locking cannot be undone.
#
# What it keeps: every Data Access audit log, which records who read a secret, used a key,
# administered the database or passed Identity-Aware Proxy; and the issuer's sign-in and
# administration events (run.tf). A change to the sink or the bucket is alerted (monitoring.tf).
resource "google_logging_project_bucket_config" "audit" {
  project        = var.project_id
  location       = "us"
  bucket_id      = "cfokit-audit"
  description    = "Audit evidence, locked for 400 days (infra/gcp/audit.tf)."
  retention_days = 400
  locked         = true

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_logging_project_sink" "audit" {
  name        = "cfokit-audit"
  destination = "logging.googleapis.com/${google_logging_project_bucket_config.audit.id}"
  filter = join(" OR ", [
    "logName=\"projects/${var.project_id}/logs/cloudaudit.googleapis.com%2Fdata_access\"",
    "(resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"${google_cloud_run_v2_service.issuer.name}\" AND textPayload:\"org.keycloak.events\")",
  ])
  unique_writer_identity = true
}
