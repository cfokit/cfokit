"""Capabilities, roles, and the intersection `IAM-11` requires."""

from __future__ import annotations

import pytest

from cfokit.ledger.errors import NotAuthorised
from cfokit.ledger.service.authorisation import (
    ROLE_CAPABILITIES,
    Capability,
    capabilities_for,
    effective,
    require,
)
from cfokit.ledger.service.principal import ActorClass, Principal

PERSON = Principal(id="user:geoff", actor_class=ActorClass.PERSON)
AGENT = Principal(id="skill:bookkeeper", actor_class=ActorClass.AGENT, acting_for="user:geoff")


def test_holding_no_role_confers_nothing() -> None:
    """`IAM-01`: "an identity holding no role for an entity can do nothing with it"."""
    assert capabilities_for(frozenset()) == frozenset()


@pytest.mark.parametrize(
    ("role", "capability", "expected"),
    [
        ("reader", Capability.READ, True),
        ("reader", Capability.RECORD, False),
        ("recorder", Capability.RECORD, True),
        ("recorder", Capability.POST, False),
        ("poster", Capability.POST, True),
        ("poster", Capability.ADMINISTER, False),
        ("administrator", Capability.ADMINISTER, True),
    ],
)
def test_roles_distinguish_the_things_iam_02_requires(
    role: str, capability: Capability, expected: bool
) -> None:
    assert (capability in ROLE_CAPABILITIES[role]) is expected


def test_recording_and_posting_are_separable() -> None:
    """`IAM-16` requires the person who drafts not to be the person who posts, where an entity
    segregates duties. A single "writer" role would make that unexpressible."""
    assert Capability.RECORD in ROLE_CAPABILITIES["recorder"]
    assert Capability.POST not in ROLE_CAPABILITIES["recorder"]


def test_a_persons_authority_is_simply_their_roles() -> None:
    assert effective(PERSON, frozenset({"poster"}), frozenset()) == ROLE_CAPABILITIES["poster"]


def test_an_agent_cannot_exceed_the_person_it_acts_for() -> None:
    """`IAM-11`: "its effective authority is the intersection of the two"."""
    granted = effective(AGENT, frozenset({"poster"}), frozenset({"reader"}))

    assert granted == frozenset({Capability.READ})


def test_a_person_cannot_reach_through_an_agent_that_lacks_the_capability() -> None:
    """The intersection binds in both directions, which is what stops a skill's own grant
    being a way around the person's, or the person's a way around the skill's."""
    granted = effective(AGENT, frozenset({"reader"}), frozenset({"administrator"}))

    assert granted == frozenset({Capability.READ})


def test_an_agent_acting_for_someone_with_no_roles_has_none() -> None:
    """ "No shared credential, service account, or ambient authority stands in for either.\""""
    assert effective(AGENT, frozenset({"administrator"}), frozenset()) == frozenset()


def test_require_raises_with_the_stable_code() -> None:
    with pytest.raises(NotAuthorised) as caught:
        require(Capability.POST, PERSON, frozenset({"reader"}), frozenset())

    assert caught.value.code == "not_authorised"


def test_require_names_the_capability_not_the_roles_held() -> None:
    """What a caller is missing is useful to them; the shape of someone else's access is not."""
    with pytest.raises(NotAuthorised, match="post") as caught:
        require(Capability.POST, PERSON, frozenset({"reader"}), frozenset())

    assert "reader" not in caught.value.message
