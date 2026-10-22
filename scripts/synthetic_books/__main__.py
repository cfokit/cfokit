"""Write the synthetic company's events, payloads and manifest, or check they are current.

PYTHONPATH=scripts uv run python -m synthetic_books           # rewrite generated/
PYTHONPATH=scripts uv run python -m synthetic_books --check   # exit 1 if generated/ is stale
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

from synthetic_books import business, quickbooks
from synthetic_books.events import Event, Json, dumps, record

FIXTURE = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "quickbooks"
GENERATED = FIXTURE / "generated"


def catalog() -> list[dict[str, object]]:
    with (FIXTURE / "catalog.toml").open("rb") as file:
        cases: list[dict[str, object]] = tomllib.load(file)["case"]
    return cases


def manifest(
    cases: list[dict[str, object]],
    events: list[tuple[str, Event]],
    payloads: list[quickbooks.Payload],
) -> dict[str, Json]:
    """Each catalog id, with the events tagged with it and the payloads those events became.

    An event tagged with an id the catalog does not have is an error: a case that exists only in
    the generator is a case nobody reviewed.
    """
    known = {str(case["id"]) for case in cases}
    for event_id, event in events:
        unknown = set(event.cases) - known
        if unknown:
            raise ValueError(f"{event_id} is tagged with cases not in the catalog: {unknown}")
    by_event: dict[str, list[str]] = {}
    for payload in payloads:
        by_event.setdefault(payload.event, []).append(payload.id)

    out: dict[str, Json] = {}
    for case in cases:
        case_id = str(case["id"])
        tagged = [event_id for event_id, event in events if case_id in event.cases]
        entry: dict[str, Json] = {
            "category": str(case["category"]),
            "events": list(tagged),
            "payloads": [p for event_id in tagged for p in by_event.get(event_id, [])],
        }
        if case["category"] == "file":
            # A mutation of the export, written when the export exists (ADR-0075).
            entry["mutation"] = case_id
        out[case_id] = entry
    return out


def render() -> dict[str, str]:
    """Every generated file's name and content."""
    events = business.write()
    payloads = quickbooks.payloads(events)
    return {
        "events.jsonl": "".join(dumps(record(i, e)) + "\n" for i, e in events),
        "payloads.jsonl": "".join(dumps(p.record()) + "\n" for p in payloads),
        "manifest.json": dumps(
            {"seed": business.SEED, "cases": manifest(catalog(), events, payloads)}
        )
        + "\n",
    }


def main(argv: list[str]) -> int:
    files = render()
    if "--check" in argv:
        stale = [
            name
            for name, content in files.items()
            if not (GENERATED / name).exists()
            or (GENERATED / name).read_text(encoding="utf-8") != content
        ]
        for name in stale:
            print(f"stale: {GENERATED / name}; regenerate with python -m synthetic_books")
        return 1 if stale else 0
    GENERATED.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (GENERATED / name).write_text(content, encoding="utf-8")
        print(f"wrote {GENERATED / name} ({len(content.encode()):,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
