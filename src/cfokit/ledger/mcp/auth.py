"""Bearer token verification for the MCP surface (ADR-0019, `IAM-10`).

MCP's authorization model makes the server an OAuth **resource server**: the client obtains a
token from the issuer and presents it on every request, and the server validates it and
publishes protected-resource metadata saying which issuer to go to. That is the same posture
the REST surface already has, against the same issuer and the same audience, so this adds a
transport binding rather than a second authentication path — which is what `NFR-11` and
ADR-0032 both ask for, and why nothing issuer-specific appears here.

**`verify_token` is `async` because the SDK's protocol is** (ADR-0024). It calls synchronous
verification and blocks the loop while `PyJWKClient` fetches keys, which this adapter is
permitted to do: it owns its event loop. The fetch happens once per key rotation, not per
request.

**A rejected token returns `None`, not an exception.** The SDK turns `None` into a 401 carrying
`WWW-Authenticate` and the resource metadata URL, which is what an MCP client needs in order to
discover the issuer and retry. Raising would produce a 500 and tell the client nothing.
"""

from __future__ import annotations

from typing import Any

from mcp.server.auth.provider import AccessToken

from cfokit.ledger.errors import NotAuthenticated
from cfokit.ledger.service.authentication import Authenticator

__all__ = ["LedgerTokenVerifier"]


class LedgerTokenVerifier:
    """Adapts the ledger's `Authenticator` to the SDK's `TokenVerifier` protocol."""

    def __init__(self, authenticator: Authenticator) -> None:
        self._authenticator = authenticator

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            claims = self._authenticator.claims_for(f"Bearer {token}")
        except NotAuthenticated:
            return None

        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject:
            return None

        return AccessToken(
            token=token,
            # The subject identifies the caller. `client_id` is the SDK's label for whoever
            # holds the token, and for a delegated token that is still the acting principal —
            # `IAM-11` keeps the person it acts for in `act`, which travels in the claims.
            client_id=subject,
            scopes=[],
            expires_at=_expiry(claims),
            subject=subject,
            claims=claims,
        )


def _expiry(claims: dict[str, Any]) -> int | None:
    expires = claims.get("exp")
    return expires if isinstance(expires, int) else None
