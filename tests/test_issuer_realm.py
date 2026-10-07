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
