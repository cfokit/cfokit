# The database has a private IP only. Services and jobs reach it through Direct VPC egress into
# this subnet, so DATABASE_URL is a plain connection string, as the contract says (ADR-0060 § 4).

resource "google_compute_network" "this" {
  name                    = "cfokit"
  auto_create_subnetworks = false
  depends_on              = [google_project_service.this]
}

resource "google_compute_subnetwork" "run" {
  name          = "cfokit-run"
  network       = google_compute_network.this.id
  region        = var.region
  ip_cidr_range = "10.10.0.0/24"

  # Which addresses every service and job reached, and when (SOC2-24): half of the flows,
  # summed over five minutes, which is enough to see an unexpected destination at a cost
  # proportional to traffic that is mostly the database.
  log_config {
    aggregation_interval = "INTERVAL_5_MIN"
    flow_sampling        = 0.5
    metadata             = "INCLUDE_ALL_METADATA"
  }
}

# Private services access: the range Cloud SQL's private IP is allocated from.
resource "google_compute_global_address" "sql" {
  name          = "cfokit-sql"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 20
  network       = google_compute_network.this.id
}

resource "google_service_networking_connection" "sql" {
  network                 = google_compute_network.this.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.sql.name]
}
