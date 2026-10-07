# Organization policy on the project: what may not be created here, whoever asks (SOC2-14,
# SOC2-21). IAM decides who may act; these decide what nobody may do, an Owner included, without
# first changing a policy, which is itself an audited and alerted change (monitoring.tf).
#
# Set on the project rather than the organization, so they move with it. Two kinds of policy
# belong to the organization instead, and are not here: those read only when a project is created
# (no default network, no automatic Editor grant to default service accounts), and
# domain-restricted sharing, which would refuse the `allUsers` grants the web bucket and the
# load balancer's backends need (loadbalancer.tf, run.tf).
#
# Public access prevention on buckets is not enforced either: the web client's bucket is public
# by design, because it is what every browser downloads (ADR-0055).
#
# Setting these needs `roles/orgpolicy.policyAdmin`, which only exists at the organization; a
# deployment whose project has no organization sets var.org_policies to false.

locals {
  org_policy_enforced = var.org_policies ? toset([
    # No long-lived key for any service account: runtimes use their attached identity, and the
    # deploy federates from GitHub (iam.tf).
    "iam.disableServiceAccountKeyCreation",
    "iam.disableServiceAccountKeyUpload",
    # The database is reachable on its private address only (database.tf).
    "sql.restrictPublicIp",
    "sql.restrictAuthorizedNetworks",
    "storage.uniformBucketLevelAccess",
    # No virtual machines run here; if one ever does, it is reached through OS Login, not a key
    # in metadata, and has no serial console.
    "compute.requireOsLogin",
    "compute.disableSerialPortAccess",
  ]) : toset([])

  org_policy_allowed = var.org_policies ? {
    # Customer data stays in the United States. Global resources, such as the load balancer, are
    # not located and so not restricted.
    "gcp.resourceLocations" = ["in:us-locations"]
    # The only ways in are the load balancer's hostnames (ADR-0060 § 2), and the only way out
    # of a service into the network is to private addresses (run.tf).
    "run.allowedIngress"   = ["internal-and-cloud-load-balancing"]
    "run.allowedVPCEgress" = ["private-ranges-only"]
    # Federation trusts GitHub Actions and no other issuer (iam.tf).
    "iam.workloadIdentityPoolProviders" = ["https://token.actions.githubusercontent.com"]
  } : {}
}

resource "google_org_policy_policy" "enforced" {
  for_each = local.org_policy_enforced
  name     = "projects/${var.project_id}/policies/${each.value}"
  parent   = "projects/${var.project_id}"

  spec {
    rules {
      enforce = "TRUE"
    }
  }

  depends_on = [google_project_service.this]
}

resource "google_org_policy_policy" "allowed" {
  for_each = local.org_policy_allowed
  name     = "projects/${var.project_id}/policies/${each.key}"
  parent   = "projects/${var.project_id}"

  spec {
    rules {
      values {
        allowed_values = each.value
      }
    }
  }

  depends_on = [google_project_service.this]
}

# No virtual machine may have a public address.
resource "google_org_policy_policy" "no_vm_external_ip" {
  count  = var.org_policies ? 1 : 0
  name   = "projects/${var.project_id}/policies/compute.vmExternalIpAccess"
  parent = "projects/${var.project_id}"

  spec {
    rules {
      deny_all = "TRUE"
    }
  }

  depends_on = [google_project_service.this]
}
