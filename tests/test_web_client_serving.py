"""The REST service serves the web client's build at /app/, and nothing else (ADR-0049 § 5).

No database and no real build: a directory shaped like Vite's output stands in for it, because
what is under test is how the files are handed out, not how they were made.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cfokit.ledger.config import Settings
from cfokit.server import rest_app

INDEX = "<!doctype html><title>CFOKit</title>"
SCRIPT = "console.log('client')"


def settings() -> Settings:
    return Settings(
        database_url="postgresql://web.invalid/none",
        public_base_url="http://localhost:8080",
        auth_issuer_url="http://localhost:8180/realms/cfokit",
        auth_audience="cfokit-ledger",
    )


@pytest.fixture
def build(tmp_path: Path) -> Path:
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text(INDEX)
    (tmp_path / "assets" / "index-abc123.js").write_text(SCRIPT)
    (tmp_path.parent / "secret.txt").write_text("outside the build")
    return tmp_path


@pytest.fixture
def client(build: Path) -> TestClient:
    return TestClient(rest_app(settings(), web_root=build), follow_redirects=False)


def test_the_root_sends_a_browser_to_the_client(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 308
    assert response.headers["location"] == "/app/"


def test_the_client_path_without_a_slash_is_redirected(client: TestClient) -> None:
    response = client.get("/app")
    assert response.status_code == 308
    assert response.headers["location"] == "/app/"


def test_the_client_index_is_served(client: TestClient) -> None:
    response = client.get("/app/")
    assert response.status_code == 200
    assert response.text == INDEX


def test_a_deep_link_is_answered_with_the_index_for_the_router(client: TestClient) -> None:
    response = client.get("/app/entities/42/import")
    assert response.status_code == 200
    assert response.text == INDEX


def test_a_missing_file_is_404_not_the_index(client: TestClient) -> None:
    """HTML handed to a script tag fails confusingly; a missing chunk must fail as missing."""
    assert client.get("/app/assets/index-gone.js").status_code == 404


def test_nothing_outside_the_build_is_reachable(client: TestClient) -> None:
    assert client.get("/app/../secret.txt").status_code == 404
    assert client.get("/app/%2e%2e/secret.txt").status_code == 404


def test_every_client_response_carries_the_csp(client: TestClient) -> None:
    """ADR-0049 § 6: default-src 'self', on every page and file the client is served from."""
    for path in ("/app/", "/app/entities/42", "/app/assets/index-abc123.js"):
        csp = client.get(path).headers["content-security-policy"]
        assert "default-src 'self'" in csp
        assert client.get(path).headers["x-content-type-options"] == "nosniff"


def test_hashed_assets_are_immutable_and_the_index_revalidates(client: TestClient) -> None:
    """ADR-0055 § 2: a content-hashed file never changes meaning; the index must, per deploy."""
    asset = client.get("/app/assets/index-abc123.js").headers["cache-control"]
    assert "immutable" in asset
    assert client.get("/app/").headers["cache-control"] == "no-cache"


def test_the_client_adds_nothing_to_the_published_interface(build: Path) -> None:
    """ADR-0049 § 4: no endpoints of its own. Serving files is not API; gate 5 sees nothing."""
    with_client = set(rest_app(settings(), web_root=build).openapi()["paths"])
    without = set(rest_app(settings()).openapi()["paths"])
    assert with_client == without


def test_without_a_build_the_api_is_served_alone() -> None:
    client = TestClient(rest_app(settings()), follow_redirects=False)
    assert client.get("/app/").status_code == 404
    assert client.get("/healthz").status_code == 200
