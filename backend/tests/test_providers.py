import pytest

from app.providers import DuckDBProvider, UnsafeQueryError, validate_read_only_sql


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM sales",
        "select category from sales;",
        "WITH t AS (SELECT 1 AS x) SELECT x FROM t",
        "SELECT * FROM sales WHERE product = 'drop table; delete'",
        "-- comment\nSELECT 1",
    ],
)
def test_validator_accepts_reads(sql):
    validate_read_only_sql(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "",
        "DROP TABLE sales",
        "DELETE FROM sales",
        "SELECT 1; DROP TABLE sales",
        "UPDATE sales SET quantity = 0",
        "WITH x AS (DELETE FROM sales RETURNING *) SELECT * FROM x",
        "ATTACH 'other.duckdb'",
        "/* hi */ INSERT INTO sales VALUES (7,'a','b',1,1,2024)",
    ],
)
def test_validator_rejects_writes(sql):
    with pytest.raises(UnsafeQueryError):
        validate_read_only_sql(sql)


def test_duckdb_provider_runs_query(temp_db):
    provider = DuckDBProvider()
    assert "sales" in provider.get_schema()
    result = provider.run_query(
        "SELECT category, SUM(quantity * unit_price) AS revenue "
        "FROM sales GROUP BY category ORDER BY category"
    )
    assert result["columns"] == ["category", "revenue"]
    assert result["rows"] == [["Electronics", 166000.0], ["Furniture", 36000.0]]
    assert result["truncated"] is False


def test_duckdb_provider_blocks_unsafe_sql(temp_db):
    with pytest.raises(UnsafeQueryError):
        DuckDBProvider().run_query("DROP TABLE sales")


# --- validator edge cases ---------------------------------------------------- #


@pytest.mark.parametrize(
    "sql, executable",
    [
        # Keywords inside quoted identifiers are not SQL.
        ('SELECT "set", "drop" FROM t', 'SELECT "set", "drop" FROM t'),
        # Comment markers inside strings are kept, not stripped.
        ("SELECT '--not a comment' AS a FROM t", "SELECT '--not a comment' AS a FROM t"),
        ("SELECT '/* x */' AS a", "SELECT '/* x */' AS a"),
        # Real comments become whitespace; one trailing semicolon is removed.
        ("SELECT 1 /* c */ AS a; -- done", "SELECT 1   AS a"),
        ("  select 1 ;  ", "select 1"),
        # Doubled quotes and backslashes not followed by a quote are unambiguous.
        ("SELECT 'it''s' AS a", "SELECT 'it''s' AS a"),
        ("SELECT 'C:\\data\\file' AS p", "SELECT 'C:\\data\\file' AS p"),
        ('SELECT "a""b" FROM t', 'SELECT "a""b" FROM t'),
    ],
)
def test_validator_executable_output(sql, executable):
    assert validate_read_only_sql(sql) == executable


@pytest.mark.parametrize(
    "sql",
    [
        # Snowflake reads \' as an escaped quote, DuckDB does not: rejected
        # because each engine would see a different statement boundary.
        "SELECT 'x\\'' ; DROP TABLE t; SELECT ''",
        "SELECT 'a\\', 1; DROP TABLE t; SELECT '1'",
        "SELECT 'unterminated",
        'SELECT "unterminated',
        "SELECT 1 /* unterminated",
        "SELECT 1;;",
        "SELECT 1; SELECT 2",
        ";",
        "-- only a comment",
        "/* only */ ;",
        "SELECT * INTO new_table FROM sales",
        "SELECT SYSTEM$CANCEL_ALL_QUERIES(1)",
        "SELECT system$abort_session(1)",
        "SELECT 1 FROM t WHERE x = 1 UNION SELECT 1 FROM t; UNDROP TABLE t",
        "SHOW TABLES",
        "EXPLAIN SELECT 1",
        "VALUES (1)",
    ],
)
def test_validator_rejects_edge_cases(sql):
    with pytest.raises(UnsafeQueryError):
        validate_read_only_sql(sql)


def test_validator_strings_cannot_hide_statements():
    sql = "SELECT 'a;b' AS x, \"c;d\" FROM t WHERE y = 'DROP TABLE t'"
    assert validate_read_only_sql(sql) == sql


# --- shared interface -------------------------------------------------------- #


def test_both_providers_implement_the_interface():
    from app.providers import DataProvider, SnowflakeProvider

    duck, snow = DuckDBProvider(), SnowflakeProvider()  # no credentials needed
    for provider in (duck, snow):
        assert isinstance(provider, DataProvider)
    # Validation, limits and conversion come from one shared implementation.
    assert type(duck).run_query is type(snow).run_query
    assert {duck.name, snow.name} == {"duckdb", "snowflake"}


def test_duckdb_schema_structure(temp_db):
    schema = DuckDBProvider().get_schema()
    assert schema["sales"][0] == {"name": "order_id", "type": "INTEGER", "nullable": False}
    assert all(set(c) == {"name", "type", "nullable"} for c in schema["sales"])
    assert all(c["nullable"] is False for c in schema["sales"])  # all NOT NULL


def test_duckdb_schema_reports_nullable_and_orders_tables(temp_db):
    import duckdb

    with duckdb.connect(str(temp_db.get_db_path())) as con:
        con.execute("CREATE TABLE aaa_notes (id INTEGER NOT NULL, note VARCHAR)")
    schema = DuckDBProvider().get_schema()
    assert list(schema) == ["aaa_notes", "sales"]
    assert schema["aaa_notes"] == [
        {"name": "id", "type": "INTEGER", "nullable": False},
        {"name": "note", "type": "VARCHAR", "nullable": True},
    ]


def test_duckdb_results_are_json_serializable(temp_db):
    import json

    result = DuckDBProvider().run_query(
        """
        SELECT 1.50::DECIMAL(10,2) AS amount, 7::DECIMAL(10,0) AS whole,
               DATE '2024-01-02' AS d, TIMESTAMP '2024-01-02 03:04:05' AS ts,
               INTERVAL 90 MINUTE AS iv, '\\xAA'::BLOB AS b,
               '12345678-1234-5678-1234-567812345678'::UUID AS u,
               [1, 2] AS l, {'k': 1.5::DECIMAL(3,1)} AS s, NULL AS n,
               'nan'::DOUBLE AS bad
        """
    )
    assert result["rows"] == [
        [1.5, 7, "2024-01-02", "2024-01-02T03:04:05", 5400.0, "aa",
         "12345678-1234-5678-1234-567812345678", [1, 2], {"k": 1.5}, None, "NaN"]
    ]
    json.dumps(result, allow_nan=False)


def test_duckdb_row_limit(temp_db):
    from app.providers import MAX_ROWS

    result = DuckDBProvider().run_query(f"SELECT * FROM range({MAX_ROWS + 5})")
    assert len(result["rows"]) == MAX_ROWS and result["truncated"] is True
    exact = DuckDBProvider().run_query(f"SELECT * FROM range({MAX_ROWS})")
    assert len(exact["rows"]) == MAX_ROWS and exact["truncated"] is False


def test_duckdb_query_connection_blocks_file_access(temp_db, tmp_path):
    import duckdb

    secret = tmp_path / "outside.csv"
    secret.write_text("a\n1\n")
    with pytest.raises(duckdb.Error, match="(?i)permission|external"):
        DuckDBProvider().run_query(f"SELECT * FROM read_csv('{secret.as_posix()}')")


def test_duckdb_query_connection_config_is_locked(temp_db):
    import duckdb

    with temp_db._connect(read_only=True) as con:
        with pytest.raises(duckdb.Error):
            con.execute("SET enable_external_access = true")


# --- error codes and location ------------------------------------------------ #


@pytest.mark.parametrize(
    "sql, code, refusal",
    [
        ("DROP TABLE sales", "not_select", True),
        ("SELECT 1; SELECT 2", "multiple_statements", True),
        ("SELECT * FROM t WHERE x IN (DELETE)", "forbidden_keyword", True),
        ("SELECT 'open", "syntax", False),
        ("SELECT 1 /* open", "syntax", False),
        ("", "empty", False),
    ],
)
def test_validator_error_codes(sql, code, refusal):
    with pytest.raises(UnsafeQueryError) as err:
        validate_read_only_sql(sql)
    assert err.value.code == code
    assert err.value.is_refusal is refusal


def test_duckdb_location(temp_db):
    assert DuckDBProvider().location() == {"database": "test", "schema": "main"}


def test_duckdb_result_has_no_provider_query_id(temp_db):
    assert "provider_query_id" not in DuckDBProvider().run_query("SELECT 1")
