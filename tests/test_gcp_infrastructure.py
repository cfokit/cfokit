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
