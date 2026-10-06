# Cloud Armor in front of every backend that runs code.
#
# The issuer locks an account after repeated failures (infra/keycloak/README.md), which stops
# guessing one person's password. It does not stop one address trying a few passwords against
# many accounts, or registering clients by the thousand; these do, before the request reaches
# Keycloak. Every decision is in the load balancer's request log.
#
# Limits are per client address. Claude's custom connectors reach the issuer and MCP from
# Anthropic's addresses, shared by every person using one, so the limits that a connector meets
# are set well above what one person's sessions make.

resource "google_compute_security_policy" "issuer" {
  name        = "cfokit-issuer"
  description = "Rate limits on sign-in, token and client registration."

  adaptive_protection_config {
    layer_7_ddos_defense_config {
      enable = true
    }
  }

  # Sign-in, registration and reset forms are posted by a person, a few times a minute at most.
  # An address posting more is guessing; it is refused for fifteen minutes.
  rule {
    priority    = 1000
    action      = "rate_based_ban"
    description = "Forms: 20 a minute per address, then a 15-minute ban."
    match {
      expr {
        expression = "request.path.matches('^/realms/[^/]+/login-actions/')"
      }
    }
    rate_limit_options {
      conform_action   = "allow"
      exceed_action    = "deny(429)"
      enforce_on_key   = "IP"
      ban_duration_sec = 900
      rate_limit_threshold {
        count        = 20
        interval_sec = 60
      }
    }
  }

  # Token refreshes and client registration come from programs, including connectors that share
  # an address, so these are throttled rather than banned.
  rule {
    priority    = 1100
    action      = "throttle"
    description = "Token and registration endpoints: 300 a minute per address."
    match {
      expr {
        # Two expressions, because Cloud Armor refuses a capture group in a regular expression.
        expression = "request.path.matches('^/realms/[^/]+/protocol/openid-connect/token') || request.path.matches('^/realms/[^/]+/clients-registrations/')"
      }
    }
    rate_limit_options {
      conform_action = "allow"
      exceed_action  = "deny(429)"
      enforce_on_key = "IP"
      rate_limit_threshold {
        count        = 300
        interval_sec = 60
      }
    }
  }

  rule {
    priority    = 2147483647
    action      = "allow"
    description = "Everything else."
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
  }
}

resource "google_compute_security_policy" "api" {
  name        = "cfokit-api"
  description = "A ceiling on requests per address to REST and MCP."

  adaptive_protection_config {
    layer_7_ddos_defense_config {
      enable = true
    }
  }

  rule {
    priority    = 1000
    action      = "throttle"
    description = "1200 requests a minute per address."
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
    rate_limit_options {
      conform_action = "allow"
      exceed_action  = "deny(429)"
      enforce_on_key = "IP"
      rate_limit_threshold {
        count        = 1200
        interval_sec = 60
      }
    }
  }

  rule {
    priority    = 2147483647
    action      = "allow"
    description = "Everything else."
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
  }
}
