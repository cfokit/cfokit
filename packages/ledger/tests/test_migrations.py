"""Migration discovery, and the guarantee that importing does not apply anything."""

from __future__ import annotations

from pathlib import Path

from cfokit.ledger.migrations import SQL_DIR, discover


def test_sql_directory_ships_inside_the_package() -> None:
    """The same files must be present in the container, on a laptop, and in CI."""
    assert SQL_DIR.parent.name == "migrations"
    assert SQL_DIR.is_dir()


def test_first_migration_is_discovered() -> None:
    """0001 establishes the core schema; discovery must find it in the package."""
    found = discover()
    assert [m.version for m in found] == ["0001"]
    assert found[0].name == "create-core-ledger"


def test_first_migration_declares_the_invariants() -> None:
    """The guarantees live in SQL, not only in the service layer (ADR-0006, ADR-0007)."""
    sql = discover()[0].sql
    assert "DEFERRABLE INITIALLY DEFERRED" in sql, "zero-sum must be deferred (ADR-0006)"
    assert "assert_posted_transaction_balanced" in sql
    assert "append_only_violated" in sql
    assert "ENABLE ROW LEVEL SECURITY" in sql, "entity isolation is two-layer (ADR-0003)"


def test_every_decimal_column_is_numeric_28_10() -> None:
    """ADR-0005 fixes the scale; CI gate 4 catches float types, this catches the scale."""
    sql = discover()[0].sql
    assert sql.count("numeric(") == sql.count("numeric(28,10)"), (
        "every decimal column must be NUMERIC(28,10)"
    )


def test_transaction_carries_both_dates() -> None:
    """ADR-0013: recorded_at cannot be retrofitted, so it ships in the first migration."""
    sql = discover()[0].sql
    assert "transaction_date" in sql
    assert "recorded_at" in sql


def test_lot_shape_is_reserved_though_deferred() -> None:
    """LED-18 defers lots but reserves the columns, to avoid a later migration."""
    sql = discover()[0].sql
    assert "cost_amount" in sql
    assert "lot_id" in sql


def test_missing_directory_is_not_an_error(tmp_path: Path) -> None:
    assert discover(tmp_path / "absent") == []


def test_migrations_are_ordered_lexically(tmp_path: Path) -> None:
    for name in ("0010-later.sql", "0002-earlier.sql", "0001-first.sql"):
        (tmp_path / name).write_text("SELECT 1;", encoding="utf-8")

    found = discover(tmp_path)

    assert [m.version for m in found] == ["0001", "0002", "0010"]
    assert [m.name for m in found] == ["first", "earlier", "later"]


def test_migration_exposes_its_sql(tmp_path: Path) -> None:
    (tmp_path / "0001-create-entity.sql").write_text(
        "CREATE TABLE entity (id BIGSERIAL PRIMARY KEY);", encoding="utf-8"
    )

    (migration,) = discover(tmp_path)

    assert migration.sql.startswith("CREATE TABLE entity")


def test_non_sql_files_are_ignored(tmp_path: Path) -> None:
    (tmp_path / ".gitkeep").write_text("notes", encoding="utf-8")
    (tmp_path / "README.md").write_text("notes", encoding="utf-8")
    assert discover(tmp_path) == []
