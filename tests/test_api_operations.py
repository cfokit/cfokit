"""Liveness and readiness behave differently on purpose (ADR-0004, infra/README.md)."""

from __future__ import annotations

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from cfokit.ledger import api as api_module
from cfokit.ledger.api import create_app
from cfokit.ledger.config import Settings
from cfokit.ledger.errors import NotAuthenticated
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


class _Accepts:
    def claims_for(self, credential: str | None) -> dict[str, object]:
        return {"sub": "user:ana"}


class _Refuses:
    def claims_for(self, credential: str | None) -> dict[str, object]:
        raise NotAuthenticated("no credential")


def test_connection_names_the_configured_mcp_address() -> None:
    """The address comes from MCP_PUBLIC_BASE_URL, with the MCP surface's fixed path."""
    settings = replace(SETTINGS, mcp_public_base_url="https://mcp.example.test/")
    client = TestClient(create_app(settings, authenticator=_Accepts()))

    response = client.get("/connection", headers={"Authorization": "Bearer t"})

    assert response.status_code == 200
    assert response.json() == {"mcp_url": "https://mcp.example.test/mcp"}


def test_connection_says_so_when_it_is_not_told() -> None:
    client = TestClient(create_app(SETTINGS, authenticator=_Accepts()))

    assert client.get("/connection").json() == {"mcp_url": None}


def test_connection_ignores_the_host_it_was_reached_at() -> None:
    """Never derived from a request header (ADR-0004)."""
    settings = replace(SETTINGS, mcp_public_base_url="https://mcp.example.test")
    client = TestClient(create_app(settings, authenticator=_Accepts()))

    body = client.get("/connection", headers={"Host": "attacker.test"}).json()

    assert body == {"mcp_url": "https://mcp.example.test/mcp"}


def test_connection_needs_a_signed_in_person() -> None:
    client = TestClient(create_app(SETTINGS, authenticator=_Refuses()))

    assert client.get("/connection").status_code == 401
