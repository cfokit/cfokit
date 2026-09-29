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
    auditor tests it cheaply and once. An agent judgment is neither. The rule path is the
    one to maximize, and making it invisible in the data removes the incentive to.

    **This records why a posting was made. It is never an authority check** (ADR-0042). Whether
    a caller may do something is `authorise`'s question, read from entity grants server-side.
    The two were conflated once, and `PERSON` does not mean a human authenticated — it means the
    token carried no RFC 8693 delegation, which a component's token also does not.

    `RULE` is set on the write path when a rule determined a coding, never derived from a token:
    the rule runs after authentication, and one credential carries both a rule-assigned posting
    and a judgment in the same session. `SOC1-04` describes it that way — an agent completes a
    transaction *assigned by an approved rule* — so the assignment belongs to the transaction.
    Nothing assigns it yet because no rules engine exists.
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
