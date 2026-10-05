output "load_balancer_ip" {
  description = "Point each hostname's A record here, unproxied (ADR-0060 § 2)."
  value       = google_compute_global_address.lb.address
}

output "dns_records" {
  description = "The records to set at the DNS provider."
  value = {
    for host in [local.app_host, local.mcp_host, local.auth_host, local.admin_host] :
    host => "A ${google_compute_global_address.lb.address} (DNS only, not proxied)"
  }
}

output "database_instance" {
  description = "The Cloud SQL instance's name."
  value       = google_sql_database_instance.this.name
}

output "database_private_ip" {
  description = "The host every DATABASE_URL names."
  value       = google_sql_database_instance.this.private_ip_address
}

output "workload_identity_provider" {
  description = "The deploy workflow's workload_identity_provider."
  value       = google_iam_workload_identity_pool_provider.github.name
}

output "deploy_service_account" {
  description = "The deploy workflow's service_account."
  value       = google_service_account.deploy.email
}

output "image_repository" {
  description = "Where the deploy workflow pushes images."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}"
}

output "web_bucket" {
  description = "Where the deploy workflow uploads the web build."
  value       = google_storage_bucket.web.name
}
