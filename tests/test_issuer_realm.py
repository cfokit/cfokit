"""What the realm CFOKit's issuer imports must hold, whatever the deployment (PLT-17, SOC2-19).

The realm is read as data: Keycloak applies it at import, and the issuer conformance suite
drives the running result. These pin the settings that make sign-in defensible on their own.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

REALM = Path(__file__).resolve().parent.parent / "infra" / "keycloak" / "cfokit-realm.json"


def _realm() -> dict[str, Any]:
    realm: dict[str, Any] = json.loads(REALM.read_text(encoding="utf-8"))
    return realm


def test_repeated_failures_lock_the_account_for_a_while() -> None:
    """Online guessing is bounded per account. Temporary rather than permanent, so a stranger
    cannot lock a person out of their own books for good by mistyping their address."""
    realm = _realm()
    assert realm["bruteForceProtected"] is True
    assert realm["permanentLockout"] is False


def test_a_password_alone_is_at_least_fifteen_characters() -> None:
    """NIST SP 800-63B-4 § 3.1.1.2: a password that is the only authenticator is at least 15
    characters, and no composition rule is imposed. A second factor is optional outside a
    service organization (IAM-23), so a password can be the only one."""
    policy = _realm()["passwordPolicy"]
    length = re.search(r"\blength\((\d+)\)", policy)
    assert length and int(length.group(1)) >= 15
    for composition in ("digits", "upperCase", "lowerCase", "specialChars"):
        assert composition not in policy


def test_sign_ins_and_administration_are_recorded() -> None:
    """PLT-17: authentication is a security event, recorded and retrievable apart from the
    books. The issuer's log is where a deployment collects it; administrative changes too, with
    what changed."""
    realm = _realm()
    assert realm["eventsEnabled"] is True
    assert "jboss-logging" in realm["eventsListeners"]
    assert realm["adminEventsEnabled"] is True
    assert realm["adminEventsDetailsEnabled"] is True


def test_the_access_token_lifetime_is_the_deployments_to_set() -> None:
    """SOC2-20: revocation reaches a bearer token only when it expires, so a deployment operated
    as a service sets the lifetime rather than inheriting a laptop's."""
    assert _realm()["accessTokenLifespan"].startswith("${CFOKIT_ACCESS_TOKEN_LIFESPAN:")


SETTINGS = REALM.parent / "realm-settings.sh"


def _settings() -> dict[str, Any]:
    """Each `-s key=value` the script sets, as the value JSON would hold."""
    script = SETTINGS.read_text(encoding="utf-8")
    values: dict[str, Any] = {}
    for key, raw in re.findall(r"-s '?(\w+)=([^'\s)]+)'?", script):
        values[key] = json.loads(raw) if raw[0] in "[0123456789tf" else raw
    policy = re.search(r"password_policy='([^']+)'", script)
    assert policy
    values["passwordPolicy"] = policy.group(1)
    return values


def test_a_running_issuer_receives_the_values_a_new_realm_imports() -> None:
    """A realm is imported once, so the script that sets these on a realm that already exists
    must hold the same values as the file, or a running deployment and a new one differ."""
    realm, settings = _realm(), _settings()
    assert set(settings) <= set(realm), "the script sets something the file does not hold"
    for key in settings.keys() - {"accessTokenLifespan"}:
        assert settings[key] == realm[key], key


def test_the_settings_script_deletes_its_temporary_administrator() -> None:
    """A temporary administrator left behind is a standing credential. The script deletes it
    whatever happens, and proves it gone by being refused, before it reports success."""
    script = SETTINGS.read_text(encoding="utf-8")
    assert "trap cleanup EXIT" in script
    assert (
        'if login 2>/dev/null; then fail "this run\'s own client still signs in"; fi' in script
    )


def test_the_issuer_image_carries_the_settings_script() -> None:
    """It runs as a job from the issuer image, which is the only place it is."""
    dockerfile = (REALM.parent.parent.parent / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY infra/keycloak/realm-settings.sh /opt/cfokit/realm-settings.sh" in dockerfile


CLAUDE_CALLBACK = r"^https://claude\.(ai|com)/api/mcp/auth_callback$"
LOOPBACK = r"^http://(127\.0\.0\.1|\[::1\]|localhost)(:[0-9]{1,5})?/[^?#*]*$"


def _registered_redirects() -> tuple[dict[str, Any], dict[str, Any]]:
    realm = _realm()
    (profile,) = realm["clientProfiles"]["profiles"]
    (policy,) = realm["clientPolicies"]["policies"]
    return profile, policy


def test_a_registered_client_may_redirect_only_to_claude_or_loopback() -> None:
    """ADR-0064: on a reachable deployment, a sign-in goes only to Claude's callback or the
    person's own machine. One executor, on the redirect URIs and no other field, so a client
    that also names a homepage still registers."""
    profile, policy = _registered_redirects()
    (executor,) = profile["executors"]
    assert executor["executor"] == "secure-client-uris-pattern"
    assert executor["configuration"]["client-uri-fields"] == ["redirectUris"]
    assert executor["configuration"]["allowed-patterns"] == [CLAUDE_CALLBACK, LOOPBACK]
    assert policy["profiles"] == [profile["name"]]


def test_the_restriction_covers_only_clients_that_register_themselves() -> None:
    """ADR-0064: registration without an administrator, and that client's own later changes.
    The realm's own clients, and an administrator's, are configured deliberately."""
    _, policy = _registered_redirects()
    (condition,) = policy["conditions"]
    assert condition["condition"] == "client-updater-context"
    sources = set(condition["configuration"]["update-client-source"])
    assert sources == {"ByAnonymous", "ByRegistrationAccessToken"}


def test_the_restriction_is_the_deployments_to_switch_on() -> None:
    """ADR-0064: off on a laptop, where nothing else reaches the issuer."""
    _, policy = _registered_redirects()
    assert policy["enabled"] == "${CFOKIT_RESTRICT_REGISTERED_REDIRECTS:false}"


def test_the_patterns_admit_the_supported_clients_and_nothing_resembling_them() -> None:
    """ADR-0064's accepted and refused forms. A name that resolves to 127.0.0.1 is not loopback:
    the check is the text, so registering one and repointing it later gains nothing."""
    allowed = (CLAUDE_CALLBACK, LOOPBACK)
    accepted = [
        "https://claude.ai/api/mcp/auth_callback",
        "https://claude.com/api/mcp/auth_callback",
        "http://127.0.0.1:33418/oauth/callback",
        "http://localhost:33418/oauth/callback",
        "http://[::1]:33418/callback",
        "http://localhost/callback",
    ]
    refused = [
        "https://evil.example/cb",
        "http://claude.ai/api/mcp/auth_callback",
        "https://evil.claude.ai/api/mcp/auth_callback",
        "https://claude.ai.evil.example/api/mcp/auth_callback",
        "https://claude.ai/api/mcp/auth_callback?next=https://evil.example",
        "https://claude.ai/api/mcp/*",
        "http://localtest.me/cb",
        "http://lvh.me/cb",
        "http://127.0.0.1.nip.io/cb",
        "http://localhost.evil.example/cb",
        "http://localhost@evil.example/cb",
        "http://localhost:1234/*",
        "http://localhost:1234/cb#fragment",
        "http://10.0.0.5/cb",
        "myapp://callback",
    ]
    for uri in accepted:
        assert any(re.fullmatch(p, uri) for p in allowed), uri
    for uri in refused:
        assert not any(re.fullmatch(p, uri) for p in allowed), uri


def test_a_running_issuer_receives_the_same_redirect_patterns() -> None:
    """realm-settings.sh applies the profile to a realm that already exists; its patterns are
    the file's."""
    script = SETTINGS.read_text(encoding="utf-8")
    block = re.search(r"registered_redirects=\(\n(.*?)\n\)", script, re.DOTALL)
    assert block
    patterns = re.findall(r"'([^']+)'", block.group(1))
    assert patterns == [CLAUDE_CALLBACK, LOOPBACK]
    assert '"enabled":${CFOKIT_RESTRICT_REGISTERED_REDIRECTS}' in script
