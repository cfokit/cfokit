"""Creating entities and moving grants around — the acts every other authority descends from.

Three obligations that are easy to state and easy to miss:

- **`IAM-05`**: "Creating an entity assigns its first administrator in the same act. An entity
  never exists without one, and no separate step is required to make it usable." So the entity
  and its first grant are written in one transaction, or neither is.
- **`IAM-03`**: granting, revoking and changing a role assignment are administrative
  capabilities "available to no other role".
- **`IAM-04`**: "An entity always has at least one identity holding the administrative role. The
  last administrator cannot be removed or demoted."

Every one of these writes an `audit_log` row, which is what `IAM-13` requires — "every grant,
invitation, revocation, lapse and role change is recorded, with who made it and when" — and
which nothing satisfied while grants were raw inserts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from cfokit.ledger.errors import LastAdministrator, NotAuthorised
from cfokit.ledger.repository.unit_of_work import Database, EntityWrite
from cfokit.ledger.service.authorisation import Capability, require
from cfokit.ledger.service.principal import Principal

__all__ = [
    "DEPLOYMENT_ADMINISTRATOR",
    "EntityCreated",
    "create_entity",
    "grant_role",
    "revoke_grant",
]

DEPLOYMENT_ADMINISTRATOR = "administrator"


@dataclass(frozen=True, slots=True)
class EntityCreated:
    entity_id: str
    administrator_grant_id: str


def create_entity(
    database: Database,
    *,
    principal: Principal,
    request_id: str,
    slug: str,
    name: str,
    accounting_basis: str,
    fiscal_year_end_month: int,
    fiscal_year_end_day: int,
    functional_currency: str,
    time_zone: str,
    administrator: str | None = None,
) -> EntityCreated:
    """Create an entity and assign its first administrator, atomically (`IAM-05`).

    Requires a deployment-scoped administrative role (`IAM-18`, ADR-0038): an entity role
    cannot confer this, because there is no entity yet to hold one in.

    `administrator` defaults to the creating principal, which is the ordinary case. Naming
    someone else is the case where an operator provisions on a customer's behalf.

    Not entity-scoped, so it does not use `Database.entity_write`: there is no entity to scope
    to or lock on until this commits.
    """
    now = datetime.now(UTC)
    first_administrator = administrator or principal.id

    with database.deployment_write() as write:
        if DEPLOYMENT_ADMINISTRATOR not in write.deployment_roles_in_force(principal.id, now):
            raise NotAuthorised("creating an entity requires a deployment administrator")

        entity_id = write.create_entity(
            slug=slug,
            name=name,
            accounting_basis=accounting_basis,
            fiscal_year_end_month=fiscal_year_end_month,
            fiscal_year_end_day=fiscal_year_end_day,
            functional_currency=functional_currency,
            time_zone=time_zone,
        )
        # Row-level security applies to inserts too, so the grant and the audit row — both of
        # which carry this entity_id — need the session scoped to it first.
        write.scope_to(entity_id)

        # Same transaction as the entity. IAM-05: "An entity never exists without one."
        grant_id = write.grant_entity_role(
            entity_id=entity_id,
            principal_id=first_administrator,
            role="administrator",
            granted_by=principal.id,
        )
        write.record_audit(
            entity_id=entity_id,
            request_id=request_id,
            actor=principal.audit_actor,
            action="create_entity",
            subject_type="entity",
            subject_id=entity_id,
            detail={"administrator": first_administrator},
        )

    return EntityCreated(entity_id=entity_id, administrator_grant_id=grant_id)


def grant_role(
    database: Database,
    *,
    entity_id: str,
    principal: Principal,
    request_id: str,
    to_principal: str,
    role: str,
    lapses_at: datetime | None = None,
) -> str:
    """Grant a role in an entity. Administrative only (`IAM-03`)."""
    now = datetime.now(UTC)
    with database.entity_write(entity_id) as write:
        _require_administrator(write, principal, now)
        grant_id = write.grant_role(
            principal_id=to_principal, role=role, granted_by=principal.id, lapses_at=lapses_at
        )
        write.record_audit(
            request_id=request_id,
            actor=principal.audit_actor,
            action="grant_role",
            subject_type="entity_grant",
            subject_id=grant_id,
            # The principal and role are identifiers, not amounts or names, so they belong in
            # the trail — IAM-13 asks for exactly this.
            detail={"to": to_principal, "role": role},
        )
    return grant_id


def revoke_grant(
    database: Database,
    *,
    entity_id: str,
    principal: Principal,
    request_id: str,
    grant_id: str,
) -> None:
    """Revoke a grant, unless it is the last administrator's (`IAM-03`, `IAM-04`).

    The last-administrator check runs inside the locked transaction, so two concurrent
    revocations cannot each see the other's administrator and leave the entity with none — the
    per-entity advisory lock is what makes that a check rather than a race (ADR-0011).
    """
    now = datetime.now(UTC)
    with database.entity_write(entity_id) as write:
        _require_administrator(write, principal, now)

        if write.would_remove_last_administrator(grant_id, now):
            raise LastAdministrator(
                "an entity always has at least one administrator; grant another first"
            )

        if not write.revoke_grant(grant_id, revoked_by=principal.id):
            raise NotAuthorised("no such grant in this entity, or it is already revoked")

        write.record_audit(
            request_id=request_id,
            actor=principal.audit_actor,
            action="revoke_grant",
            subject_type="entity_grant",
            subject_id=grant_id,
            detail=None,
        )


def _require_administrator(write: EntityWrite, principal: Principal, now: datetime) -> None:
    """`IAM-03`: administering is available to no other role."""
    roles = write.roles_in_force(principal.id, now)
    acted_for = (
        write.roles_in_force(principal.acting_for, now)
        if principal.acting_for is not None
        else frozenset()
    )
    require(Capability.ADMINISTER, principal, roles, acted_for)
