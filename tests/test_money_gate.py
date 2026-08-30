"""The CI gate that keeps floats away from money must actually catch one (ADR-0005).

A gate nobody has seen fail has not been verified.
"""

from __future__ import annotations

from check_money import offending_lines, offending_python_lines


def test_numeric_columns_pass() -> None:
    sql = """
    CREATE TABLE posting (
        id          BIGSERIAL PRIMARY KEY,
        amount      NUMERIC(28,10) NOT NULL,
        commodity   TEXT NOT NULL
    );
    """
    assert offending_lines(sql) == []


def test_double_precision_is_caught() -> None:
    sql = "CREATE TABLE posting (amount DOUBLE PRECISION NOT NULL);"
    assert len(offending_lines(sql)) == 1


def test_real_and_money_are_caught() -> None:
    assert offending_lines("amount REAL")
    assert offending_lines("amount MONEY")
    assert offending_lines("amount FLOAT8")


def test_comments_are_ignored() -> None:
    """A comment explaining why floats are banned must not trip the gate."""
    assert offending_lines("-- never use REAL or DOUBLE PRECISION here") == []


def test_column_names_containing_a_keyword_are_not_false_positives() -> None:
    assert offending_lines("floating_holiday_accrual NUMERIC(28,10)") == []


# --- Python source ---------------------------------------------------------------------


def test_decimal_code_passes() -> None:
    source = (
        "from decimal import Decimal\n\n"
        "def total(a: Decimal, b: Decimal) -> Decimal:\n"
        "    return a + b\n"
    )
    assert offending_python_lines(source) == []


def test_float_annotation_is_caught() -> None:
    assert len(offending_python_lines("def total(amount: float) -> None: ...")) == 1


def test_float_return_annotation_is_caught() -> None:
    assert offending_python_lines("def balance() -> float: ...")


def test_float_cast_is_caught() -> None:
    assert offending_python_lines("amount = float(row['amount'])")


def test_float_inside_a_generic_is_caught() -> None:
    assert offending_python_lines("amounts: list[float] = []")


def test_prose_mentioning_float_is_not_flagged() -> None:
    """The gate must not flag documentation of its own rule — an earlier version did."""
    source = '"""Money is `decimal.Decimal`, never `float` (ADR-0005)."""\n'
    assert offending_python_lines(source) == []


def test_comment_mentioning_float_is_not_flagged() -> None:
    assert offending_python_lines("# never use float for money\nx = 1\n") == []


def test_a_string_containing_float_is_not_flagged() -> None:
    assert offending_python_lines('message = "no float allowed"\n') == []


def test_identifier_containing_float_is_not_flagged() -> None:
    assert offending_python_lines("floating_holiday = 3\n") == []


def test_not_money_marker_permits_a_genuine_non_monetary_float() -> None:
    source = "def wait(timeout: float) -> None: ...  # not-money: seconds\n"
    assert offending_python_lines(source) == []
