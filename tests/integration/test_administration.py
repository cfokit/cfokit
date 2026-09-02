"""The administrative path: creating entities, and provisioning access within them.

Until this existed nothing in `src/` created an entity, an account or a grant — only test
fixtures did, with owner-role SQL. So the system authenticated and authorised callers into a
state no legitimate path could produce.

Four requirements carry this file:

- **`IAM-06`**: creating an entity requires an authenticated identity and no prior role.
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

from cfokit.ledger.errors import LastAdministrator, NotAuthorised
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.administration import create_entity, grant_role, revoke_grant
from cfokit.ledger.service.principal import ActorClass, Principal

pytestmark = pytest.mark.integration


def person(name: str) -> Principal:
    return Principal(id=name, actor_class=ActorClass.PERSON)


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


# --- Creating an entity (IAM-05, IAM-06) --------------------------------------------------


def test_any_authenticated_identity_can_create_an_entity(
    database: Database, owner_conn: psycopg.Connection[Any]
) -> None:
    """`IAM-06`: authentication is the whole of the requirement.

    A caller holding no role anywhere creates an entity and, in the same act, becomes the
    identity administering it. This is what makes a running deployment usable as it stands,
    and the grant it asserts is `IAM-05`: "an entity never exists without one".
    """
    entity_id = new_entity(database, person("user:newcomer"))

    with owner_conn.cursor() as cur:
        cur.execute(
            "SELECT principal_id, role FROM entity_grant WHERE entity_id = %s", (entity_id,)
        )
        assert cur.fetchall() == [("user:newcomer", "administrator")]


def test_creating_an_entity_confers_nothing_in_any_other_entity(database: Database) -> None:
    """The counterweight: `IAM-08` gives one identity independent roles per entity.

    Creating an entity requires no prior role, so the test that it grants no *further* reach
    is what keeps that from being a way in. The creator of one entity is a stranger to the
    next.
    """
    theirs = new_entity(database, person("user:incumbent"))
    new_entity(database, person("user:newcomer"))

    with pytest.raises(NotAuthorised):
        grant_role(
            database,
            entity_id=theirs,
            principal=person("user:newcomer"),
            request_id="req",
            to_principal="user:newcomer",
            role="administrator",
        )


def test_the_first_administrator_can_be_someone_else(
    database: Database,
    owner_conn: psycopg.Connection[Any],
) -> None:
    """The case where one person provisions on another's behalf."""

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
) -> None:
    """The entity and its administrator are one act, so a failure leaves neither."""
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


def test_granting_requires_the_administrative_capability(database: Database) -> None:
    """`IAM-03`: granting is "available to no other role"."""
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
) -> None:
    """`IAM-13`, which nothing satisfied while grants were raw inserts."""
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
) -> None:
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


def test_the_last_administrator_cannot_be_revoked(database: Database) -> None:
    """`IAM-04`: an entity always has at least one identity holding the administrative role,
    and the last one cannot be removed or demoted."""
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


def test_an_administrator_can_be_revoked_once_another_exists(database: Database) -> None:
    """The positive control. Without it, a rule refusing every revocation would pass."""
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
) -> None:
    """The check must not refuse an ordinary revocation in a single-administrator entity."""
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
