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
  `GRANT` cannot revoke an owner (ADR-0038).

Every one of these writes an `audit_log` row, which is what `IAM-13` requires — "every grant,
invitation, revocation, lapse and role change is recorded, with who made it and when" — and
which nothing satisfied while grants were raw inserts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import quote

from cfokit.ledger.errors import (
    AgentActsForNoMember,
    LastOwner,
    NotAnAgentRole,
    NotAuthorized,
    UnknownRole,
)
from cfokit.ledger.repository.administration import Grant
from cfokit.ledger.repository.connections import Connection
from cfokit.ledger.repository.unit_of_work import Database, EntityWrite
from cfokit.ledger.service.authorization import Capability, authorize
from cfokit.ledger.service.notifications import answer, notify
from cfokit.ledger.service.principal import Principal

__all__ = [
    "AGENT_ALLOWED",
    "EntityCreated",
    "Grant",
    "agents_allowed_here",
    "create_account",
    "create_entity",
    "grant_role",
    "list_grants",
    "revoke_grant",
]


# What an agent holds in an entity it created for its person (ADR-0066 § 5).
CREATING_AGENT_ROLE = "bookkeeper"

# The only roles an agent may hold: neither grants nor owns, so an agent never widens anyone's
# access, its own included (ADR-0066 § 2, migration 0021).
AGENT_ROLES = frozenset({"reader", "bookkeeper"})

# What a company's other administrators are told when an agent is allowed there, about
# that agent (ADR-0066 § 6). Revoking the agent's grant there answers it.
AGENT_ALLOWED = "agent_allowed"


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

    An agent creating an entity for its person makes the person the owner, never itself, and is
    granted `bookkeeper` there in the same act, with its own audit row (ADR-0066 § 5). The
    entity did not exist until the person asked their agent to set it up, so that request is the
    person's authorization of that agent in it; the grant is one they see and revoke like any
    other.

    Not entity-scoped, so it does not use `Database.entity_write`: there is no entity to scope
    to or lock on until this commits.
    """
    first_owner = owner or principal.acting_for or principal.id

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

        if principal.acting_for is not None:
            agent_grant_id = write.grant_entity_role(
                entity_id=entity_id,
                principal_id=principal.id,
                role=CREATING_AGENT_ROLE,
                granted_by=principal.id,
            )
            write.record_audit(
                entity_id=entity_id,
                request_id=request_id,
                actor=principal.audit_actor,
                action="grant_role",
                subject_type="entity_grant",
                subject_id=agent_grant_id,
                detail={"to": principal.id, "role": CREATING_AGENT_ROLE},
            )

    return EntityCreated(entity_id=entity_id, owner_grant_id=grant_id)


def create_account(
    database: Database,
    *,
    entity_id: str,
    principal: Principal,
    request_id: str,
    code: str,
    name: str,
    account_type: str,
    parent_id: str | None = None,
    retained_earnings: bool = False,
    opening_balance: bool = False,
) -> str:
    """Add an account to the entity's chart (`LED-01`, `LED-02`).

    Administrative rather than a posting capability: the chart is the shape of the books, and
    someone who may record a transaction is not thereby deciding what the books are made of.

    `retained_earnings` names this account as the one a fiscal year closes to (`LED-12`), and
    `opening_balance` as the one carried-in balances balance against (`LED-10`). Both must be
    equity accounts, and they are deliberately separate: retained earnings holds what the
    business has earned, and the opening balance account holds the counterweight to figures
    that arrived from a system CFOKit never saw.
    """
    with database.entity_write(entity_id) as write:
        authorize(write, Capability.GRANT, principal)

        if (retained_earnings or opening_balance) and account_type != "equity":
            raise NotAuthorized("a named equity role must be an equity account")

        account_id = write.create_account(
            code=code, name=name, account_type=account_type, parent_id=parent_id
        )
        if retained_earnings:
            write.set_retained_earnings_account(account_id)
        if opening_balance:
            write.set_opening_balance_account(account_id)

        write.record_audit(
            request_id=request_id,
            actor=principal.audit_actor,
            action="create_account",
            subject_type="account",
            subject_id=account_id,
            detail={
                "code": code,
                "type": account_type,
                "retained_earnings": retained_earnings,
                "opening_balance": opening_balance,
            },
        )
    return account_id


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
    if to_principal.startswith("client:") and role not in AGENT_ROLES:
        raise NotAnAgentRole(f"an agent holds reader or bookkeeper, not {role!r}")
    with database.entity_write(entity_id) as write:
        definition = write.role_definition(role)
        if definition is None:
            raise UnknownRole(f"no role {role!r} in this deployment")
        # Granting a role that carries `own` is itself an owner's act: handing the entity away
        # is not part of staffing it (`IAM-21`).
        confers_ownership = Capability.OWN in definition.privileges
        authorize(write, Capability.OWN if confers_ownership else Capability.GRANT, principal)
        if definition.never_lapses and lapses_at is not None:
            # IAM-09's lapse happens without anyone acting, and must never unhold an entity.
            raise NotAuthorized(f"the {role!r} role cannot be granted for a stated period")
        agent = to_principal.startswith("client:")
        if agent and not write.member_connections(to_principal):
            # An agent acts with no more than its person holds (`IAM-11`), so one acting for no
            # one here could do nothing with the grant (ADR-0066 § 2).
            raise AgentActsForNoMember(
                "this agent has not connected for anyone who holds a role in this company; "
                "allow it after connecting it, signed in as a member"
            )
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
        if agent:
            _tell_other_administrators(write, agent=to_principal, allowed_by=principal.id)
    return grant_id


def _tell_other_administrators(write: EntityWrite, *, agent: str, allowed_by: str) -> None:
    """Notify all here who could revoke the agent, except whoever allowed it (ADR-0066 § 6).

    Inside the act that allowed it, so the notification exists exactly when the grant does
    (ADR-0052 § 1). It concerns this company alone and goes only to people who hold it.
    """
    for recipient in write.holders_of(Capability.GRANT.value, datetime.now(UTC)):
        if recipient == allowed_by:
            continue
        notify(
            write,
            recipient=recipient,
            notification_class=AGENT_ALLOWED,
            subject_ref=agent,
            link=f"/app/agents/{quote(agent, safe='')}",
        )


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
        authorize(write, Capability.OWN if confers_ownership else Capability.GRANT, principal)

        if write.would_remove_last_owner(grant_id, now):
            raise LastOwner("an entity always has at least one owner; grant another first")

        holder = write.holder_of_grant(grant_id)

        if not write.revoke_grant(grant_id, revoked_by=principal.id):
            raise NotAuthorized("no such grant in this entity, or it is already revoked")

        write.record_audit(
            request_id=request_id,
            actor=principal.audit_actor,
            action="revoke_grant",
            subject_type="entity_grant",
            subject_id=grant_id,
            detail=None,
        )
        if holder is not None and holder.startswith("client:"):
            # Revoking the agent here answers the notice that it was allowed (ADR-0066 § 6).
            answer(
                write,
                notification_class=AGENT_ALLOWED,
                subject_ref=holder,
                principal=principal,
                act_ref=grant_id,
            )


def list_grants(database: Database, *, entity_id: str, principal: Principal) -> list[Grant]:
    """Every grant in force in this entity, for someone who may grant or revoke there.

    Granting is what reading the grants is for, so the same capability gates it (`IAM-03`): a
    reader or a bookkeeper learns nothing about who else holds the books. A read, so no audit
    row.
    """
    with database.entity_write(entity_id) as write:
        authorize(write, Capability.GRANT, principal)
        return write.grants_in_force(datetime.now(UTC))


def agents_allowed_here(
    database: Database, *, entity_id: str, principal: Principal
) -> list[Connection]:
    """The connections of each agent allowed in this entity, for someone who may revoke it: what
    each reported, and the member account it signed in as (ADR-0066 § 6).

    Gated like the grants, because it is the same question with names on it. A read, so no audit
    row.
    """
    with database.entity_write(entity_id) as write:
        authorize(write, Capability.GRANT, principal)
        allowed = {
            grant.principal_id
            for grant in write.grants_in_force(datetime.now(UTC))
            if grant.principal_id.startswith("client:")
        }
        return [found for found in write.member_connections() if found.agent_id in allowed]
