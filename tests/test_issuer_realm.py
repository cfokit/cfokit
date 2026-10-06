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
