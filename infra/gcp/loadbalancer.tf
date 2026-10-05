# One global external Application Load Balancer for three hostnames (ADR-0055, ADR-0060 § 2).
#
#   app  — /app/* from the web bucket behind Cloud CDN; / redirects to /app/; everything else,
#          /.well-known/ included, to the REST service.
#   mcp  — everything to the MCP service.
#   auth — everything to the issuer.

# ---------------------------------------------------------------------------------------------
# The web client's bucket. Objects are stored under app/, so the request path is the object name.
# ---------------------------------------------------------------------------------------------
resource "google_storage_bucket" "web" {
  name                        = "${var.project_id}-web"
  location                    = "US"
  uniform_bucket_level_access = true
  public_access_prevention    = "inherited"
  force_destroy               = false
  depends_on                  = [google_project_service.this]
}

# The build is public: it is what every browser downloads.
resource "google_storage_bucket_iam_member" "web_public" {
  bucket = google_storage_bucket.web.name
  role   = "roles/storage.objectViewer"
  member = "allUsers"
}

resource "google_compute_backend_bucket" "web" {
  name        = "cfokit-web"
  bucket_name = google_storage_bucket.web.name
  enable_cdn  = true

  cdn_policy {
    # Each object's Cache-Control is set at upload: hashed assets immutable for a year, the
    # rest revalidated (ADR-0055 § 2).
    cache_mode = "USE_ORIGIN_HEADERS"
  }

  # The same headers the REST service sends for /app/, from one source: security_headers() in
  # src/cfokit/server/web.py. tests/test_gcp_infrastructure.py asserts they agree.
  custom_response_headers = [
    "Content-Security-Policy: default-src 'self'; connect-src 'self' ${local.issuer_origin}; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; form-action 'self'",
    "X-Content-Type-Options: nosniff",
    "Referrer-Policy: same-origin",
  ]
}

# ---------------------------------------------------------------------------------------------
# Each Cloud Run service, as a serverless network endpoint group and a backend.
# ---------------------------------------------------------------------------------------------
locals {
  run_backends = {
    rest   = google_cloud_run_v2_service.api["rest"].name
    mcp    = google_cloud_run_v2_service.api["mcp"].name
    issuer = google_cloud_run_v2_service.issuer.name
  }
}

resource "google_compute_region_network_endpoint_group" "run" {
  for_each              = local.run_backends
  name                  = "cfokit-${each.key}"
  region                = var.region
  network_endpoint_type = "SERVERLESS"

  cloud_run {
    service = each.value
  }
}

resource "google_compute_backend_service" "run" {
  for_each              = local.run_backends
  name                  = "cfokit-${each.key}"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  protocol              = "HTTPS"

  backend {
    group = google_compute_region_network_endpoint_group.run[each.key].id
  }

  log_config {
    enable      = true
    sample_rate = 1.0
  }
}

# ---------------------------------------------------------------------------------------------
# Routing.
# ---------------------------------------------------------------------------------------------
resource "google_compute_url_map" "https" {
  name            = "cfokit"
  default_service = google_compute_backend_service.run["rest"].id

  host_rule {
    hosts        = [local.app_host]
    path_matcher = "app"
  }
  host_rule {
    hosts        = [local.mcp_host]
    path_matcher = "mcp"
  }
  host_rule {
    hosts        = [local.auth_host]
    path_matcher = "auth"
  }

  path_matcher {
    name            = "app"
    default_service = google_compute_backend_service.run["rest"].id

    path_rule {
      paths = ["/", "/app"]
      url_redirect {
        path_redirect          = "/app/"
        redirect_response_code = "FOUND"
        strip_query            = false
      }
    }

    path_rule {
      paths   = ["/app/*"]
      service = google_compute_backend_bucket.web.id

      # A deep link names no object, so the bucket answers 404; the client's own page answers
      # instead, with 200, and its router takes it from there (ADR-0055 § 1). Scoped to this
      # rule, so a REST 404 stays a 404.
      custom_error_response_policy {
        error_response_rule {
          match_response_codes   = ["404"]
          path                   = "/app/index.html"
          override_response_code = 200
        }
        error_service = google_compute_backend_bucket.web.id
      }
    }
  }

  path_matcher {
    name            = "mcp"
    default_service = google_compute_backend_service.run["mcp"].id
  }

  path_matcher {
    name            = "auth"
    default_service = google_compute_backend_service.run["issuer"].id
  }
}

resource "google_compute_global_address" "lb" {
  name       = "cfokit"
  depends_on = [google_project_service.this]
}

resource "google_compute_managed_ssl_certificate" "this" {
  name = "cfokit"
  managed {
    domains = [local.app_host, local.mcp_host, local.auth_host]
  }
}

# TLS 1.2 and later, with modern ciphers only: customer data is encrypted in transit (SOC2-14).
resource "google_compute_ssl_policy" "this" {
  name            = "cfokit"
  profile         = "MODERN"
  min_tls_version = "TLS_1_2"
}

resource "google_compute_target_https_proxy" "this" {
  name             = "cfokit"
  url_map          = google_compute_url_map.https.id
  ssl_certificates = [google_compute_managed_ssl_certificate.this.id]
  ssl_policy       = google_compute_ssl_policy.this.id
}

resource "google_compute_global_forwarding_rule" "https" {
  name                  = "cfokit-https"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  ip_address            = google_compute_global_address.lb.address
  port_range            = "443"
  target                = google_compute_target_https_proxy.this.id
}

# Plain HTTP only redirects.
resource "google_compute_url_map" "http" {
  name = "cfokit-http"
  default_url_redirect {
    https_redirect = true
    strip_query    = false
  }
}

resource "google_compute_target_http_proxy" "this" {
  name    = "cfokit-http"
  url_map = google_compute_url_map.http.id
}

resource "google_compute_global_forwarding_rule" "http" {
  name                  = "cfokit-http"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  ip_address            = google_compute_global_address.lb.address
  port_range            = "80"
  target                = google_compute_target_http_proxy.this.id
}
