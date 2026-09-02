"""Creating entities and moving grants around — the acts every other authority descends from.

Three obligations that are easy to state and easy to miss:

- **`IAM-05`**: "Creating an entity assigns its first owner in the same act. An entity
  never exists without one, and no separate step is required to make it usable." So the entity
  and its first grant are written in one transaction, or neither is.
- **`IAM-06`**: creating an entity requires an authenticated identity and no prior role. It is
  the only act with that property, and it is what makes a running deployment usable as it
  stands.
- **`IAM-03`**: granting, revoking and changing a role assignment are administrative
  capabilities "available to no other role".
- **`IAM-04`**: "An entity always has at least one identity holding it. The last owner cannot
  be revoked or demoted."
- **`IAM-21`**: granting or revoking ownership is an owner's alone, so a role carrying only
  `GRANT` cannot revoke an owner (ADR-0039).

Every one of these writes an `audit_log` row, which is what `IAM-13` requires — "every grant,
invitation, revocation, lapse and role change is recorded, with who made it and when" — and
which nothing satisfied while grants were raw inserts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from cfokit.ledger.errors import LastOwner, NotAuthorised, UnknownRole
from cfokit.ledger.repository.unit_of_work import Database, EntityWrite
from cfokit.ledger.service.authorisation import Capability, require
from cfokit.ledger.service.principal import Principal

__all__ = [
    "EntityCreated",
    "create_entity",
    "grant_role",
    "revoke_grant",
]


@dataclass(frozen=True, slots=True)
class EntityCreated:
    entity_id: str
    owner_grant_id: str


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
    owner: str | None = None,
) -> EntityCreated:
    """Create an entity and assign its first owner, atomically (`IAM-05`).

    Authentication is the whole of the requirement (`IAM-06`). No prior role is asked for,
    because there is no entity to hold one in and a role in some other entity confers nothing
    here — a caller the issuer has authenticated may create an entity and, in the same act,
    becomes the identity holding it (`IAM-05`, `IAM-21`).

    `owner` defaults to the creating principal, which is the ordinary case. Naming someone
    else is the case where one person provisions on another's behalf.

    Not entity-scoped, so it does not use `Database.entity_write`: there is no entity to scope
    to or lock on until this commits.
    """
    first_owner = owner or principal.id

    with database.unscoped_write() as write:
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
            principal_id=first_owner,
            role="owner",
            granted_by=principal.id,
        )
        write.record_audit(
            entity_id=entity_id,
            request_id=request_id,
            actor=principal.audit_actor,
            action="create_entity",
            subject_type="entity",
            subject_id=entity_id,
            detail={"owner": first_owner},
        )

    return EntityCreated(entity_id=entity_id, owner_grant_id=grant_id)


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
    """Grant a role in an entity (`IAM-03`, `IAM-21`).

    Granting a role that carries `OWN` takes `OWN`; granting anything else takes `GRANT`, so a
    role that staffs an entity cannot hand it away.
    """
    now = datetime.now(UTC)
    with database.entity_write(entity_id) as write:
        definition = write.role_definition(role)
        if definition is None:
            raise UnknownRole(f"no role {role!r} in this deployment")
        # Granting a role that carries `own` is itself an owner's act: handing the entity away
        # is not part of staffing it (`IAM-21`).
        confers_ownership = Capability.OWN in definition.privileges
        _require(
            write, principal, now, Capability.OWN if confers_ownership else Capability.GRANT
        )
        if definition.never_lapses and lapses_at is not None:
            # IAM-09's lapse happens without anyone acting, and must never unhold an entity.
            raise NotAuthorised(f"the {role!r} role cannot be granted for a stated period")
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
    """Revoke a grant, unless it is the last owner's (`IAM-03`, `IAM-04`, `IAM-21`).

    Revoking a role that carries `OWN` takes `OWN`, so a role that only staffs an entity cannot
    remove the people whose entity it is.

    The last-owner check runs inside the locked transaction, so two concurrent revocations
    cannot each see the other's owner and leave the entity unheld — the per-entity advisory
    lock is what makes that a check rather than a race (ADR-0011).
    """
    now = datetime.now(UTC)
    with database.entity_write(entity_id) as write:
        target = write.role_of_grant(grant_id)
        held = write.role_definition(target) if target is not None else None
        # Revoking a role that holds the entity takes `own`; revoking anyone else takes
        # `grant`. An administrative role cannot remove the people whose entity it is.
        confers_ownership = held is not None and Capability.OWN in held.privileges
        _require(
            write, principal, now, Capability.OWN if confers_ownership else Capability.GRANT
        )

        if write.would_remove_last_owner(grant_id, now):
            raise LastOwner("an entity always has at least one owner; grant another first")

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


def _require(
    write: EntityWrite, principal: Principal, now: datetime, capability: Capability
) -> None:
    """`IAM-03`: administering is available to no other role."""
    actor = write.privileges_in_force(principal.id, now)
    acted_for = (
        write.privileges_in_force(principal.acting_for, now)
        if principal.acting_for is not None
        else frozenset()
    )
    require(capability, principal, actor, acted_for)
