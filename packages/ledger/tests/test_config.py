"""Configuration is environment variables only, and fails loudly when incomplete."""

from __future__ import annotations

import pytest

from cfokit.ledger.config import load_settings, require_env
from cfokit.ledger.errors import ConfigError

REQUIRED = ("DATABASE_URL", "PUBLIC_BASE_URL", "AUTH_ISSUER_URL", "AUTH_AUDIENCE")


def test_require_env_returns_the_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXAMPLE_SETTING", "value")
    assert require_env("EXAMPLE_SETTING") == "value"


def test_require_env_rejects_missing_and_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EXAMPLE_SETTING", raising=False)
    with pytest.raises(ConfigError):
        require_env("EXAMPLE_SETTING")

    monkeypatch.setenv("EXAMPLE_SETTING", "")
    with pytest.raises(ConfigError):
        require_env("EXAMPLE_SETTING")


def test_config_error_carries_a_stable_code(monkeypatch: pytest.MonkeyPatch) -> None:
    """Callers depend on the code, not the message (ADR-0015)."""
    monkeypatch.delenv("EXAMPLE_SETTING", raising=False)
    with pytest.raises(ConfigError) as caught:
        require_env("EXAMPLE_SETTING")
    assert caught.value.code == "config_invalid"


def test_config_error_never_discloses_the_value(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never log or echo secret values (CLAUDE.md, Observability)."""
    monkeypatch.setenv("EXAMPLE_SETTING", "")
    with pytest.raises(ConfigError) as caught:
        require_env("EXAMPLE_SETTING")
    assert "EXAMPLE_SETTING" in caught.value.message


def test_load_settings_reads_the_whole_surface(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in REQUIRED:
        monkeypatch.setenv(name, f"value-for-{name}")

    settings = load_settings()

    assert settings.database_url == "value-for-DATABASE_URL"
    assert settings.public_base_url == "value-for-PUBLIC_BASE_URL"
    assert settings.auth_issuer_url == "value-for-AUTH_ISSUER_URL"
    assert settings.auth_audience == "value-for-AUTH_AUDIENCE"


@pytest.mark.parametrize("missing", REQUIRED)
def test_load_settings_fails_on_any_missing_variable(
    monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    for name in REQUIRED:
        monkeypatch.setenv(name, "value")
    monkeypatch.delenv(missing, raising=False)

    with pytest.raises(ConfigError, match=missing):
        load_settings()
