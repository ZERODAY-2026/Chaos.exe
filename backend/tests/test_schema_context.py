"""Schema context: real metadata only, clearly separated from inferred hints.

Each test targets a failure measured in the evaluation (see backend/eval/README.md).
"""

import pytest

from app.providers import DuckDBProvider
from app.schema_context import (
    Relationship,
    build_context,
    declared_relationships,
    inferred_relationships,
    measure_hints,
)
from eval.datasets import build_dataset


@pytest.fixture(scope="module")
def retail(tmp_path_factory):
    path = build_dataset("retail", tmp_path_factory.mktemp("ctx"))
    provider = DuckDBProvider(db_path=path)
    return provider, build_context(provider, provider.get_schema())


@pytest.fixture(scope="module")
def sales(tmp_path_factory):
    path = build_dataset("sales", tmp_path_factory.mktemp("ctx"))
    provider = DuckDBProvider(db_path=path)
    return provider, build_context(provider, provider.get_schema())


def test_declared_foreign_keys_come_from_the_database(retail):
    provider, ctx = retail
    declared = [r.text() for r in ctx.relationships if r.declared]
    assert sorted(declared) == [
        "order_items.order_id -> orders.order_id",
        "order_items.product_id -> products.product_id",
        "orders.customer_id -> customers.customer_id",
    ]
    assert "Declared foreign keys (join on these):" in ctx.text
    # Nothing is inferred when the database already declares every key.
    assert not [r for r in ctx.relationships if not r.declared]
    assert "inferred" not in ctx.text


def test_columns_are_listed_under_their_own_table(retail):
    """R02/R03/R08: the model used order_items.unit_price, orders.product_id, order_items.status."""
    _, ctx = retail
    blocks = {}
    current = None
    for line in ctx.text.splitlines():
        if line.startswith("TABLE "):
            current = line[6:]
            blocks[current] = []
        elif line.startswith("  - ") and current and not line.startswith("  - order_items.") and "->" not in line:
            blocks[current].append(line.split()[1])
    assert "unit_price" in blocks["products"] and "unit_price" not in blocks["order_items"]
    assert "product_id" in blocks["order_items"] and "product_id" not in blocks["orders"]
    assert "status" in blocks["orders"] and "status" not in blocks["order_items"]


def test_example_values_give_exact_filter_spellings(retail, sales):
    """S08/S10/R07/R08: 'Furniture' used as a product, 'Monitors', 'Notebook' as category, 'Cancelled'."""
    _, r = retail
    _, s = sales
    assert r.values[("orders", "status")] == ["cancelled", "completed"]
    assert "Notebook" in r.values[("products", "name")]
    assert r.values[("products", "category")] == ["Electronics", "Furniture", "Stationery"]
    assert s.values[("sales", "category")] == ["Electronics", "Furniture"]
    assert "Monitor" not in s.values[("sales", "product")]  # the honest answer to S10 is empty


def test_measure_hints_from_column_names(retail, sales):
    """S01/S02/S04/S09/R04: revenue computed as SUM(price), units as COUNT."""
    _, s = sales
    _, r = retail
    assert "revenue / sales amount / money spent = SUM(sales.quantity * sales.unit_price)" in s.measures
    assert "units / items sold = SUM(sales.quantity), not COUNT" in s.measures
    assert any(m.startswith("revenue / sales amount / money spent = SUM(order_items.quantity * "
                            "products.unit_price) (join order_items to products)") for m in r.measures)
    assert s.measure_options == {"revenue": True, "units": True, "orders": True}


def test_measure_hints_use_stored_amounts_and_never_invent_unit_prices():
    """TPC-H style: L_EXTENDEDPRICE is already an amount; no QUANTITY x PRICE formula is made up."""
    def cols(*names):
        return [{"name": n, "type": "NUMBER", "nullable": False} for n in names]

    schema = {"LINEITEM": cols("L_ORDERKEY", "L_QUANTITY", "L_EXTENDEDPRICE"),
              "ORDERS": cols("O_ORDERKEY", "O_TOTALPRICE"),
              "PART": cols("P_PARTKEY", "P_RETAILPRICE")}
    rels = inferred_relationships(schema, [])
    hints, options = measure_hints(schema, rels)
    assert "money amount column(s) already stored per row: LINEITEM.L_EXTENDEDPRICE, ORDERS.O_TOTALPRICE" in hints
    assert not any("* " in h and "PRICE)" in h and "QUANTITY *" in h for h in hints)
    assert options["revenue"] and options["units"]


def test_inferred_keys_are_labelled_and_skip_declared_pairs():
    def cols(*names):
        return [{"name": n, "type": "NUMBER", "nullable": False} for n in names]

    schema = {"CUSTOMER": cols("C_CUSTKEY", "C_NATIONKEY"), "ORDERS": cols("O_ORDERKEY", "O_CUSTKEY"),
              "NATION": cols("N_NATIONKEY")}
    inferred = inferred_relationships(schema, [])
    assert {r.text() for r in inferred} == {"ORDERS.O_CUSTKEY -> CUSTOMER.C_CUSTKEY",
                                            "CUSTOMER.C_NATIONKEY -> NATION.N_NATIONKEY"}
    assert all(not r.declared for r in inferred)
    declared = [Relationship("ORDERS", "O_CUSTKEY", "CUSTOMER", "C_CUSTKEY", True)]
    assert {r.text() for r in inferred_relationships(schema, declared)} == {
        "CUSTOMER.C_NATIONKEY -> NATION.N_NATIONKEY"}


def test_relationship_discovery_failure_is_harmless():
    class NoMetadata:
        def get_relationships(self):
            raise RuntimeError("SHOW not permitted")

    assert declared_relationships(NoMetadata()) == []
    assert declared_relationships(object()) == []


def test_value_discovery_uses_only_validated_read_only_queries(tmp_path):
    seen = []

    class Spy(DuckDBProvider):
        def run_query(self, sql):
            seen.append(sql)
            return super().run_query(sql)  # validate_read_only_sql runs inside

    provider = Spy(db_path=build_dataset("retail", tmp_path))
    build_context(provider, provider.get_schema())
    assert seen and all(q.startswith("SELECT ") for q in seen)
    assert len(seen) <= 2 * 4  # at most two queries per table
    assert all("LIMIT 10000" in q for q in seen)


def test_high_cardinality_columns_get_no_values(tmp_path):
    import duckdb

    path = tmp_path / "wide.duckdb"
    with duckdb.connect(str(path)) as con:
        con.execute("CREATE TABLE t (code VARCHAR, kind VARCHAR, note VARCHAR)")
        con.execute("INSERT INTO t SELECT 'c' || i::VARCHAR, CASE WHEN i % 2 = 0 THEN 'a' ELSE 'b' END, 'x' "
                    "FROM range(50) r(i)")
    provider = DuckDBProvider(db_path=path)
    ctx = build_context(provider, provider.get_schema())
    assert ("t", "code") not in ctx.values  # 50 distinct values: not listed
    assert ctx.values[("t", "kind")] == ["a", "b"]
    assert ("t", "note") not in ctx.values  # free-text style column names are skipped


def test_include_values_false_runs_no_value_queries(tmp_path):
    class Boom(DuckDBProvider):
        def run_query(self, sql):
            raise AssertionError("no value query expected")

    provider = Boom(db_path=build_dataset("sales", tmp_path))
    ctx = build_context(provider, provider.get_schema(), include_values=False)
    assert ctx.values == {} and "values:" not in ctx.text
