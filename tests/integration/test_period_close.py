"""Period close and reopen (`LED-11`, ADR-0030, ADR-0027).

> "A period can be marked closed, signifying it has been reviewed. Once closed, no posting
> enters the period except through a recorded reopening, and anything so recorded is
> identifiable as such."

The control here is **person against agent**, not person against person. Most entities have one
person, so segregation of duties is impossible and `IAM-17` says not to raise it; what survives
is that reopening is a capability a skill does not hold and therefore cannot acknowledge its
way through (ADR-0030).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

import psycopg
import pytest

from cfokit.ledger.engine import Entry, Posting
from cfokit.ledger.engine.periods import Period, period_of
from cfokit.ledger.errors import NotAPerson, NotAuthorized, PeriodClosed, PeriodNotClosed
from cfokit.ledger.repository.unit_of_work import Database
from cfokit.ledger.service.administration import grant_role
from cfokit.ledger.service.periods import close_period, reopen_period
from cfokit.ledger.service.principal import ActorClass, Principal
from cfokit.ledger.service.write import (
    WriteContext,
    post_transaction,
    record_transaction,
    reverse_transaction,
)

pytestmark = pytest.mark.integration

MARCH = date(2026, 3, 14)
TODAY = date(2026, 9, 1)
PERSON = Principal(id="user:geoff", actor_class=ActorClass.PERSON)
AGENT = Principal(id="skill:bookkeeper", actor_class=ActorClass.AGENT, acting_for="user:geoff")


def context(entity_id: str, principal: Principal = PERSON) -> WriteContext:
    return WriteContext(
        entity_id=entity_id,
        principal=principal,
        request_id=f"req-{uuid.uuid4().hex[:8]}",
        idempotency_key=uuid.uuid4().hex,
    )


def let_the_agent_own(database: Database, entity_id: str) -> None:
    """Grant the skill everything the person holds.

    `owner` is the only role carrying `close` today, so a test about an agent's capabilities
    has to reach for it. That makes the refusal below stronger rather than weaker: the agent
    holds *every* privilege in the entity and is still refused a reopen, because the check is
    on what the principal is (ADR-0030 § 2).
    """
    grant_role(
        database,
        entity_id=entity_id,
        principal=PERSON,
        request_id="req",
        to_principal=AGENT.id,
        role="owner",
    )


def entry(cash: str, revenue: str, when: date = TODAY, amount: str = "100.00") -> Entry:
    return Entry(
        transaction_date=when,
        postings=(
            Posting(account_id=cash, amount=Decimal(amount), commodity="USD"),
            Posting(account_id=revenue, amount=-Decimal(amount), commodity="USD"),
        ),
        description="Invoice 1001",
    )


# --- Closing (LED-11) ---------------------------------------------------------------------


def test_a_closed_period_refuses_a_posting(
    database: Database, owned_books: tuple[str, str, str]
) -> None:
    """The whole of `LED-11`: "no posting enters the period"."""
    entity_id, cash, revenue = owned_books
    close_period(
        database,
        entity_id=entity_id,
        principal=PERSON,
        request_id="req",
        period=period_of(MARCH),
    )

    with pytest.raises(PeriodClosed) as caught:
        record_transaction(
            database, context(entity_id), entry=entry(cash, revenue, MARCH), post=True
        )

    assert caught.value.code == "period_closed"


def test_a_closed_period_still_accepts_a_draft(
    database: Database, owned_books: tuple[str, str, str]
) -> None:
    """`LED-11` refuses a *posting*, and a draft is not in the books (`LED-07`).

    Refusing it would stop an operator preparing the entry they are about to ask to have the
    period reopened for, which is the gesture ADR-0030 § 3 describes.
    """
    entity_id, cash, revenue = owned_books
    close_period(
        database,
        entity_id=entity_id,
        principal=PERSON,
        request_id="req",
        period=period_of(MARCH),
    )

    written = record_transaction(
        database, context(entity_id), entry=entry(cash, revenue, MARCH), post=False
    )

    assert written.status == "draft"


def test_a_draft_cannot_be_posted_into_a_closed_period(
    database: Database, owned_books: tuple[str, str, str]
) -> None:
    """The boundary is on posting, so it has to hold on the second step as well as the first.

    Without this, drafting first and posting after would be a way around the close.
    """
    entity_id, cash, revenue = owned_books
    written = record_transaction(
        database, context(entity_id), entry=entry(cash, revenue, MARCH), post=False
    )
    close_period(
        database,
        entity_id=entity_id,
        principal=PERSON,
        request_id="req",
        period=period_of(MARCH),
    )

    with pytest.raises(PeriodClosed):
        post_transaction(database, context(entity_id), transaction_id=written.transaction_id)


def test_another_period_is_unaffected(
    database: Database, owned_books: tuple[str, str, str]
) -> None:
    """ADR-0027: "reopening March reopens March. April stays closed" — and the converse.

    Closing one period must not reach any other, or the close would be a watermark.
    """
    entity_id, cash, revenue = owned_books
    close_period(
        database,
        entity_id=entity_id,
        principal=PERSON,
        request_id="req",
        period=period_of(MARCH),
    )

    written = record_transaction(
        database, context(entity_id), entry=entry(cash, revenue, TODAY), post=True
    )

    assert written.status == "posted"


def test_closing_a_period_twice_is_refused(
    database: Database, owned_books: tuple[str, str, str]
) -> None:
    entity_id, _, _ = owned_books
    close_period(
        database,
        entity_id=entity_id,
        principal=PERSON,
        request_id="req",
        period=period_of(MARCH),
    )

    with pytest.raises(PeriodClosed):
        close_period(
            database,
            entity_id=entity_id,
            principal=PERSON,
            request_id="req",
            period=period_of(MARCH),
        )


def test_an_agent_may_close(database: Database, owned_books: tuple[str, str, str]) -> None:
    """Closing asserts the books have been reviewed, and a skill that reconciled a month has
    done that. It is *reopening* a skill must not reach (ADR-0030 § 2)."""
    entity_id, _, _ = owned_books
    let_the_agent_own(database, entity_id)

    close_id = close_period(
        database,
        entity_id=entity_id,
        principal=AGENT,
        request_id="req",
        period=period_of(MARCH),
    )

    assert close_id


def test_closing_requires_the_close_privilege(
    database: Database, owned_books: tuple[str, str, str]
) -> None:
    """Not implied by posting: the point of the control is that someone who may write the
    books does not thereby decide they have been reviewed."""
    entity_id, _, _ = owned_books
    grant_role(
        database,
        entity_id=entity_id,
        principal=PERSON,
        request_id="req",
        to_principal="user:poster",
        role="poster",
    )

    with pytest.raises(NotAuthorized):
        close_period(
            database,
            entity_id=entity_id,
            principal=Principal(id="user:poster", actor_class=ActorClass.PERSON),
            request_id="req",
            period=period_of(MARCH),
        )


# --- Reopening (LED-11, SOC1-17, ADR-0030) ------------------------------------------------


def test_reopening_lets_the_posting_through(
    database: Database, owned_books: tuple[str, str, str]
) -> None:
    """The gesture ADR-0030 § 3 describes, in its parts: close, reopen, post."""
    entity_id, cash, revenue = owned_books
    close_period(
        database,
        entity_id=entity_id,
        principal=PERSON,
        request_id="req",
        period=period_of(MARCH),
    )
    reopen_period(
        database,
        entity_id=entity_id,
        principal=PERSON,
        request_id="req",
        period=period_of(MARCH),
        reason="late supplier receipt",
    )

    written = record_transaction(
        database, context(entity_id), entry=entry(cash, revenue, MARCH), post=True
    )

    assert written.status == "posted"


def test_an_agent_cannot_reopen(database: Database, owned_books: tuple[str, str, str]) -> None:
    """**The load-bearing rule** (ADR-0030 § 2).

    The agent holds the person's privileges through `IAM-11`'s intersection and is still
    refused, because the check is on what the principal *is*. An acknowledgement parameter
    could not do this: an agent would simply set it.
    """
    entity_id, _, _ = owned_books
    let_the_agent_own(database, entity_id)
    close_period(
        database,
        entity_id=entity_id,
        principal=PERSON,
        request_id="req",
        period=period_of(MARCH),
    )

    with pytest.raises(NotAPerson) as caught:
        reopen_period(
            database,
            entity_id=entity_id,
            principal=AGENT,
            request_id="req",
            period=period_of(MARCH),
            reason="it was in the way",
        )

    assert caught.value.code == "not_a_person"


def test_the_period_stays_closed_after_an_agent_tries(
    database: Database, owned_books: tuple[str, str, str]
) -> None:
    """The positive control on the rule above: refusing must also change nothing."""
    entity_id, cash, revenue = owned_books
    let_the_agent_own(database, entity_id)
    close_period(
        database,
        entity_id=entity_id,
        principal=PERSON,
        request_id="req",
        period=period_of(MARCH),
    )
    with pytest.raises(NotAPerson):
        reopen_period(
            database,
            entity_id=entity_id,
            principal=AGENT,
            request_id="req",
            period=period_of(MARCH),
            reason="it was in the way",
        )

    with pytest.raises(PeriodClosed):
        record_transaction(
            database, context(entity_id, AGENT), entry=entry(cash, revenue, MARCH), post=True
        )


def test_a_reopen_must_state_a_reason(
    database: Database, owned_books: tuple[str, str, str]
) -> None:
    """`SOC1-17` requires the reopen to capture one."""
    entity_id, _, _ = owned_books
    close_period(
        database,
        entity_id=entity_id,
        principal=PERSON,
        request_id="req",
        period=period_of(MARCH),
    )

    with pytest.raises(PeriodNotClosed):
        reopen_period(
            database,
            entity_id=entity_id,
            principal=PERSON,
            request_id="req",
            period=period_of(MARCH),
            reason="   ",
        )


def test_reopening_an_open_period_is_refused(
    database: Database, owned_books: tuple[str, str, str]
) -> None:
    entity_id, _, _ = owned_books

    with pytest.raises(PeriodNotClosed):
        reopen_period(
            database,
            entity_id=entity_id,
            principal=PERSON,
            request_id="req",
            period=period_of(MARCH),
            reason="nothing to reopen",
        )


def test_the_close_and_the_reopen_are_both_recorded(
    database: Database, owned_books: tuple[str, str, str], owner_conn: psycopg.Connection[Any]
) -> None:
    """`SOC1-17`: who closed it, who reopened it, when, and why — a history, not a flag."""
    entity_id, _, _ = owned_books
    close_period(
        database,
        entity_id=entity_id,
        principal=PERSON,
        request_id="req",
        period=period_of(MARCH),
    )
    reopen_period(
        database,
        entity_id=entity_id,
        principal=PERSON,
        request_id="req-reopen",
        period=period_of(MARCH),
        reason="late supplier receipt",
    )

    with owner_conn.cursor() as cur:
        cur.execute(
            "SELECT closed_by, reopened_by, reopen_reason FROM period_close"
            " WHERE entity_id = %s AND period_year = 2026 AND period_month = 3",
            (entity_id,),
        )
        assert cur.fetchall() == [("user:geoff", "user:geoff", "late supplier receipt")]

        cur.execute(
            "SELECT action, detail->>'reason' FROM audit_log"
            " WHERE entity_id = %s AND action IN ('close_period', 'reopen_period')"
            " ORDER BY action",
            (entity_id,),
        )
        assert cur.fetchall() == [
            ("close_period", None),
            ("reopen_period", "late supplier receipt"),
        ]


def test_a_period_can_be_closed_again_after_a_reopen(
    database: Database, owned_books: tuple[str, str, str]
) -> None:
    """ADR-0030 § 3: the period is never left silently open."""
    entity_id, _, _ = owned_books
    close_period(
        database,
        entity_id=entity_id,
        principal=PERSON,
        request_id="req",
        period=period_of(MARCH),
    )
    reopen_period(
        database,
        entity_id=entity_id,
        principal=PERSON,
        request_id="req",
        period=period_of(MARCH),
        reason="late supplier receipt",
    )

    close_period(
        database,
        entity_id=entity_id,
        principal=PERSON,
        request_id="req",
        period=period_of(MARCH),
    )

    with pytest.raises(PeriodClosed):
        close_period(
            database,
            entity_id=entity_id,
            principal=PERSON,
            request_id="req",
            period=period_of(MARCH),
        )


# --- Reversal dating follows the period state (ADR-0030 § 4) ------------------------------


def test_a_reversal_restates_an_open_original_period(
    database: Database, owned_books: tuple[str, str, str]
) -> None:
    """Nothing has been reported, so the correction belongs where the error was."""
    entity_id, cash, revenue = owned_books
    original = record_transaction(
        database, context(entity_id), entry=entry(cash, revenue, MARCH), post=True
    )

    reversal = reverse_transaction(
        database,
        context(entity_id),
        transaction_id=original.transaction_id,
        current_period_date=TODAY,
    )

    with database.entity_write(entity_id) as write:
        stored = write.load_transaction(reversal.transaction_id)
    assert stored is not None
    assert stored.transaction_date == MARCH


def test_a_reversal_of_a_closed_original_lands_in_the_current_period(
    database: Database, owned_books: tuple[str, str, str]
) -> None:
    """ADR-0030 § 4, and the reason the ledger reads the period state rather than being told
    it: prior reported figures stand, and the correction appears where it was discovered."""
    entity_id, cash, revenue = owned_books
    original = record_transaction(
        database, context(entity_id), entry=entry(cash, revenue, MARCH), post=True
    )
    close_period(
        database,
        entity_id=entity_id,
        principal=PERSON,
        request_id="req",
        period=period_of(MARCH),
    )

    reversal = reverse_transaction(
        database,
        context(entity_id),
        transaction_id=original.transaction_id,
        current_period_date=TODAY,
    )

    with database.entity_write(entity_id) as write:
        stored = write.load_transaction(reversal.transaction_id)
    assert stored is not None
    assert stored.transaction_date == TODAY
    assert period_of(stored.transaction_date) == Period(2026, 9)


def test_a_reversal_is_refused_when_the_period_it_would_land_in_is_closed(
    database: Database, owned_books: tuple[str, str, str]
) -> None:
    """A reversal is a posting, so wherever rule 4 sends it, that period must be open."""
    entity_id, cash, revenue = owned_books
    original = record_transaction(
        database, context(entity_id), entry=entry(cash, revenue, MARCH), post=True
    )
    close_period(
        database,
        entity_id=entity_id,
        principal=PERSON,
        request_id="req",
        period=period_of(MARCH),
    )
    close_period(
        database,
        entity_id=entity_id,
        principal=PERSON,
        request_id="req",
        period=period_of(TODAY),
    )

    with pytest.raises(PeriodClosed):
        reverse_transaction(
            database,
            context(entity_id),
            transaction_id=original.transaction_id,
            current_period_date=TODAY,
        )
