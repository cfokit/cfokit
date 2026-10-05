# Production's values are the defaults: every one is a name, not a secret. Secrets are
# containers in secrets.tf, populated out of band (ADR-0016).

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

variable "app_host" {
  description = "The REST API and the web client, on one origin (ADR-0049, ADR-0055)."
  type        = string
  default     = "app.cfokit.ai"
}

variable "mcp_host" {
  description = "The MCP service's own origin."
  type        = string
  default     = "mcp.cfokit.ai"
}

variable "auth_host" {
  description = "The issuer's origin. Every party must reach it by this one name (ADR-0019)."
  type        = string
  default     = "auth.cfokit.ai"
}

variable "github_repository" {
  description = "owner/name of the repository whose main branch may deploy (ADR-0060 § 5)."
  type        = string
  default     = "cfokit/cfokit"
}

variable "bootstrap_image" {
  description = <<-EOT
    The image a service or job is created with, before the first deploy replaces it. OpenTofu
    ignores the image afterwards: the deploy workflow owns it.
  EOT
  type        = string
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}
