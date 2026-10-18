import duckdb
import pytest


def test_schema_discovery(temp_db):
    schema = temp_db.get_schema()
    assert list(schema) == ["sales"]
    columns = [c["name"] for c in schema["sales"]]
    assert columns == [
        "order_id",
        "product",
        "category",
        "quantity",
        "unit_price",
        "year",
    ]


def test_category_revenue_exact(temp_db):
    assert temp_db.get_category_revenue() == {
        "Electronics": 166000.0,
        "Furniture": 36000.0,
    }


def test_initialize_is_idempotent(temp_db):
    temp_db.initialize_database()
    temp_db.initialize_database()
    with duckdb.connect(str(temp_db.get_db_path()), read_only=True) as con:
        (count,) = con.execute("SELECT COUNT(*) FROM sales").fetchone()
    assert count == 6
    assert temp_db.get_category_revenue()["Electronics"] == 166000.0


def test_read_only_connection_rejects_writes(temp_db):
    with temp_db._connect(read_only=True) as con:
        with pytest.raises(duckdb.Error):
            con.execute("DELETE FROM sales")
