"""The administrative path: bringing a deployment into service, and provisioning access.

Until this existed nothing in `src/` created an entity, an account or a grant — only test
fixtures did, with owner-role SQL. So the system authenticated and authorised callers into a
state no legitimate path could produce.

Three requirements carry this file:

- **`IAM-05`**: "Creating an entity assigns its first administrator in the same act. An entity
  never exists without one."
- **`IAM-04`**: "The last administrator cannot be removed or demoted."
- **`IAM-13`**: "Every grant, invitation, revocation, lapse, and role change is recorded, with
  who made it and when."
"""

from __future__ import annotations

import uuid
from typing import Any

import psycopg
import pytest

from cfokit.ledger.bootstrap import AlreadyBootstrapped, bootstrap
from cfokit.ledger.errors import LastAdministrator, NotAuthorised
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.administration import create_entity, grant_role, revoke_grant
from cfokit.ledger.service.principal import ActorClass, Principal

pytestmark = pytest.mark.integration

OPERATOR = "operator:test"


def person(name: str) -> Principal:
    return Principal(id=name, actor_class=ActorClass.PERSON)


@pytest.fixture
def clean_deployment(owner_conn: psycopg.Connection[Any]) -> Any:
    """A deployment with no administrator, and none left behind afterwards.

    Deployment grants are not entity-scoped, so unlike everything else in this suite they are
    global state and have to be cleared explicitly.
    """
    with owner_conn.cursor() as cur:
        cur.execute("SET session_replication_role = replica")
        cur.execute("DELETE FROM deployment_grant")
        cur.execute("SET session_replication_role = origin")
    yield
    with owner_conn.cursor() as cur:
        cur.execute("SET session_replication_role = replica")
        cur.execute("DELETE FROM deployment_grant")
        cur.execute("DELETE FROM audit_log WHERE entity_id IS NULL")
        cur.execute("SET session_replication_role = origin")


def new_entity(database: Database, admin: Principal, slug: str | None = None) -> str:
    created = create_entity(
        database,
        principal=admin,
        request_id="req-test",
        slug=slug or f"acme-{uuid.uuid4().hex[:8]}",
        name="Acme",
        accounting_basis="accrual",
        fiscal_year_end_month=12,
        fiscal_year_end_day=31,
        functional_currency="USD",
        time_zone="UTC",
    )
    return created.entity_id


# --- Bootstrap (IAM-06, ADR-0038) ---------------------------------------------------------


def test_bootstrap_establishes_the_first_administrator(
    owner_database: Database, clean_deployment: None
) -> None:
    result = bootstrap(owner_database, principal_id="user:root", operator=OPERATOR)

    assert result.principal_id == "user:root"


def test_bootstrap_refuses_once_an_administrator_exists(
    owner_database: Database, clean_deployment: None
) -> None:
    """What makes it a bootstrap rather than a standing backdoor (ADR-0038)."""
    bootstrap(owner_database, principal_id="user:root", operator=OPERATOR)

    with pytest.raises(AlreadyBootstrapped):
        bootstrap(owner_database, principal_id="user:usurper", operator=OPERATOR)


def test_running_it_twice_leaves_one_administrator(
    owner_database: Database, owner_conn: psycopg.Connection[Any], clean_deployment: None
) -> None:
    bootstrap(owner_database, principal_id="user:root", operator=OPERATOR)
    with pytest.raises(AlreadyBootstrapped):
        bootstrap(owner_database, principal_id="user:usurper", operator=OPERATOR)

    with owner_conn.cursor() as cur:
        cur.execute("SELECT count(*), min(principal_id) FROM deployment_grant")
        row = cur.fetchone()
    assert row == (1, "user:root")


def test_bootstrap_is_recorded(
    owner_database: Database, owner_conn: psycopg.Connection[Any], clean_deployment: None
) -> None:
    """`IAM-13` has no gap at the origin: the first act is evidenced like every other."""
    bootstrap(owner_database, principal_id="user:root", operator=OPERATOR)

    with owner_conn.cursor() as cur:
        cur.execute(
            "SELECT actor, action, detail->>'principal' FROM audit_log"
            " WHERE entity_id IS NULL AND action = 'bootstrap_deployment'"
        )
        row = cur.fetchone()
    assert row == (OPERATOR, "bootstrap_deployment", "user:root")


# --- Creating an entity (IAM-05, IAM-18) --------------------------------------------------


def test_creating_an_entity_requires_a_deployment_administrator(
    database: Database, clean_deployment: None
) -> None:
    """`IAM-18`: an entity role confers nothing at deployment scope — and there is no entity
    to hold one in yet, so this authority can only come from the other scope."""
    with pytest.raises(NotAuthorised):
        new_entity(database, person("user:nobody"))


def test_an_entity_never_exists_without_an_administrator(
    database: Database,
    owner_database: Database,
    owner_conn: psycopg.Connection[Any],
    clean_deployment: None,
) -> None:
    """`IAM-05`, and the reason both writes are in one transaction."""
    bootstrap(owner_database, principal_id="user:root", operator=OPERATOR)

    entity_id = new_entity(database, person("user:root"))

    with owner_conn.cursor() as cur:
        cur.execute(
            "SELECT principal_id, role FROM entity_grant WHERE entity_id = %s", (entity_id,)
        )
        assert cur.fetchall() == [("user:root", "administrator")]


def test_the_first_administrator_can_be_someone_else(
    database: Database,
    owner_conn: psycopg.Connection[Any],
    clean_deployment: None,
    owner_database: Database,
) -> None:
    """The case where an operator provisions on a customer's behalf."""
    bootstrap(owner_database, principal_id="user:root", operator=OPERATOR)

    entity_id = create_entity(
        database,
        principal=person("user:root"),
        request_id="req-test",
        slug=f"beta-{uuid.uuid4().hex[:8]}",
        name="Beta",
        accounting_basis="cash",
        fiscal_year_end_month=6,
        fiscal_year_end_day=30,
        functional_currency="USD",
        time_zone="Europe/London",
        administrator="user:customer",
    ).entity_id

    with owner_conn.cursor() as cur:
        cur.execute("SELECT principal_id FROM entity_grant WHERE entity_id = %s", (entity_id,))
        assert cur.fetchall() == [("user:customer",)]


def test_a_failed_entity_creation_leaves_nothing(
    database: Database,
    owner_conn: psycopg.Connection[Any],
    clean_deployment: None,
    owner_database: Database,
) -> None:
    """The entity and its administrator are one act, so a failure leaves neither."""
    bootstrap(owner_database, principal_id="user:root", operator=OPERATOR)
    slug = f"clash-{uuid.uuid4().hex[:8]}"
    new_entity(database, person("user:root"), slug=slug)

    with pytest.raises(psycopg.Error):
        new_entity(database, person("user:root"), slug=slug)

    with owner_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM entity WHERE slug = %s", (slug,))
        row = cur.fetchone()
    assert row is not None
    assert row[0] == 1


# --- Granting and revoking (IAM-03, IAM-04, IAM-13) ---------------------------------------


def test_granting_requires_the_administrative_capability(
    database: Database,
    clean_deployment: None,
    owner_database: Database,
) -> None:
    """`IAM-03`: granting is "available to no other role"."""
    bootstrap(owner_database, principal_id="user:root", operator=OPERATOR)
    entity_id = new_entity(database, person("user:root"))
    grant_role(
        database,
        entity_id=entity_id,
        principal=person("user:root"),
        request_id="req",
        to_principal="user:poster",
        role="poster",
    )

    with pytest.raises(NotAuthorised):
        grant_role(
            database,
            entity_id=entity_id,
            principal=person("user:poster"),
            request_id="req",
            to_principal="user:sneak",
            role="administrator",
        )


def test_every_grant_is_recorded_with_who_and_when(
    database: Database,
    owner_conn: psycopg.Connection[Any],
    clean_deployment: None,
    owner_database: Database,
) -> None:
    """`IAM-13`, which nothing satisfied while grants were raw inserts."""
    bootstrap(owner_database, principal_id="user:root", operator=OPERATOR)
    entity_id = new_entity(database, person("user:root"))

    grant_role(
        database,
        entity_id=entity_id,
        principal=person("user:root"),
        request_id="req-grant",
        to_principal="user:new",
        role="reader",
    )

    with owner_conn.cursor() as cur:
        cur.execute(
            "SELECT actor, action, detail->>'to', detail->>'role' FROM audit_log"
            " WHERE entity_id = %s AND action = 'grant_role'",
            (entity_id,),
        )
        assert cur.fetchall() == [("user:root", "grant_role", "user:new", "reader")]


def test_a_revocation_is_recorded(
    database: Database,
    owner_conn: psycopg.Connection[Any],
    clean_deployment: None,
    owner_database: Database,
) -> None:
    bootstrap(owner_database, principal_id="user:root", operator=OPERATOR)
    entity_id = new_entity(database, person("user:root"))
    grant_id = grant_role(
        database,
        entity_id=entity_id,
        principal=person("user:root"),
        request_id="req",
        to_principal="user:temp",
        role="reader",
    )

    revoke_grant(
        database,
        entity_id=entity_id,
        principal=person("user:root"),
        request_id="req-revoke",
        grant_id=grant_id,
    )

    with owner_conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM audit_log WHERE entity_id = %s AND action = 'revoke_grant'",
            (entity_id,),
        )
        row = cur.fetchone()
    assert row is not None
    assert row[0] == 1


def test_the_last_administrator_cannot_be_revoked(
    database: Database,
    clean_deployment: None,
    owner_database: Database,
) -> None:
    """`IAM-04`: an entity always has at least one identity holding the administrative role,
    and the last one cannot be removed or demoted."""
    bootstrap(owner_database, principal_id="user:root", operator=OPERATOR)
    created = create_entity(
        database,
        principal=person("user:root"),
        request_id="req",
        slug=f"solo-{uuid.uuid4().hex[:8]}",
        name="Solo",
        accounting_basis="accrual",
        fiscal_year_end_month=12,
        fiscal_year_end_day=31,
        functional_currency="USD",
        time_zone="UTC",
    )

    with pytest.raises(LastAdministrator) as caught:
        revoke_grant(
            database,
            entity_id=created.entity_id,
            principal=person("user:root"),
            request_id="req",
            grant_id=created.administrator_grant_id,
        )

    assert caught.value.code == "last_administrator"


def test_an_administrator_can_be_revoked_once_another_exists(
    database: Database,
    clean_deployment: None,
    owner_database: Database,
) -> None:
    """The positive control. Without it, a rule refusing every revocation would pass."""
    bootstrap(owner_database, principal_id="user:root", operator=OPERATOR)
    created = create_entity(
        database,
        principal=person("user:root"),
        request_id="req",
        slug=f"pair-{uuid.uuid4().hex[:8]}",
        name="Pair",
        accounting_basis="accrual",
        fiscal_year_end_month=12,
        fiscal_year_end_day=31,
        functional_currency="USD",
        time_zone="UTC",
    )
    grant_role(
        database,
        entity_id=created.entity_id,
        principal=person("user:root"),
        request_id="req",
        to_principal="user:second",
        role="administrator",
    )

    revoke_grant(
        database,
        entity_id=created.entity_id,
        principal=person("user:root"),
        request_id="req",
        grant_id=created.administrator_grant_id,
    )


def test_revoking_a_non_administrator_is_never_the_last_administrator(
    database: Database,
    clean_deployment: None,
    owner_database: Database,
) -> None:
    """The check must not refuse an ordinary revocation in a single-administrator entity."""
    bootstrap(owner_database, principal_id="user:root", operator=OPERATOR)
    entity_id = new_entity(database, person("user:root"))
    grant_id = grant_role(
        database,
        entity_id=entity_id,
        principal=person("user:root"),
        request_id="req",
        to_principal="user:reader",
        role="reader",
    )

    revoke_grant(
        database,
        entity_id=entity_id,
        principal=person("user:root"),
        request_id="req",
        grant_id=grant_id,
    )
