"""Who a write is attributed to (`LED-20`, ADR-0033).

**A `Principal` is constructed from an authenticated credential, never from a request body.**
That is the whole point: ADR-0033 rejects self-reported provenance because "a language model
is non-deterministic ... a skill instructed to record its own session faithfully will do so
most of the time, and there is no guarantee for any particular run. 'Most of the time' is not
a control."

So the adapter builds this from the validated token, and no service function accepts an actor
as a parameter a caller could set. That is the same device ADR-0013 used for `recorded_at`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

__all__ = ["ActorClass", "Principal"]


class ActorClass(StrEnum):
    """Three values, not two (ADR-0033 § 3).

    Collapsing `RULE` into "non-human" would discard the distinction that most reduces
    examination cost: a rule-assigned coding is deterministic and re-derivable, and an
    auditor tests it cheaply and once. An agent judgement is neither. The rule path is the
    one to maximise, and making it invisible in the data removes the incentive to.
    """

    PERSON = "person"
    RULE = "rule"
    AGENT = "agent"


@dataclass(frozen=True, slots=True)
class Principal:
    """The acting principal, and the person it acted for where there is one."""

    id: str
    actor_class: ActorClass
    acting_for: str | None = None

    @property
    def audit_actor(self) -> str:
        """How the trail names this principal.

        An identifier, never a name (CLAUDE.md, Observability). Attribution on the entry is
        what survives; `audit_log` has a retention schedule and the entry does not (ADR-0033).
        """
        if self.acting_for is None:
            return self.id
        return f"{self.id} for {self.acting_for}"
