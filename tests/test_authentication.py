"""Deriving a principal from a token's claims (ADR-0033, `IAM-11`).

Separated from signature verification so the rule that matters — where `actor_class` comes
from — is tested without a key, an issuer, or a network.
"""

from __future__ import annotations

import pytest

from cfokit.ledger.errors import NotAuthenticated
from cfokit.ledger.service.authentication import DenyAll, principal_from_claims
from cfokit.ledger.service.principal import ActorClass


def test_a_plain_subject_is_a_person() -> None:
    principal = principal_from_claims({"sub": "user:geoff"})

    assert principal.id == "user:geoff"
    assert principal.actor_class is ActorClass.PERSON
    assert principal.acting_for is None


def test_an_act_claim_makes_it_an_agent_acting_for_a_person() -> None:
    """RFC 8693 delegation, which `IAM-11` describes: "an agent skill acts on behalf of an
    identified person. Every action carries both the skill's own principal and that
    person's"."""
    principal = principal_from_claims({"sub": "skill:bookkeeper", "act": {"sub": "user:geoff"}})

    assert principal.id == "skill:bookkeeper"
    assert principal.actor_class is ActorClass.AGENT
    assert principal.acting_for == "user:geoff"


def test_actor_class_is_not_taken_from_a_claim() -> None:
    """ADR-0033 rejects self-reported provenance: "no prompt or instruction participates in
    the enforcement", applied to evidence rather than authority.

    A token claiming to be a person is a person only if its shape says so. Here the shape says
    agent, and the claim asking to be called a person is ignored.
    """
    principal = principal_from_claims(
        {
            "sub": "skill:bookkeeper",
            "act": {"sub": "user:geoff"},
            "actor_class": "person",
            "cfokit/class": "person",
        }
    )

    assert principal.actor_class is ActorClass.AGENT


def test_a_rule_cannot_be_claimed_by_a_token() -> None:
    """`rule` is deliberately unreachable from a credential.

    A rule's principal is the system's own when a stored rule assigns a coding; it does not
    arrive bearing a token. Nothing a caller presents can produce this class, which is what
    keeps ADR-0033 § 3's cheap-to-audit path from being claimable by an agent.
    """
    principal = principal_from_claims({"sub": "whoever", "actor_class": "rule"})

    assert principal.actor_class is not ActorClass.RULE


@pytest.mark.parametrize(
    "claims",
    [
        {},
        {"sub": ""},
        {"sub": 42},
        {"sub": "a", "act": "not-an-object"},
        {"sub": "a", "act": {}},
        {"sub": "a", "act": {"sub": ""}},
    ],
    ids=[
        "no sub",
        "empty sub",
        "sub not a string",
        "act not an object",
        "act empty",
        "act sub empty",
    ],
)
def test_malformed_claims_are_refused(claims: dict[str, object]) -> None:
    with pytest.raises(NotAuthenticated):
        principal_from_claims(claims)


def test_deny_all_refuses_even_a_credential() -> None:
    """The default wherever an authenticator is not supplied."""
    with pytest.raises(NotAuthenticated) as caught:
        DenyAll().claims_for("Bearer anything")

    assert caught.value.code == "not_authenticated"
