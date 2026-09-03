"""Opening a set of books with balances carried in (`LED-10`).

> "An entity's books can be opened with balances carried in from before CFOKit held them.
> Opening balances are ordinary postings, balance to zero against a single identified equity
> account, and are identifiable as opening balances."

**Ordinary postings.** Nothing here writes a special kind of row. The entry is balanced like
any other and the zero-sum trigger checks it like any other (ADR-0006); `entry_kind = 'opening'`
is what makes it identifiable, and it is the only thing that distinguishes it.

**The equity side is computed, not supplied.** A caller states what each account carried and
the ledger works out the counterweight, so an entry that does not balance is impossible rather
than refused. That is also why a caller who got a figure wrong finds out from the books rather
than from an error message.

**Books are opened once.** Opening them again would double every carried-in figure, and a
figure that was wrong or an account missed at the time is corrected the way every other posted
mistake is — an ordinary entry against the same equity account (`LED-08`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

from cfokit.ledger.engine import Posting
from cfokit.ledger.engine.periods import period_of
from cfokit.ledger.errors import (
    AlreadyOpened,
    CommodityNotPermitted,
    OpeningBalanceAccountUnset,
    PeriodClosed,
    TransactionIncomplete,
)
from cfokit.ledger.repository.unit_of_work import Database, EntityWrite
from cfokit.ledger.service.authorisation import Capability, require
from cfokit.ledger.service.principal import Principal

__all__ = ["CarriedBalance", "OpenedBooks", "open_balances"]


@dataclass(frozen=True, slots=True)
class CarriedBalance:
    """One account's balance as it stood in the system CFOKit is taking over from."""

    account_id: str
    amount: Decimal
    commodity: str


@dataclass(frozen=True, slots=True)
class OpenedBooks:
    """What opening the books produced."""

    transaction_id: str
    as_of: date
    equity_amount: Decimal


def open_balances(
    database: Database,
    *,
    entity_id: str,
    principal: Principal,
    request_id: str,
    as_of: date,
    balances: list[CarriedBalance],
) -> OpenedBooks:
    """Carry balances in, dated `as_of`, balancing to the entity's opening balance account.

    `as_of` is the day the balances stood at — conventionally the day before the first period
    CFOKit keeps, so the opening figures sit outside every period it reports on.
    """
    now = datetime.now(UTC)
    if not balances:
        raise TransactionIncomplete("opening the books needs at least one balance")

    with database.entity_write(entity_id) as write:
        _require_post(write, principal, now)

        equity_account = write.settings.opening_balance_account_id
        if equity_account is None:
            raise OpeningBalanceAccountUnset(
                "this entity has no opening balance account; name one before opening the books"
            )
        if write.any_opening_entry():
            raise AlreadyOpened(
                "these books already carry opening balances; correct them with an entry"
            )
        if write.close_in_force(period_of(as_of)) is not None:
            raise PeriodClosed(f"period {period_of(as_of)} is closed; reopen it to open here")

        functional = write.functional_currency
        offending = {b.commodity for b in balances} - {functional}
        if offending:
            # The same refusal an ordinary posting gets, for the same reason (`LED-15`).
            raise CommodityNotPermitted(
                f"this entity is denominated in {functional}; refused "
                f"{', '.join(sorted(offending))}"
            )

        equity_amount = -sum((b.amount for b in balances), Decimal(0))
        postings = [
            Posting(account_id=b.account_id, amount=b.amount, commodity=b.commodity)
            for b in balances
        ]
        if equity_amount != 0:
            postings.append(
                Posting(account_id=equity_account, amount=equity_amount, commodity=functional)
            )

        transaction_id = write.insert_draft(
            transaction_date=as_of,
            description="Opening balances",
            reverses_id=None,
            entry_kind="opening",
            actor_principal_id=principal.id,
            actor_class=principal.actor_class.value,
            acting_for_principal_id=principal.acting_for,
        )
        write.add_postings(transaction_id, tuple(postings))
        write.mark_posted(transaction_id)

        write.record_audit(
            request_id=request_id,
            actor=principal.audit_actor,
            action="open_balances",
            subject_type="ledger_transaction",
            subject_id=transaction_id,
            # Counts and dates, never amounts (CLAUDE.md, Observability).
            detail={"as_of": as_of.isoformat(), "accounts": len(balances)},
        )

    return OpenedBooks(transaction_id=transaction_id, as_of=as_of, equity_amount=equity_amount)


def _require_post(write: EntityWrite, principal: Principal, now: datetime) -> None:
    """Posting, because the caller chooses the amounts.

    Distinct from the year-end close, which needs `CLOSE` and derives everything it writes.
    """
    actor = write.privileges_in_force(principal.id, now)
    acted_for = (
        write.privileges_in_force(principal.acting_for, now)
        if principal.acting_for is not None
        else frozenset()
    )
    require(Capability.POST, principal, actor, acted_for)
