"""The sandbox validation tool, offline: everything but the HTTP calls (ADR-0075).

No test here reaches QuickBooks; CI never does. The report shape in `REPORT` is the Reports
API's documented nesting — rows that are `Data` with `ColData`, or a `Section` with a `Header`,
`Rows` and a `Summary` — written by hand with figures of our own, not a response that was
recorded.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from synthetic_books import sandbox
from synthetic_books.quickbooks_export import RENDERINGS

FIXTURE = Path(__file__).parent / "fixtures" / "quickbooks"

REPORT: dict[str, Any] = {
    "Header": {"ReportName": "ProfitAndLoss"},
    "Rows": {
        "Row": [
            {
                "type": "Section",
                "Header": {"ColData": [{"value": "Income"}, {"value": ""}]},
                "Rows": {
                    "Row": [
                        {
                            "type": "Data",
                            "ColData": [{"value": "Design Services"}, {"value": "1200.00"}],
                        },
                        {
                            "type": "Data",
                            "ColData": [{"value": "Workshops"}, {"value": "300.50"}],
                        },
                    ]
                },
                "Summary": {"ColData": [{"value": "Total Income"}, {"value": "1500.50"}]},
            },
            {
                "type": "Section",
                "Summary": {"ColData": [{"value": "Net Income"}, {"value": "1500.50"}]},
            },
        ]
    },
}


def test_a_reference_becomes_the_id_quickbooks_assigned() -> None:
    ids = {"customer:acme": "58", "invoice:inv-1": "130"}
    body = {
        "CustomerRef": {"$ref": "customer:acme"},
        "EntityRef": {"$ref": "customer:acme", "type": "Customer"},
        "Line": [{"LinkedTxn": [{"TxnId": {"$id": "invoice:inv-1"}, "TxnType": "Invoice"}]}],
    }
    assert sandbox.resolve(body, ids) == {
        "CustomerRef": {"value": "58"},
        "EntityRef": {"value": "58", "type": "Customer"},
        "Line": [{"LinkedTxn": [{"TxnId": "130", "TxnType": "Invoice"}]}],
    }


def test_an_undefined_reference_is_an_error_not_a_guess() -> None:
    with pytest.raises(KeyError):
        sandbox.resolve({"CustomerRef": {"$ref": "customer:nobody"}}, {})


def test_amounts_go_out_with_their_exact_digits() -> None:
    sent = sandbox.encode({"Amount": Decimal("1234.50"), "Qty": 1})
    assert sent == b'{"Amount":1234.50,"Qty":1}'


def test_a_report_flattens_to_its_rows_in_order() -> None:
    assert sandbox.flatten(REPORT) == [
        ("Income", ""),
        ("Design Services", "1200.00"),
        ("Workshops", "300.50"),
        ("Total Income", "1500.50"),
        ("Net Income", "1500.50"),
    ]


def test_comparison_ignores_layout_but_not_figures() -> None:
    assert sandbox.comparable(("   Workshops", "=300.50")) != sandbox.comparable(
        ("Workshops", "300.50")
    )
    assert sandbox.comparable(("   Workshops", "300.5")) == sandbox.comparable(
        ("Workshops", "300.50")
    )
    assert sandbox.comparable(("Income", None)) == sandbox.comparable(("Income", ""))
    assert sandbox.comparable(("Rent", "0.00")) == sandbox.comparable(("Rent",))
    assert sandbox.comparable(("Rent", "650.00")) != sandbox.comparable(("Rent", "650.01"))


def test_our_archive_against_itself_is_the_same_cells(tmp_path: Path) -> None:
    copy = tmp_path / "export.zip"
    copy.write_bytes((FIXTURE / "archives" / "accrual" / "export.zip").read_bytes())
    assert sandbox.compare_export(copy, "accrual") == 0


def test_without_credentials_it_stops_and_names_what_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("QBO_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("QBO_REALM_ID", raising=False)
    with pytest.raises(SystemExit, match="QBO_ACCESS_TOKEN is not set"):
        sandbox.Sandbox()


def test_the_fixture_is_what_quickbooks_last_agreed_with() -> None:
    """ADR-0075: a fixture changed after its validation is unvalidated until the next one."""
    record = FIXTURE / "validation.json"
    if not record.exists():
        pytest.skip(
            "not yet validated against a QuickBooks sandbox: see synthetic_books.sandbox"
        )
    validated = json.loads(record.read_text())
    assert validated["result"] == "agrees"
    for rendering in RENDERINGS:
        assert validated["archives"][rendering.name] == sandbox.archive_digest(rendering), (
            f"{rendering.name} changed after its validation; run the sandbox validation again"
        )
