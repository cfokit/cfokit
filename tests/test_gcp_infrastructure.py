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
