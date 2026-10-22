"""The synthetic QuickBooks company: current, deterministic, covering its catalog (ADR-0075).

No expected figure here comes from running the generator. What is asserted is that the committed
files are what the generator writes, that every catalog case is realized, and invariants any set
of books must hold — a journal balances, a payment never applies more than it brings, nothing is
deposited twice. Whether the figures are what QuickBooks makes of these events is the sandbox's
question, not this file's.
"""

from __future__ import annotations

import json
import tomllib
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from synthetic_books import business
from synthetic_books.__main__ import GENERATED, catalog, render

FIXTURE = Path(__file__).parent / "fixtures" / "quickbooks"
CHECK_KINDS = {"balance", "account", "text", "skipped", "refused", "reconciliation"}


def jsonl(name: str) -> list[dict[str, Any]]:
    text = (GENERATED / name).read_text(encoding="utf-8")
    return [json.loads(line, parse_float=Decimal) for line in text.splitlines()]


@pytest.fixture(scope="module")
def events() -> list[dict[str, Any]]:
    return jsonl("events.jsonl")


@pytest.fixture(scope="module")
def payloads() -> list[dict[str, Any]]:
    return jsonl("payloads.jsonl")


@pytest.fixture(scope="module")
def manifest() -> dict[str, Any]:
    cases: dict[str, Any] = json.loads((GENERATED / "manifest.json").read_text())["cases"]
    return cases


# --- current and deterministic --------------------------------------------------------------


def test_the_committed_files_are_what_the_generator_writes() -> None:
    for name, content in render().items():
        assert (GENERATED / name).read_text(encoding="utf-8") == content, (
            f"{name} is stale: PYTHONPATH=scripts uv run python -m synthetic_books"
        )


def test_the_same_seed_writes_the_same_business() -> None:
    assert business.write() == business.write()


def test_another_seed_writes_another_business() -> None:
    assert business.write(seed=1) != business.write()


# --- the coverage gate ----------------------------------------------------------------------


def test_catalog_ids_are_unique_and_name_their_category() -> None:
    cases = catalog()
    ids = [str(case["id"]) for case in cases]
    assert len(ids) == len(set(ids))
    for case in cases:
        assert str(case["id"]).startswith(str(case["category"])[0] + "-"), case["id"]
        assert case["category"] in ("data", "file")
        assert str(case["description"]).strip()


def test_every_check_is_one_of_the_closed_set_of_kinds() -> None:
    with (FIXTURE / "catalog.toml").open("rb") as file:
        for case in tomllib.load(file)["case"]:
            assert case["check"]["kind"] in CHECK_KINDS, case["id"]


def test_every_catalog_id_is_in_the_manifest(manifest: dict[str, Any]) -> None:
    assert set(manifest) == {str(case["id"]) for case in catalog()}


def test_every_data_case_reaches_an_event_and_a_payload(manifest: dict[str, Any]) -> None:
    for case_id, entry in manifest.items():
        if entry["category"] == "data":
            assert entry["events"], f"{case_id} is realized by no event"
            assert entry["payloads"], f"{case_id}'s events became no payload"


def test_every_file_case_names_its_mutation(manifest: dict[str, Any]) -> None:
    for case_id, entry in manifest.items():
        if entry["category"] == "file":
            assert entry["mutation"] == case_id


# --- invariants of the books ----------------------------------------------------------------


def amounts(lines: list[dict[str, Any]]) -> Decimal:
    return sum((Decimal(line["amount"]) for line in lines), Decimal(0))


def test_amounts_are_decimal_strings_of_whole_cents(events: list[dict[str, Any]]) -> None:
    def walk(value: object) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "amount":
                    assert isinstance(item, str)
                    assert Decimal(item).as_tuple().exponent == -2, item
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(events)


def test_every_journal_balances(events: list[dict[str, Any]]) -> None:
    journals = [e for e in events if e["kind"] == "journal"]
    assert journals
    for event in journals:
        assert amounts(event["lines"]) == 0, event["id"]


def test_events_are_in_date_order(events: list[dict[str, Any]]) -> None:
    dates = [event["date"] for event in events]
    assert dates == sorted(dates)
    assert dates[0] >= business.START.isoformat()
    assert dates[-1] <= business.END.isoformat()


def test_nothing_is_settled_for_more_than_it_was_issued(events: list[dict[str, Any]]) -> None:
    issued: dict[str, Decimal] = {}
    settled: Counter[str] = Counter()
    for event in events:
        if event["kind"] in ("issue_invoice", "receive_bill"):
            issued[event["key"]] = amounts(event["lines"])
        elif event["kind"] == "issue_credit" and event["applies_to"]:
            settled[event["applies_to"]] += amounts(event["lines"])  # type: ignore[assignment]
        for applied in event.get("applies", []) + event.get("bills", []):
            assert applied["target"] in issued, (
                f"{event['id']} settles a document not yet issued"
            )
            settled[applied["target"]] += Decimal(applied["amount"])  # type: ignore[assignment]
    for target, total in settled.items():
        assert total <= issued[target], target


def test_a_payment_never_applies_more_than_it_brings(events: list[dict[str, Any]]) -> None:
    for event in events:
        if event["kind"] == "receive_payment":
            applied = sum((Decimal(a["amount"]) for a in event["applies"]), Decimal(0))
            assert applied <= Decimal(event["amount"]), event["id"]


def test_held_payments_are_banked_once_and_whole(events: list[dict[str, Any]]) -> None:
    held = {e["key"]: Decimal(e["amount"]) for e in events if e.get("into") == "held"}
    banked: Counter[str] = Counter()
    for event in events:
        if event["kind"] == "bank_deposit":
            for payment in event["payments"]:
                assert held[payment["target"]] == Decimal(payment["amount"])
                banked[payment["target"]] += 1
    assert banked and max(banked.values()) == 1


def test_nothing_posts_to_an_account_after_it_is_retired(events: list[dict[str, Any]]) -> None:
    retired = {e["account"]: e["date"] for e in events if e["kind"] == "deactivate_account"}
    assert retired
    for event in events:
        for line in event.get("lines", []):
            if line.get("account") in retired:
                assert event["date"] < retired[line["account"]], event["id"]


# --- the payloads ---------------------------------------------------------------------------


def references(value: object) -> list[str]:
    if isinstance(value, dict):
        found = [str(value[k]) for k in ("$ref", "$id") if k in value]
        return found + [r for item in value.values() for r in references(item)]
    if isinstance(value, list):
        return [r for item in value for r in references(item)]
    return []


def test_every_reference_is_defined_before_it_is_used(payloads: list[dict[str, Any]]) -> None:
    defined: set[str] = set()
    for payload in payloads:
        for target in references(payload["body"]):
            assert target.startswith("system:") or target in defined, (
                f"{payload['id']} uses {target} before anything defines it"
            )
        if payload["defines"] is not None:
            assert payload["defines"] not in defined, payload["defines"]
            defined.add(payload["defines"])


def test_every_payload_comes_from_an_event_and_every_event_reaches_one(
    events: list[dict[str, Any]], payloads: list[dict[str, Any]]
) -> None:
    assert {p["event"] for p in payloads} == {e["id"] for e in events}


def test_payload_amounts_are_exact_numbers(payloads: list[dict[str, Any]]) -> None:
    def walk(value: object) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key in ("Amount", "TotalAmt", "UnitPrice"):
                    assert isinstance(item, int | Decimal), (key, item)
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(payloads)


def test_journal_payloads_balance(payloads: list[dict[str, Any]]) -> None:
    for payload in payloads:
        if payload["entity"] == "JournalEntry":
            signed = [
                Decimal(line["Amount"])
                * (1 if line["JournalEntryLineDetail"]["PostingType"] == "Debit" else -1)
                for line in payload["body"]["Line"]
            ]
            assert sum(signed, Decimal(0)) == 0, payload["id"]
