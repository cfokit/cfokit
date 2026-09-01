"""Zero-sum, checked per commodity (`LED-03`, ADR-0006)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from cfokit.ledger.engine import Posting, assert_balanced, is_balanced, totals_by_commodity
from cfokit.ledger.errors import UnbalancedTransaction


def posting(amount: str, commodity: str = "USD", account: str = "a") -> Posting:
    """Construct from `str`, never from `float` (ADR-0005) — fixtures are in scope."""
    return Posting(account_id=account, amount=Decimal(amount), commodity=commodity)


def test_a_balanced_pair_is_balanced() -> None:
    assert is_balanced([posting("100.00"), posting("-100.00")])


def test_an_unbalanced_pair_is_not() -> None:
    assert not is_balanced([posting("100.00"), posting("-99.99")])


def test_empty_postings_sum_to_zero() -> None:
    """Vacuously balanced, which is why `postability` refuses it separately.

    A balance check alone would let an entry recording nothing pass as correct.
    """
    assert is_balanced([])


def test_balance_is_checked_per_commodity_never_netted() -> None:
    """A shortfall in one commodity must not be hidden by a surplus in another.

    These net to zero when summed across commodities, which is exactly the mistake ADR-0006
    forbids: "the check applies per commodity, not to a summed total across commodities".
    """
    postings = [posting("100.00", "USD"), posting("-100.00", "EUR")]

    assert not is_balanced(postings)


def test_multi_commodity_balances_when_each_commodity_does() -> None:
    postings = [
        posting("100.00", "USD"),
        posting("-100.00", "USD"),
        posting("80.00", "EUR"),
        posting("-80.00", "EUR"),
    ]

    assert is_balanced(postings)


def test_exactness_admits_no_tolerance() -> None:
    """`NFR-01` for the ledger: "a tolerance is a defect, not a target".

    One unit in the tenth decimal place is an imbalance, not a rounding artefact. This is a
    deliberate divergence from Beancount, which infers tolerances (ADR-0025).
    """
    assert not is_balanced([posting("100.0000000000"), posting("-99.9999999999")])


def test_totals_are_exact_sums() -> None:
    """`LED-04`: a balance is the exact sum of its postings, with no representation error."""
    totals = totals_by_commodity([posting("0.1"), posting("0.2")])

    assert totals == {"USD": Decimal("0.3")}


def test_assert_balanced_carries_the_stable_code() -> None:
    """Callers depend on `code`, never on the wording (ADR-0015)."""
    with pytest.raises(UnbalancedTransaction) as caught:
        assert_balanced([posting("100.00"), posting("-99.00")])

    assert caught.value.code == "unbalanced_transaction"


def test_assert_balanced_names_the_offending_commodity() -> None:
    """ADR-0006 wants a good message before the trigger produces a blunt one."""
    postings = [posting("100.00", "USD"), posting("-100.00", "USD"), posting("5", "EUR")]

    with pytest.raises(UnbalancedTransaction, match="EUR"):
        assert_balanced(postings)


def test_the_reported_commodity_is_stable_across_runs() -> None:
    """Sorted rather than arbitrary, so the same input always produces the same message."""
    postings = [posting("1", "ZAR"), posting("1", "AUD"), posting("1", "EUR")]

    with pytest.raises(UnbalancedTransaction, match="AUD"):
        assert_balanced(postings)


def test_a_balanced_set_raises_nothing() -> None:
    assert_balanced([posting("100.00"), posting("-100.00")])
