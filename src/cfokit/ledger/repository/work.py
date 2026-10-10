"""SQL for unattended work: enqueueing, timers, claiming, and the record of attempts (ADR-0061).

Two kinds of caller, and the functions say which they serve:

* **A cause**, inside its own act's transaction — a person's request, a verified webhook, the
  act that creates what a timer serves. These run under the entity's scope and lock, like any
  write, so the work commits with its cause or not at all (§ 1).
* **The pass**, which claims across entities before it has an entity to scope to. These tables
  carry no row-level security for that reason, and no content (§ 6, migration 0020).

Times are the database's. A pass and a cause on two machines agree on what is due because both
ask the same clock.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import psycopg

# The first key of the throttle's two-key advisory locks.
THROTTLE_LOCK_NAMESPACE = 61_001

__all__ = [
    "Claimed",
    "LapsedRun",
    "Schedule",
    "candidates",
    "claim",
    "database_now",
    "end_schedule",
    "enqueue",
    "fail",
    "lapsed",
    "last_success",
    "lock_kind",
    "mark_window",
    "schedules",
    "start_schedule",
    "started_since",
    "succeed",
    "sweep",
]


@dataclass(frozen=True, slots=True)
class Schedule:
    """A live operational timer."""

    id: str
    entity_id: str
    kind: str
    reference: str
    created_at: datetime
    last_window_end: datetime | None


@dataclass(frozen=True, slots=True)
class Claimed:
    """A run this pass now holds, and the attempt it is on."""

    id: str
    entity_id: str
    kind: str
    reference: str
    window_start: datetime | None
    window_end: datetime | None
    attempt: int
    claimed_at: datetime


@dataclass(frozen=True, slots=True)
class LapsedRun:
    """A run whose worker stopped without saying how it went."""

    id: str
    entity_id: str
    kind: str
    reference: str
    attempts: int
    # Joined into a run already waiting for the same reference, if one was.
    merged_into: str | None
    # Out of attempts, with nothing waiting to take its work: failed rather than due again.
    failed: bool


def database_now(conn: psycopg.Connection[Any]) -> datetime:
    """The database's clock, which every decision about what is due is taken against."""
    with conn.cursor() as cur:
        cur.execute("SELECT clock_timestamp()")
        row = cur.fetchone()
    assert row is not None  # noqa: S101 - a SELECT of a function always yields a row
    value: datetime = row[0]
    return value


# --- a cause, in its own act --------------------------------------------------------------


def enqueue(
    conn: psycopg.Connection[Any],
    *,
    entity_id: str,
    kind: str,
    reference: str,
    cause: str,
    cause_ref: str,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
) -> str:
    """Enqueue a run, or join the one already waiting for this reference. Returns its id.

    Joining widens the waiting run's window to cover both and keeps the earlier due time, so a
    run that was waiting to retry is brought forward by a fresh cause. Every cause is recorded
    against the run it landed in, so a joined run names each of them (ADR-0061 § 1, § 4).
    """
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO work_run (entity_id, kind, reference, window_start, window_end)"
            " VALUES (%s, %s, %s, %s, %s)"
            " ON CONFLICT (entity_id, kind, reference) WHERE state = 'waiting'"
            " DO UPDATE SET window_start = LEAST(work_run.window_start, EXCLUDED.window_start),"
            "               window_end = GREATEST(work_run.window_end, EXCLUDED.window_end),"
            "               due_at = LEAST(work_run.due_at, EXCLUDED.due_at)"
            " RETURNING id",
            (entity_id, kind, reference, window_start, window_end),
        )
        row = cur.fetchone()
        assert row is not None  # noqa: S101 - an upsert with RETURNING always yields a row
        run_id = str(row[0])
        cur.execute(
            "INSERT INTO work_run_cause (entity_id, run_id, cause, cause_ref)"
            " VALUES (%s, %s, %s, %s)",
            (entity_id, run_id, cause, cause_ref),
        )
    return run_id


def start_schedule(
    conn: psycopg.Connection[Any], *, entity_id: str, kind: str, reference: str
) -> str:
    """Start a timer for a reference, or return the live one it already has."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO work_schedule (entity_id, kind, reference) VALUES (%s, %s, %s)"
            " ON CONFLICT (entity_id, kind, reference) WHERE ended_at IS NULL DO NOTHING"
            " RETURNING id",
            (entity_id, kind, reference),
        )
        row = cur.fetchone()
        if row is None:
            cur.execute(
                "SELECT id FROM work_schedule"
                " WHERE entity_id = %s AND kind = %s AND reference = %s AND ended_at IS NULL",
                (entity_id, kind, reference),
            )
            row = cur.fetchone()
        assert row is not None  # noqa: S101 - inserted, or the conflict that stopped it exists
    return str(row[0])


def end_schedule(
    conn: psycopg.Connection[Any], *, entity_id: str, kind: str, reference: str
) -> bool:
    """End a reference's timer. Whether there was one to end."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE work_schedule SET ended_at = clock_timestamp()"
            " WHERE entity_id = %s AND kind = %s AND reference = %s AND ended_at IS NULL",
            (entity_id, kind, reference),
        )
        return cur.rowcount > 0


# --- the pass, across entities ------------------------------------------------------------


def schedules(conn: psycopg.Connection[Any], *, kinds: list[str]) -> list[Schedule]:
    """Every live timer of these kinds."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, entity_id, kind, reference, created_at, last_window_end"
            "  FROM work_schedule WHERE ended_at IS NULL AND kind = ANY(%s)"
            " ORDER BY created_at, id",
            (kinds,),
        )
        return [
            Schedule(
                id=str(r[0]),
                entity_id=str(r[1]),
                kind=str(r[2]),
                reference=str(r[3]),
                created_at=r[4],
                last_window_end=r[5],
            )
            for r in cur.fetchall()
        ]


def mark_window(
    conn: psycopg.Connection[Any], *, schedule_id: str, window_end: datetime
) -> bool:
    """Record that a timer's window has been dealt with. False if another pass got there first.

    The conditional update is the claim on the window: two passes coming round at once both try
    it, and one row changes, so the window is enqueued once.
    """
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE work_schedule SET last_window_end = %s"
            " WHERE id = %s AND ended_at IS NULL"
            "   AND (last_window_end IS NULL OR last_window_end < %s)",
            (window_end, schedule_id, window_end),
        )
        return cur.rowcount > 0


def last_success(
    conn: psycopg.Connection[Any], *, entity_id: str, kind: str, reference: str
) -> datetime | None:
    """When work for this reference last finished successfully, or None if it never has."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT max(finished_at) FROM work_run"
            " WHERE entity_id = %s AND kind = %s AND reference = %s AND state = 'succeeded'",
            (entity_id, kind, reference),
        )
        row = cur.fetchone()
    return row[0] if row is not None else None


def lapsed(conn: psycopg.Connection[Any]) -> list[tuple[str, str]]:
    """Runs whose lease has lapsed, as (run, entity), each to sweep under its entity's lock."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, entity_id FROM work_run"
            " WHERE state = 'running' AND lease_expires_at < clock_timestamp()"
            " ORDER BY lease_expires_at"
        )
        return [(str(r[0]), str(r[1])) for r in cur.fetchall()]


def sweep(
    conn: psycopg.Connection[Any], *, run_id: str, max_attempts: dict[str, int]
) -> LapsedRun | None:
    """Record a lapsed run's attempt as interrupted, and settle the run. None if it is no longer
    lapsed — another pass swept it, or its worker finished after all.

    Run in the entity's write, under its lock, so it is serialized with every cause that could
    enqueue for the same reference, and so a run failed here is failed in the transaction that
    raises its notification. A run with a cause waiting behind it is joined into that one,
    which then covers both windows. Any other is due again at once, from the start — unless the
    interrupted attempt was its last by its kind's bound in `max_attempts`, in which case it is
    failed: a handler that kills its worker every time would otherwise be retried for ever. A
    kind this pass does not know keeps its run due.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT entity_id, kind, reference, attempts, claimed_at, window_start, window_end"
            "  FROM work_run"
            " WHERE id = %s AND state = 'running' AND lease_expires_at < clock_timestamp()"
            " FOR UPDATE SKIP LOCKED",
            (run_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        entity_id, kind, reference, attempts, claimed_at, start, end = row
        cur.execute(
            "INSERT INTO work_attempt"
            " (entity_id, run_id, attempt, started_at, ended_at, outcome)"
            " VALUES (%s, %s, %s, %s, clock_timestamp(), 'interrupted')",
            (entity_id, run_id, attempts + 1, claimed_at),
        )
        merged_into = _join_waiting(
            cur,
            run_id=run_id,
            entity_id=entity_id,
            kind=kind,
            reference=reference,
            window_start=start,
            window_end=end,
            attempts=attempts + 1,
        )
        bound = max_attempts.get(str(kind))
        exhausted = bound is not None and attempts + 1 >= bound
        if merged_into is None and exhausted:
            cur.execute(
                "UPDATE work_run SET state = 'failed', attempts = %s, claimed_at = NULL,"
                "       lease_expires_at = NULL, finished_at = clock_timestamp()"
                " WHERE id = %s",
                (attempts + 1, run_id),
            )
        elif merged_into is None:
            cur.execute(
                "UPDATE work_run SET state = 'waiting', attempts = %s,"
                "       due_at = clock_timestamp(), claimed_at = NULL,"
                "       lease_expires_at = NULL"
                " WHERE id = %s",
                (attempts + 1, run_id),
            )
    return LapsedRun(
        id=run_id,
        entity_id=str(entity_id),
        kind=str(kind),
        reference=str(reference),
        attempts=int(attempts) + 1,
        merged_into=merged_into,
        failed=merged_into is None and exhausted,
    )


def lock_kind(conn: psycopg.Connection[Any], *, kind: str) -> None:
    """Serialize claims of one throttled kind until this transaction ends.

    The two-key form, under a namespace of its own: Postgres keeps the two-key and one-key
    advisory lock spaces apart, so this never contends with an entity's lock, which is keyed
    on `entity.lock_key` alone (ADR-0011). Two kinds whose names hash alike only wait on each
    other.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT pg_advisory_xact_lock(%s, hashtext(%s))", (THROTTLE_LOCK_NAMESPACE, kind)
        )


def _join_waiting(
    cur: psycopg.Cursor[Any],
    *,
    run_id: Any,
    entity_id: Any,
    kind: str,
    reference: str,
    window_start: datetime | None,
    window_end: datetime | None,
    attempts: int,
) -> str | None:
    """Join a running run's work into the run waiting behind it, if there is one.

    The waiting run was enqueued by a cause that arrived during this one (§ 1). It will read the
    source afresh, so it does what this one would have; its window is widened to cover this
    one's, and this run is marked as merged into it rather than retried beside it.
    """
    cur.execute(
        "UPDATE work_run SET window_start = LEAST(window_start, %s),"
        "                    window_end = GREATEST(window_end, %s)"
        " WHERE entity_id = %s AND kind = %s AND reference = %s AND state = 'waiting'"
        " RETURNING id",
        (window_start, window_end, entity_id, kind, reference),
    )
    row = cur.fetchone()
    if row is None:
        return None
    cur.execute(
        "UPDATE work_run SET state = 'merged', merged_into = %s, attempts = %s,"
        "       claimed_at = NULL, lease_expires_at = NULL, finished_at = clock_timestamp()"
        " WHERE id = %s",
        (row[0], attempts, run_id),
    )
    return str(row[0])


def candidates(conn: psycopg.Connection[Any], *, kinds: list[str], limit: int) -> list[str]:
    """Due runs worth trying to claim, in turn: each entity's oldest, least recently served
    entity first, then each one's next.

    Ranked within its entity by due time, then across entities by when each last had a run
    claimed, so an entity with two years of history to sync takes one turn and then waits for
    every other entity with work due to take one. Ordering by due time alone would not: the
    busy entity's next run is always older than a newcomer's. An entity with a run already
    running is left out; the claim enforces that as well, by index.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM ("
            "  SELECT r.id, r.due_at,"
            "         row_number() OVER (PARTITION BY r.entity_id"
            "                            ORDER BY r.due_at, r.id) AS n,"
            "         (SELECT max(s.claimed_at) FROM work_run s"
            "           WHERE s.entity_id = r.entity_id) AS served"
            "    FROM work_run r"
            "   WHERE r.state = 'waiting' AND r.due_at <= clock_timestamp()"
            "     AND r.kind = ANY(%s)"
            "     AND NOT EXISTS (SELECT 1 FROM work_run x"
            "                      WHERE x.entity_id = r.entity_id AND x.state = 'running')"
            ") ranked ORDER BY n, served NULLS FIRST, due_at, id LIMIT %s",
            (kinds, limit),
        )
        return [str(r[0]) for r in cur.fetchall()]


def claim(conn: psycopg.Connection[Any], *, run_id: str, lease_seconds: int) -> Claimed | None:
    """Take one run if it is still waiting and due and no other run of its entity is running.

    None when another pass took it first, when it is locked by one taking it now, or when its
    entity already has a run running — which the unique index on running runs refuses, so two
    passes cannot each start a different run for one entity. Run in a savepoint, so a refusal
    leaves the caller's transaction usable.
    """
    try:
        with conn.transaction(), conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM work_run"
                " WHERE id = %s AND state = 'waiting' AND due_at <= clock_timestamp()"
                " FOR UPDATE SKIP LOCKED",
                (run_id,),
            )
            if cur.fetchone() is None:
                return None
            cur.execute(
                "UPDATE work_run SET state = 'running', claimed_at = clock_timestamp(),"
                "       lease_expires_at = clock_timestamp() + make_interval(secs => %s)"
                " WHERE id = %s"
                " RETURNING id, entity_id, kind, reference, window_start, window_end,"
                "           attempts, claimed_at",
                (lease_seconds, run_id),
            )
            row = cur.fetchone()
    except psycopg.errors.UniqueViolation:
        return None
    assert row is not None  # noqa: S101 - the row was locked by this transaction above
    return Claimed(
        id=str(row[0]),
        entity_id=str(row[1]),
        kind=str(row[2]),
        reference=str(row[3]),
        window_start=row[4],
        window_end=row[5],
        attempt=int(row[6]) + 1,
        claimed_at=row[7],
    )


def started_since(conn: psycopg.Connection[Any], *, kind: str, seconds: int) -> int:
    """How many runs of a kind began within the last `seconds`: ended attempts and running."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT (SELECT count(*) FROM work_attempt a JOIN work_run r ON r.id = a.run_id"
            "         WHERE r.kind = %(kind)s"
            "           AND a.started_at > clock_timestamp() - make_interval(secs => %(s)s))"
            "     + (SELECT count(*) FROM work_run"
            "         WHERE kind = %(kind)s AND state = 'running'"
            "           AND claimed_at > clock_timestamp() - make_interval(secs => %(s)s))",
            {"kind": kind, "s": seconds},
        )
        row = cur.fetchone()
    return int(row[0]) if row is not None else 0


def _still_held(cur: psycopg.Cursor[Any], run: Claimed) -> bool:
    """Whether this claim still holds the run, locking it if so.

    A claim stops holding its run when a sweep took it as abandoned: its lease lapsed while the
    handler was still working, and the sweep recorded the attempt as interrupted and made the
    run due again or joined it to the run waiting behind it. What the late handler did is then
    neither this attempt's record nor the run's state to set, and writing either would collide
    with what the sweep wrote.
    """
    cur.execute(
        "SELECT 1 FROM work_run"
        " WHERE id = %s AND state = 'running' AND claimed_at = %s FOR UPDATE",
        (run.id, run.claimed_at),
    )
    return cur.fetchone() is not None


def succeed(conn: psycopg.Connection[Any], *, run: Claimed) -> bool:
    """Record the attempt as succeeded, and the run with it.

    False, writing nothing, when the claim no longer holds the run (`_still_held`).
    """
    with conn.cursor() as cur:
        if not _still_held(cur, run):
            return False
        cur.execute(
            "INSERT INTO work_attempt"
            " (entity_id, run_id, attempt, started_at, ended_at, outcome)"
            " VALUES (%s, %s, %s, %s, clock_timestamp(), 'succeeded')",
            (run.entity_id, run.id, run.attempt, run.claimed_at),
        )
        cur.execute(
            "UPDATE work_run SET state = 'succeeded', attempts = %s,"
            "       finished_at = clock_timestamp(), lease_expires_at = NULL"
            " WHERE id = %s",
            (run.attempt, run.id),
        )
    return True


def fail(
    conn: psycopg.Connection[Any],
    *,
    run: Claimed,
    error_code: str,
    retry_after_seconds: int | None,
) -> str:
    """Record the attempt as failed, then retry the run, join it, or fail it.

    Returns what became of the run: `retrying`, `merged`, `failed`, or `released` — writing
    nothing — when the claim no longer holds the run (`_still_held`). With a retry delay it is
    due again after the delay, unless a cause arrived while it ran, in which case the run
    waiting behind it does its work. Without one, it has exhausted its retries and is failed.
    """
    with conn.cursor() as cur:
        if not _still_held(cur, run):
            return "released"
        cur.execute(
            "INSERT INTO work_attempt"
            " (entity_id, run_id, attempt, started_at, ended_at, outcome, error_code)"
            " VALUES (%s, %s, %s, %s, clock_timestamp(), 'failed', %s)",
            (run.entity_id, run.id, run.attempt, run.claimed_at, error_code),
        )
        if retry_after_seconds is None:
            cur.execute(
                "UPDATE work_run SET state = 'failed', attempts = %s,"
                "       finished_at = clock_timestamp(), lease_expires_at = NULL"
                " WHERE id = %s",
                (run.attempt, run.id),
            )
            return "failed"
        merged_into = _join_waiting(
            cur,
            run_id=run.id,
            entity_id=run.entity_id,
            kind=run.kind,
            reference=run.reference,
            window_start=run.window_start,
            window_end=run.window_end,
            attempts=run.attempt,
        )
        if merged_into is not None:
            return "merged"
        cur.execute(
            "UPDATE work_run SET state = 'waiting', attempts = %s, claimed_at = NULL,"
            "       lease_expires_at = NULL,"
            "       due_at = clock_timestamp() + make_interval(secs => %s)"
            " WHERE id = %s",
            (run.attempt, retry_after_seconds, run.id),
        )
    return "retrying"
