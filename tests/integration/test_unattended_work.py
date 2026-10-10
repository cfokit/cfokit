"""Unattended work against a real database (`PLT-14`, `PLT-07`, `PLT-18`, ADR-0061).

ADR-0036 layer 3. Each expected value is ADR-0061's stated confirmation: work commits with its
cause or not at all; no run is claimed twice; a cause arriving during a run waits behind it and
is claimed only after it; one entity's backlog does not hold up another's due run; a throttled
kind starts no more runs than its limit; a lapsed lease makes a run due again; a pass told to
stop, or out of budget, claims nothing more; a run out of attempts reaches a person.

Every test declares kinds of its own, named for the test, so a pass here claims nothing another
test enqueued, in a database the whole suite shares.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg
import pytest

from cfokit.ledger.errors import LedgerError
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.repository.work import Schedule
from cfokit.ledger.service.administration import create_entity
from cfokit.ledger.service.notifications import open_notifications
from cfokit.ledger.service.principal import ActorClass, Principal
from cfokit.ledger.service.work import WORK_FAILED, Flow, Kind, Run, run_pass, window_due

pytestmark = pytest.mark.integration

OWNER = Principal(id="user:geoff", actor_class=ActorClass.PERSON)


class ProviderRefused(LedgerError):
    code = "provider_refused"


def kind_name() -> str:
    return f"test_{uuid.uuid4().hex[:12]}"


def a_kind(
    name: str,
    handler: Callable[[Database, Run], None],
    *,
    max_attempts: int = 3,
    per_minute: int | None = None,
    interval: timedelta | None = None,
) -> Kind:
    return Kind(
        name=name,
        handler=handler,
        flow=Flow.INGESTION,
        max_attempts=max_attempts,
        failure_link=lambda entity_id, reference: f"/app/companies/{entity_id}/{reference}",
        per_minute=per_minute,
        interval=interval,
    )


def new_entity(database: Database) -> str:
    return create_entity(
        database,
        principal=OWNER,
        request_id="fixture",
        slug=f"work-{uuid.uuid4().hex[:12]}",
        name="Books",
        accounting_basis="accrual",
        fiscal_year_end_month=12,
        fiscal_year_end_day=31,
        functional_currency="USD",
        time_zone="UTC",
    ).entity_id


def enqueue(
    database: Database,
    entity_id: str,
    kind: str,
    reference: str = "ref-1",
    cause: str = "request",
) -> str:
    with database.entity_write(entity_id) as write:
        return write.enqueue_work(
            kind=kind, reference=reference, cause=cause, cause_ref=uuid.uuid4().hex
        )


def runs(owner_conn: psycopg.Connection[Any], kind: str) -> list[tuple[Any, ...]]:
    """(id, entity, reference, state, attempts) for every run of a kind, oldest first."""
    with owner_conn.cursor() as cur:
        cur.execute(
            "SELECT id::text, entity_id::text, reference, state, attempts FROM work_run"
            " WHERE kind = %s ORDER BY enqueued_at, id",
            (kind,),
        )
        return cur.fetchall()


def attempts(owner_conn: psycopg.Connection[Any], run_id: str) -> list[tuple[Any, ...]]:
    with owner_conn.cursor() as cur:
        cur.execute(
            "SELECT attempt, outcome, error_code FROM work_attempt"
            " WHERE run_id = %s ORDER BY attempt",
            (run_id,),
        )
        return cur.fetchall()


def make_due(owner_conn: psycopg.Connection[Any], kind: str) -> None:
    """Skip a retry's backoff, so the next pass may take it."""
    with owner_conn.cursor() as cur:
        cur.execute(
            "UPDATE work_run SET due_at = clock_timestamp()"
            " WHERE kind = %s AND state = 'waiting'",
            (kind,),
        )


# --- work commits with its cause ---------------------------------------------------------


def test_a_run_enqueued_in_a_transaction_that_rolls_back_is_never_claimed(
    database: Database, owner_conn: psycopg.Connection[Any]
) -> None:
    entity_id = new_entity(database)
    name = kind_name()
    with pytest.raises(RuntimeError), database.entity_write(entity_id) as write:
        write.enqueue_work(kind=name, reference="ref-1", cause="request", cause_ref="req-1")
        raise RuntimeError("the cause failed after enqueueing")

    seen: list[str] = []
    run_pass(database, {name: a_kind(name, lambda _db, run: seen.append(run.id))})

    assert seen == []
    assert runs(owner_conn, name) == []


def test_a_pass_runs_what_is_due_and_records_the_attempt(
    database: Database, owner_conn: psycopg.Connection[Any]
) -> None:
    entity_id = new_entity(database)
    name = kind_name()
    run_id = enqueue(database, entity_id, name)

    seen: list[Run] = []
    report = run_pass(database, {name: a_kind(name, lambda _db, run: seen.append(run))})

    assert [(r.id, r.entity_id, r.reference, r.attempt) for r in seen] == [
        (run_id, entity_id, "ref-1", 1)
    ]
    assert report.succeeded == 1
    assert runs(owner_conn, name) == [(run_id, entity_id, "ref-1", "succeeded", 1)]
    assert attempts(owner_conn, run_id) == [(1, "succeeded", None)]


def test_every_cause_is_recorded_against_the_run_it_landed_in(
    database: Database, owner_conn: psycopg.Connection[Any]
) -> None:
    """A run several causes joined names each of them (`PLT-18`)."""
    entity_id = new_entity(database)
    name = kind_name()
    first = enqueue(database, entity_id, name, cause="webhook")
    second = enqueue(database, entity_id, name, cause="request")

    assert first == second
    with owner_conn.cursor() as cur:
        cur.execute(
            "SELECT cause FROM work_run_cause WHERE run_id = %s ORDER BY caused_at", (first,)
        )
        assert [r[0] for r in cur.fetchall()] == ["webhook", "request"]


# --- a run is never claimed twice --------------------------------------------------------


def test_two_passes_at_once_never_run_the_same_run(database: Database) -> None:
    entities = [new_entity(database) for _ in range(6)]
    name = kind_name()
    for entity_id in entities:
        enqueue(database, entity_id, name)

    seen: list[str] = []
    lock = threading.Lock()

    def handler(_db: Database, run: Run) -> None:
        time.sleep(0.05)
        with lock:
            seen.append(run.id)

    kinds = {name: a_kind(name, handler)}
    passes = [threading.Thread(target=run_pass, args=(database, kinds)) for _ in range(3)]
    for p in passes:
        p.start()
    for p in passes:
        p.join()

    assert len(seen) == 6
    assert len(set(seen)) == 6


def test_a_cause_during_a_run_waits_behind_it_and_runs_after(
    database: Database, owner_conn: psycopg.Connection[Any]
) -> None:
    """What the second cause announces may have arrived after the first run read its source,
    so it is a run of its own — and never concurrent with the first (§ 1)."""
    entity_id = new_entity(database)
    name = kind_name()
    first = enqueue(database, entity_id, name)
    order: list[str] = []
    second: list[str] = []

    def handler(_db: Database, run: Run) -> None:
        order.append(f"start {run.id}")
        if run.id == first:
            second.append(enqueue(database, entity_id, name))
        order.append(f"end {run.id}")

    run_pass(database, {name: a_kind(name, handler)}, concurrency=4)

    assert second and second[0] != first
    assert order == [f"start {first}", f"end {first}", f"start {second[0]}", f"end {second[0]}"]
    assert [r[3] for r in runs(owner_conn, name)] == ["succeeded", "succeeded"]


def test_an_entity_runs_one_run_at_a_time(database: Database) -> None:
    entity_id = new_entity(database)
    name = kind_name()
    for reference in ("ref-1", "ref-2", "ref-3"):
        enqueue(database, entity_id, name, reference)
    active = 0
    most = 0
    lock = threading.Lock()

    def handler(_db: Database, _run: Run) -> None:
        nonlocal active, most
        with lock:
            active += 1
            most = max(most, active)
        time.sleep(0.05)
        with lock:
            active -= 1

    run_pass(database, {name: a_kind(name, handler)}, concurrency=4)

    assert most == 1


# --- fairness and limits -----------------------------------------------------------------


def test_one_entitys_backlog_does_not_hold_up_anothers_due_run(database: Database) -> None:
    busy = new_entity(database)
    quiet = new_entity(database)
    name = kind_name()
    for n in range(5):
        enqueue(database, busy, name, f"ref-{n}")
    enqueue(database, quiet, name, "ref-q")
    order: list[str] = []

    run_pass(
        database,
        {name: a_kind(name, lambda _db, run: order.append(run.entity_id))},
        concurrency=1,
    )

    # The quiet entity's only run comes before the busy one's second, not after its fifth.
    assert order.index(quiet) <= 1


def test_a_throttled_kind_starts_no_more_runs_than_its_limit(
    database: Database, owner_conn: psycopg.Connection[Any]
) -> None:
    name = kind_name()
    for _ in range(5):
        enqueue(database, new_entity(database), name)

    report = run_pass(database, {name: a_kind(name, lambda _db, _run: None, per_minute=2)})

    assert report.succeeded == 2
    assert [r[3] for r in runs(owner_conn, name)].count("waiting") == 3


def test_passes_at_once_share_a_throttled_kinds_limit(
    database: Database, owner_conn: psycopg.Connection[Any]
) -> None:
    """The limit is the provider's, so it holds across every pass, not within each."""
    name = kind_name()
    for _ in range(6):
        enqueue(database, new_entity(database), name)

    def handler(_db: Database, _run: Run) -> None:
        time.sleep(0.05)

    kinds = {name: a_kind(name, handler, per_minute=2)}
    passes = [threading.Thread(target=run_pass, args=(database, kinds)) for _ in range(3)]
    for p in passes:
        p.start()
    for p in passes:
        p.join()

    assert [r[3] for r in runs(owner_conn, name)].count("succeeded") == 2


# --- what a failure does -----------------------------------------------------------------


def test_a_failed_attempt_is_retried_after_a_backoff_and_records_its_code(
    database: Database, owner_conn: psycopg.Connection[Any]
) -> None:
    entity_id = new_entity(database)
    name = kind_name()
    run_id = enqueue(database, entity_id, name)

    def handler(_db: Database, _run: Run) -> None:
        raise ProviderRefused("the provider said no")

    report = run_pass(database, {name: a_kind(name, handler, max_attempts=3)})

    assert report.retrying == 1
    assert runs(owner_conn, name) == [(run_id, entity_id, "ref-1", "waiting", 1)]
    assert attempts(owner_conn, run_id) == [(1, "failed", "provider_refused")]
    with owner_conn.cursor() as cur:
        cur.execute("SELECT due_at > clock_timestamp() FROM work_run WHERE id = %s", (run_id,))
        row = cur.fetchone()
    assert row is not None
    assert row[0], "a retry is not due at once"


def test_a_run_out_of_attempts_is_failed_and_reaches_the_owners(
    database: Database, owner_conn: psycopg.Connection[Any]
) -> None:
    """`PLT-07`: a scheduled run that did not complete reaches the people who operate the
    entity. Nothing fails silently (§ 4)."""
    entity_id = new_entity(database)
    name = kind_name()
    run_id = enqueue(database, entity_id, name, "conn-7")

    def handler(_db: Database, _run: Run) -> None:
        raise RuntimeError("not a ledger error")

    kinds = {name: a_kind(name, handler, max_attempts=2)}
    first = run_pass(database, kinds)
    make_due(owner_conn, name)
    # Full jitter can make the retry due at once, so the second attempt may be the first
    # pass's; across both, the run fails once.
    second = run_pass(database, kinds)

    assert first.failed + second.failed == 1
    assert runs(owner_conn, name) == [(run_id, entity_id, "conn-7", "failed", 2)]
    assert [a[1:] for a in attempts(owner_conn, run_id)] == [
        ("failed", "internal_error"),
        ("failed", "internal_error"),
    ]
    raised = [
        n
        for n in open_notifications(database, entity_id=entity_id, principal=OWNER)
        if n.notification_class == WORK_FAILED
    ]
    assert [(n.subject_ref, n.link) for n in raised] == [
        (f"work_run:{run_id}", f"/app/companies/{entity_id}/conn-7")
    ]


def test_a_retry_with_a_cause_waiting_behind_it_joins_that_run(
    database: Database, owner_conn: psycopg.Connection[Any]
) -> None:
    entity_id = new_entity(database)
    name = kind_name()
    first = enqueue(database, entity_id, name)
    calls: list[str] = []

    def handler(_db: Database, run: Run) -> None:
        calls.append(run.id)
        if run.id == first:
            enqueue(database, entity_id, name)
            raise ProviderRefused("the provider said no")

    run_pass(database, {name: a_kind(name, handler)})

    states = {r[0]: r[3] for r in runs(owner_conn, name)}
    assert states[first] == "merged"
    assert len(calls) == 2 and "succeeded" in states.values()


# --- a worker that died ------------------------------------------------------------------


def test_a_run_whose_lease_lapsed_is_due_again_and_its_attempt_recorded_as_interrupted(
    database: Database, owner_conn: psycopg.Connection[Any]
) -> None:
    entity_id = new_entity(database)
    name = kind_name()
    run_id = enqueue(database, entity_id, name)
    with owner_conn.cursor() as cur:
        # As a worker leaves a run when it is killed mid-way: running, its lease lapsed.
        cur.execute(
            "UPDATE work_run SET state = 'running',"
            "       claimed_at = clock_timestamp() - interval '1 hour',"
            "       lease_expires_at = clock_timestamp() - interval '1 minute'"
            " WHERE id = %s",
            (run_id,),
        )

    seen: list[int] = []
    report = run_pass(database, {name: a_kind(name, lambda _db, run: seen.append(run.attempt))})

    assert report.interrupted == 1
    assert seen == [2]
    assert attempts(owner_conn, run_id) == [(1, "interrupted", None), (2, "succeeded", None)]


@pytest.mark.parametrize("finishes", ["succeeds", "fails"])
def test_a_handler_that_outlives_its_lease_has_its_late_outcome_discarded(
    database: Database, owner_conn: psycopg.Connection[Any], finishes: str
) -> None:
    """Nothing bounds a handler's time, so a sweep can take a run from one still working.
    When it finishes, the sweep's record stands, the run is not set twice, and the pass
    carries on."""
    entity_id = new_entity(database)
    name = kind_name()
    run_id = enqueue(database, entity_id, name)
    calls: list[int] = []

    def handler(_db: Database, run: Run) -> None:
        calls.append(run.attempt)
        if run.attempt == 1:
            # Another pass finds this run's lease lapsed while it is still being worked.
            with owner_conn.cursor() as cur:
                cur.execute(
                    "UPDATE work_run SET lease_expires_at = clock_timestamp() - interval '1s'"
                    " WHERE id = %s",
                    (run.id,),
                )
            with database.entity_write(entity_id) as write:
                write.sweep_run(run.id, max_attempts={name: 3})
            if finishes == "fails":
                raise ProviderRefused("too late to matter")

    run_pass(database, {name: a_kind(name, handler)}, concurrency=1)

    assert calls == [1, 2]
    assert attempts(owner_conn, run_id) == [(1, "interrupted", None), (2, "succeeded", None)]
    assert runs(owner_conn, name) == [(run_id, entity_id, "ref-1", "succeeded", 2)]


# --- stopping ----------------------------------------------------------------------------


def test_a_pass_told_to_stop_claims_nothing_more_and_finishes_what_it_holds(
    database: Database, owner_conn: psycopg.Connection[Any]
) -> None:
    name = kind_name()
    for _ in range(3):
        enqueue(database, new_entity(database), name)
    stop = threading.Event()
    finished: list[str] = []

    def handler(_db: Database, run: Run) -> None:
        stop.set()
        time.sleep(0.05)
        finished.append(run.id)

    run_pass(database, {name: a_kind(name, handler)}, concurrency=1, stop=stop)

    assert len(finished) == 1
    assert sorted(r[3] for r in runs(owner_conn, name)) == ["succeeded", "waiting", "waiting"]


def test_a_pass_out_of_budget_claims_nothing_more(
    database: Database, owner_conn: psycopg.Connection[Any]
) -> None:
    name = kind_name()
    for _ in range(3):
        enqueue(database, new_entity(database), name)

    def handler(_db: Database, _run: Run) -> None:
        time.sleep(0.2)

    run_pass(database, {name: a_kind(name, handler)}, concurrency=1, budget=timedelta(0))

    assert [r[3] for r in runs(owner_conn, name)].count("waiting") == 3


# --- timers ------------------------------------------------------------------------------


def test_a_timer_enqueues_its_window_once_however_many_passes_come_round(
    database: Database, owner_conn: psycopg.Connection[Any]
) -> None:
    entity_id = new_entity(database)
    name = kind_name()
    with database.entity_write(entity_id) as write:
        write.start_work_schedule(kind=name, reference="conn-1")
    with owner_conn.cursor() as cur:
        # Started two days ago, so a one-day window has certainly ended since.
        cur.execute(
            "UPDATE work_schedule SET created_at = clock_timestamp() - interval '2 days'"
            " WHERE kind = %s",
            (name,),
        )
    seen: list[Run] = []
    kinds = {name: a_kind(name, lambda _db, run: seen.append(run), interval=timedelta(days=1))}

    run_pass(database, kinds)
    run_pass(database, kinds)

    assert len(seen) == 1
    assert seen[0].window_start is not None and seen[0].window_end is not None
    with owner_conn.cursor() as cur:
        cur.execute(
            "SELECT c.cause FROM work_run_cause c JOIN work_run r ON r.id = c.run_id"
            " WHERE r.kind = %s",
            (name,),
        )
        assert [r[0] for r in cur.fetchall()] == ["schedule"]


def test_a_timer_does_not_redo_work_its_cause_already_did(
    database: Database, owner_conn: psycopg.Connection[Any]
) -> None:
    """A backstop, not a timetable: a reference synchronized within the interval is not
    synchronized again because the timer came round (§ 2)."""
    entity_id = new_entity(database)
    name = kind_name()
    interval = timedelta(days=1)
    with database.entity_write(entity_id) as write:
        write.start_work_schedule(kind=name, reference="conn-1")
    with owner_conn.cursor() as cur:
        cur.execute(
            "UPDATE work_schedule SET created_at = clock_timestamp() - interval '2 days'"
            " WHERE kind = %s",
            (name,),
        )
    with database.work_queue() as queue:
        now = queue.now()
        (schedule,) = queue.schedules([name])
    window = window_due(schedule, interval=interval, now=now)
    assert window is not None
    # The webhook's run, finished inside the window that has just ended.
    run_id = enqueue(database, entity_id, name, "conn-1", cause="webhook")
    with owner_conn.cursor() as cur:
        cur.execute(
            "UPDATE work_run SET state = 'succeeded', attempts = 1, finished_at = %s"
            " WHERE id = %s",
            (window[1] - timedelta(hours=1), run_id),
        )
    seen: list[str] = []

    report = run_pass(
        database, {name: a_kind(name, lambda _db, run: seen.append(run.id), interval=interval)}
    )

    assert report.enqueued == 0
    assert seen == []
    with owner_conn.cursor() as cur:
        cur.execute("SELECT last_window_end FROM work_schedule WHERE kind = %s", (name,))
        row = cur.fetchone()
    assert row is not None
    assert row[0] == window[1], "the window is dealt with, so the next pass skips it too"


def test_an_ended_timer_enqueues_nothing(
    database: Database, owner_conn: psycopg.Connection[Any]
) -> None:
    entity_id = new_entity(database)
    name = kind_name()
    with database.entity_write(entity_id) as write:
        write.start_work_schedule(kind=name, reference="conn-1")
        assert write.end_work_schedule(kind=name, reference="conn-1")
    with owner_conn.cursor() as cur:
        cur.execute(
            "UPDATE work_schedule SET created_at = clock_timestamp() - interval '2 days'"
            " WHERE kind = %s",
            (name,),
        )

    report = run_pass(
        database, {name: a_kind(name, lambda _db, _run: None, interval=timedelta(days=1))}
    )

    assert report.enqueued == 0


def test_timers_fall_due_spread_across_the_interval() -> None:
    """A deployment's references fall due across the interval, never all at its top (§ 2)."""
    now = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)
    interval = timedelta(hours=6)
    ends = set()
    for n in range(200):
        schedule = Schedule(
            id=str(n),
            entity_id=str(uuid.UUID(int=n)),
            kind="feed_sync",
            reference=f"conn-{n}",
            created_at=now - timedelta(days=1),
            last_window_end=None,
        )
        window = window_due(schedule, interval=interval, now=now)
        assert window is not None
        ends.add(window[1])

    # 200 references over six hours: if they were not spread they would share one boundary.
    assert len(ends) > 150
    assert all(now - interval < end <= now for end in ends)


# --- the queue holds routing, never content ----------------------------------------------


def test_the_queue_holds_no_money_and_no_free_text(owner_conn: psycopg.Connection[Any]) -> None:
    """§ 6: read across entities, so it must stay content-free to stay harmless. Every text
    column is a code, a state or an identifier, each held to a pattern by a check."""
    with owner_conn.cursor() as cur:
        cur.execute(
            "SELECT table_name, column_name, data_type FROM information_schema.columns"
            " WHERE table_schema = 'public' AND table_name LIKE 'work\\_%%'"
        )
        columns = cur.fetchall()

    assert columns
    assert not [c for c in columns if c[2] in {"numeric", "money", "real", "double precision"}]
    text = {(t, c) for t, c, kind in columns if kind == "text"}
    assert text == {
        ("work_schedule", "kind"),
        ("work_schedule", "reference"),
        ("work_run", "kind"),
        ("work_run", "reference"),
        ("work_run", "state"),
        ("work_run_cause", "cause"),
        ("work_run_cause", "cause_ref"),
        ("work_attempt", "outcome"),
        ("work_attempt", "error_code"),
    }


def test_a_reference_carrying_free_text_is_refused(database: Database) -> None:
    entity_id = new_entity(database)
    with (
        pytest.raises(psycopg.errors.CheckViolation),
        database.entity_write(entity_id) as write,
    ):
        write.enqueue_work(
            kind="feed_sync", reference="Joe's Coffee $4.50", cause="request", cause_ref="r"
        )
