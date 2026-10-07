# Alerting, defined per event class rather than left to inspection (SOC2-24).
#
# audit.tf decides what is recorded; this decides what a person is told about as it happens. Each
# class below is a change to the control environment, a use of privileged access, or a sign that
# the service or its sign-in is under strain. Each sends at most one email per five minutes, and
# what fired stays in Cloud Monitoring as the record that the control operated (NFR-18).

resource "google_monitoring_notification_channel" "email" {
  for_each     = toset(var.alert_emails)
  display_name = "CFOKit alerts: ${each.value}"
  type         = "email"
  labels = {
    email_address = each.value
  }
  depends_on = [google_project_service.this]
}

locals {
  channels = [for channel in google_monitoring_notification_channel.email : channel.name]

  activity    = "logName=\"projects/${var.project_id}/logs/cloudaudit.googleapis.com%2Factivity\""
  data_access = "logName=\"projects/${var.project_id}/logs/cloudaudit.googleapis.com%2Fdata_access\""
  issuer_log  = "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"${google_cloud_run_v2_service.issuer.name}\""

  # Each a log query; one matching entry is one alert.
  log_alerts = {
    iam = {
      name   = "Access changed"
      detail = "An IAM policy, a service account, a key for one, or the GitHub federation changed. Expected only from `tofu apply`."
      filter = "${local.activity} AND (protoPayload.methodName:\"SetIamPolicy\" OR protoPayload.methodName:(\"CreateServiceAccount\" OR \"DeleteServiceAccount\" OR \"DisableServiceAccount\" OR \"EnableServiceAccount\" OR \"ServiceAccountKey\" OR \"WorkloadIdentityPool\"))"
    }
    logging = {
      name   = "Audit logging changed"
      detail = "A log sink, bucket, exclusion or log was changed or deleted: the evidence itself."
      filter = "${local.activity} AND protoPayload.serviceName=\"logging.googleapis.com\" AND protoPayload.methodName:(\"Sink\" OR \"Bucket\" OR \"Exclusion\" OR \"DeleteLog\")"
    }
    kms = {
      name   = "Encryption key changed"
      detail = "A KMS key or key version was disabled, destroyed, restored or reconfigured. Disabling the database key makes the books unreadable (SOC2-14)."
      filter = "${local.activity} AND protoPayload.serviceName=\"cloudkms.googleapis.com\" AND protoPayload.methodName:(\"UpdateCryptoKey\" OR \"DestroyCryptoKeyVersion\" OR \"RestoreCryptoKeyVersion\")"
    }
    secrets = {
      name   = "Secret read by a person, or changed"
      detail = "A person, not a runtime identity, read a secret's value; or a secret or one of its versions was added, disabled, destroyed or deleted."
      filter = "protoPayload.serviceName=\"secretmanager.googleapis.com\" AND ((${local.data_access} AND protoPayload.methodName:\"AccessSecretVersion\" AND NOT protoPayload.authenticationInfo.principalEmail:\"gserviceaccount.com\") OR (${local.activity} AND protoPayload.methodName:(\"AddSecretVersion\" OR \"DisableSecretVersion\" OR \"DestroySecretVersion\" OR \"DeleteSecret\")))"
    }
    database = {
      name   = "Database administered"
      detail = "The Cloud SQL instance's settings, users or backups changed, or its data was exported, imported, cloned or restored."
      filter = "${local.activity} AND protoPayload.serviceName=\"cloudsql.googleapis.com\" AND protoPayload.methodName:(\"cloudsql.instances.update\" OR \"cloudsql.instances.delete\" OR \"cloudsql.instances.export\" OR \"cloudsql.instances.import\" OR \"cloudsql.instances.clone\" OR \"cloudsql.instances.restoreBackup\" OR \"cloudsql.users.\" OR \"cloudsql.backupRuns.delete\")"
    }
    network = {
      name   = "Network or load balancer changed"
      detail = "A network, firewall rule, route, Cloud Armor policy, or part of the load balancer changed. Expected only from `tofu apply`."
      filter = "${local.activity} AND protoPayload.serviceName=\"compute.googleapis.com\" AND protoPayload.methodName:(\"networks.\" OR \"subnetworks.\" OR \"firewalls.\" OR \"routes.\" OR \"securityPolicies.\" OR \"urlMaps.\" OR \"backendServices.\" OR \"backendBuckets.\" OR \"sslPolicies.\" OR \"targetHttpsProxies.\" OR \"globalForwardingRules.\")"
    }
    runtime = {
      name   = "Service or job changed outside the deploy"
      detail = "A Cloud Run service or job was created, changed or deleted by someone other than the deploy identity: `tofu apply`, `realm.sh`, or a hand."
      filter = "${local.activity} AND protoPayload.serviceName=\"run.googleapis.com\" AND protoPayload.methodName:(\"Service\" OR \"Job\") AND NOT protoPayload.methodName:\"IamPolicy\" AND NOT protoPayload.authenticationInfo.principalEmail=\"${google_service_account.deploy.email}\""
    }
    console = {
      name   = "Admin console opened"
      detail = "Someone passed Identity-Aware Proxy into the issuer's admin console or master realm: privileged access (SOC2-23)."
      # Granted only. The hostname is public, so scanners are refused by IAP around the clock;
      # each refusal stays in the audit log, and none is a reason to wake anyone.
      filter = "${local.data_access} AND protoPayload.serviceName=\"iap.googleapis.com\" AND protoPayload.authorizationInfo.granted=true"
    }
    lockout = {
      name   = "Account locked"
      detail = "The issuer locked an account after repeated failed sign-ins (infra/keycloak/README.md)."
      filter = "${local.issuer_log} AND textPayload:\"user_temporarily_disabled\""
    }
  }
}

resource "google_monitoring_alert_policy" "log" {
  for_each              = local.log_alerts
  display_name          = each.value.name
  combiner              = "OR"
  notification_channels = local.channels

  conditions {
    display_name = each.value.name
    condition_matched_log {
      filter = each.value.filter
    }
  }

  alert_strategy {
    notification_rate_limit {
      period = "300s"
    }
    auto_close = "1800s"
  }

  documentation {
    content   = each.value.detail
    mime_type = "text/markdown"
  }
}

# ---------------------------------------------------------------------------------------------
# Rates: failed sign-ins, and errors the services return.
# ---------------------------------------------------------------------------------------------
resource "google_logging_metric" "sign_in_failures" {
  name   = "cfokit/sign-in-failures"
  filter = "${local.issuer_log} AND textPayload:\"type=\\\"LOGIN_ERROR\\\"\""
  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
  }
}

resource "google_monitoring_alert_policy" "sign_in_failures" {
  display_name          = "Failed sign-ins"
  combiner              = "OR"
  notification_channels = local.channels

  conditions {
    display_name = "More than 20 failed sign-ins in five minutes"
    condition_threshold {
      filter          = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.sign_in_failures.name}\" AND resource.type=\"cloud_run_revision\""
      comparison      = "COMPARISON_GT"
      threshold_value = 20
      duration        = "0s"
      aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_SUM"
        cross_series_reducer = "REDUCE_SUM"
      }
    }
  }

  documentation {
    content   = "Many sign-ins are failing: someone guessing passwords across accounts, or the sign-in itself is broken. Cloud Armor's decisions are in the load balancer's request log."
    mime_type = "text/markdown"
  }
}

resource "google_monitoring_alert_policy" "server_errors" {
  display_name          = "Server errors"
  combiner              = "OR"
  notification_channels = local.channels

  conditions {
    display_name = "More than 10 responses of 5xx in five minutes"
    condition_threshold {
      filter          = "metric.type=\"loadbalancing.googleapis.com/https/request_count\" AND resource.type=\"https_lb_rule\" AND metric.label.response_code_class=500"
      comparison      = "COMPARISON_GT"
      threshold_value = 10
      duration        = "0s"
      aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_SUM"
        cross_series_reducer = "REDUCE_SUM"
      }
    }
  }

  documentation {
    content   = "The load balancer is returning server errors: a service, the issuer or the database is failing."
    mime_type = "text/markdown"
  }
}

# ---------------------------------------------------------------------------------------------
# Reachability, from outside, of what is always running: the sign-in service, and the web
# client through the load balancer, its certificate and DNS. The REST and MCP services scale to
# zero, and a probe every few minutes would keep each warm and billed all month; their failures
# reach the server-errors alert above instead.
# ---------------------------------------------------------------------------------------------
locals {
  uptime = {
    issuer = { host = local.auth_host, path = "/realms/cfokit/.well-known/openid-configuration" }
    web    = { host = local.app_host, path = "/app/" }
  }
}

resource "google_monitoring_uptime_check_config" "this" {
  for_each     = local.uptime
  display_name = "${each.value.host}${each.value.path}"
  timeout      = "10s"
  period       = "300s"

  http_check {
    path         = each.value.path
    port         = 443
    use_ssl      = true
    validate_ssl = true
  }

  monitored_resource {
    type = "uptime_url"
    labels = {
      project_id = var.project_id
      host       = each.value.host
    }
  }

  depends_on = [google_project_service.this]
}

resource "google_monitoring_alert_policy" "uptime" {
  for_each              = local.uptime
  display_name          = "Unreachable: ${each.value.host}"
  combiner              = "OR"
  notification_channels = local.channels

  conditions {
    display_name = "${each.value.host}${each.value.path} failing from more than one region"
    condition_threshold {
      filter          = "metric.type=\"monitoring.googleapis.com/uptime_check/check_passed\" AND resource.type=\"uptime_url\" AND metric.label.check_id=\"${google_monitoring_uptime_check_config.this[each.key].uptime_check_id}\""
      comparison      = "COMPARISON_GT"
      threshold_value = 1
      duration        = "600s"
      aggregations {
        alignment_period     = "1200s"
        per_series_aligner   = "ALIGN_NEXT_OLDER"
        cross_series_reducer = "REDUCE_COUNT_FALSE"
        group_by_fields      = ["resource.label.host"]
      }
    }
  }

  documentation {
    content   = "Uptime checks from several regions cannot reach ${each.value.host}: DNS, the certificate, the load balancer or the service."
    mime_type = "text/markdown"
  }
}
