"""Closing a fiscal year (`LED-12`, ADR-0027).

> "At fiscal year end, income and expense balances are closed to retained earnings so the new
> year opens with them at zero. The closing entries are ordinary postings and are identifiable
> as such."

**Ordinary postings.** Nothing here writes a special kind of row. A close is a balanced
transaction like any other, marked `closing` so `LED-12` can identify it and so ADR-0027's
staleness query can tell machinery from activity.

**Staleness is detected, not remembered** (ADR-0027). A close moved the balances as they stood
when it ran; a posting recorded into that year afterwards means it moved the wrong amount. The
closing transaction's own `recorded_at` is the watermark, so this is a comparison rather than a
flag someone maintains and can forget to.

**A re-run reverses and re-posts** (`LED-08`). The stale entries are not edited and not
removed: what retained earnings was believed to be, and what it is now, both stay retrievable.

**The monthly period lock does not apply to these entries.** `LED-11` refuses a posting
*entering* a closed period, and a closing entry is not that — it is the review act itself, and
its amounts are computed from the books rather than supplied by the caller. Someone holding
`CLOSE` cannot move an amount of their choosing to retained earnings; they can only ask for the
one the ledger derives.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from cfokit.ledger.engine import Posting
from cfokit.ledger.engine.periods import FiscalYear, fiscal_year_of
from cfokit.ledger.errors import NothingToClose, RetainedEarningsUnset, YearAlreadyClosed
from cfokit.ledger.repository.unit_of_work import Database, EntityWrite
from cfokit.ledger.service.authorisation import Capability, require
from cfokit.ledger.service.principal import Principal

__all__ = ["YearClosed", "close_fiscal_year", "is_close_stale"]


class YearClosed:
    """What a close did, and to which year."""

    __slots__ = ("fiscal_year", "reversed_transaction_ids", "transaction_id")

    def __init__(
        self,
        *,
        fiscal_year: FiscalYear,
        transaction_id: str,
        reversed_transaction_ids: list[str],
    ) -> None:
        self.fiscal_year = fiscal_year
        self.transaction_id = transaction_id
        self.reversed_transaction_ids = reversed_transaction_ids


def close_fiscal_year(
    database: Database,
    *,
    entity_id: str,
    principal: Principal,
    request_id: str,
    day_in_year: date,
) -> YearClosed:
    """Close the fiscal year containing `day_in_year`, or re-run a close made stale.

    The year is derived from what the entity declared, never from the caller: a caller who
    could state the fiscal year end could choose which year a close applied to.
    """
    now = datetime.now(UTC)
    with database.entity_write(entity_id) as write:
        _require_close(write, principal, now)

        settings = write.settings
        year = fiscal_year_of(
            day_in_year,
            end_month=settings.fiscal_year_end_month,
            end_day=settings.fiscal_year_end_day,
        )
        retained_earnings = settings.retained_earnings_account_id
        if retained_earnings is None:
            raise RetainedEarningsUnset(
                "this entity has no retained earnings account; name one before closing a year"
            )

        existing = write.closing_entries(year)
        reversed_ids = _reverse_if_stale(write, year, existing, principal)

        balances = write.income_statement_balances(year)
        if not balances:
            raise NothingToClose(f"{year} has no income or expense balance to close")

        transaction_id = _post_closing_entry(
            write,
            year=year,
            balances=balances,
            retained_earnings=retained_earnings,
            principal=principal,
        )

        write.record_audit(
            request_id=request_id,
            actor=principal.audit_actor,
            action="close_fiscal_year",
            subject_type="ledger_transaction",
            subject_id=transaction_id,
            # Counts and identifiers, never amounts (CLAUDE.md, Observability).
            detail={
                "fiscal_year": str(year),
                "accounts_closed": len(balances),
                "reversed": len(reversed_ids),
            },
        )

    return YearClosed(
        fiscal_year=year, transaction_id=transaction_id, reversed_transaction_ids=reversed_ids
    )


def is_close_stale(database: Database, *, entity_id: str, day_in_year: date) -> bool:
    """Whether the fiscal year containing `day_in_year` has a close that no longer holds.

    False for a year that was never closed: there is no claim to have gone stale.
    """
    with database.entity_write(entity_id) as write:
        settings = write.settings
        year = fiscal_year_of(
            day_in_year,
            end_month=settings.fiscal_year_end_month,
            end_day=settings.fiscal_year_end_day,
        )
        existing = write.closing_entries(year)
        return bool(existing) and write.posted_after(year, existing[-1]) > 0


def _reverse_if_stale(
    write: EntityWrite, year: FiscalYear, existing: list[str], principal: Principal
) -> list[str]:
    """Reverse a stale close so the year can be closed again, or refuse a sound one."""
    if not existing:
        return []

    if write.posted_after(year, existing[-1]) == 0:
        raise YearAlreadyClosed(f"{year} is closed and its close is current")

    reversed_ids: list[str] = []
    for original in existing:
        stored = write.load_transaction(original)
        if stored is None or stored.reverses_id is not None:
            # Already a reversal; reversing it again would undo the correction.
            continue
        reversed_ids.append(
            _post(
                write,
                # Dated at the original, not in the current period: a close is restated in its
                # own year or the year no longer nets to zero, which is the whole point of
                # ADR-0027's re-run. That is why this does not go through `build_reversal`,
                # whose dating rule sends a closed period's correction forward.
                when=stored.transaction_date,
                postings=tuple(
                    Posting(
                        account_id=posting.account_id,
                        amount=-posting.amount,
                        commodity=posting.commodity,
                    )
                    for posting in stored.postings
                ),
                description=f"Reversal of stale {year} close",
                principal=principal,
                reverses_id=original,
            )
        )
    return reversed_ids


def _post_closing_entry(
    write: EntityWrite,
    *,
    year: FiscalYear,
    balances: list[tuple[str, Decimal, str]],
    retained_earnings: str,
    principal: Principal,
) -> str:
    """One transaction: every income and expense balance to zero, the net to retained earnings.

    The retained earnings side is the sum of what the others move, so the entry balances by
    construction rather than by arithmetic anyone has to check — and the deferred zero-sum
    trigger (ADR-0006) still checks it.
    """
    postings: list[Posting] = []
    net: dict[str, Decimal] = {}
    for account_id, balance, commodity in balances:
        postings.append(Posting(account_id=account_id, amount=-balance, commodity=commodity))
        net[commodity] = net.get(commodity, Decimal(0)) + balance

    postings.extend(
        Posting(account_id=retained_earnings, amount=amount, commodity=commodity)
        for commodity, amount in sorted(net.items())
        if amount != 0
    )

    return _post(
        write,
        when=year.end,
        postings=tuple(postings),
        description=f"{year} close",
        principal=principal,
        reverses_id=None,
    )


def _post(
    write: EntityWrite,
    *,
    when: date,
    postings: tuple[Posting, ...],
    description: str,
    principal: Principal,
    reverses_id: str | None,
) -> str:
    transaction_id = write.insert_draft(
        transaction_date=when,
        description=description,
        reverses_id=reverses_id,
        entry_kind="closing",
        actor_principal_id=principal.id,
        actor_class=principal.actor_class.value,
        acting_for_principal_id=principal.acting_for,
    )
    write.add_postings(transaction_id, postings)
    write.mark_posted(transaction_id)
    return transaction_id


def _require_close(write: EntityWrite, principal: Principal, now: datetime) -> None:
    actor = write.privileges_in_force(principal.id, now)
    acted_for = (
        write.privileges_in_force(principal.acting_for, now)
        if principal.acting_for is not None
        else frozenset()
    )
    require(Capability.CLOSE, principal, actor, acted_for)
