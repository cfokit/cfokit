"""Liveness and readiness behave differently on purpose (ADR-0004, infra/README.md)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from cfokit.ledger import api as api_module
from cfokit.ledger.api import create_app
from cfokit.ledger.config import Settings
from cfokit.ledger.service.readiness import Readiness

SETTINGS = Settings(
    database_url="postgresql://unreachable.invalid/none",
    public_base_url="http://localhost:8080",
    auth_issuer_url="http://localhost:8180/realms/cfokit",
    auth_audience="cfokit-ledger",
)


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(SETTINGS))


def test_healthz_is_ok_without_a_database(client: TestClient) -> None:
    """Liveness must not depend on the database.

    The settings above point at an unreachable host deliberately: if /healthz touched it,
    this test would fail, and in production a database blip would restart every healthy
    container.
    """
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readyz_reports_503_when_the_database_is_unreachable(client: TestClient) -> None:
    response = client.get("/readyz")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["database_reachable"] is False


def test_readyz_never_leaks_the_connection_string(client: TestClient) -> None:
    """The detail says what failed, never the DSN — it carries credentials."""
    body = client.get("/readyz").json()
    assert "unreachable.invalid" not in body["detail"]
    assert "postgresql://" not in body["detail"]


def test_readyz_is_not_ready_when_migrations_are_pending(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A schema older than the code is not ready — it is wrong."""
    monkeypatch.setattr(
        api_module,
        "check_readiness",
        lambda _url: Readiness(True, False, 2, "2 migration(s) pending; run the migrate job"),
    )
    app_client = TestClient(create_app(SETTINGS))
    response = app_client.get("/readyz")
    assert response.status_code == 503
    body = response.json()
    assert body["database_reachable"] is True
    assert body["migrations_current"] is False


def test_readyz_is_ready_when_everything_is_current(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        api_module, "check_readiness", lambda _url: Readiness(True, True, 0, "ready")
    )
    response = TestClient(create_app(SETTINGS)).get("/readyz")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_openapi_document_is_generated(client: TestClient) -> None:
    """CI gate 5 diffs this document; it has to exist first (ADR-0015)."""
    schema = client.get("/openapi.json").json()
    assert "/healthz" in schema["paths"]
    assert "/readyz" in schema["paths"]
