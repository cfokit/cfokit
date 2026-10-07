# CFOKit's own production values are the defaults; a self-hosted deployment sets its own through
# TF_VAR_* (setup/env.sh does). Every value is a name, not a secret. Secrets are containers in
# secrets.tf, populated out of band (ADR-0016).

variable "project_id" {
  description = "The GCP project production runs in."
  type        = string
  default     = "cfokit-prod"
}

variable "region" {
  description = "Where the services, the job and the database run."
  type        = string
  default     = "us-central1"
}

variable "zone" {
  description = "The database's zone. The instance is zonal (ADR-0060 § 4)."
  type        = string
  default     = "us-central1-a"
}

variable "domain" {
  description = <<-EOT
    The deployment's domain. The API and web client are app.<domain>, MCP is mcp.<domain>, and
    the issuer is auth.<domain> (ADR-0060 § 2).
  EOT
  type        = string
  default     = "cfokit.ai"
}

variable "github_repository" {
  description = "owner/name of the repository whose main branch may deploy: yours, if a fork (ADR-0060 § 5)."
  type        = string
  default     = "cfokit/cfokit"
}

variable "admin_members" {
  description = <<-EOF2
    Who may reach the issuer's admin console through Identity-Aware Proxy, as IAM members
    ("user:someone@example.com"). setup/env.sh sets it to whoever runs the setup; no address is
    kept in the repository.
  EOF2
  type        = list(string)
}


variable "alert_emails" {
  description = <<-EOT
    Where monitoring.tf sends alerts, as email addresses. setup/env.sh sets it to whoever runs
    the setup; no address is kept in the repository.
  EOT
  type        = list(string)
}

variable "org_policies" {
  description = <<-EOT
    Whether orgpolicy.tf sets organization policy on the project. Needs roles/orgpolicy.policyAdmin
    at the organization; false for a project that has no organization.
  EOT
  type        = bool
  default     = true
}
