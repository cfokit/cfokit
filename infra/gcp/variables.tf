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

variable "bootstrap_image" {
  description = <<-EOT
    The image a service or job is created with, before the first deploy replaces it. OpenTofu
    ignores the image afterwards: the deploy workflow owns it.
  EOT
  type        = string
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}
