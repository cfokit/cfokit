"""What a kind of work must declare, and how retries are spaced (ADR-0061 § 3, § 4).

ADR-0036 layer 1: no database. The pass itself is tested against one, in
`tests/integration/test_unattended_work.py`.
"""

from __future__ import annotations

import random
from datetime import timedelta

import pytest

from cfokit.ledger.service.work import (
    BACKOFF_BASE_SECONDS,
    BACKOFF_CAP_SECONDS,
    Flow,
    Kind,
    backoff,
)
from cfokit.server.__main__ import main


def kind(**overrides: object) -> Kind:
    fields: dict[str, object] = {
        "name": "feed_sync",
        "handler": lambda _db, _run: None,
        "flow": Flow.INGESTION,
        "max_attempts": 5,
        "failure_link": lambda entity_id, reference: f"/app/companies/{entity_id}",
    }
    fields.update(overrides)
    return Kind(**fields)  # type: ignore[arg-type]


def test_a_kind_with_its_declarations_constructs() -> None:
    assert kind(per_minute=2500, interval=timedelta(hours=6)).name == "feed_sync"


@pytest.mark.parametrize(
    "overrides",
    [
        {"name": "Feed-Sync"},
        {"max_attempts": 0},
        {"per_minute": 0},
        {"interval": timedelta(seconds=30)},
    ],
)
def test_a_kind_with_an_unusable_declaration_does_not_construct(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        kind(**overrides)


def test_a_kind_missing_a_declaration_does_not_construct() -> None:
    """ADR-0061: a kind that leaves one undeclared does not register."""
    with pytest.raises(TypeError):
        Kind(name="feed_sync", handler=lambda _db, _run: None)  # type: ignore[call-arg]


@pytest.mark.parametrize("attempt", [1, 2, 3, 8, 30])
def test_a_retry_waits_a_random_delay_up_to_an_exponential_cap(attempt: int) -> None:
    rng = random.Random(attempt)  # noqa: S311 - seeded so the test repeats; no secret here
    bound = min(BACKOFF_CAP_SECONDS, BACKOFF_BASE_SECONDS * 2 ** (attempt - 1))
    delays = [backoff(attempt, rng=rng) for _ in range(200)]

    assert all(1 <= d <= bound for d in delays)
    # Full jitter: spread over the whole range, not clustered at its top.
    assert min(delays) < bound / 4 < bound * 3 / 4 < max(delays)


@pytest.mark.parametrize(
    "args", [["work", "--twice"], ["work", "--once", "extra"], ["worker"], []]
)
def test_the_entrypoint_refuses_what_it_does_not_run(
    args: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(args) == 2
    assert "work [--once]" in capsys.readouterr().err
