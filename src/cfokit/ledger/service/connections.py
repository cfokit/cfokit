"""Recording which agents connect, and showing a person theirs (ADR-0066 § 3).

The server learns an agent only as a client ID. What lets the person recognize it is what the
client says about itself when it opens an MCP session, its name and version, and which of the
person's accounts the token was issued for. Both are recorded at that moment, with one
`audit_log` row, and read back by the person to name the agent in the web client.

**What the client reports decides nothing.** It is the client's own claim, shown beside its ID.
Whether the agent may act anywhere is the grant's question alone (ADR-0066 § 2).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from cfokit.ledger.errors import NotAPerson
from cfokit.ledger.repository.connections import Connection
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.principal import Principal

__all__ = ["Connection", "agent_connections", "record_connection", "signed_in_as"]

# A client names itself in a free-text field. Kept to a length a page can show, so a client
# cannot store a document in the person's records by calling itself one.
REPORTED_LENGTH = 200


def signed_in_as(claims: Mapping[str, Any]) -> tuple[str | None, str | None]:
    """The account a token was issued for, as its email and name, where the issuer sends them.

    The standard OpenID Connect claims, so the same on every issuer (ADR-0019). Absent ones are
    None rather than a refusal: they label a connection and authorize nothing.
    """
    return _reported(claims.get("email")), _reported(claims.get("name"))


def record_connection(
    database: Database,
    *,
    principal: Principal,
    request_id: str,
    client_name: str | None,
    client_version: str | None,
    person_email: str | None,
    person_name: str | None,
) -> Connection | None:
    """Record that an agent opened a session for its person. None for a person's own token,
    which is not an agent connecting.
    """
    if principal.acting_for is None:
        return None
    with database.person_records(principal.acting_for) as records:
        connection = records.record_connection(
            agent_id=principal.id,
            client_name=_reported(client_name),
            client_version=_reported(client_version),
            person_email=_reported(person_email),
            person_name=_reported(person_name),
        )
        # Identifiers and the client's own label only; the account's email and name stay in
        # the connection row, which the person alone reads.
        records.record_audit(
            request_id=request_id,
            actor=principal.audit_actor,
            action="connect_agent",
            subject_type="agent_connection",
            detail={
                "agent_id": principal.id,
                "client_name": connection.client_name,
                "client_version": connection.client_version,
            },
        )
    return connection


def agent_connections(
    database: Database, *, principal: Principal, agent_id: str | None = None
) -> list[Connection]:
    """The agents that have connected for this person, most recent first.

    The person's own question. An agent asking is refused: which other software a person has
    connected is not the business of any one of them.
    """
    if principal.acting_for is not None:
        raise NotAPerson("which agents a person has connected is theirs to read")
    with database.person_records(principal.id) as records:
        return records.connections(agent_id)


def _reported(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()[:REPORTED_LENGTH]
