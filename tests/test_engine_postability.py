"""What makes a draft fit to post (`LED-07`, `LED-15`)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from cfokit.ledger.engine import Entry, Posting, check_postable, is_postable
from cfokit.ledger.errors import (
    CommodityNotPermitted,
    TransactionIncomplete,
    UnbalancedTransaction,
)

TODAY = date(2026, 9, 1)


def entry(*postings: Posting) -> Entry:
    return Entry(transaction_date=TODAY, postings=postings)


def usd(amount: str, account: str = "a") -> Posting:
    return Posting(account_id=account, amount=Decimal(amount), commodity="USD")


def test_a_balanced_entry_in_the_functional_currency_is_postable() -> None:
    check_postable(entry(usd("100.00"), usd("-100.00", "b")), functional_currency="USD")

    assert is_postable(entry(usd("100.00"), usd("-100.00", "b")), functional_currency="USD")


def test_an_unbalanced_entry_is_not_postable() -> None:
    """`LED-03`: the system refuses to record one that does not balance."""
    candidate = entry(usd("100.00"), usd("-99.00", "b"))

    with pytest.raises(UnbalancedTransaction) as caught:
        check_postable(candidate, functional_currency="USD")

    assert caught.value.code == "unbalanced_transaction"
    assert not is_postable(candidate, functional_currency="USD")


def test_a_foreign_commodity_is_refused_with_a_reason() -> None:
    """`LED-15`'s acceptance clause: refused, with a reason, rather than converted.

    `LED-16` is what would permit conversion and is deferred until an entity first transacts
    in another currency.
    """
    candidate = entry(
        Posting(account_id="a", amount=Decimal("100.00"), commodity="EUR"),
        Posting(account_id="b", amount=Decimal("-100.00"), commodity="EUR"),
    )

    with pytest.raises(CommodityNotPermitted, match="EUR") as caught:
        check_postable(candidate, functional_currency="USD")

    assert caught.value.code == "commodity_not_permitted"


def test_a_foreign_commodity_is_refused_even_when_the_entry_balances() -> None:
    """Balancing in EUR does not make EUR acceptable to a USD entity."""
    candidate = entry(
        usd("100.00"),
        usd("-100.00", "b"),
        Posting(account_id="c", amount=Decimal("80.00"), commodity="EUR"),
        Posting(account_id="d", amount=Decimal("-80.00"), commodity="EUR"),
    )

    with pytest.raises(CommodityNotPermitted):
        check_postable(candidate, functional_currency="USD")


def test_an_empty_entry_is_refused_as_incomplete_not_as_unbalanced() -> None:
    """Empty postings sum to zero in every commodity, so a balance check alone would pass it.

    The two codes are distinct because the fixes are different: one entry records nothing,
    the other records the wrong amounts.
    """
    with pytest.raises(TransactionIncomplete) as caught:
        check_postable(entry(), functional_currency="USD")

    assert caught.value.code == "transaction_incomplete"


def test_a_single_posting_is_refused() -> None:
    """Double entry moves value between at least two places."""
    with pytest.raises(TransactionIncomplete):
        check_postable(entry(usd("0.00")), functional_currency="USD")


def test_incompleteness_is_reported_before_imbalance() -> None:
    """The error a caller sees is the one worth fixing first."""
    with pytest.raises(TransactionIncomplete):
        check_postable(entry(usd("100.00")), functional_currency="USD")


def test_the_reported_commodity_is_stable_across_runs() -> None:
    candidate = entry(
        Posting(account_id="a", amount=Decimal("1"), commodity="ZAR"),
        Posting(account_id="b", amount=Decimal("-1"), commodity="AUD"),
    )

    with pytest.raises(CommodityNotPermitted, match="AUD"):
        check_postable(candidate, functional_currency="USD")


def test_is_postable_returns_false_rather_than_raising_for_every_reason() -> None:
    """A predicate whose contract is a bool must not leak any refusal (`LED-07`)."""
    cases = [
        entry(),
        entry(usd("100.00")),
        entry(usd("100.00"), usd("-99.00", "b")),
        entry(
            Posting(account_id="a", amount=Decimal("1"), commodity="EUR"),
            Posting(account_id="b", amount=Decimal("-1"), commodity="EUR"),
        ),
    ]

    assert [is_postable(case, functional_currency="USD") for case in cases] == [
        False,
        False,
        False,
        False,
    ]


def test_postability_does_not_take_the_accounting_basis() -> None:
    """ADR-0037: no posting path branches on the entity's declared basis.

    The ledger is intrinsically accrual and the cash view is derived at presentation, so a
    basis parameter here would be the exact failure that record exists to prevent. Asserted
    against the signature, because the review rule ADR-0037 relies on has no other gate.
    """
    import inspect

    parameters = set(inspect.signature(check_postable).parameters)

    assert "basis" not in parameters
    assert "accounting_basis" not in parameters
    assert parameters == {"entry", "functional_currency"}
