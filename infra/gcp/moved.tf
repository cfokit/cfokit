# The issuer's resources, renamed for the capability they provide: identity. Each was the same
# resource under another address, so OpenTofu plans a replacement where the name changed, made
# create-before-destroy so nothing in the sign-in path is missing at any moment, and leaves a
# binding or a map entry that only moved in place. Kept until every deployment has
# applied the rename (setup/rename-identity.sh), then removed.

# The old service is forgotten rather than moved: deletion protection lives in OpenTofu's state,
# so a replacement could not remove it. cfokit-identity is created beside it, the load balancer
# moves to the new one, and setup/rename-identity.sh deletes cfokit-issuer once sign-in works.
removed {
  from = google_cloud_run_v2_service.issuer

  lifecycle {
    destroy = false
  }
}

moved {
  from = google_cloud_run_v2_job.issuer_import
  to   = google_cloud_run_v2_job.identity_import
}

moved {
  from = google_cloud_run_v2_job.issuer_settings
  to   = google_cloud_run_v2_job.identity_settings
}

moved {
  from = google_service_account.issuer
  to   = google_service_account.identity
}

moved {
  from = google_compute_security_policy.issuer
  to   = google_compute_security_policy.identity
}

moved {
  from = google_compute_backend_service.issuer_admin
  to   = google_compute_backend_service.identity_admin
}

moved {
  from = google_compute_region_network_endpoint_group.run["issuer"]
  to   = google_compute_region_network_endpoint_group.run["identity"]
}

moved {
  from = google_compute_backend_service.run["issuer"]
  to   = google_compute_backend_service.run["identity"]
}

moved {
  from = google_cloud_run_v2_service_iam_member.public["issuer"]
  to   = google_cloud_run_v2_service_iam_member.public["identity"]
}

moved {
  from = google_service_account_iam_member.deploy_acts_as["issuer"]
  to   = google_service_account_iam_member.deploy_acts_as["identity"]
}

moved {
  from = google_monitoring_uptime_check_config.this["issuer"]
  to   = google_monitoring_uptime_check_config.this["identity"]
}

moved {
  from = google_monitoring_alert_policy.uptime["issuer"]
  to   = google_monitoring_alert_policy.uptime["identity"]
}
