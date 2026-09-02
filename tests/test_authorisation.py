"""What a principal may do in an entity (`IAM-01`, `IAM-02`, `IAM-11`).

Pure: privileges arrive as a set, so this layer needs no database and no catalogue. Which
roles carry which privileges is data and is asserted against the catalogue in the integration
suite (ADR-0036, layer 1 versus layer 3).
"""

from __future__ import annotations

import pytest

from cfokit.ledger.errors import NotAuthorised
from cfokit.ledger.service.authorisation import Capability, effective, require
from cfokit.ledger.service.principal import ActorClass, Principal

PERSON = Principal(id="user:ana", actor_class=ActorClass.PERSON)
AGENT = Principal(id="skill:bookkeeper", actor_class=ActorClass.AGENT, acting_for="user:ana")

EVERYTHING = frozenset(c.value for c in Capability)
READ_ONLY = frozenset({Capability.READ.value})


def test_no_privileges_is_no_authority() -> None:
    """`IAM-01`: an identity holding no role "can do nothing with it", not the default."""
    assert effective(PERSON, frozenset(), frozenset()) == frozenset()


def test_a_persons_authority_is_simply_what_it_holds() -> None:
    assert effective(PERSON, EVERYTHING, frozenset()) == frozenset(Capability)


def test_an_unknown_privilege_confers_nothing() -> None:
    """A row naming a privilege the code does not define fails closed (ADR-0039).

    A typo in a migration must not widen anyone's authority, and it must not crash the request
    either — the name is simply not a capability anything checks.
    """
    granted = effective(PERSON, frozenset({"read", "teleport"}), frozenset())

    assert granted == frozenset({Capability.READ})


def test_an_agent_cannot_exceed_the_person_it_acts_for() -> None:
    """`IAM-11`: "its effective authority is the intersection of the two"."""
    assert effective(AGENT, EVERYTHING, READ_ONLY) == frozenset({Capability.READ})


def test_a_person_cannot_reach_through_an_agent_that_lacks_the_capability() -> None:
    """The intersection binds in both directions, which is what stops a skill's own grant
    being a way around the person's, or the person's a way around the skill's."""
    assert effective(AGENT, READ_ONLY, EVERYTHING) == frozenset({Capability.READ})


def test_an_agent_acting_for_someone_with_no_roles_has_none() -> None:
    """ "No shared credential, service account, or ambient authority stands in for either.\""""
    assert effective(AGENT, EVERYTHING, frozenset()) == frozenset()


def test_require_raises_with_the_stable_code() -> None:
    with pytest.raises(NotAuthorised) as caught:
        require(Capability.POST, PERSON, READ_ONLY, frozenset())

    assert caught.value.code == "not_authorised"


def test_require_names_the_capability_not_the_roles_held() -> None:
    """What a caller is missing is useful to them; the shape of someone else's access is not."""
    with pytest.raises(NotAuthorised) as caught:
        require(Capability.POST, PERSON, READ_ONLY, frozenset())

    assert "post" in str(caught.value)
    assert "read" not in str(caught.value)
