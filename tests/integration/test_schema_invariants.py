"""The guarantees the schema makes, exercised against a real database.

ADR-0006 and ADR-0007 are both `accepted` — the first migration embodies them in something
that cannot be taken back — and until now neither was tested behaviourally. What existed was
`test_migrations.py` asserting that the string `append_only_violated` appears in the DDL,
which proves the text was written, not that the trigger fires.

That gap is exactly the one these records exist to close. ADR-0006 puts zero-sum in a
constraint trigger rather than in application code because "a check that lives on one code
path is only as reliable as every future code path", and then the check itself went
unverified.

**These run as the schema owner, deliberately.** The application role does not hold `DELETE`
on `ledger_transaction`, so as the application a refused delete raises `InsufficientPrivilege`
before any trigger runs — which tests the grant, not the trigger it exists to back up. The
privilege layer is tested separately in `test_entity_isolation.py`. Two layers, two tests.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import psycopg
import pytest

pytestmark = pytest.mark.integration

USD = "USD"


def new_transaction(
    conn: psycopg.Connection[Any], entity_id: str, *, status: str = "draft"
) -> str:
    """Insert a transaction. `posted_at` is set iff posted, per the schema's CHECK."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO ledger_transaction
                (entity_id, status, posted_at, transaction_date,
                 actor_principal_id, actor_class)
            VALUES (%s, %s, CASE WHEN %s = 'posted' THEN now() END, DATE '2026-09-01',
                    'user:test', 'person')
            RETURNING id
            """,
            (entity_id, status, status),
        )
        row = cur.fetchone()
        assert row is not None
        return str(row[0])


def add_posting(
    conn: psycopg.Connection[Any],
    txn_id: str,
    entity_id: str,
    account_id: str,
    amount: str,
    commodity: str = USD,
) -> None:
    """Amounts arrive as `str` and become `Decimal`. Never a float (ADR-0005)."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO posting (transaction_id, entity_id, account_id, amount, commodity)"
            " VALUES (%s, %s, %s, %s, %s)",
            (txn_id, entity_id, account_id, Decimal(amount), commodity),
        )


# --- Zero-sum, per commodity, at posting (ADR-0006, LED-03) ------------------------------


def test_a_balanced_posted_transaction_commits(
    owner_conn: psycopg.Connection[Any], books: tuple[str, str, str]
) -> None:
    """The positive control. Without it, a trigger that rejected everything would pass."""
    entity_id, cash, revenue = books

    with owner_conn.transaction():
        txn = new_transaction(owner_conn, entity_id, status="posted")
        add_posting(owner_conn, txn, entity_id, cash, "100.00")
        add_posting(owner_conn, txn, entity_id, revenue, "-100.00")

    with owner_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM posting WHERE transaction_id = %s", (txn,))
        row = cur.fetchone()
        assert row is not None
        assert row[0] == 2


def test_an_unbalanced_posted_transaction_is_refused(
    owner_conn: psycopg.Connection[Any], books: tuple[str, str, str]
) -> None:
    """`LED-03`: the system refuses to record one that does not balance."""
    entity_id, cash, _ = books

    with pytest.raises(psycopg.Error, match="zero_sum_violated"), owner_conn.transaction():
        txn = new_transaction(owner_conn, entity_id, status="posted")
        add_posting(owner_conn, txn, entity_id, cash, "100.00")


def test_the_check_is_deferred_so_intermediate_states_are_legal(
    owner_conn: psycopg.Connection[Any], books: tuple[str, str, str]
) -> None:
    """ADR-0006's whole reason for a *deferred* trigger.

    Postings are inserted one row at a time, so a transaction is legitimately unbalanced
    between the first insert and the last. An immediate trigger would make correct code
    impossible to write.
    """
    entity_id, cash, revenue = books

    with owner_conn.transaction():
        txn = new_transaction(owner_conn, entity_id, status="posted")
        # Unbalanced right now, and this statement must not raise.
        add_posting(owner_conn, txn, entity_id, cash, "100.00")
        add_posting(owner_conn, txn, entity_id, revenue, "-100.00")


def test_a_draft_may_be_unbalanced(
    owner_conn: psycopg.Connection[Any], books: tuple[str, str, str]
) -> None:
    """`LED-07`: a draft is freely editable and is not part of the books yet."""
    entity_id, cash, _ = books

    with owner_conn.transaction():
        txn = new_transaction(owner_conn, entity_id, status="draft")
        add_posting(owner_conn, txn, entity_id, cash, "100.00")


def test_posting_an_unbalanced_draft_is_refused(
    owner_conn: psycopg.Connection[Any], books: tuple[str, str, str]
) -> None:
    """The draft-to-posted transition, where no posting row changes.

    This is why 0001 carries a second constraint trigger on `ledger_transaction` as well as
    the one on `posting`. Without it an unbalanced draft could be posted by an UPDATE that
    touched no posting at all.
    """
    entity_id, cash, _ = books

    with owner_conn.transaction():
        txn = new_transaction(owner_conn, entity_id, status="draft")
        add_posting(owner_conn, txn, entity_id, cash, "100.00")

    with (
        pytest.raises(psycopg.Error, match="zero_sum_violated"),
        owner_conn.transaction(),
        owner_conn.cursor() as cur,
    ):
        cur.execute(
            "UPDATE ledger_transaction SET status = 'posted', posted_at = now() WHERE id = %s",
            (txn,),
        )


def test_balance_is_required_in_each_commodity_separately(
    owner_conn: psycopg.Connection[Any], books: tuple[str, str, str]
) -> None:
    """ADR-0006: "per commodity, not to a summed total across commodities".

    These net to zero if you add them up ignoring the commodity, which is the mistake the
    per-commodity grouping exists to prevent.
    """
    entity_id, cash, revenue = books

    with pytest.raises(psycopg.Error, match="zero_sum_violated"), owner_conn.transaction():
        txn = new_transaction(owner_conn, entity_id, status="posted")
        add_posting(owner_conn, txn, entity_id, cash, "100.00", "USD")
        add_posting(owner_conn, txn, entity_id, revenue, "-100.00", "EUR")


def test_a_multi_commodity_transaction_balancing_in_each_commits(
    owner_conn: psycopg.Connection[Any], books: tuple[str, str, str]
) -> None:
    entity_id, cash, revenue = books

    with owner_conn.transaction():
        txn = new_transaction(owner_conn, entity_id, status="posted")
        add_posting(owner_conn, txn, entity_id, cash, "100.00", "USD")
        add_posting(owner_conn, txn, entity_id, revenue, "-100.00", "USD")
        add_posting(owner_conn, txn, entity_id, cash, "80.00", "EUR")
        add_posting(owner_conn, txn, entity_id, revenue, "-80.00", "EUR")


def test_exactness_admits_no_tolerance(
    owner_conn: psycopg.Connection[Any], books: tuple[str, str, str]
) -> None:
    """`NFR-01` for the ledger: "a tolerance is a defect, not a target".

    One unit in the tenth decimal place, which is the finest NUMERIC(28,10) can hold.
    """
    entity_id, cash, revenue = books

    with pytest.raises(psycopg.Error, match="zero_sum_violated"), owner_conn.transaction():
        txn = new_transaction(owner_conn, entity_id, status="posted")
        add_posting(owner_conn, txn, entity_id, cash, "100.0000000000")
        add_posting(owner_conn, txn, entity_id, revenue, "-99.9999999999")


# --- Append-only from posting (ADR-0007, LED-08) -----------------------------------------


def posted_transaction(
    conn: psycopg.Connection[Any], entity_id: str, cash: str, revenue: str
) -> str:
    with conn.transaction():
        txn = new_transaction(conn, entity_id, status="posted")
        add_posting(conn, txn, entity_id, cash, "100.00")
        add_posting(conn, txn, entity_id, revenue, "-100.00")
    return txn


def test_a_posted_transaction_cannot_be_updated(
    owner_conn: psycopg.Connection[Any], books: tuple[str, str, str]
) -> None:
    """`LED-08`: a posted transaction is never altered. Corrections are new entries."""
    entity_id, cash, revenue = books
    txn = posted_transaction(owner_conn, entity_id, cash, revenue)

    with pytest.raises(psycopg.Error, match="append_only_violated"), owner_conn.cursor() as cur:
        cur.execute(
            "UPDATE ledger_transaction SET description = 'edited' WHERE id = %s", (txn,)
        )


def test_a_posted_transaction_cannot_be_deleted(
    owner_conn: psycopg.Connection[Any], books: tuple[str, str, str]
) -> None:
    entity_id, cash, revenue = books
    txn = posted_transaction(owner_conn, entity_id, cash, revenue)

    with pytest.raises(psycopg.Error, match="append_only_violated"), owner_conn.cursor() as cur:
        cur.execute("DELETE FROM ledger_transaction WHERE id = %s", (txn,))


def test_even_a_draft_cannot_be_deleted(
    owner_conn: psycopg.Connection[Any], books: tuple[str, str, str]
) -> None:
    """The trigger refuses every DELETE, not only deletes of posted rows.

    ADR-0007 says financial records are append-only; a draft that vanished without trace
    would still be a record that vanished without trace.
    """
    entity_id, _, _ = books
    txn = new_transaction(owner_conn, entity_id, status="draft")

    with pytest.raises(psycopg.Error, match="append_only_violated"), owner_conn.cursor() as cur:
        cur.execute("DELETE FROM ledger_transaction WHERE id = %s", (txn,))


def test_attribution_cannot_be_rewritten(
    owner_conn: psycopg.Connection[Any], books: tuple[str, str, str]
) -> None:
    """`LED-20` keeps attribution "for the life of the transaction"."""
    entity_id, cash, revenue = books
    txn = posted_transaction(owner_conn, entity_id, cash, revenue)

    with pytest.raises(psycopg.Error, match="append_only_violated"), owner_conn.cursor() as cur:
        cur.execute(
            "UPDATE ledger_transaction SET actor_principal_id = 'someone:else' WHERE id = %s",
            (txn,),
        )


def test_recorded_at_never_changes(
    owner_conn: psycopg.Connection[Any], books: tuple[str, str, str]
) -> None:
    """ADR-0013: `recorded_at` is what makes "the books as we knew them at T" a WHERE clause.

    Refused even on a draft, because the whole point is that it cannot be moved.
    """
    entity_id, _, _ = books
    txn = new_transaction(owner_conn, entity_id, status="draft")

    with pytest.raises(psycopg.Error, match="append_only_violated"), owner_conn.cursor() as cur:
        cur.execute(
            "UPDATE ledger_transaction SET recorded_at = now() - interval '1 year'"
            " WHERE id = %s",
            (txn,),
        )


def test_postings_of_a_posted_transaction_are_immutable(
    owner_conn: psycopg.Connection[Any], books: tuple[str, str, str]
) -> None:
    entity_id, cash, revenue = books
    txn = posted_transaction(owner_conn, entity_id, cash, revenue)

    with pytest.raises(psycopg.Error, match="append_only_violated"), owner_conn.cursor() as cur:
        cur.execute(
            "UPDATE posting SET amount = %s WHERE transaction_id = %s", (Decimal("1"), txn)
        )


def test_postings_of_a_posted_transaction_cannot_be_deleted(
    owner_conn: psycopg.Connection[Any], books: tuple[str, str, str]
) -> None:
    entity_id, cash, revenue = books
    txn = posted_transaction(owner_conn, entity_id, cash, revenue)

    with pytest.raises(psycopg.Error, match="append_only_violated"), owner_conn.cursor() as cur:
        cur.execute("DELETE FROM posting WHERE transaction_id = %s", (txn,))


def test_a_draft_is_freely_editable(
    owner_conn: psycopg.Connection[Any], books: tuple[str, str, str]
) -> None:
    """`LED-07`'s other half, and the positive control for every test above.

    Without it, a trigger that refused all writes would pass the whole append-only section.
    """
    entity_id, cash, _ = books
    txn = new_transaction(owner_conn, entity_id, status="draft")
    add_posting(owner_conn, txn, entity_id, cash, "100.00")

    with owner_conn.cursor() as cur:
        cur.execute(
            "UPDATE ledger_transaction SET description = 'reworded' WHERE id = %s", (txn,)
        )
        cur.execute(
            "UPDATE posting SET amount = %s WHERE transaction_id = %s", (Decimal("50.00"), txn)
        )
        cur.execute("DELETE FROM posting WHERE transaction_id = %s", (txn,))


def test_the_audit_log_cannot_be_rewritten(
    owner_conn: psycopg.Connection[Any], books: tuple[str, str, str]
) -> None:
    """Never rewritten, or it is not a trail. Refused even to the schema owner."""
    entity_id, _, _ = books
    with owner_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO audit_log (entity_id, request_id, actor, action, subject_type)"
            " VALUES (%s, 'req-1', 'user:test', 'test', 'entity')",
            (entity_id,),
        )

    with pytest.raises(psycopg.Error, match="append_only_violated"), owner_conn.cursor() as cur:
        cur.execute(
            "UPDATE audit_log SET actor = 'someone:else' WHERE entity_id = %s", (entity_id,)
        )

    with pytest.raises(psycopg.Error, match="append_only_violated"), owner_conn.cursor() as cur:
        cur.execute("DELETE FROM audit_log WHERE entity_id = %s", (entity_id,))
