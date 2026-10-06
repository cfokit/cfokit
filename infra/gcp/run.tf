# The services and the migration job (ADR-0023: one image, two shapes; ADR-0060).
#
# Every service's ingress is internal and Cloud Load Balancing only, so the load balancer's
# hostnames are the only public addresses (ADR-0060 § 2). Each is created from the `latest` image
# setup/images.sh pushes; the deploy owns the image from then on, which is why OpenTofu ignores it.

locals {
  images    = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}"
  app_image = "${local.images}/app:latest"

  vpc_egress = {
    network    = google_compute_network.this.id
    subnetwork = google_compute_subnetwork.run.id
  }

  # What the REST and MCP services both read. PUBLIC_BASE_URL differs per service, so it is
  # set beside each (infra/README.md).
  service_env = {
    AUTH_ISSUER_URL = local.issuer_url
    AUTH_AUDIENCE   = local.audience
    LOG_LEVEL       = "info"
  }
}

resource "google_cloud_run_v2_service" "api" {
  for_each = {
    rest = { host = local.app_host, extra = { MCP_PUBLIC_BASE_URL = "https://${local.mcp_host}" } }
    mcp  = { host = local.mcp_host, extra = {} }
  }

  name                = "cfokit-${each.key}"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"
  deletion_protection = true

  template {
    service_account = google_service_account.service.email

    scaling {
      min_instance_count = 0
      max_instance_count = 4
    }

    vpc_access {
      network_interfaces {
        network    = local.vpc_egress.network
        subnetwork = local.vpc_egress.subnetwork
      }
      egress = "PRIVATE_RANGES_ONLY"
    }

    containers {
      image   = local.app_image
      command = ["python", "-m", "cfokit.server", each.key]

      ports {
        container_port = 8080
      }

      dynamic "env" {
        for_each = merge(local.service_env, each.value.extra, {
          PUBLIC_BASE_URL = "https://${each.value.host}"
        })
        content {
          name  = env.key
          value = env.value
        }
      }

      env {
        name = "DATABASE_URL"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.this["database-url-app"].secret_id
            version = "latest"
          }
        }
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
        startup_cpu_boost = true
      }

      # Liveness only: /healthz does not touch the database, so a migration never restarts a
      # healthy container (infra/README.md, "Health endpoints").
      startup_probe {
        http_get {
          path = "/healthz"
        }
      }
      liveness_probe {
        http_get {
          path = "/healthz"
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [
      template[0].containers[0].image,
      client,
      client_version,
    ]
  }

  depends_on = [google_secret_manager_secret_iam_member.reader]
}

# ---------------------------------------------------------------------------------------------
# The issuer: Keycloak, one instance, never scaled to zero (ADR-0060 § 3).
# ---------------------------------------------------------------------------------------------
locals {
  # One definition, read by the service and by the realm import job below, so the two can never
  # disagree about which database or which settings the realm is built from.
  issuer_env = {
    KC_DB             = "postgres"
    KC_DB_URL         = "jdbc:postgresql://${google_sql_database_instance.this.private_ip_address}:5432/keycloak?sslmode=require"
    KC_DB_USERNAME    = "keycloak"
    KC_HOSTNAME       = local.issuer_origin
    KC_HOSTNAME_ADMIN = "https://${local.admin_host}"
    KC_HTTP_ENABLED   = "true"
    KC_HTTP_PORT      = "8080"
    KC_PROXY_HEADERS  = "xforwarded"
    KC_HEALTH_ENABLED = "true"
    KC_CACHE          = "local"
    # The realm's web client redirects to the web client and nowhere else.
    PUBLIC_BASE_URL             = "https://${local.app_host}"
    KC_BOOTSTRAP_ADMIN_USERNAME = "admin"
    # The hosted service is a service organization: every person signs in with a second
    # factor (SOC2-19). Read when the realm is first imported; a self-hosted install
    # leaves it unset and the factor optional (IAM-23).
    CFOKIT_REQUIRE_SECOND_FACTOR = "true"
  }

  issuer_secrets = {
    KC_DB_PASSWORD              = "keycloak-db-password"
    KC_BOOTSTRAP_ADMIN_PASSWORD = "keycloak-admin-password"
  }
}
resource "google_cloud_run_v2_service" "issuer" {
  name                = "cfokit-issuer"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"
  deletion_protection = true

  template {
    service_account = google_service_account.issuer.email

    # Exactly one: clustering needs instances to discover each other, which Cloud Run does not
    # provide, and a sign-in must not wait for a JVM to start.
    scaling {
      min_instance_count = 1
      max_instance_count = 1
    }

    vpc_access {
      network_interfaces {
        network    = local.vpc_egress.network
        subnetwork = local.vpc_egress.subnetwork
      }
      egress = "PRIVATE_RANGES_ONLY"
    }

    containers {
      image = "${local.images}/issuer:latest"
      args  = ["start", "--import-realm"]

      ports {
        container_port = 8080
      }

      dynamic "env" {
        for_each = local.issuer_env
        content {
          name  = env.key
          value = env.value
        }
      }

      dynamic "env" {
        for_each = local.issuer_secrets
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.this[env.value].secret_id
              version = "latest"
            }
          }
        }
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "2Gi"
        }
        # Billed per request, with the one instance kept warm: about $20 a month against $58 with
        # CPU always allocated (Cloud Billing catalog, us-central1). Between requests the CPU is
        # throttled, so Keycloak's background work — expiring sessions, cleaning caches — runs
        # slowly; sessions persist in the database, so nobody is signed out, and a sign-in runs
        # at full speed. Set false if sign-ins ever stall after an idle spell.
        cpu_idle          = true
        startup_cpu_boost = true
      }

      # Ready when a realm answers, not when the port opens: Keycloak listens before it has
      # bootstrapped and answers 503 until it has. Until this passes the instance is starting and
      # has its full CPU, so the bootstrap finishes before traffic arrives rather than crawling
      # between throttled requests. Health is on the management port, which Cloud Run cannot probe.
      startup_probe {
        http_get {
          path = "/realms/master"
          port = 8080
        }
        initial_delay_seconds = 10
        period_seconds        = 10
        timeout_seconds       = 5
        failure_threshold     = 30
      }
    }
  }

  lifecycle {
    ignore_changes = [
      template[0].containers[0].image,
      template[0].revision,
      client,
      client_version,
    ]
  }

  depends_on = [google_secret_manager_secret_iam_member.reader]
}

# Replaces the realm with the one in the issuer image (setup/realm.sh). Keycloak imports a realm
# only when it does not exist, so a change to infra/keycloak/cfokit-realm.json reaches a running
# deployment only through this, and it removes the realm's accounts.
resource "google_cloud_run_v2_job" "issuer_import" {
  name                = "cfokit-issuer-import"
  location            = var.region
  deletion_protection = false

  template {
    task_count = 1
    template {
      service_account = google_service_account.issuer.email
      max_retries     = 0
      timeout         = "900s"

      vpc_access {
        network_interfaces {
          network    = local.vpc_egress.network
          subnetwork = local.vpc_egress.subnetwork
        }
        egress = "PRIVATE_RANGES_ONLY"
      }

      containers {
        image = "${local.images}/issuer:latest"
        args  = ["import", "--dir", "/opt/keycloak/data/import", "--override", "true"]

        dynamic "env" {
          for_each = local.issuer_env
          content {
            name  = env.key
            value = env.value
          }
        }

        dynamic "env" {
          for_each = local.issuer_secrets
          content {
            name = env.key
            value_source {
              secret_key_ref {
                secret  = google_secret_manager_secret.this[env.value].secret_id
                version = "latest"
              }
            }
          }
        }

        resources {
          limits = {
            cpu    = "1"
            memory = "2Gi"
          }
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [
      template[0].template[0].containers[0].image,
      client,
      client_version,
    ]
  }

  depends_on = [google_secret_manager_secret_iam_member.reader]
}

# The load balancer reaches every service without IAM, so each admits unauthenticated
# invocation; ingress keeps it to the load balancer. The application authenticates every
# request itself (ADR-0019).
resource "google_cloud_run_v2_service_iam_member" "public" {
  for_each = {
    rest   = google_cloud_run_v2_service.api["rest"].name
    mcp    = google_cloud_run_v2_service.api["mcp"].name
    issuer = google_cloud_run_v2_service.issuer.name
  }
  name     = each.value
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# ---------------------------------------------------------------------------------------------
# Migrations: a job, run explicitly by the deploy before any revision rolls out, never at
# startup (ADR-0004). No request timeout.
# ---------------------------------------------------------------------------------------------
resource "google_cloud_run_v2_job" "migrate" {
  name                = "cfokit-migrate"
  location            = var.region
  deletion_protection = true

  template {
    task_count = 1
    template {
      service_account = google_service_account.migrate.email
      max_retries     = 0
      timeout         = "1800s"

      vpc_access {
        network_interfaces {
          network    = local.vpc_egress.network
          subnetwork = local.vpc_egress.subnetwork
        }
        egress = "PRIVATE_RANGES_ONLY"
      }

      containers {
        image   = local.app_image
        command = ["python", "-m", "cfokit.ledger.migrations"]

        env {
          name  = "LOG_LEVEL"
          value = "info"
        }
        env {
          name = "DATABASE_URL"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.this["database-url-owner"].secret_id
              version = "latest"
            }
          }
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [
      template[0].template[0].containers[0].image,
      client,
      client_version,
    ]
  }

  depends_on = [google_secret_manager_secret_iam_member.reader]
}
