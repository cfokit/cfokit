"""The published interfaces, and the parts of them that need no database (ADR-0015).

Three interfaces are published: the REST API, the MCP tool surface, and the error codes. CI
gate 5 regenerates all three and fails on a diff. These tests cover what that gate cannot:
that the committed artifacts are actually current, so a contributor finds out locally rather
than from a red pipeline, and that the default deployment refuses to write.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from cfokit.ledger.api import create_app
from cfokit.ledger.api.models import PostingModel
from cfokit.ledger.config import Settings

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACTS = REPO_ROOT / "docs" / "contracts"

SETTINGS = Settings(
    database_url="postgresql://unreachable.invalid/none",
    public_base_url="http://localhost:8080",
    auth_issuer_url="http://localhost:4444",
    auth_audience="cfokit-ledger",
)

WRITE_ROUTES = [
    ("post", "/entities/e/transactions"),
    ("post", "/entities/e/transactions/t/post"),
    ("post", "/entities/e/transactions/t/reversal"),
    ("get", "/entities/e/transactions/t"),
]


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(SETTINGS))


# --- The default deployment cannot write --------------------------------------------------


@pytest.mark.parametrize(("method", "path"), WRITE_ROUTES)
def test_every_ledger_route_refuses_an_unauthenticated_caller(
    client: TestClient, method: str, path: str
) -> None:
    """The default authenticator denies everything, structurally.

    A deployment that has not wired authentication must not book a transaction for an
    anonymous caller. `LED-20` requires every transaction to record what wrote it, and there
    would be nothing true to record.
    """
    kwargs: dict[str, object] = {"json": {}} if method == "post" else {}
    response = getattr(client, method)(path, **kwargs)

    assert response.status_code == 401
    assert response.json()["code"] == "not_authenticated"


def test_the_error_body_carries_a_code_not_only_a_message(client: TestClient) -> None:
    """Callers branch on `code`; `message` is not contractual and may be reworded
    (ADR-0015)."""
    body = client.get("/entities/e/transactions/t").json()

    assert set(body) == {"code", "message"}


# --- The committed artifacts are current --------------------------------------------------


def test_the_committed_openapi_matches_the_application() -> None:
    """CI gate 5 diffs this. Failing here first is friendlier than failing there."""
    committed = json.loads((CONTRACTS / "openapi.json").read_text(encoding="utf-8"))

    assert committed == json.loads(json.dumps(create_app(SETTINGS).openapi()))


def test_every_error_code_is_published() -> None:
    """ADR-0015: "adding a code is a contract change; renaming or removing one is breaking".

    A code that exists in the codebase and not in the artifact is an unpublished contract.
    """
    from cfokit.ledger import errors

    in_code = {
        member.code
        for member in vars(errors).values()
        if isinstance(member, type)
        and issubclass(member, errors.LedgerError)
        and member is not errors.LedgerError
    }
    published = {
        entry["code"]
        for entry in json.loads((CONTRACTS / "error-codes.json").read_text(encoding="utf-8"))
    }

    assert in_code == published


def test_the_mcp_tool_surface_is_published() -> None:
    published = json.loads((CONTRACTS / "mcp-tools.json").read_text(encoding="utf-8"))

    assert [tool["name"] for tool in published] == [
        "account_detail",
        "balance_sheet",
        "post_transaction",
        "profit_and_loss",
        "read_transaction",
        "record_transaction",
        "reverse_transaction",
        "trial_balance",
    ]
    assert all(tool["description"] for tool in published), "every tool describes itself"


def test_both_adapters_publish_the_same_codes() -> None:
    """ADR-0009: "Errors surface the same stable code through both protocols."

    The MCP adapter returns a refusal carrying `code` rather than raising, precisely so this
    holds: the SDK renders a raised exception as a formatted message, and a code recoverable
    only by substring-parsing that message is not a contract.
    """
    from cfokit.ledger.errors import UnbalancedTransaction
    from cfokit.ledger.mcp import refused

    rendered = refused(UnbalancedTransaction.code, "off by 1")

    assert rendered == {"ok": False, "code": "unbalanced_transaction", "message": "off by 1"}


# --- Money on the wire --------------------------------------------------------------------


def test_an_amount_may_be_a_decimal_string() -> None:
    posting = PostingModel.model_validate(
        {"account_id": "a", "amount": "100.00", "commodity": "USD"}
    )

    assert posting.amount == Decimal("100.00")


def test_a_json_number_is_refused_as_an_amount() -> None:
    """A JSON number cannot carry scale: `100.00` parses to `Decimal("100")`.

    That loses the display scale (`LED-06`) and changes the idempotency digest, which is taken
    over the parameters as sent. Refusing is the only way to keep what the caller wrote.
    """
    with pytest.raises(ValidationError, match="decimal string"):
        PostingModel.model_validate({"account_id": "a", "amount": 100.00, "commodity": "USD"})


def test_an_amount_keeps_the_scale_it_was_written_at() -> None:
    """`Decimal("100.00")` and `Decimal("100")` are equal and are not the same request."""
    posting = PostingModel.model_validate(
        {"account_id": "a", "amount": "100.00", "commodity": "USD"}
    )

    assert str(posting.amount) == "100.00"
