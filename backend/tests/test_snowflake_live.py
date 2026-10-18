"""Opt-in tests against a REAL Snowflake account.

Skipped unless DATAMIND_SNOWFLAKE_LIVE=1 and the SNOWFLAKE_* variables are set.
These are the only tests that verify actual Snowflake connectivity.
"""

import os

import pytest

from app.providers import SnowflakeProvider, UnsafeQueryError

pytestmark = pytest.mark.skipif(
    os.environ.get("DATAMIND_SNOWFLAKE_LIVE") != "1",
    reason="Set DATAMIND_SNOWFLAKE_LIVE=1 to run live Snowflake tests.",
)


@pytest.fixture(scope="module")
def provider():
    return SnowflakeProvider()


def test_live_session_uses_configured_role(provider):
    result = provider.run_query("SELECT CURRENT_ROLE(), CURRENT_WAREHOUSE()")
    role, warehouse = result["rows"][0]
    assert role == provider.settings.role.upper()
    assert warehouse == provider.settings.warehouse.upper()


def test_live_schema_has_sales(provider):
    schema = provider.get_schema()
    assert "SALES" in schema
    names = [c["name"] for c in schema["SALES"]]
    assert names == ["ORDER_ID", "PRODUCT", "CATEGORY", "QUANTITY", "UNIT_PRICE", "YEAR"]


def test_live_category_revenue(provider):
    result = provider.run_query(
        "SELECT category, SUM(quantity * unit_price) AS revenue "
        "FROM sales GROUP BY category ORDER BY category"
    )
    assert [[c, float(r)] for c, r in result["rows"]] == [
        ["Electronics", 166000.0],
        ["Furniture", 36000.0],
    ]


def test_live_validator_blocks_writes(provider):
    with pytest.raises(UnsafeQueryError):
        provider.run_query("DELETE FROM sales")
