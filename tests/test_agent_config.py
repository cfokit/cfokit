"""The agent's configuration, from the environment only (ADR-0004, `infra/README.md`).

ADR-0036 layer 1. Expected values come from `infra/README.md`, which names the variables, what
is required, and the defaults."""

from __future__ import annotations

import pytest

from cfokit.agent.config import DEFAULT_MODEL, AgentSettings, ConfigError

REQUIRED = {
    "CFOKIT_API_URL": "https://ledger:8080/",
    "CFOKIT_MCP_URL": "https://mcp:8081/mcp",
    "AUTH_ISSUER_URL": "https://issuer.example/realms/cfokit",
    "AUTH_CLIENT_ID": "cfokit-agent",
    "AUTH_CLIENT_SECRET": "out-of-band",
    "WEB_PUBLIC_BASE_URL": "https://books.example/",
}


def test_what_is_not_required_has_its_documented_default() -> None:
    settings = AgentSettings.from_env(REQUIRED)
    assert settings.anthropic_api_key is None
    assert settings.model == DEFAULT_MODEL
    assert settings.port == 8082
    assert (settings.tls_cert_file, settings.tls_key_file) == (None, None)
    assert settings.web_origin == "https://books.example"


@pytest.mark.parametrize("missing", sorted(REQUIRED))
def test_a_required_variable_missing_fails_at_start(missing: str) -> None:
    with pytest.raises(ConfigError, match=missing):
        AgentSettings.from_env({k: v for k, v in REQUIRED.items() if k != missing})


@pytest.mark.parametrize("half", ["TLS_CERT_FILE", "TLS_KEY_FILE"])
def test_the_tls_pair_is_set_together_or_not_at_all(half: str) -> None:
    with pytest.raises(ConfigError):
        AgentSettings.from_env({**REQUIRED, half: "/etc/cfokit/tls-server/x.pem"})
