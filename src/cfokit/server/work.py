"""``python -m cfokit.server work`` — run unattended work (ADR-0061 § 3).

The pass is the ledger's (`cfokit.ledger.service.work`); which kinds of work exist is this
package's to say, because only the composition point knows the module list. A module declares
its kinds; they are listed here.

**Two ways to run it, one code path.** `--once` runs a single pass and exits, which is how a
platform that starts a job on a tick and on request runs it — a Cloud Run job, on GCP. Without
it, passes run back to back, a few seconds apart, until the process is told to stop, which is
how a deployment with no tick runs it: the local stack, or one always-running worker.
"""

from __future__ import annotations

import logging
import signal
import threading
from types import FrameType

from cfokit.ledger.config import Settings
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.work import Kind, PassReport, run_pass

__all__ = ["kinds", "work"]

logger = logging.getLogger("cfokit.server")

# Between passes when looping. Short, because a local deployment has no wake: a run a person is
# waiting on is claimed by the next pass, so this is how long they wait at most.
IDLE_SECONDS = 5


def kinds(settings: Settings) -> dict[str, Kind]:
    """Every kind of unattended work this deployment runs, by name.

    Built from what each module declares. A pass with none still sweeps runs whose worker
    stopped, so a deployment that has run work keeps its record of it straight.
    """
    del settings
    return {}


def work(settings: Settings, *, once: bool) -> int:
    """Run one pass, or passes until stopped. Returns the process's exit status."""
    stop = threading.Event()

    def _stop(signum: int, frame: FrameType | None) -> None:
        del signum, frame
        # Claim nothing more; finish what is held (§ 3). A run cut off by the platform anyway
        # is due again when its lease lapses.
        stop.set()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    database = Database(settings.database_url)
    registered = kinds(settings)
    while True:
        if once:
            # A job's pass that fails exits non-zero, so the platform records the failure; what
            # it did not finish is due again for the next.
            _log(run_pass(database, registered, stop=stop))
            return 0
        try:
            _log(run_pass(database, registered, stop=stop))
        except Exception:
            # Looping, a pass that fails — the database away for a moment — is followed by the
            # next, rather than ending the worker and relying on the target to restart it.
            logger.exception("pass failed")
        if stop.wait(IDLE_SECONDS):
            return 0


def _log(report: PassReport) -> None:
    logger.info(
        "pass complete",
        extra={
            "fields": {
                "enqueued": report.enqueued,
                "succeeded": report.succeeded,
                "retrying": report.retrying,
                "failed": report.failed,
                "interrupted": report.interrupted,
                "by_kind": report.by_kind,
            }
        },
    )
