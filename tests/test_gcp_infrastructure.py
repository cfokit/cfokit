"""What the GCP configuration must agree with in the application (ADR-0055, ADR-0060).

CI runs no cloud deployment (ADR-0004), so these read `infra/gcp/` as text. Whether the load
balancer then routes as declared is the deployment check's to verify, after each deploy.
"""

from __future__ import annotations

import re
from pathlib import Path

from cfokit.server.web import security_headers

GCP = Path(__file__).resolve().parent.parent / "infra" / "gcp"


def _terraform() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in sorted(GCP.glob("*.tf")))


def _default(name: str) -> str:
    match = re.search(
        rf'variable "{name}" \{{.*?default\s*=\s*"([^"]+)"', _terraform(), flags=re.DOTALL
    )
    assert match, f"variable {name} has no default"
    return match.group(1)


def test_the_bucket_sends_the_headers_the_rest_service_sends() -> None:
    """ADR-0055 § 2: one set of security headers, from `security_headers()`, in two serving
    paths. The OpenTofu writes the issuer's origin as a reference; resolved, every header the
    REST service sends for /app/ must be configured on the backend bucket verbatim."""
    issuer_origin = f"https://auth.{_default('domain')}"
    configured = _terraform().replace("${local.issuer_origin}", issuer_origin)

    for name, value in security_headers(f"{issuer_origin}/realms/cfokit").items():
        assert f'"{name}: {value}"' in configured, name


def test_no_database_role_is_declared() -> None:
    """ADR-0060 § 4: a role's password would be in state. Roles are created out of band."""
    assert "google_sql_user" not in _terraform()


def test_no_secret_value_is_declared() -> None:
    """ADR-0016: IaC creates secret containers, never values."""
    assert "google_secret_manager_secret_version" not in _terraform()


def test_the_master_realm_answers_only_behind_identity_aware_proxy() -> None:
    """SOC2-23: the realm holding the administrators is privileged access. On the public sign-in
    host its paths are served by the backend Identity-Aware Proxy guards, as the console is."""
    auth = re.search(r'path_matcher \{\s*name\s*=\s*"auth".*?\n  \}\n', _terraform(), re.DOTALL)
    assert auth, "no auth path matcher"
    rule = re.search(
        r'paths\s*=\s*\["/realms/master", "/realms/master/\*"\]\s*service\s*=\s*([\w.]+)',
        auth.group(0),
    )
    assert rule and rule.group(1) == "google_compute_backend_service.issuer_admin.id"
    assert re.search(
        r'resource "google_compute_backend_service" "issuer_admin" \{'
        r".*?iap \{\s*enabled\s*=\s*true",
        _terraform(),
        re.DOTALL,
    )


def test_production_sets_the_access_token_lifetime() -> None:
    """SOC2-20: the hosted service does not inherit the eight hours a laptop uses."""
    match = re.search(r'CFOKIT_ACCESS_TOKEN_LIFESPAN\s*=\s*"(\d+)"', _terraform())
    assert match and int(match.group(1)) <= 900


def test_every_backend_that_runs_code_has_a_security_policy() -> None:
    """Every backend service carries Cloud Armor; the bucket serves only static files."""
    terraform = _terraform()
    backends = re.findall(
        r'resource "google_compute_backend_service" "(\w+)" \{(.*?)\n\}', terraform, re.DOTALL
    )
    assert backends
    for name, body in backends:
        assert "security_policy" in body, name


def test_no_cloud_armor_expression_has_a_capture_group() -> None:
    """Cloud Armor refuses a regular expression containing a capture group ("Capture Groups
    are not allowed"), and only when the policy is created: OpenTofu sees only a string."""
    armor = (GCP / "armor.tf").read_text(encoding="utf-8")
    for pattern in re.findall(r"matches\('([^']*)'\)", armor):
        assert "(" not in pattern.replace("(?:", ""), pattern


def test_the_master_realm_is_pointed_at_the_admin_console_host() -> None:
    """The console signs in to the master realm at its frontend URL, from a hidden frame. On the
    public host, Identity-Aware Proxy guards the master realm and cannot answer in a frame, so
    the settings job points it at the console's own host."""
    job = re.search(
        r'resource "google_cloud_run_v2_job" "issuer_settings" \{.*?\n\}',
        _terraform(),
        re.DOTALL,
    )
    assert job, "no settings job"
    assert re.search(
        r'CFOKIT_MASTER_FRONTEND_URL\s*=\s*"https://\$\{local\.admin_host\}"', job.group(0)
    )
    assert 'command = ["/bin/bash", "/opt/cfokit/realm-settings.sh"]' in job.group(0)


def test_production_restricts_where_a_registered_client_may_redirect() -> None:
    """ADR-0064: the hosted issuer is reachable from anywhere, so the switch is on, and the
    settings job applies the same value to the running realm."""
    terraform = _terraform()
    assert re.search(r'CFOKIT_RESTRICT_REGISTERED_REDIRECTS\s*=\s*"true"', terraform)
    assert re.search(
        r"CFOKIT_RESTRICT_REGISTERED_REDIRECTS\s*=\s*local\.issuer_env\.CFOKIT_RESTRICT_REGISTERED_REDIRECTS",
        terraform,
    )


def test_every_cloud_run_ingress_and_egress_is_one_the_org_policy_allows() -> None:
    """A service or job declared with a setting the project's policy refuses fails only when
    OpenTofu applies it. Each ingress and egress in run.tf must be among the policy's values."""
    terraform = _terraform()
    named = {
        "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER": "internal-and-cloud-load-balancing",
        "PRIVATE_RANGES_ONLY": "private-ranges-only",
    }
    for setting, constraint in (
        ("ingress", "run.allowedIngress"),
        ("egress", "run.allowedVPCEgress"),
    ):
        allowed = re.search(rf'"{re.escape(constraint)}"\s*=\s*\[([^\]]*)\]', terraform)
        assert allowed, constraint
        for used in set(re.findall(rf'\b{setting}\s*=\s*"([A-Z_]+)"', terraform)):
            assert f'"{named[used]}"' in allowed.group(1), (setting, used)


def test_a_change_to_organization_policy_is_alerted() -> None:
    """orgpolicy.tf rests on a policy change being audited and alerted (SOC2-24): an alert's log
    filter names the Org Policy service, and the legacy methods that set the same policies."""
    monitoring = (GCP / "monitoring.tf").read_text(encoding="utf-8")
    filters = re.findall(r"filter\s*=\s*\"(.*)\"\n", monitoring)
    assert any(
        'serviceName=\\"orgpolicy.googleapis.com\\"' in f and "SetOrgPolicy" in f
        for f in filters
    )


def test_the_database_refuses_deletion_and_its_backups_outlive_it() -> None:
    """SOC2-14: deletion is refused by Cloud SQL itself, not only by OpenTofu, and a deleted
    instance's backups are kept."""
    database = (GCP / "database.tf").read_text(encoding="utf-8")
    assert re.search(r"deletion_protection_enabled\s*=\s*true", database)
    assert re.search(r"retain_backups_on_delete\s*=\s*true", database)


def test_audit_evidence_is_kept_where_nobody_can_delete_it() -> None:
    """SOC2-24: Data Access audit logs, and the issuer's sign-in events, are routed to a bucket
    that is locked for 400 days, the review period and its lookback."""
    audit = (GCP / "audit.tf").read_text(encoding="utf-8")
    bucket = re.search(
        r'resource "google_logging_project_bucket_config" "audit" \{(.*?)\n\}', audit, re.DOTALL
    )
    assert bucket
    assert re.search(r"locked\s*=\s*true", bucket.group(1))
    assert re.search(r"retention_days\s*=\s*400", bucket.group(1))
    sink = re.search(
        r'resource "google_logging_project_sink" "audit" \{(.*?)\n\}', audit, re.DOTALL
    )
    assert sink
    assert "cloudaudit.googleapis.com%2Fdata_access" in sink.group(1)
    assert "org.keycloak.events" in sink.group(1)


def test_a_slow_cold_start_is_waited_for() -> None:
    """A REST or MCP instance's startup probe allows at least a minute. Production's cold
    starts took two or three of Cloud Run's three default checks; the slowest were killed."""
    run = (GCP / "run.tf").read_text(encoding="utf-8")
    api = re.search(r'resource "google_cloud_run_v2_service" "api" \{(.*?)\n\}', run, re.DOTALL)
    assert api
    probe = re.search(r"startup_probe \{(.*?)\n      \}", api.group(1), re.DOTALL)
    assert probe
    period = re.search(r"period_seconds\s*=\s*(\d+)", probe.group(1))
    tries = re.search(r"failure_threshold\s*=\s*(\d+)", probe.group(1))
    assert period and tries
    assert int(period.group(1)) * int(tries.group(1)) >= 60
