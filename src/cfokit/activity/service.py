"""Recording a statement, and asking whether the books agree with it (`BKP-03`, ADR-0046).

Two calls.

`record_statement` proves the statement against its own balances and stores it. It posts
nothing, and codes nothing: what comes back is each line with the source reference a
transaction coded from it will carry, for the caller to hand to assignment. The two modules
never import each other (ADR-0022), so that hand-off is the caller's.

`statement_agreement` compares the statement's balances with the books' own figures for the
account over the same period. It is what says the lines reached the books as the statement
printed them — the proof on the way in checks the transcription against the statement; this
checks the books against both.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cfokit.activity import Continuity, Statement, content_digest, continuity, prove
from cfokit.activity.errors import StatementNotFound, StatementOverlaps
from cfokit.activity.repository import (
    StoredStatement,
    insert_statement,
    load_statement,
    overlapping,
    previous,
)
from cfokit.ledger.errors import AccountNotFound
from cfokit.ledger.repository.unit_of_work import Database, EntityWrite
from cfokit.ledger.service.authorisation import Capability, authorise
from cfokit.ledger.service.principal import Principal
from cfokit.ledger.service.reports import account_detail

__all__ = ["Agreement", "Recorded", "record_statement", "statement_agreement"]


@dataclass(frozen=True, slots=True)
class Recorded:
    """A statement as stored, and how it follows the one before it."""

    stored: StoredStatement
    replayed: bool
    continuity: Continuity | None


@dataclass(frozen=True, slots=True)
class Agreement:
    """The statement's balances beside the books' posted balances for the same period.

    Two figures and whether they agree, and nothing about which is wrong: a comparison
    detects a difference and cannot say which side caused it. Drafts are not in the books
    (`LED-07`), so a statement whose lines are drafted but not yet posted disagrees by
    exactly what is waiting.
    """

    statement_id: str
    stated_opening: Decimal
    books_opening: Decimal
    stated_closing: Decimal
    books_closing: Decimal

    @property
    def agrees(self) -> bool:
        return (
            self.stated_opening == self.books_opening
            and self.stated_closing == self.books_closing
        )


def record_statement(
    database: Database,
    *,
    entity_id: str,
    principal: Principal,
    request_id: str,
    statement: Statement,
) -> Recorded:
    """Prove a statement, then store it. Refused whole if any part of it fails.

    **The same statement sent twice replays.** Its identity is its account, its period and
    its content — which ADR-0029 forbids for a transaction, because two identical coffees are
    two transactions, and which is right for a statement, because two statements covering the
    same days of one account are never both genuine. A different statement for an overlapping
    period is refused (`statement_overlaps`).
    """
    prove(statement)
    digest = content_digest(statement)

    with database.entity_write(entity_id) as write:
        authorise(write, Capability.RECORD, principal)
        if write.account(statement.account_id) is None:
            raise AccountNotFound(f"no account {statement.account_id} in this entity")
        conn = write.connection

        clashes = overlapping(
            conn,
            entity_id=entity_id,
            account_id=statement.account_id,
            period_start=statement.period_start,
            period_end=statement.period_end,
        )
        for clash_id, start, end, clash_digest in clashes:
            if (start, end, clash_digest) == (
                statement.period_start,
                statement.period_end,
                digest,
            ):
                # No work, and deliberately no audit row: a replay is not a state change.
                stored = load_statement(conn, entity_id=entity_id, statement_id=clash_id)
                assert stored is not None  # noqa: S101 - just found under the same lock
                return Recorded(
                    stored=stored,
                    replayed=True,
                    continuity=_continuity(write, entity_id, statement),
                )
        if clashes:
            _, start, end, _ = clashes[0]
            raise StatementOverlaps(
                f"a statement for this account already covers {start} to {end}"
            )

        statement_id = insert_statement(
            conn,
            entity_id=entity_id,
            statement=statement,
            content_digest=digest,
            recorded_by=principal.id,
        )
        write.record_audit(
            request_id=request_id,
            actor=principal.audit_actor,
            action="record_account_statement",
            subject_type="account_statement",
            subject_id=statement_id,
            # Identifiers and counts. Never balances, amounts or payees.
            detail={"lines": len(statement.lines), "account_id": statement.account_id},
        )
        follows = _continuity(write, entity_id, statement)

    return Recorded(
        stored=StoredStatement(id=statement_id, content_digest=digest, statement=statement),
        replayed=False,
        continuity=follows,
    )


def _continuity(write: EntityWrite, entity_id: str, statement: Statement) -> Continuity | None:
    before = previous(
        write.connection,
        entity_id=entity_id,
        account_id=statement.account_id,
        before=statement.period_start,
    )
    if before is None:
        return None
    previous_id, previous_end, previous_closing = before
    return continuity(
        statement,
        previous_statement_id=previous_id,
        previous_end=previous_end,
        previous_closing=previous_closing,
    )


def statement_agreement(
    database: Database, *, entity_id: str, principal: Principal, statement_id: str
) -> Agreement:
    """Whether the books' posted balances for the account match what the statement states.

    A read. The ledger's own account detail supplies the books' side, under its own
    authorisation, so this module adds no second way of computing a balance.

    The books' balance is the account's across every commodity it holds, which is what
    `account_detail` reports; for an account held in one commodity, which a bank account is,
    that is the figure the statement prints.
    """
    with database.entity_write(entity_id) as write:
        authorise(write, Capability.READ, principal)
        stored = load_statement(
            write.connection, entity_id=entity_id, statement_id=statement_id
        )
    if stored is None:
        raise StatementNotFound(f"no statement {statement_id} in this entity")

    statement = stored.statement
    detail = account_detail(
        database,
        entity_id=entity_id,
        principal=principal,
        account_id=statement.account_id,
        since=statement.period_start,
        as_of=statement.period_end,
    )
    return Agreement(
        statement_id=stored.id,
        stated_opening=statement.opening_balance,
        books_opening=detail.opening_balance,
        stated_closing=statement.closing_balance,
        books_closing=detail.closing_balance,
    )
