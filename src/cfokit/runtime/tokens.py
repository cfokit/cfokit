"""A token for the person the runtime serves, exchanged from theirs (ADR-0077).

RFC 8693 standard token exchange, at the token endpoint the issuer's own metadata names. The
runtime authenticates as its confidential client and presents the person's access token; what
comes back is issued to the runtime, for the person, with the audience the issuer binds every
token to, which is CFOKit's API; the request names none (RFC 8693 § 2.1). The
server then sees the agent `client:<runtime>` acting for that person, allowed per company like
any agent (ADR-0066).

Nothing here names an issuer (ADR-0019): the endpoint comes from metadata, and the request is
the RFC's. The token is held for one turn and never stored or logged.
"""

from __future__ import annotations

from typing import Protocol

import httpx2

__all__ = ["Exchange", "TokenRefused", "TokenSource"]

GRANT = "urn:ietf:params:oauth:grant-type:token-exchange"
# A URN naming a kind of token, not a secret.
ACCESS_TOKEN = "urn:ietf:params:oauth:token-type:access_token"  # noqa: S105


class TokenRefused(Exception):
    """The issuer would not exchange the person's token, so the turn has no authority to act."""

    code = "token_refused"


class TokenSource(Protocol):
    async def for_person(self, person_token: str) -> str:
        """An access token issued to the runtime for the holder of `person_token`."""
        ...


class Exchange:
    """Standard token exchange against the configured issuer."""

    def __init__(
        self,
        *,
        issuer_url: str,
        client_id: str,
        client_secret: str,
        http: httpx2.AsyncClient,
    ) -> None:
        self._metadata_url = f"{issuer_url.rstrip('/')}/.well-known/openid-configuration"
        self._client = (client_id, client_secret)
        self._http = http
        self._token_endpoint: str | None = None

    async def _endpoint(self) -> str:
        if self._token_endpoint is None:
            response = await self._http.get(self._metadata_url)
            response.raise_for_status()
            self._token_endpoint = str(response.json()["token_endpoint"])
        return self._token_endpoint

    async def for_person(self, person_token: str) -> str:
        response = await self._http.post(
            await self._endpoint(),
            data={
                "grant_type": GRANT,
                "subject_token": person_token,
                "subject_token_type": ACCESS_TOKEN,
                "requested_token_type": ACCESS_TOKEN,
            },
            auth=self._client,
        )
        if response.status_code != 200:
            # The status only: an issuer's error body can echo what it was sent.
            raise TokenRefused(f"the issuer refused the exchange ({response.status_code})")
        token = response.json().get("access_token")
        if not isinstance(token, str) or not token:
            raise TokenRefused("the issuer answered the exchange without an access token")
        return token
