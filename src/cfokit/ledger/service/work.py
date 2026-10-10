"""Unattended work: what a kind of work declares, and a pass that runs what is due (ADR-0061).

**A pass** enqueues every timer window that has come due, claims due runs one at a time, runs
each in a thread up to a bound, and stops claiming when nothing is due, when its budget runs
out, or when it is told to stop — then finishes what it holds and returns. A tick starts one
every fifteen minutes on GCP, a person's request starts one at once, and a local deployment
loops (§ 3). The pass knows no schedule: what is due is the database's to say.

**A kind of work** is a handler and its declarations: whether it ingests or sends, how many
attempts it gets, the provider limit it stays inside, and, for an operational kind, the
interval its timer backstops. Modules declare kinds; `cfokit.server` is the only place that
knows the list, and hands it to the pass.

**A handler opens its own transactions.** It is given the database and the run, not a
transaction, because a sync talks to a provider before it writes anything, and holding an
entity's lock across a provider's paging is what ADR-0011 and ADR-0024 rule out. Every write it
makes goes through `entity_write` for the run's entity, under row-level security and the lock,
with an idempotency key, so a run cut off and run again from the start writes nothing twice
(ADR-0029). Every `audit_log` row it writes carries the run's id as its request id (§ 4).
"""

from __future__ import annotations

import hashlib
import logging
import random
import re
import threading
import time
from collections.abc import Callable, Mapping
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum

from cfokit.ledger.errors import LedgerError
from cfokit.ledger.repository.unit_of_work import Database, EntityWrite
from cfokit.ledger.repository.work import Claimed, Schedule
from cfokit.ledger.service.authorization import Capability
from cfokit.ledger.service.notifications import notify_holders

__all__ = [
    "WORK_FAILED",
    "Flow",
    "Kind",
    "PassReport",
    "Run",
    "backoff",
    "run_pass",
    "window_due",
]

logger = logging.getLogger("cfokit.work")

# The notification raised when a run exhausts its attempts (`PLT-07`).
WORK_FAILED = "work_failed"

# How long a claim holds before a pass may take the run as abandoned: a worker that died leaves
# its run due after this. Well beyond a pass's budget, so an ordinary run finishes inside it.
# Nothing bounds a handler's time, though, so a run can still be taken from a handler that is
# working. Its late outcome is then discarded (`succeed_run` and `fail_run` write nothing for a
# claim that no longer holds), and what it wrote is safe twice, as every handler's writes must
# be (ADR-0029).
LEASE_SECONDS = 30 * 60

# Full jitter over an exponential backoff, capped (§ 4). Whole seconds: nothing here needs less.
BACKOFF_BASE_SECONDS = 30
BACKOFF_CAP_SECONDS = 60 * 60

# What a throttle counts over: a provider's limit per minute.
THROTTLE_WINDOW_SECONDS = 60


class Flow(StrEnum):
    """Whether a kind brings activity in or sends something out (§ 5, `PLT-10`, `PLT-12`)."""

    INGESTION = "ingestion"
    OUTBOUND = "outbound"


@dataclass(frozen=True, slots=True)
class Run:
    """What a handler is told about the run it is doing."""

    id: str
    entity_id: str
    kind: str
    reference: str
    window_start: datetime | None
    window_end: datetime | None
    attempt: int


Handler = Callable[[Database, Run], None]


@dataclass(frozen=True, slots=True)
class Kind:
    """A kind of unattended work, and everything the pass needs to know to run it.

    Every declaration is required; a kind that leaves one out does not construct.
    """

    name: str
    handler: Handler
    flow: Flow
    # Attempts before the run is failed and a person is told.
    max_attempts: int
    # Where the notification about a failed run is answered, given the run's entity and
    # reference: a path under the deployment's own address, as every notification's link is.
    failure_link: Callable[[str, str], str]
    # The provider's limit on runs started a minute, if it calls one. Counted across every
    # pass, so two passes at once share it.
    per_minute: int | None = None
    # For an operational kind, the interval its timer backstops: a reference with no
    # successful run within it is enqueued at its window's end. None for a kind with no timer.
    interval: timedelta | None = None

    def __post_init__(self) -> None:
        # The pattern migration 0020 checks the column against, so a kind that constructs is
        # one the queue can store.
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", self.name):
            raise ValueError(f"a kind's name is lower snake case, not {self.name!r}")
        if self.max_attempts < 1:
            raise ValueError("a kind gets at least one attempt")
        if self.per_minute is not None and self.per_minute < 1:
            raise ValueError("a throttle allows at least one run a minute")
        if self.interval is not None and self.interval < timedelta(minutes=1):
            raise ValueError("an interval is at least a minute")


@dataclass(slots=True)
class PassReport:
    """What one pass did, in counts. What each run did is in the queue's own record."""

    enqueued: int = 0
    succeeded: int = 0
    failed: int = 0
    retrying: int = 0
    interrupted: int = 0
    by_kind: dict[str, int] = field(default_factory=dict)


def backoff(attempt: int, *, rng: random.Random | None = None) -> int:
    """Seconds before a failed attempt's run is due again: full jitter, capped (§ 4).

    A random delay up to the exponential bound, so retries after a shared failure — a provider
    down for everyone — do not all arrive together when it comes back.
    """
    bound = min(BACKOFF_CAP_SECONDS, BACKOFF_BASE_SECONDS * 2 ** max(attempt - 1, 0))
    # At least a second, so a retry is never due in the instant it failed, and the pass that
    # failed it moves on rather than taking it straight back.
    return (rng or random.SystemRandom()).randint(1, bound)


def window_due(
    schedule: Schedule, *, interval: timedelta, now: datetime
) -> tuple[datetime, datetime] | None:
    """The window a timer's reference has most recently completed, if not yet dealt with.

    Windows are the interval, offset by a hash of the reference, so a deployment's references
    fall due spread across the interval rather than together at its top (§ 2). The window
    returned starts where the last one dealt with ended — or when the timer started — so a
    window missed by a late or skipped tick is covered by the next, never dropped.
    """
    seconds = int(interval.total_seconds())
    digest = hashlib.sha256(
        f"{schedule.entity_id}:{schedule.kind}:{schedule.reference}".encode()
    ).digest()
    offset = int.from_bytes(digest[:8], "big") % seconds
    epoch = now.timestamp()
    boundary = ((int(epoch) - offset) // seconds) * seconds + offset
    end = datetime.fromtimestamp(boundary, tz=now.tzinfo)
    if end <= schedule.created_at:
        return None
    if schedule.last_window_end is not None and schedule.last_window_end >= end:
        return None
    return (schedule.last_window_end or schedule.created_at, end)


def run_pass(
    database: Database,
    kinds: Mapping[str, Kind],
    *,
    budget: timedelta = timedelta(minutes=10),
    concurrency: int = 4,
    stop: threading.Event | None = None,
) -> PassReport:
    """Enqueue what timers have made due, then run what is due until done, out of budget or
    stopped, and return what it did.

    Two passes at once are safe: the claim is the only way to a run, and two claims never take
    the same one. The budget bounds what a pass costs, not whether it is correct.
    """
    stop = stop or threading.Event()
    report = PassReport()
    deadline = time.monotonic() + budget.total_seconds()
    names = sorted(kinds)

    _sweep(database, kinds, report)
    _enqueue_windows(database, kinds, report)
    if not names:
        return report

    running: dict[Future[None], Claimed] = {}
    with ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix="work") as pool:
        while True:
            claiming = not stop.is_set() and time.monotonic() < deadline
            while claiming and len(running) < concurrency:
                claimed = _claim_next(database, kinds, names)
                if claimed is None:
                    break
                kind = kinds[claimed.kind]
                running[pool.submit(kind.handler, database, _run(claimed))] = claimed
            if not running:
                break
            done, _ = wait(running, timeout=5, return_when=FIRST_COMPLETED)
            for future in done:
                _settle(
                    database, kinds[running[future].kind], running.pop(future), future, report
                )
    return report


def _run(claimed: Claimed) -> Run:
    return Run(
        id=claimed.id,
        entity_id=claimed.entity_id,
        kind=claimed.kind,
        reference=claimed.reference,
        window_start=claimed.window_start,
        window_end=claimed.window_end,
        attempt=claimed.attempt,
    )


def _sweep(database: Database, kinds: Mapping[str, Kind], report: PassReport) -> None:
    """Make abandoned runs due again, and tell a person about any that were out of attempts."""
    with database.work_queue() as queue:
        lapsed = queue.sweep_lapsed({name: k.max_attempts for name, k in kinds.items()})
    for run in lapsed:
        report.interrupted += 1
        logger.warning(
            "run interrupted",
            extra={"fields": {"run_id": run.id, "kind": run.kind, "attempts": run.attempts}},
        )
        if run.failed:
            report.failed += 1
            with database.entity_write(run.entity_id) as write:
                _notify_failed(write, kinds[run.kind], run.id, run.reference)


def _enqueue_windows(database: Database, kinds: Mapping[str, Kind], report: PassReport) -> None:
    """Enqueue a backstop run for each timer whose window has come due with no success in it."""
    timed = {name: kind for name, kind in kinds.items() if kind.interval is not None}
    if not timed:
        return
    with database.work_queue() as queue:
        now = queue.now()
        live = queue.schedules(sorted(timed))
    for schedule in live:
        interval = timed[schedule.kind].interval
        assert interval is not None  # noqa: S101 - filtered to timed kinds above
        window = window_due(schedule, interval=interval, now=now)
        if window is None:
            continue
        start, end = window
        with database.entity_write(schedule.entity_id) as write:
            if not write.mark_work_window(schedule_id=schedule.id, window_end=end):
                continue
            # A backstop, not a timetable: work its cause already did within the interval —
            # a feed synchronized on a webhook an hour ago — is not done again because the
            # timer came round (§ 2).
            last = write.last_work_success(kind=schedule.kind, reference=schedule.reference)
            if last is not None and last > end - interval:
                continue
            write.enqueue_work(
                kind=schedule.kind,
                reference=schedule.reference,
                cause="schedule",
                cause_ref=f"{schedule.id}:{int(end.timestamp())}",
                window_start=start,
                window_end=end,
            )
        report.enqueued += 1


def _claim_next(
    database: Database, kinds: Mapping[str, Kind], names: list[str]
) -> Claimed | None:
    """The next due run this pass may start, claimed, or None if there is none it may."""
    with database.work_queue() as queue:
        throttled = {
            name
            for name in names
            if kinds[name].per_minute is not None
            and queue.started_since(name, seconds=THROTTLE_WINDOW_SECONDS)
            >= (kinds[name].per_minute or 0)
        }
        allowed = [name for name in names if name not in throttled]
        if not allowed:
            return None
        for run_id in queue.candidates(allowed, limit=20):
            claimed = queue.claim(run_id, lease_seconds=LEASE_SECONDS)
            if claimed is not None:
                return claimed
    return None


def _settle(
    database: Database,
    kind: Kind,
    claimed: Claimed,
    future: Future[None],
    report: PassReport,
) -> None:
    """Record how a run's attempt ended, without letting one run's record stop the pass.

    A failure to record — the database unreachable for a moment — leaves the run running under
    its lease, so it is swept and due again; the pass carries on settling the others.
    """
    try:
        _record_outcome(database, kind, claimed, future, report)
    except Exception:
        logger.exception(
            "run outcome not recorded",
            extra={"fields": {"run_id": claimed.id, "kind": kind.name}},
        )


def _record_outcome(
    database: Database,
    kind: Kind,
    claimed: Claimed,
    future: Future[None],
    report: PassReport,
) -> None:
    """Record how a run's attempt ended: succeeded, due again after a backoff, or failed."""
    error = future.exception()
    report.by_kind[kind.name] = report.by_kind.get(kind.name, 0) + 1
    with database.entity_write(claimed.entity_id) as write:
        if error is None:
            if write.succeed_run(claimed):
                report.succeeded += 1
            else:
                _released(claimed, kind)
            return
        code = error.code if isinstance(error, LedgerError) else "internal_error"
        # The code and the class, never the message, which can carry what a provider or a
        # person wrote (CLAUDE.md, Observability).
        logger.error(
            "run failed",
            extra={
                "fields": {
                    "run_id": claimed.id,
                    "kind": kind.name,
                    "attempt": claimed.attempt,
                    "code": code,
                    "error": type(error).__name__,
                }
            },
        )
        exhausted = claimed.attempt >= kind.max_attempts
        outcome = write.fail_run(
            claimed,
            error_code=code,
            retry_after_seconds=None if exhausted else backoff(claimed.attempt),
        )
        if outcome == "failed":
            report.failed += 1
            _notify_failed(write, kind, claimed.id, claimed.reference)
        elif outcome == "retrying":
            report.retrying += 1
        elif outcome == "released":
            _released(claimed, kind)


def _released(claimed: Claimed, kind: Kind) -> None:
    """A handler finished after its run was taken from it as abandoned. Nothing is recorded."""
    logger.warning(
        "run finished after its lease lapsed; outcome discarded",
        extra={"fields": {"run_id": claimed.id, "kind": kind.name}},
    )


def _notify_failed(write: EntityWrite, kind: Kind, run_id: str, reference: str) -> None:
    """Tell the entity's owners that a run did not complete (`PLT-07`). Nothing fails silently.

    In the transaction that records the failure, so the run cannot be failed without the
    notification or the notification exist for a run that was not failed.
    """
    notify_holders(
        write,
        Capability.OWN,
        notification_class=WORK_FAILED,
        subject_ref=f"work_run:{run_id}",
        link=kind.failure_link(write.entity_id, reference),
    )
