# The evidence a SOC 2 Type 2 examination samples over its review period.
#
# Admin Activity audit logs are always on and kept 400 days by Google. Data Access logs are off by
# default; these turn them on where a read is itself a security event: who read a secret, who
# used a key, who touched the database's configuration or an identity's credentials.

resource "google_project_iam_audit_config" "this" {
  for_each = toset([
    "secretmanager.googleapis.com",
    "cloudkms.googleapis.com",
    "sqladmin.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "sts.googleapis.com",
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
