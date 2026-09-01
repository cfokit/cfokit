"""Turning a bearer token into the principal a write is attributed to (ADR-0019).

The issuer is a **swappable dependency**. This module reads `AUTH_ISSUER_URL` and
`AUTH_AUDIENCE` and nothing else, and contains no issuer-specific code: discovery finds the
JWKS endpoint, and everything after that is standard OIDC.

**Audience validation is mandatory on every request** (ADR-0011, ADR-0019). A token from a
shared issuer is otherwise replayable against any resource server that trusts it, which is
the failure the audience claim exists to prevent — so it is checked here rather than left to
a caller to remember.

**`actor_class` comes from the shape of the token, never from a claim the caller sets**
(ADR-0033). An RFC 8693 `act` claim means delegation: the subject is acting *for* the
principal it names, which is an agent acting for a person (`IAM-11`). Its absence is a person
acting for themselves. Nothing here reads a claim that says "I am an agent", because a
principal that can describe itself is a principal that can describe itself wrongly, and
ADR-0033 rejects self-reported provenance by name.

`rule` is deliberately unreachable from a token. A rule's principal is the system's own when
a stored rule assigns a coding, and it will not arrive bearing a credential.

Synchronous throughout, like everything else outside `mcp` (ADR-0024). `PyJWKClient` fetches
over `urllib` and caches, so no event loop and no new dependency.
"""

from __future__ import annotations

import json
import urllib.request
from typing import Any, Protocol

import jwt
from jwt import PyJWKClient

from cfokit.ledger.errors import NotAuthenticated
from cfokit.ledger.service.principal import ActorClass, Principal

__all__ = ["Authenticator", "DenyAll", "TokenAuthenticator", "principal_from_claims"]

DISCOVERY_PATHS = (
    "/.well-known/openid-configuration",
    "/.well-known/oauth-authorization-server",
)
ALGORITHMS = ["RS256", "ES256"]
DISCOVERY_TIMEOUT_SECONDS = 5


class Authenticator(Protocol):
    """Turns a credential into the principal a write is attributed to."""

    def principal_for(self, credential: str | None) -> Principal:
        """Return the authenticated principal, or raise `NotAuthenticated`."""
        ...


class DenyAll:
    """Refuses everything.

    The default wherever an authenticator is not supplied, so a deployment that has not wired
    one cannot book a transaction for an anonymous caller. `LED-20` requires every transaction
    to record what wrote it, and there would be nothing true to record.
    """

    def principal_for(self, credential: str | None) -> Principal:
        raise NotAuthenticated(
            "no authenticator is configured; this deployment cannot accept writes"
        )


def principal_from_claims(claims: dict[str, Any]) -> Principal:
    """Derive the principal from validated claims.

    Separated from verification so the derivation — the part carrying ADR-0033's rule — can be
    tested without a key, an issuer, or a network.
    """
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject:
        raise NotAuthenticated("token carries no subject")

    delegation = claims.get("act")
    if delegation is None:
        return Principal(id=subject, actor_class=ActorClass.PERSON)

    if not isinstance(delegation, dict):
        raise NotAuthenticated("act claim is not a delegation object")
    acting_for = delegation.get("sub")
    if not isinstance(acting_for, str) or not acting_for:
        raise NotAuthenticated("act claim names no subject")

    # RFC 8693: `act` names who the token is acting *for*. The subject is the actor.
    return Principal(id=subject, actor_class=ActorClass.AGENT, acting_for=acting_for)


class TokenAuthenticator:
    """Validates a bearer token against the issuer's JWKS, then derives the principal."""

    def __init__(self, issuer_url: str, audience: str) -> None:
        self._issuer_url = issuer_url.rstrip("/")
        self._audience = audience
        self._jwks: PyJWKClient | None = None

    def _jwks_client(self) -> PyJWKClient:
        """Discover the JWKS endpoint once, then let `PyJWKClient` cache the keys.

        Discovery rather than a configured URL, because ADR-0019's contract requires the
        issuer to publish metadata and reading it is what keeps the issuer swappable without
        a second variable.
        """
        if self._jwks is None:
            self._jwks = PyJWKClient(self._discover_jwks_uri(), cache_keys=True)
        return self._jwks

    def _discover_jwks_uri(self) -> str:
        errors: list[str] = []
        for path in DISCOVERY_PATHS:
            url = f"{self._issuer_url}{path}"
            try:
                with urllib.request.urlopen(  # noqa: S310 — issuer URL is operator config
                    url, timeout=DISCOVERY_TIMEOUT_SECONDS
                ) as response:
                    document = json.loads(response.read())
            except (OSError, ValueError) as exc:
                errors.append(exc.__class__.__name__)
                continue
            uri = document.get("jwks_uri")
            if isinstance(uri, str) and uri:
                return uri
            errors.append("no jwks_uri")

        raise NotAuthenticated(f"issuer metadata unavailable: {', '.join(errors)}")

    def principal_for(self, credential: str | None) -> Principal:
        """Validate the token and return its principal.

        The message never quotes the token or the reason a signature failed. A validation
        message is a useful oracle to an attacker and useless to a legitimate caller.
        """
        if not credential:
            raise NotAuthenticated("no credential presented")

        scheme, _, token = credential.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise NotAuthenticated("expected a bearer token")

        try:
            key = self._jwks_client().get_signing_key_from_jwt(token).key
            claims = jwt.decode(
                token,
                key=key,
                algorithms=ALGORITHMS,
                audience=self._audience,
                issuer=self._issuer_url,
                options={"require": ["exp", "iat", "sub", "aud", "iss"]},
            )
        except jwt.PyJWTError as exc:
            raise NotAuthenticated(f"token rejected: {exc.__class__.__name__}") from exc

        return principal_from_claims(claims)
