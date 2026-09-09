"""Reads, which are authorised like everything else.

A read is not a state change, so it writes no audit row and needs no idempotency key. It does
need a grant: `IAM-01` says an identity holding no role for an entity "can do nothing with
it", and reading someone else's books is something.

The check happens here rather than in an adapter, so both surfaces get it (ADR-0009).
"""

from __future__ import annotations

from cfokit.ledger.errors import TransactionNotFound
from cfokit.ledger.repository.transactions import StoredTransaction
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.authorisation import Capability, authorise
from cfokit.ledger.service.principal import Principal

__all__ = ["read_transaction"]


def read_transaction(
    database: Database, *, entity_id: str, principal: Principal, transaction_id: str
) -> StoredTransaction:
    """Read a transaction, or raise.

    Raises `TransactionNotFound` when it does not exist *or* is another entity's: row-level
    security makes those the same answer, and distinguishing them would leak the other
    entity's existence (`NFR-04`).
    """
    with database.entity_write(entity_id) as write:
        authorise(write, Capability.READ, principal)
        stored = write.load_transaction(transaction_id)

    if stored is None:
        raise TransactionNotFound(f"no transaction {transaction_id}")
    return stored
