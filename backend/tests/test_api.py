"""API tests for the frontend contract. No Snowflake account or model needed."""

import datetime as dt
import json
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.api import MODEL_UNAVAILABLE_MESSAGE, create_app
from app.providers import MAX_ROWS, DuckDBProvider, SnowflakeProvider, SnowflakeSettings

SNOWFLAKE_ENV = {
    "SNOWFLAKE_ACCOUNT": "myorg-myacct",
    "SNOWFLAKE_USER": "datamind_svc",
    "SNOWFLAKE_ROLE": "DATAMIND_READONLY",
    "SNOWFLAKE_WAREHOUSE": "DATAMIND_WH",
    "SNOWFLAKE_DATABASE": "DATAMIND",
    "SNOWFLAKE_SCHEMA": "PUBLIC",
    "SNOWFLAKE_PASSWORD": "pw-secret-value",
}
SECRET = "pw-secret-value"

REVENUE_SQL = (
    "SELECT category, SUM(quantity * unit_price) AS revenue "
    "FROM sales GROUP BY category ORDER BY category"
)


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    monkeypatch.setenv("DATAMIND_DUCKDB_PATH", str(tmp_path / "api.duckdb"))
    for var in list(SNOWFLAKE_ENV) + ["SNOWFLAKE_PRIVATE_KEY_PATH", "DATAMIND_PROVIDER"]:
        monkeypatch.delenv(var, raising=False)


def make_client(**kwargs):
    kwargs.setdefault("health_cache_seconds", 0)
    kwargs.setdefault("env", {})
    return TestClient(create_app(**kwargs))


@pytest.fixture
def client():
    with make_client() as c:  # context manager runs startup (DuckDB seed)
        yield c


def ask(client, question, **extra):
    res = client.post("/api/query", json={"question": question, **extra})
    return res.status_code, res.json()


# --- fakes for a Snowflake connection (no network) ------------------------- #


class FakeSnowflakeCursor:
    sfqid = "01b2c3d4-0000-1111-2222-333344445555"

    def __init__(self, conn):
        self.conn, self.description, self._rows = conn, None, []

    def execute(self, sql, params=None):
        self.conn.executed.append(sql)
        if self.conn.fail_with and not sql.startswith("ALTER SESSION"):
            raise self.conn.fail_with
        if "information_schema" in sql:
            self._rows = [("SALES", "AMOUNT", "NUMBER", "YES")]
        elif not sql.startswith("ALTER SESSION"):
            self.description = [("REGION",), ("REVENUE",), ("DAY",)]
            self._rows = [("EUROPE", Decimal("43750214321.47"), dt.date(1998, 8, 2))]
        return self

    def fetchall(self):
        return self._rows

    def fetchmany(self, size):
        return self._rows[:size]


class FakeSnowflakeConnection:
    def __init__(self, fail_with=None):
        self.fail_with, self.executed, self.closed = fail_with, [], False

    def cursor(self):
        return FakeSnowflakeCursor(self)

    def close(self):
        self.closed = True


def fake_snowflake(fail_with=None):
    conn = FakeSnowflakeConnection(fail_with)
    settings = SnowflakeSettings.from_env(SNOWFLAKE_ENV)
    return SnowflakeProvider(settings, connect=lambda **_: conn), conn


# --- /api/health ------------------------------------------------------------ #


def test_health_reports_real_connectivity(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["row_limit"] == MAX_ROWS
    duck, snow = body["providers"]
    assert duck == {
        "id": "duckdb", "label": "DuckDB (local)", "connected": True,
        "is_default": True, "database": "api", "schema": "main",
    }
    assert snow["id"] == "snowflake" and snow["connected"] is False
    assert "Not configured" in snow["detail"]
    assert body["model"]["available"] is False
    # DuckDB works but Gemma is unavailable, so the backend is not fully "ok".
    assert body["status"] == "degraded"


def test_health_down_when_no_provider_connects():
    class Broken(DuckDBProvider):
        def run_query(self, sql):
            raise RuntimeError("boom")

    with make_client(providers={"duckdb": Broken()}, initialize_duckdb=False) as c:
        body = c.get("/api/health").json()
    assert body["status"] == "down"
    assert body["providers"][0]["connected"] is False


def test_health_snowflake_connected_via_select_1():
    provider, conn = fake_snowflake()
    with make_client(providers={"duckdb": DuckDBProvider(), "snowflake": provider}) as c:
        snow = c.get("/api/health").json()["providers"][1]
    assert snow["connected"] is True
    assert snow["database"] == "DATAMIND" and snow["warehouse"] == "DATAMIND_WH"
    assert "SELECT 1" in conn.executed


def test_health_never_leaks_secrets():
    provider, _ = fake_snowflake(fail_with=RuntimeError("login failed for myorg-myacct.snowflakecomputing.com:443"))
    with make_client(providers={"duckdb": DuckDBProvider(), "snowflake": provider}) as c:
        text = c.get("/api/health").text
    assert SECRET not in text
    assert "snowflakecomputing.com" not in text


def test_health_checks_are_cached():
    calls = []

    class Counting(DuckDBProvider):
        def run_query(self, sql):
            calls.append(sql)
            return super().run_query(sql)

    with make_client(providers={"duckdb": Counting()}, health_cache_seconds=60) as c:
        c.get("/api/health")
        c.get("/api/health")
    assert calls == ["SELECT 1"]


# --- CORS -------------------------------------------------------------------- #


def test_cors_allows_local_frontend(client):
    res = client.options(
        "/api/query",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST",
                 "Access-Control-Request-Headers": "content-type"},
    )
    assert res.status_code == 200
    assert res.headers["access-control-allow-origin"] == "http://localhost:3000"
    get = client.get("/api/health", headers={"Origin": "http://localhost:3000"})
    assert get.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_cors_rejects_other_origins(client):
    res = client.get("/api/health", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in res.headers


def test_cors_origins_configurable():
    with make_client(env={"DATAMIND_CORS_ORIGINS": "http://localhost:5173/"}) as c:
        res = c.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert res.headers["access-control-allow-origin"] == "http://localhost:5173"


# --- /api/schema ------------------------------------------------------------- #


def test_schema_contract_shape(client):
    res = client.get("/api/schema", params={"provider": "duckdb"})
    assert res.status_code == 200
    body = res.json()
    assert body["provider"] == "duckdb" and body["database"] == "api"
    [schema] = body["schemas"]
    assert schema["name"] == "main"
    [table] = schema["tables"]
    assert table["name"] == "sales"
    assert table["columns"][0] == {"name": "order_id", "data_type": "INTEGER", "nullable": False}
    assert [c["name"] for c in table["columns"]] == [
        "order_id", "product", "category", "quantity", "unit_price", "year"
    ]


def test_schema_defaults_to_default_provider(client):
    assert client.get("/api/schema").json()["provider"] == "duckdb"


def test_schema_unknown_provider(client):
    res = client.get("/api/schema", params={"provider": "postgres"})
    assert res.status_code == 400


def test_schema_unconfigured_snowflake(client):
    res = client.get("/api/schema", params={"provider": "snowflake"})
    assert res.status_code == 503
    assert "not configured" in res.json()["detail"]


def test_schema_snowflake_fake():
    provider, conn = fake_snowflake()
    with make_client(providers={"duckdb": DuckDBProvider(), "snowflake": provider}) as c:
        body = c.get("/api/schema", params={"provider": "snowflake"}).json()
    assert body["database"] == "DATAMIND"
    assert body["schemas"][0]["name"] == "PUBLIC"
    assert body["schemas"][0]["tables"][0]["columns"] == [
        {"name": "AMOUNT", "data_type": "NUMBER", "nullable": True}
    ]
    assert conn.closed


# --- /api/query: success ------------------------------------------------------ #


def test_query_direct_sql_executes_on_duckdb(client):
    status, body = ask(client, REVENUE_SQL)
    assert status == 200
    assert body["status"] == "success"
    assert body["executed"] is True
    assert body["provider"] == "duckdb"
    assert body["sql"] == REVENUE_SQL
    assert body["columns"] == [{"name": "category"}, {"name": "revenue"}]
    assert body["rows"] == [["Electronics", 166000.0], ["Furniture", 36000.0]]
    assert body["row_count"] == 2 and body["truncated"] is False
    assert body["validation"] == {"passed": True, "read_only": True, "limit_applied": MAX_ROWS, "messages": []}
    assert body["execution"]["duration_ms"] >= 0
    assert body["execution"]["started_at"].endswith("Z")
    assert body["execution"]["database"] == "api"
    assert body["answer"] == "The query returned 2 rows."
    assert "No language model was used" in body["explanation"]["summary"]
    assert any("Direct SQL mode" in w for w in body["warnings"])
    assert "model" not in body  # no model was involved
    assert body["query_id"].startswith("q_")


def test_query_ids_are_unique(client):
    ids = {ask(client, "SELECT 1")[1]["query_id"] for _ in range(5)}
    assert len(ids) == 5


def test_query_zero_rows(client):
    _, body = ask(client, "SELECT * FROM sales WHERE year = 1900")
    assert body["status"] == "success" and body["executed"] is True
    assert body["rows"] == [] and body["row_count"] == 0
    assert body["answer"] == "The query ran and returned no rows."


def test_query_truncation_omits_unknown_total(client):
    _, body = ask(client, f"SELECT * FROM range({MAX_ROWS + 5})")
    assert body["status"] == "success"
    assert len(body["rows"]) == MAX_ROWS and body["truncated"] is True
    assert "row_count" not in body  # true total is unknown, so it is not invented


def test_query_values_are_json_normalized(client):
    _, body = ask(
        client,
        "SELECT 12.50::DECIMAL(10,2) AS amount, DATE '2024-01-02' AS d, "
        "TIMESTAMP '2024-01-02 03:04:05' AS ts, NULL AS n",
    )
    assert body["rows"] == [[12.5, "2024-01-02", "2024-01-02T03:04:05", None]]


def test_query_leading_comment_still_direct_sql(client):
    _, body = ask(client, "-- revenue\nSELECT 1 AS one")
    assert body["status"] == "success" and body["rows"] == [[1]]


def test_query_snowflake_fake_success():
    provider, conn = fake_snowflake()
    with make_client(providers={"duckdb": DuckDBProvider(), "snowflake": provider}) as c:
        _, body = ask(c, "SELECT region, revenue, day FROM t", provider="snowflake")
    assert body["status"] == "success" and body["provider"] == "snowflake"
    assert body["rows"] == [["EUROPE", 43750214321.47, "1998-08-02"]]
    assert body["execution"]["provider_query_id"] == FakeSnowflakeCursor.sfqid
    assert body["execution"]["warehouse"] == "DATAMIND_WH"
    assert conn.closed


# --- /api/query: model unavailable -------------------------------------------- #


@pytest.mark.parametrize(
    "question",
    ["Which category has the most revenue?", "show me sales by year", "DROP TABLE sales"],
)
def test_natural_language_reports_model_unavailable(client, question):
    status, body = ask(client, question)
    assert status == 200
    assert body["status"] == "error"
    assert body["error"] == {"stage": "generation", "code": "model_unavailable", "message": MODEL_UNAVAILABLE_MESSAGE}
    assert body["executed"] is False
    for absent in ("sql", "rows", "answer", "model"):
        assert absent not in body


def test_direct_sql_can_be_disabled():
    with make_client(allow_direct_sql=False) as c:
        _, body = ask(c, "SELECT 1")
    assert body["error"]["code"] == "model_unavailable"
    assert body["executed"] is False


def test_direct_sql_env_toggle():
    with make_client(env={"DATAMIND_ALLOW_DIRECT_SQL": "false"}) as c:
        assert ask(c, "SELECT 1")[1]["error"]["code"] == "model_unavailable"


# --- /api/query: unsafe SQL ----------------------------------------------------- #


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1; DROP TABLE sales",
        "SELECT * INTO copy_of_sales FROM sales",
        "WITH x AS (DELETE FROM sales RETURNING *) SELECT * FROM x",
        "SELECT SYSTEM$CANCEL_ALL_QUERIES(1)",
    ],
)
def test_unsafe_sql_is_refused_and_not_executed(client, sql):
    status, body = ask(client, sql)
    assert status == 200
    assert body["status"] == "refused"
    assert body["executed"] is False
    assert body["validation"]["passed"] is False
    assert body["validation"]["messages"]
    assert body["sql"] == sql
    assert "rows" not in body
    # The table is untouched.
    assert ask(client, "SELECT COUNT(*) FROM sales")[1]["rows"] == [[6]]


def test_malformed_sql_is_validation_error(client):
    _, body = ask(client, "SELECT 'unterminated")
    assert body["status"] == "error"
    assert body["error"]["stage"] == "validation" and body["error"]["code"] == "syntax"
    assert body["executed"] is False


# --- /api/query: database errors ------------------------------------------------ #


def test_database_error_is_execution_error(client):
    status, body = ask(client, "SELECT * FROM missing_table")
    assert status == 200
    assert body["status"] == "error"
    assert body["error"]["stage"] == "execution" and body["error"]["code"] == "execution_failed"
    assert "missing_table" in body["error"]["message"]
    assert body["executed"] is False
    assert body["sql"] == "SELECT * FROM missing_table"
    assert "rows" not in body


def test_snowflake_not_configured(client):
    _, body = ask(client, "SELECT 1", provider="snowflake")
    assert body["error"]["stage"] == "execution"
    assert body["error"]["code"] == "provider_not_configured"
    assert body["executed"] is False


def test_snowflake_error_is_sanitized():
    from snowflake.connector.errors import ProgrammingError

    err = ProgrammingError(
        msg="SQL compilation error: invalid identifier 'X' at myorg-myacct.snowflakecomputing.com:443"
    )
    provider, conn = fake_snowflake(fail_with=err)
    with make_client(providers={"duckdb": DuckDBProvider(), "snowflake": provider}) as c:
        res = c.post("/api/query", json={"question": "SELECT x FROM t", "provider": "snowflake"})
    body = res.json()
    assert body["error"]["code"] == "execution_failed"
    assert "invalid identifier" in body["error"]["message"]
    assert "snowflakecomputing.com" not in res.text
    assert SECRET not in res.text
    assert conn.closed


def test_unexpected_failure_is_internal_500_without_details():
    class Buggy(DuckDBProvider):
        def run_query(self, sql):
            if sql == "SELECT 1":
                return super().run_query(sql)
            raise KeyError("secret internal detail")

    with make_client(providers={"duckdb": Buggy()}) as c:
        res = c.post("/api/query", json={"question": "SELECT 2"})
    assert res.status_code == 500
    body = res.json()
    assert body["status"] == "error" and body["error"]["stage"] == "internal"
    assert body["executed"] is False
    assert "secret internal detail" not in res.text


def test_unknown_provider_in_query(client):
    status, body = ask(client, "SELECT 1", provider="postgres")
    assert status == 200
    assert body["error"]["code"] == "unknown_provider"
    assert body["executed"] is False


def test_blank_provider_uses_default(client):
    assert ask(client, "SELECT 1", provider="  ")[1]["provider"] == "duckdb"


# --- /api/query: invalid input ----------------------------------------------------- #


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"question": ""},
        {"question": "   \n  "},
        {"question": "x" * 1001},
        {"question": 123},
        {"question": None},
        {"question": "SELECT 1", "provider": "p" * 65},
        {"question": "SELECT 1", "provider": 5},
    ],
)
def test_invalid_request_bodies_are_422(client, payload):
    res = client.post("/api/query", json=payload)
    assert res.status_code == 422
    assert "detail" in res.json()


def test_non_json_body_is_422(client):
    res = client.post("/api/query", content="not json", headers={"Content-Type": "application/json"})
    assert res.status_code == 422


def test_question_is_trimmed(client):
    _, body = ask(client, "   SELECT 1 AS one   ")
    assert body["question"] == "SELECT 1 AS one"
    assert body["status"] == "success"


def test_every_response_is_strict_json(client):
    for q in [REVENUE_SQL, "hello", "SELECT 1; DROP TABLE x", "SELECT * FROM nope", "SELECT 'nan'::DOUBLE"]:
        res = client.post("/api/query", json={"question": q})
        json.loads(res.text, parse_constant=lambda c: pytest.fail(f"non-JSON constant {c}"))
