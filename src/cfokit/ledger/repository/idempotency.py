"""Idempotency keys, mandatory on every write (ADR-0029).

> "Every write carries an idempotency key. A write without one is rejected. A repeated key
> returns the original result rather than applying the operation again."

**The per-entity advisory lock is what makes this simple.** Two concurrent writes to one
entity serialise (ADR-0011), so the interleaving that would otherwise need careful handling —
two callers claiming the same key at once — cannot happen. The `ON CONFLICT` below is a
second line rather than the only one.
"""

from __future__ import annotations

from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from cfokit.ledger.errors import IdempotencyKeyReused

__all__ = ["claim", "store_result"]


def claim(
    conn: psycopg.Connection[Any], entity_id: str, key: str, request_hash: str
) -> dict[str, Any] | None:
    """Claim `key` for this write, or return the result the first use stored.

    `None` means this is the first use and the caller should do the work. A dict means the
    key has been used before with the same parameters, and that stored result is the answer —
    the operation must not be applied again.

    Raises `IdempotencyKeyReused` when the same key arrives with different parameters. That
    is a client error rather than a replay: ADR-0029 requires that a repeat "must not silently
    succeed with a different one".
    """
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO idempotency_key (entity_id, key, request_hash)"
            " VALUES (%s, %s, %s) ON CONFLICT (entity_id, key) DO NOTHING",
            (entity_id, key, request_hash),
        )
        if cur.rowcount == 1:
            return None

        cur.execute(
            "SELECT request_hash, result FROM idempotency_key"
            " WHERE entity_id = %s AND key = %s",
            (entity_id, key),
        )
        row = cur.fetchone()

    if row is None:  # pragma: no cover — the insert conflicted, so the row is there
        raise IdempotencyKeyReused(f"idempotency key {key} could not be read back")

    stored_hash, result = row
    if stored_hash != request_hash:
        # Deliberately says nothing about what differed. The parameters carry amounts and
        # account identifiers (CLAUDE.md, Observability).
        raise IdempotencyKeyReused(
            f"idempotency key {key} was already used with different parameters"
        )

    # A replay that arrives before the first call stored its result would be a bug in the
    # locking, not a state to tolerate: the advisory lock means the first call has committed.
    return dict(result) if result is not None else {}


def store_result(
    conn: psycopg.Connection[Any], entity_id: str, key: str, result: dict[str, Any]
) -> None:
    """Record what this key produced, so a replay can return it rather than repeat it."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE idempotency_key SET result = %s WHERE entity_id = %s AND key = %s",
            (Jsonb(result), entity_id, key),
        )
