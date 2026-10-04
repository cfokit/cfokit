"""The import module's REST surface (ADR-0041, `IMP-01` to `IMP-08`).

Driven through FastAPI's `TestClient`, so request validation, dependency resolution and the
error mapping all run — the same path a client takes.

**The archive never appears here**, which is the point. The reader runs in the person's
browser, in the web client (`web/src/quickbooks/` and its tests); what crosses this boundary is
the neutral shape, and these tests are written against that shape directly.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from cfokit.ledger.config import Settings
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.administration import create_entity
from cfokit.ledger.service.principal import ActorClass, Principal
from cfokit.server import rest_app

pytestmark = pytest.mark.integration

PERSON = Principal(id="user:geoff", actor_class=ActorClass.PERSON)
AGENT = Principal(id="agent:skill", actor_class=ActorClass.AGENT, acting_for="user:geoff")

FINGERPRINT = "a" * 64
OTHER_FINGERPRINT = "b" * 64


class StubAuthenticator:
    """Stands in for the issuer, not for the verification.

    The adapter composes `claims_for` with `principal_from_claims`, so faking the first still
    exercises the derivation ADR-0033 turns on: a token's *shape* decides `actor_class`, and
    nothing a caller sends can assert one.
    """

    def __init__(self, principal: Principal = PERSON) -> None:
        self._principal = principal

    def claims_for(self, credential: str | None) -> dict[str, Any]:
        claims: dict[str, Any] = {
            "sub": self._principal.id,
            "iss": "http://localhost:8180/realms/cfokit",
            "aud": "cfokit-ledger",
        }
        if self._principal.acting_for is not None:
            # An RFC 8693 delegation. This shape is what makes the caller an agent.
            claims["act"] = {"sub": self._principal.acting_for}
        return claims


@pytest.fixture
def settings(app_dsn: str) -> Settings:
    return Settings(
        database_url=app_dsn,
        public_base_url="http://localhost:8080",
        auth_issuer_url="http://localhost:8180/realms/cfokit",
        auth_audience="cfokit-ledger",
    )


@pytest.fixture
def client(settings: Settings) -> TestClient:
    return TestClient(rest_app(settings, authenticator=StubAuthenticator()))


@pytest.fixture
def entity(database: Database) -> str:
    return create_entity(
        database,
        principal=PERSON,
        request_id="import",
        slug=f"ingest-{uuid.uuid4().hex[:8]}",
        name="Synthetic Co",
        accounting_basis="accrual",
        fiscal_year_end_month=12,
        fiscal_year_end_day=31,
        functional_currency="USD",
        time_zone="UTC",
    ).entity_id


def shape(**over: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "shape_version": "1",
        "system": "QuickBooks Online",
        "fingerprint": FINGERPRINT,
        "basis": "unknown",
        "balances_basis": "cash",
        "commodity": "USD",
        "accounts": [
            {"code": "Checking", "name": "Checking", "account_type": "asset", "parent": ""},
            {"code": "Income", "name": "Income", "account_type": "income", "parent": ""},
            {
                "code": "Income:Consulting",
                "name": "Income:Consulting",
                "account_type": "income",
                "parent": "Income",
            },
        ],
    }
    body.update(over)
    return body


def batch(*entries: dict[str, Any], fingerprint: str = FINGERPRINT) -> dict[str, Any]:
    return {"system": "QuickBooks Online", "fingerprint": fingerprint, "entries": list(entries)}


def entry(reference: str, amount: str = "100.00") -> dict[str, Any]:
    return {
        "reference": reference,
        "transaction_date": "2026-01-15",
        "description": "Consulting",
        "lines": [
            {"account_code": "Checking", "amount": amount, "commodity": "USD"},
            {"account_code": "Income:Consulting", "amount": f"-{amount}", "commodity": "USD"},
        ],
    }


def opened(client: TestClient, entity: str, **over: Any) -> str:
    response = client.post(f"/entities/{entity}/imports", json=shape(**over))
    assert response.status_code == 201, response.text
    return str(response.json()["import_id"])


# --- opening -----------------------------------------------------------------------------


def test_opening_creates_the_chart(client: TestClient, entity: str) -> None:
    response = client.post(f"/entities/{entity}/imports", json=shape())

    assert response.status_code == 201
    assert response.json()["accounts_created"] == 3
    assert response.json()["accounts_already_present"] == 0


def test_opening_twice_creates_nothing_twice(client: TestClient, entity: str) -> None:
    """A client that retries the opening step must not double the chart. Idempotent by
    observation — an account already present is skipped — rather than by a key."""
    client.post(f"/entities/{entity}/imports", json=shape())
    again = client.post(f"/entities/{entity}/imports", json=shape())

    assert again.status_code == 201
    assert again.json()["accounts_created"] == 0
    assert again.json()["accounts_already_present"] == 3


def test_the_import_id_is_the_same_for_the_same_file(client: TestClient, entity: str) -> None:
    """Derived from the fingerprint, so re-reading the same export names the same import rather
    than looking like a second, unrelated one (`IMP-04`)."""
    first = opened(client, entity)
    second = opened(client, entity)

    assert first == second


def test_a_different_file_is_a_different_import(client: TestClient, entity: str) -> None:
    assert opened(client, entity) != opened(client, entity, fingerprint=OTHER_FINGERPRINT)


def test_a_conflicting_basis_is_refused(client: TestClient, entity: str) -> None:
    """`IMP-06`. Read from the entity, never from the body: a caller who could state the basis
    could state its way past the refusal."""
    response = client.post(f"/entities/{entity}/imports", json=shape(basis="cash"))

    assert response.status_code == 422
    assert response.json()["code"] == "import_refused"


def test_a_foreign_commodity_is_refused(client: TestClient, entity: str) -> None:
    """`IMP-07`, on the same terms as any other foreign amount (`LED-15`)."""
    response = client.post(f"/entities/{entity}/imports", json=shape(commodity="GBP"))

    assert response.status_code == 422
    assert response.json()["code"] == "import_refused"


def test_a_delegated_agent_may_not_open_one(settings: Settings, entity: str) -> None:
    """ADR-0007: the agent proposes, a person's confirmation posts. Creating a company's chart
    is the first half of that act, not a preliminary to it."""
    agent = TestClient(rest_app(settings, authenticator=StubAuthenticator(AGENT)))

    response = agent.post(f"/entities/{entity}/imports", json=shape())

    assert response.status_code == 403
    assert response.json()["code"] == "not_a_person"


# --- entries -----------------------------------------------------------------------------


def test_a_batch_posts(client: TestClient, entity: str) -> None:
    import_id = opened(client, entity)

    response = client.post(
        f"/entities/{entity}/imports/{import_id}/entries",
        json=batch(entry("1"), entry("2")),
    )

    assert response.status_code == 200
    assert response.json()["posted"] == 2
    assert response.json()["replayed"] == 0
    assert response.json()["refusals"] == []


def test_the_same_batch_twice_posts_once(client: TestClient, entity: str) -> None:
    """**The failure worth a test.** A client that times out partway through and retries would
    otherwise post a company's history twice, and append-only leaves no correction short of a
    reversing entry per duplicate (ADR-0007, ADR-0029)."""
    import_id = opened(client, entity)
    url = f"/entities/{entity}/imports/{import_id}/entries"

    first = client.post(url, json=batch(entry("1"), entry("2")))
    second = client.post(url, json=batch(entry("1"), entry("2")))

    assert (first.json()["posted"], first.json()["replayed"]) == (2, 0)
    assert (second.json()["posted"], second.json()["replayed"]) == (0, 2)


def test_a_resumed_import_posts_only_what_is_missing(client: TestClient, entity: str) -> None:
    """A client that died after the first batch resumes by sending both. The overlap replays and
    the remainder posts, which is what makes resume safe without a stage table."""
    import_id = opened(client, entity)
    url = f"/entities/{entity}/imports/{import_id}/entries"

    client.post(url, json=batch(entry("1")))
    resumed = client.post(url, json=batch(entry("1"), entry("2")))

    assert resumed.json()["posted"] == 1
    assert resumed.json()["replayed"] == 1


def test_an_import_id_that_does_not_match_the_fingerprint_is_refused(
    client: TestClient, entity: str
) -> None:
    """Derived rather than stored, so this checks the caller is continuing the import it opened
    rather than looking anything up."""
    import_id = opened(client, entity)

    response = client.post(
        f"/entities/{entity}/imports/{import_id}/entries",
        json=batch(entry("1"), fingerprint=OTHER_FINGERPRINT),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "import_refused"


def test_an_unbalanced_entry_is_refused_and_the_batch_proceeds(
    client: TestClient, entity: str
) -> None:
    """`IMP-05`: an export with three malformed rows out of eleven thousand imports the rest and
    says so."""
    import_id = opened(client, entity)
    broken = entry("2")
    broken["lines"][1]["amount"] = "-90.00"

    response = client.post(
        f"/entities/{entity}/imports/{import_id}/entries",
        json=batch(entry("1"), broken, entry("3")),
    )

    body = response.json()
    assert body["posted"] == 2
    assert [refusal["code"] for refusal in body["refusals"]] == ["unbalanced"]
    assert body["refusals"][0]["reference"] == "2"


def test_a_single_line_entry_is_refused(client: TestClient, entity: str) -> None:
    """A zero-amount single line sums to zero, so a balance check alone would pass it while it
    records no movement of value."""
    import_id = opened(client, entity)
    stub = entry("1")
    stub["lines"] = [{"account_code": "Checking", "amount": "0.00", "commodity": "USD"}]

    response = client.post(f"/entities/{entity}/imports/{import_id}/entries", json=batch(stub))

    assert [r["code"] for r in response.json()["refusals"]] == ["transaction_incomplete"]


def test_an_entry_naming_an_unopened_account_is_refused(
    client: TestClient, entity: str
) -> None:
    """A batch against a chart that was never created — the client skipped the opening step, or
    sent one file's entries against another file's chart."""
    import_id = opened(client, entity)
    stray = entry("1")
    stray["lines"][0]["account_code"] = "Nowhere"

    response = client.post(f"/entities/{entity}/imports/{import_id}/entries", json=batch(stray))

    assert [r["code"] for r in response.json()["refusals"]] == ["unknown_account"]


def test_a_delegated_agent_may_not_post_entries(settings: Settings, entity: str) -> None:
    person = TestClient(rest_app(settings, authenticator=StubAuthenticator()))
    import_id = opened(person, entity)
    agent = TestClient(rest_app(settings, authenticator=StubAuthenticator(AGENT)))

    response = agent.post(
        f"/entities/{entity}/imports/{import_id}/entries", json=batch(entry("1"))
    )

    assert response.status_code == 403
    assert response.json()["code"] == "not_a_person"


def test_a_json_number_amount_is_refused(client: TestClient, entity: str) -> None:
    """A JSON number cannot carry scale, and the idempotency digest is over the parameters as
    sent — so two spellings of one value would be two requests (ADR-0005)."""
    import_id = opened(client, entity)
    numeric = entry("1")
    numeric["lines"][0]["amount"] = 100.00

    response = client.post(
        f"/entities/{entity}/imports/{import_id}/entries", json=batch(numeric)
    )

    assert response.status_code == 422


# --- reconciliation ------------------------------------------------------------------------


def test_it_reconciles_against_the_sources_own_figures(client: TestClient, entity: str) -> None:
    """**`IMP-08`, and the reason any of this is trustworthy.** Against what the source states
    for itself, not a sum computed from the journal we just loaded."""
    import_id = opened(client, entity)
    client.post(f"/entities/{entity}/imports/{import_id}/entries", json=batch(entry("1")))

    response = client.post(
        f"/entities/{entity}/imports/{import_id}/reconciliation",
        json={
            "balances": [
                {"account_code": "Checking", "balance": "100.00"},
                {"account_code": "Income:Consulting", "balance": "-100.00"},
            ]
        },
    )

    assert response.status_code == 201
    assert response.json()["agreed"] == 2
    assert response.json()["compared"] == 2
    assert response.json()["divergences"] == []


def test_a_divergence_is_reported_with_both_figures(client: TestClient, entity: str) -> None:
    """No tolerance. `NFR-01`: "a tolerance is a defect, not a target"."""
    import_id = opened(client, entity)
    client.post(f"/entities/{entity}/imports/{import_id}/entries", json=batch(entry("1")))

    response = client.post(
        f"/entities/{entity}/imports/{import_id}/reconciliation",
        json={"balances": [{"account_code": "Checking", "balance": "90.00"}]},
    )

    body = response.json()
    assert body["agreed"] == 0
    assert body["divergences"][0]["account_code"] == "Checking"
    assert Decimal(body["divergences"][0]["theirs"]) == Decimal("90.00")


def test_reconciling_again_records_again(client: TestClient, entity: str) -> None:
    """A second reconciliation sits beside the first rather than replacing it (ADR-0007)."""
    import_id = opened(client, entity)
    url = f"/entities/{entity}/imports/{import_id}/reconciliation"
    payload = {"balances": [{"account_code": "Checking", "balance": "0.00"}]}

    first = client.post(url, json=payload).json()["reconciliation_id"]
    second = client.post(url, json=payload).json()["reconciliation_id"]

    assert first != second


def test_a_delegated_agent_may_not_record_one(settings: Settings, entity: str) -> None:
    """Recording what the import was reconciled to finishes the import, which is a person's act
    (ADR-0007). An agent reads it instead."""
    import_id = opened(
        TestClient(rest_app(settings, authenticator=StubAuthenticator())), entity
    )
    agent = TestClient(rest_app(settings, authenticator=StubAuthenticator(AGENT)))

    response = agent.post(
        f"/entities/{entity}/imports/{import_id}/reconciliation",
        json={"balances": [{"account_code": "Checking", "balance": "0.00"}]},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "not_a_person"


def test_a_statement_is_compared_by_account(client: TestClient, entity: str) -> None:
    """A statement prints income positive; a posting signs it negative. The comparison is where
    the two conventions meet."""
    import_id = opened(client, entity)
    client.post(f"/entities/{entity}/imports/{import_id}/entries", json=batch(entry("1")))

    response = client.post(
        f"/entities/{entity}/imports/{import_id}/reconciliation",
        json={
            "statements": [
                {
                    "report": "profit_and_loss",
                    "basis": "cash",
                    "lines": [{"account_code": "Income:Consulting", "balance": "100.00"}],
                }
            ]
        },
    )

    statement = response.json()["statements"][0]
    assert statement["agreed"] == 1
    assert statement["divergences"] == []
    assert statement["their_basis"] == "cash"
    assert statement["our_basis"] == "accrual"
