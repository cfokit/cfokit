"""Reads, which are authorized like everything else.

A read is not a state change, so it writes no audit row and needs no idempotency key. It does
need a grant: `IAM-01` says an identity holding no role for an entity "can do nothing with
it", and reading someone else's books is something.

The check happens here rather than in an adapter, so both surfaces get it (ADR-0009).
"""

from __future__ import annotations

from datetime import UTC, datetime

from cfokit.ledger.errors import EntityNotFound, NotAuthorized, TransactionNotFound
from cfokit.ledger.repository.administration import Entity
from cfokit.ledger.repository.transactions import StoredTransaction
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.authorization import Capability, authorize
from cfokit.ledger.service.principal import Principal

__all__ = ["Entity", "list_entities", "read_entity", "read_transaction"]


def read_transaction(
    database: Database, *, entity_id: str, principal: Principal, transaction_id: str
) -> StoredTransaction:
    """Read a transaction, or raise.

    Raises `TransactionNotFound` when it does not exist *or* is another entity's: row-level
    security makes those the same answer, and distinguishing them would leak the other
    entity's existence (`NFR-04`).
    """
    with database.entity_write(entity_id) as write:
        authorize(write, Capability.READ, principal)
        stored = write.load_transaction(transaction_id)

    if stored is None:
        raise TransactionNotFound(f"no transaction {transaction_id}")
    return stored


def read_entity(database: Database, *, entity_id: str, principal: Principal) -> Entity:
    """Read what an entity declared at creation, or raise.

    Needs the same grant as reading its books: an entity's name is something, and `IAM-01`
    says a caller holding no role can do nothing with it.
    """
    with database.entity_write(entity_id) as write:
        authorize(write, Capability.READ, principal)
        found = write.declarations()

    if found is None:  # pragma: no cover — `entity_write` refused an absent entity already
        raise EntityNotFound(f"no entity {entity_id}")
    return found


def list_entities(database: Database, *, principal: Principal) -> list[Entity]:
    """Every entity this principal may read, by name: where to point every other call.

    Found from the principal's own grants (migration 0019), then each one checked as any read
    of it is, under its own scope — so what is listed is exactly what `read_entity` would
    answer. For an agent acting for a person, an entity is listed only where both hold a grant
    and their intersection reads (`IAM-11`): a company the person holds and the agent was never
    authorized in (`IAM-12`) is not one the agent can reach, so it is not one to tell it about.
    """
    now = datetime.now(UTC)
    with database.principal_read() as reader:
        held = reader.entities_held(principal.id, now)
        if principal.acting_for is not None:
            held &= reader.entities_held(principal.acting_for, now)

    found: list[Entity] = []
    for entity_id in sorted(held):
        with database.entity_write(entity_id) as write:
            try:
                authorize(write, Capability.READ, principal)
            except NotAuthorized:
                # A grant whose role carries no read: held, and nothing to show.
                continue
            declared = write.declarations()
        if declared is not None:
            found.append(declared)
    return sorted(found, key=lambda entity: (entity.name.casefold(), entity.id))
