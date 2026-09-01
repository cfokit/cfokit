"""What a principal may do in an entity (`IAM-01`, `IAM-02`, `IAM-11`).

> "An identity's access to an entity is governed by a role. A role carries a defined set of
> capabilities, and an identity holding no role for an entity can do nothing with it."

**Checked server-side regardless of token contents** (ADR-0011, ADR-0019). A token says who
the caller is; it never says what they may do, because a claim the caller can influence is not
an authorisation.

**An agent's authority is the intersection of two principals** (`IAM-11`): "Every action
carries both the skill's own principal and that person's, and its effective authority is the
intersection of the two. No shared credential, service account, or ambient authority stands in
for either." So a skill granted `poster` acting for a person granted `reader` can read and
nothing more — and the same in reverse.
"""

from __future__ import annotations

from enum import StrEnum

from cfokit.ledger.errors import NotAuthorised
from cfokit.ledger.service.principal import Principal

__all__ = ["ROLE_CAPABILITIES", "Capability", "capabilities_for", "require"]


class Capability(StrEnum):
    """The distinctions `IAM-02` requires roles to make."""

    READ = "read"
    RECORD = "record"
    POST = "post"
    ADMINISTER = "administer"


# Recording and posting are separate because `IAM-16` requires the person who drafts a
# transaction not to be the person who posts it where an entity segregates duties. A single
# "writer" role would make that unexpressible.
ROLE_CAPABILITIES: dict[str, frozenset[Capability]] = {
    "reader": frozenset({Capability.READ}),
    "recorder": frozenset({Capability.READ, Capability.RECORD}),
    "poster": frozenset({Capability.READ, Capability.RECORD, Capability.POST}),
    "administrator": frozenset(Capability),
}


def capabilities_for(roles: frozenset[str]) -> frozenset[Capability]:
    """Everything the given roles confer, taken together."""
    granted: set[Capability] = set()
    for role in roles:
        granted |= ROLE_CAPABILITIES.get(role, frozenset())
    return frozenset(granted)


def effective(
    principal: Principal,
    actor_roles: frozenset[str],
    acted_for_roles: frozenset[str],
) -> frozenset[Capability]:
    """The authority actually in force for this principal.

    For a principal acting for itself, that is what its roles confer. For an agent acting for
    a person, it is the **intersection** of both — `IAM-11` is explicit that neither stands in
    for the other, so a skill cannot exceed the person it acts for, and a person cannot reach
    through a skill that was never granted the capability.
    """
    if principal.acting_for is None:
        return capabilities_for(actor_roles)
    return capabilities_for(actor_roles) & capabilities_for(acted_for_roles)


def require(
    capability: Capability,
    principal: Principal,
    actor_roles: frozenset[str],
    acted_for_roles: frozenset[str],
) -> None:
    """Raise `NotAuthorised` unless the capability is in force.

    The message names the capability and not the roles held. What a caller is missing is
    useful to them; the shape of someone else's access is not.
    """
    if capability not in effective(principal, actor_roles, acted_for_roles):
        raise NotAuthorised(f"this principal may not {capability.value} in this entity")
