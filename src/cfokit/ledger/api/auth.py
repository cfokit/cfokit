"""Who is calling, and the fact that nothing here answers that yet.

**The default authenticator denies every request.** That is deliberate and structural: a
deployment that has not wired authentication returns 401 rather than booking a transaction
for an unauthenticated caller. An adapter that quietly accepted anonymous writes would be a
gate the project claims and does not have, which is the failure mode a sweep of this
repository has already found four times.

What is missing, and what it needs:

- **Token validation.** ADR-0019 makes audience validation mandatory on every request, against
  `AUTH_AUDIENCE`, with local signature verification against cached JWKS from
  `AUTH_ISSUER_URL`. `pyjwt[crypto]` is a runtime dependency for exactly this and is not yet
  used.
- **Entity grants.** ADR-0011 requires them validated server-side regardless of token
  contents. There is no grant model in the schema to validate against.

`CLAUDE.md` puts authentication among the changes needing human review before proceeding, so
this file establishes the seam and stops there rather than guessing at the mechanism.
"""

from __future__ import annotations

from typing import Protocol

from cfokit.ledger.errors import NotAuthenticated
from cfokit.ledger.service.principal import Principal

__all__ = ["Authenticator", "DenyAll"]


class Authenticator(Protocol):
    """Turns a credential into the principal a write is attributed to.

    The seam ADR-0019 needs: the issuer is swappable, so nothing above this names one.
    """

    def principal_for(self, credential: str | None) -> Principal:
        """Return the authenticated principal, or raise `NotAuthenticated`."""
        ...


class DenyAll:
    """Refuses everything. The default, so an unconfigured deployment cannot write."""

    def principal_for(self, credential: str | None) -> Principal:
        raise NotAuthenticated(
            "no authenticator is configured; this deployment cannot accept writes"
        )
