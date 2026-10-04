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


# --- float literals, rejected under src/ only --------------------------------------------


def test_a_float_literal_is_caught_when_literals_are_rejected() -> None:
    """`Decimal(0.1)` names no `float`, so the Name walk cannot see it. CLAUDE.md forbids it by
    name: it carries the binary expansion into the type chosen to avoid it."""
    assert len(offending_python_lines("amount = Decimal(0.1)", literals=True)) == 1


def test_a_float_literal_is_allowed_by_default() -> None:
    """A fixture modeling a foreign file format legitimately holds one: an .xlsx cell is an
    IEEE double, so the faithful fixture carries the float. The default is what runs over
    tests/."""
    assert offending_python_lines("cell = 647.75") == []


def test_a_decimal_from_a_string_is_not_a_literal() -> None:
    """The correction the gate exists to push people toward must itself pass."""
    assert offending_python_lines('amount = Decimal("0.1")', literals=True) == []


def test_an_integer_is_not_a_float_literal() -> None:
    assert offending_python_lines("scale = 10", literals=True) == []


def test_a_bool_is_not_a_float_literal() -> None:
    """`bool` subclasses `int` and never `float`, but a naive isinstance check on a numeric
    constant is the kind that catches `True`."""
    assert offending_python_lines("posted = True", literals=True) == []
