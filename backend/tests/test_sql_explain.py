from app.sql_explain import explain_sql, summarize


def test_aggregation_with_group_and_order():
    e = explain_sql(
        "SELECT CATEGORY, SUM(QUANTITY * UNIT_PRICE) AS TOTAL_REVENUE FROM SALES "
        "GROUP BY CATEGORY ORDER BY TOTAL_REVENUE DESC",
        "snowflake", 1000,
    )
    assert e.parsed and e.tables == ["SALES"] and e.filters == []
    assert "TOTAL_REVENUE = SUM(QUANTITY * UNIT_PRICE)" in e.assumptions
    assert "Grouped by CATEGORY" in e.assumptions
    assert "Sorted by TOTAL_REVENUE descending" in e.assumptions
    assert e.assumptions[-1] == "At most 1000 rows are returned."


def test_filters_split_on_and_including_having():
    e = explain_sql(
        "SELECT product FROM sales WHERE year = 2025 AND (category = 'Electronics' AND quantity > 1) "
        "GROUP BY product HAVING SUM(quantity) > 2",
        "duckdb", 1000,
    )
    assert e.filters == ["year = 2025", "category = 'Electronics'", "quantity > 1", "HAVING SUM(quantity) > 2"]


def test_or_conditions_stay_together():
    e = explain_sql("SELECT * FROM sales WHERE year = 2024 OR year = 2025", "duckdb", 1000)
    assert e.filters == ["year = 2024 OR year = 2025"]


def test_joins_and_ctes_report_only_real_tables():
    e = explain_sql(
        "WITH spend AS (SELECT o.customer_id, SUM(i.quantity) AS units FROM orders o "
        "JOIN order_items i ON o.order_id = i.order_id GROUP BY o.customer_id) "
        "SELECT c.name, s.units FROM spend s JOIN customers c ON c.customer_id = s.customer_id "
        "ORDER BY s.units DESC LIMIT 1",
        "duckdb", 1000,
    )
    assert sorted(e.tables) == ["customers", "order_items", "orders"]  # CTE "spend" is not a table
    assert "Joined customers AS c on c.customer_id = s.customer_id" in e.assumptions
    assert "Joined order_items AS i on o.order_id = i.order_id" in e.assumptions  # join inside the CTE
    assert "Only the first 1 row(s) are shown (LIMIT)" in e.assumptions


def test_qualified_table_names():
    e = explain_sql("SELECT COUNT(*) FROM SNOWFLAKE_SAMPLE_DATA.TPCH_SF1.REGION", "snowflake", 1000)
    assert e.tables == ["SNOWFLAKE_SAMPLE_DATA.TPCH_SF1.REGION"]
    assert "COUNT(*) = COUNT(*)" in e.assumptions


def test_plain_columns_are_not_listed_as_calculations():
    e = explain_sql("SELECT product, category FROM sales", "duckdb", 50)
    assert e.assumptions == ["At most 50 rows are returned."]


def test_distinct():
    assert "Duplicate rows removed (DISTINCT)" in explain_sql("SELECT DISTINCT category FROM sales", "duckdb", 9).assumptions


def test_unparseable_sql_degrades_honestly():
    e = explain_sql("SELECT FROM WHERE (", "duckdb", 1000)
    assert e.parsed is False and e.tables == [] and e.filters == []
    assert "could not be analysed" in summarize(e, 0, False)


def test_summary_is_factual():
    e = explain_sql("SELECT * FROM sales WHERE year = 2025", "duckdb", 1000)
    assert summarize(e, 3, False) == "Read sales with 1 filter and returned 3 rows."
    assert summarize(explain_sql("SELECT 1", "duckdb", 1000), 1, False) == "Read no table with no filters and returned 1 row."
    assert "more than the 1000 rows shown" in summarize(e, 1000, True)
