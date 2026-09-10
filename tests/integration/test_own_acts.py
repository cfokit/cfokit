"""Acts reserved to a principal's own judgement (ADR-0042).

Two of them: reopening a closed period (ADR-0030) and importing a company's books (ADR-0041).
Both take `ACT_AS_PRINCIPAL` **and** a principal that is not acting for another, and neither
condition implies the other.

The gap this closes: the check was `actor_class is PERSON`, and `principal_from_claims` assigns
`PERSON` to any token carrying no RFC 8693 `act` claim — which a client credentials token does
not. A component granted capabilities in an entity therefore passed a check reading "a person
did
this". These tests are written against the grant, not against the token, because that is where
the reservation now lives.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import psycopg
import pytest

from cfokit.imports import open_books, post_entries
from cfokit.imports.source import SourceAccount, SourceBooks, SourceEntry, SourceLine
from cfokit.ledger.engine.periods import Period
from cfokit.ledger.errors import NotAPerson, NotAuthorised
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.administration import create_entity
from cfokit.ledger.service.periods import close_period, reopen_period
from cfokit.ledger.service.principal import ActorClass, Principal

pytestmark = pytest.mark.integration

OWNER = Principal(id="user:geoff", actor_class=ActorClass.PERSON)
PERIOD = Period(2026, 1)

# A caller with every class of work and none of the reservation — the component ADR-0042 is
# about, and the one the old check let through.
COMPONENT = Principal(id="service:ingestion", actor_class=ActorClass.PERSON)

# A skill acting for the owner. `IAM-11` intersects its authority with the owner's, so it holds
# the capability transitively — which is exactly why the delegation check is separate.
SKILL = Principal(id="skill:bookkeeper", actor_class=ActorClass.AGENT, acting_for=OWNER.id)


def grant(conn: psycopg.Connection[Any], entity_id: str, principal_id: str, name: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO entity_grant (entity_id, principal_id, role, granted_by)"
            " VALUES (%s, %s, %s, 'test')",
            (entity_id, principal_id, name),
        )


@pytest.fixture
def entity(database: Database) -> str:
    return create_entity(
        database,
        principal=OWNER,
        request_id="fixture",
        slug=f"own-acts-{uuid.uuid4().hex[:8]}",
        name="Books",
        accounting_basis="accrual",
        fiscal_year_end_month=12,
        fiscal_year_end_day=31,
        functional_currency="USD",
        time_zone="UTC",
    ).entity_id


def shape(fingerprint: str = "f" * 64) -> SourceBooks:
    return SourceBooks(
        system="QuickBooks Online",
        fingerprint=fingerprint,
        basis="unknown",
        balances_basis="cash",
        commodity="USD",
        accounts=(SourceAccount(code="Cash", name="Cash", account_type="asset"),),
    )


def entries() -> tuple[SourceEntry, ...]:
    return (
        SourceEntry(
            reference="1",
            transaction_date=date(2026, 3, 1),
            description="",
            lines=(
                SourceLine("Cash", Decimal("1.00"), "USD"),
                SourceLine("Cash", Decimal("-1.00"), "USD"),
            ),
        ),
    )


# --- the capability is what admits the act ---------------------------------------------------


def test_an_owner_may_reopen_a_period(database: Database, entity: str) -> None:
    """`IAM-05` and `IAM-06`: an entity is usable the moment it is created, so its owner needs
    no
    separate grant to do an owner's job."""
    close_period(database, entity_id=entity, principal=OWNER, request_id="r", period=PERIOD)

    reopened = reopen_period(
        database,
        entity_id=entity,
        principal=OWNER,
        request_id="r",
        period=PERIOD,
        reason="a late invoice arrived",
    )

    assert reopened


def test_an_owner_may_import(database: Database, entity: str) -> None:
    opened = open_books(
        database, entity_id=entity, principal=OWNER, request_id="r", books=shape()
    )

    assert opened.accounts_created == 1


# --- a component holding every class of work still may not ------------------------------------


def test_a_component_with_close_may_not_reopen(
    database: Database, owner_conn: psycopg.Connection[Any], entity: str
) -> None:
    """**The gap ADR-0042 closes.** A client credentials token carries no `act` claim, so this
    principal was classified `PERSON` and passed. It holds `CLOSE` — it may decide the books
    have
    been reviewed — and must still not reach the act that lets a write back into a period
    somebody has reported on."""
    grant(owner_conn, entity, COMPONENT.id, "month-end")
    close_period(database, entity_id=entity, principal=OWNER, request_id="r", period=PERIOD)

    with pytest.raises(NotAuthorised):
        reopen_period(
            database,
            entity_id=entity,
            principal=COMPONENT,
            request_id="r",
            period=PERIOD,
            reason="automated",
        )


def test_a_component_with_every_other_capability_may_not_import(
    database: Database, owner_conn: psycopg.Connection[Any], entity: str
) -> None:
    grant(owner_conn, entity, COMPONENT.id, "everything-else")

    with pytest.raises(NotAuthorised):
        open_books(
            database, entity_id=entity, principal=COMPONENT, request_id="r", books=shape()
        )


def test_a_component_granted_the_capability_may_import(
    database: Database, owner_conn: psycopg.Connection[Any], entity: str
) -> None:
    """**Possible and recorded, rather than impossible and unenforceable.** An operator who
    grants
    this has made a deliberate decision with a grantor, a timestamp and an audit row — which is
    the whole of what the token-shape check could not offer."""
    grant(owner_conn, entity, COMPONENT.id, "importer")

    opened = open_books(
        database, entity_id=entity, principal=COMPONENT, request_id="r", books=shape()
    )

    assert opened.accounts_created == 1


# --- delegation is refused even where the person holds it -------------------------------------


def test_a_skill_acting_for_the_owner_may_not_reopen(
    database: Database, owner_conn: psycopg.Connection[Any], entity: str
) -> None:
    """**The condition intersection alone would let through.** `IAM-11` makes the skill's
    authority the intersection of its grants and the owner's, so granting it `owner` gives it
    the
    capability transitively. ADR-0007 is about who *confirms*, not about what they may do."""
    grant(owner_conn, entity, SKILL.id, "owner")
    close_period(database, entity_id=entity, principal=OWNER, request_id="r", period=PERIOD)

    with pytest.raises(NotAPerson):
        reopen_period(
            database,
            entity_id=entity,
            principal=SKILL,
            request_id="r",
            period=PERIOD,
            reason="the user asked",
        )


def test_a_skill_acting_for_the_owner_may_not_import(
    database: Database, owner_conn: psycopg.Connection[Any], entity: str
) -> None:
    grant(owner_conn, entity, SKILL.id, "owner")

    with pytest.raises(NotAPerson):
        open_books(database, entity_id=entity, principal=SKILL, request_id="r", books=shape())


def test_a_skill_may_not_post_entries_either(
    database: Database, owner_conn: psycopg.Connection[Any], entity: str
) -> None:
    """Both halves of an import are reserved. Opening the chart without being able to fill it
    would be a reservation in name only."""
    grant(owner_conn, entity, SKILL.id, "owner")
    open_books(database, entity_id=entity, principal=OWNER, request_id="r", books=shape())

    with pytest.raises(NotAPerson):
        post_entries(
            database,
            entity_id=entity,
            principal=SKILL,
            request_id="r",
            system="QuickBooks Online",
            fingerprint="f" * 64,
            entries=entries(),
        )


# --- the catalogue cannot widen it by accident ------------------------------------------------


def test_owner_is_the_only_seeded_role_carrying_it(
    owner_conn: psycopg.Connection[Any],
) -> None:
    """A future migration must not confer this on a role added for a component. `_known` already
    fails closed on a privilege the enum does not define; this is the same property from the
    other side."""
    with owner_conn.cursor() as cur:
        cur.execute(
            "SELECT role_name FROM role_privilege WHERE privilege = 'act_as_principal'"
            " AND role_name NOT IN (SELECT name FROM role WHERE description LIKE"
            " 'Defined by the integration suite%')"
        )
        carriers = sorted(row[0] for row in cur.fetchall())

    assert carriers == ["owner"]


def test_the_capability_is_recorded_against_a_real_role(
    owner_conn: psycopg.Connection[Any],
) -> None:
    """A privilege naming a role that does not exist confers nothing and hides a typo."""
    with owner_conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM role_privilege p"
            " WHERE p.privilege = 'act_as_principal'"
            " AND NOT EXISTS (SELECT 1 FROM role r WHERE r.name = p.role_name)"
        )
        row = cur.fetchone()

    assert row is not None
    assert row[0] == 0


def test_the_reopen_audit_row_still_names_the_actor(
    database: Database, entity: str, owner_conn: psycopg.Connection[Any]
) -> None:
    """`SOC1-15`: the trail says who. Moving the reservation from the token to the grant must
    not
    change what is recorded about the act."""
    close_period(database, entity_id=entity, principal=OWNER, request_id="r", period=PERIOD)
    reopen_period(
        database,
        entity_id=entity,
        principal=OWNER,
        request_id="r",
        period=PERIOD,
        reason="a late invoice arrived",
    )

    with owner_conn.cursor() as cur:
        cur.execute(
            "SELECT actor, detail FROM audit_log"
            " WHERE entity_id = %s AND action = 'reopen_period'",
            (entity,),
        )
        row = cur.fetchone()

    assert row is not None
    assert OWNER.id in row[0]
    assert row[1]["reason"] == "a late invoice arrived"


def test_the_lapse_of_a_grant_removes_the_capability(
    database: Database, owner_conn: psycopg.Connection[Any], entity: str
) -> None:
    """`IAM-09`: a grant lapses without anyone acting, and the reservation lapses with it —
    which
    a token-shape check could never do."""
    with owner_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO entity_grant (entity_id, principal_id, role, granted_by, lapses_at)"
            " VALUES (%s, %s, 'importer', 'test', %s)",
            (
                entity,
                COMPONENT.id,
                datetime.now(UTC) - timedelta(days=1),
            ),
        )

    with pytest.raises(NotAuthorised):
        open_books(
            database, entity_id=entity, principal=COMPONENT, request_id="r", books=shape()
        )
