# Production on GCP (ADR-0017, ADR-0055, ADR-0060). Applied by a person, never by the deploy
# pipeline: the identity that changes networks, databases and IAM does not run on every merge.
#
# The state bucket and its KMS key exist before `tofu init` can, so they are created once by
# hand; README.md has the commands.

terraform {
  required_version = ">= 1.10"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 8.5"
    }
  }

  backend "gcs" {
    bucket = "cfokit-prod-tofu-state"
    prefix = "prod"
  }

  # State holds every resource's attributes, including some that are sensitive. Encrypted with a
  # KMS key, a reader of the bucket alone reads nothing (ADR-0016, ADR-0060 § 6).
  encryption {
    key_provider "gcp_kms" "state" {
      kms_encryption_key = "projects/cfokit-prod/locations/us-central1/keyRings/tofu/cryptoKeys/state"
      key_length         = 32
    }
    method "aes_gcm" "state" {
      keys = key_provider.gcp_kms.state
    }
    state {
      method   = method.aes_gcm.state
      enforced = true
    }
    plan {
      method   = method.aes_gcm.state
      enforced = true
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}
