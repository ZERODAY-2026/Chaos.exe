"""Local DuckDB development database for DataMind.

DuckDB is a development substitute only. The final PS1 submission must run
against Snowflake (see backend/README.md).

The database file lives inside the project root (``data/datamind_dev.duckdb``)
and is ignored by Git. Set ``DATAMIND_DUCKDB_PATH`` to use a different file
(the tests do this so they never touch your dev database).
"""

from __future__ import annotations

import os
from pathlib import Path

import duckdb

from .results import Schema, build_schema

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "datamind_dev.duckdb"

SALES_DDL = """
CREATE TABLE IF NOT EXISTS sales (
    order_id   INTEGER PRIMARY KEY,
    product    VARCHAR NOT NULL,
    category   VARCHAR NOT NULL,
    quantity   INTEGER NOT NULL,
    unit_price DOUBLE  NOT NULL,
    year       INTEGER NOT NULL
)
"""

# Deterministic synthetic rows.
# Electronics revenue: 100000 + 60000 + 6000 = 166000
# Furniture revenue:    24000 + 10000 + 2000 =  36000
SAMPLE_SALES = [
    (1, "Laptop", "Electronics", 2, 50000.0, 2024),
    (2, "Smartphone", "Electronics", 3, 20000.0, 2025),
    (3, "Headphones", "Electronics", 4, 1500.0, 2025),
    (4, "Desk", "Furniture", 2, 12000.0, 2024),
    (5, "Chair", "Furniture", 4, 2500.0, 2025),
    (6, "Lamp", "Furniture", 2, 1000.0, 2024),
]


def get_db_path() -> Path:
    """Return the DuckDB file path, honouring ``DATAMIND_DUCKDB_PATH``."""
    override = os.environ.get("DATAMIND_DUCKDB_PATH")
    return Path(override) if override else DEFAULT_DB_PATH


# Query-only connections also cannot touch local files, URLs or other
# databases (read_csv, httpfs, ATTACH, ...) and cannot re-enable that access.
_READ_ONLY_CONFIG = {"enable_external_access": False, "lock_configuration": True}


def _connect(read_only: bool) -> duckdb.DuckDBPyConnection:
    if read_only:
        return duckdb.connect(
            str(get_db_path()), read_only=True, config=dict(_READ_ONLY_CONFIG)
        )
    return duckdb.connect(str(get_db_path()), read_only=False)


def initialize_database() -> None:
    """Create the ``sales`` table and seed it only if it is empty.

    Safe to call repeatedly: rows are never duplicated.
    """
    path = get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with _connect(read_only=False) as con:
        con.execute(SALES_DDL)
        (count,) = con.execute("SELECT COUNT(*) FROM sales").fetchone()
        if count == 0:
            con.executemany(
                "INSERT INTO sales VALUES (?, ?, ?, ?, ?, ?)", SAMPLE_SALES
            )


def get_schema() -> Schema:
    """Return the user tables in the shared ``Schema`` format (see ``results``)."""
    with _connect(read_only=True) as con:
        rows = con.execute(
            """
            SELECT table_name, column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = 'main'
            ORDER BY table_name, ordinal_position
            """
        ).fetchall()
    return build_schema(rows)


def get_category_revenue() -> dict[str, float]:
    """Return total revenue (quantity * unit_price) per category."""
    with _connect(read_only=True) as con:
        rows = con.execute(
            """
            SELECT category, SUM(quantity * unit_price) AS revenue
            FROM sales
            GROUP BY category
            ORDER BY category
            """
        ).fetchall()
    return {category: float(revenue) for category, revenue in rows}
