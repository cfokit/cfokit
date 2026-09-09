"""What a principal may do in an entity (`IAM-01`, `IAM-02`, `IAM-11`).

> "An identity's access to an entity is governed by a role. A role carries a defined set of
> capabilities, and an identity holding no role for an entity can do nothing with it."

**Checked server-side regardless of token contents** (ADR-0011, ADR-0019). A token says who
the caller is; it never says what they may do, because a claim the caller can influence is not
an authorisation.

**An agent's authority is the intersection of two principals** (`IAM-11`): "Every action
carries both the skill's own principal and that person's, and its effective authority is the
intersection of the two. No shared credential, service account, or ambient authority stands in
for either." So a skill holding `post` acting for a person holding only `read` can read and
nothing more — and the same in reverse. The intersection is over privileges, not roles, which
is what lets the two principals hold unrelated roles and still compose.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from cfokit.ledger.errors import NotAuthorised
from cfokit.ledger.repository.unit_of_work import EntityWrite
from cfokit.ledger.service.principal import Principal

__all__ = ["Capability", "authorise", "effective", "require"]


class Capability(StrEnum):
    """One flag per thing a caller can do. `IAM-02` names the distinctions these must make.

    **Privileges are code; roles are rows** (ADR-0039). A flag means something only because
    something checks it, so the set lives here. Which roles exist and which flags each carries
    is data, seeded and changed by migration — see `0004-ownership.sql`.

    Recording and posting are separate because `IAM-16` requires the person who drafts a
    transaction not to be the person who posts it where an entity segregates duties. A single
    "writer" flag would make that unexpressible.

    Closing a period is separate from posting because the control in `LED-11` is that someone
    who may write the books does not thereby decide they have been reviewed.

    Managing ownership is separate from managing other grants because `IAM-21` reserves
    granting and revoking ownership to owners. Nothing carries `GRANT` without `OWN` today —
    `owner` is the only role — and the split is what lets a role that delegates staffing
    without handing the entity over be added by migration rather than by code.
    """

    READ = "read"
    RECORD = "record"
    POST = "post"
    GRANT = "grant"
    CLOSE = "close"
    OWN = "own"


def _known(privileges: frozenset[str]) -> frozenset[Capability]:
    """The privileges the code defines, from what the catalogue returned.

    A row naming a privilege this enum does not have confers nothing. Failing closed is the
    only safe direction: a typo in a migration must not widen anyone's authority.
    """
    defined = {c.value for c in Capability}
    return frozenset(Capability(p) for p in privileges & defined)


def effective(
    principal: Principal,
    actor_privileges: frozenset[str],
    acted_for_privileges: frozenset[str],
) -> frozenset[Capability]:
    """The authority actually in force for this principal.

    For a principal acting for itself, that is what its roles confer. For an agent acting for
    a person, it is the **intersection** of both — `IAM-11` is explicit that neither stands in
    for the other, so a skill cannot exceed the person it acts for, and a person cannot reach
    through a skill that was never granted the capability.
    """
    if principal.acting_for is None:
        return _known(actor_privileges)
    return _known(actor_privileges) & _known(acted_for_privileges)


def require(
    capability: Capability,
    principal: Principal,
    actor_privileges: frozenset[str],
    acted_for_privileges: frozenset[str],
) -> None:
    """Raise `NotAuthorised` unless the capability is in force.

    The message names the capability and not the roles held. What a caller is missing is
    useful to them; the shape of someone else's access is not.
    """
    if capability not in effective(principal, actor_privileges, acted_for_privileges):
        raise NotAuthorised(f"this principal may not {capability.value} in this entity")


def authorise(write: EntityWrite, capability: Capability, principal: Principal) -> None:
    """Raise `NotAuthorised` unless `principal` holds `capability` in this entity, now.

    **The way a service or a module checks a capability.** `require` above is the pure rule and
    takes both privilege sets as arguments; this reads them, which is the half every call site
    was assembling for itself.

    That assembly is not boilerplate, it is the control. `IAM-11` makes an agent's effective
    authority the intersection of its own grants and the grants of the person it acts for, so
    the check is over *two* principals — and a call site that looks up only the actor, or
    passes an empty set for the second, silently hands an agent the actor's full authority.
    That failure raises nothing, fails no test, and widens access, which is the combination
    worth removing the opportunity for rather than reviewing for.

    Read inside the caller's locked, entity-scoped transaction, which is what makes `IAM-15`
    true: a revocation committed a moment ago is already in force, because this is a query
    rather than something cached at the edge (ADR-0011, ADR-0019).

    `now` is read here rather than taken as a parameter, for the same reason `recorded_at` is
    server-assigned (ADR-0013): a caller who could state the time could state its way past a
    grant that has lapsed (`IAM-09`).
    """
    now = datetime.now(UTC)
    acted_for = (
        write.privileges_in_force(principal.acting_for, now)
        if principal.acting_for is not None
        else frozenset[str]()
    )
    require(capability, principal, write.privileges_in_force(principal.id, now), acted_for)
