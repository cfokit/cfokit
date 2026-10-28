"""Write the synthetic company's events, payloads, manifest and archives, or check them.

PYTHONPATH=scripts uv run python -m synthetic_books           # rewrite generated/
PYTHONPATH=scripts uv run python -m synthetic_books --check   # exit 1 if generated/ is stale
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

from synthetic_books import business, quickbooks, quickbooks_books, quickbooks_export, xlsx
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
    """Each catalog id, with its check, the events tagged with it and the payloads those events
    became. The check is the catalog's, carried here so a reader in another language needs no
    TOML to know what each case expects (ADR-0079).

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
        check: Json = case["check"]  # type: ignore[assignment]
        entry: dict[str, Json] = {
            "category": str(case["category"]),
            "check": check,
            "events": list(tagged),
            "payloads": [p for event_id in tagged for p in by_event.get(event_id, [])],
        }
        if case["category"] == "archive":
            entry["rendering"] = case_id.removeprefix("a-")
        if case["category"] == "file":
            # A mutation of the accrual archive, made from it at test time (ADR-0078).
            entry["mutation"] = case_id
        out[case_id] = entry
    return out


def render() -> dict[str, bytes]:
    """Every generated file, by its path under the fixture directory."""
    events = business.write()
    payloads = quickbooks.payloads(events)
    books = quickbooks_books.record(quickbooks_export.COMPANY, events)
    files: dict[str, bytes] = {
        "generated/events.jsonl": "".join(
            dumps(record(i, e)) + "\n" for i, e in events
        ).encode(),
        "generated/payloads.jsonl": "".join(
            dumps(p.record()) + "\n" for p in payloads
        ).encode(),
        "generated/manifest.json": (
            dumps({"seed": business.SEED, "cases": manifest(catalog(), events, payloads)})
            + "\n"
        ).encode(),
    }
    for rendering in quickbooks_export.RENDERINGS:
        directory = f"archives/{rendering.name}"
        files[f"{directory}/export.zip"] = quickbooks_export.export(books, rendering)
        if rendering.name in quickbooks_export.OWN_TRIAL_BALANCES:
            files[f"{directory}/trial_balances.json"] = quickbooks_export.trial_balances(
                books, rendering
            ).encode()
    for name, account in quickbooks_export.AGING:
        files[f"aging/{name}"] = xlsx.workbook(quickbooks_export.aging(books, account))
    return files


def same(name: str, content: bytes) -> bool:
    """Whether the committed file says what `content` says. An archive or a workbook is
    compared by its members' contents, because a zip's bytes depend on the zlib that wrote
    it."""
    path = FIXTURE / name
    if not path.exists():
        return False
    if name.endswith((".zip", ".xlsx")):
        return xlsx.contents(path.read_bytes()) == xlsx.contents(content)
    return path.read_bytes() == content


def main(argv: list[str]) -> int:
    files = render()
    if "--check" in argv:
        stale = [name for name, content in files.items() if not same(name, content)]
        for name in stale:
            print(f"stale: {FIXTURE / name}; regenerate with python -m synthetic_books")
        return 1 if stale else 0
    for name, content in files.items():
        path = FIXTURE / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if not same(name, content):
            path.write_bytes(content)
        print(f"{FIXTURE / name} ({len(content):,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
