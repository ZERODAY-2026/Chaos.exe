"""Snowflake provider tests using fakes: no credentials, network, or account needed."""

import sys

import pytest

from app.providers import (
    MAX_ROWS,
    DuckDBProvider,
    SnowflakeConfigError,
    SnowflakeProvider,
    SnowflakeSettings,
    UnsafeQueryError,
    get_provider,
)

BASE_ENV = {
    "SNOWFLAKE_ACCOUNT": "myorg-myacct",
    "SNOWFLAKE_USER": "datamind_svc",
    "SNOWFLAKE_ROLE": "DATAMIND_READONLY",
    "SNOWFLAKE_WAREHOUSE": "DATAMIND_WH",
    "SNOWFLAKE_DATABASE": "DATAMIND",
    "SNOWFLAKE_SCHEMA": "public",
}


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.description = None
        self._rows = []

    def execute(self, sql, params=None):
        self.conn.executed.append((sql, params))
        if sql.startswith("ALTER SESSION"):
            return self
        if "information_schema.columns" in sql:
            self.description = [("TABLE_NAME",), ("COLUMN_NAME",), ("DATA_TYPE",)]
            self._rows = list(self.conn.schema_rows)
        else:
            self.description = [(c,) for c in self.conn.result_columns]
            self._rows = list(self.conn.result_rows)
        return self

    def fetchall(self):
        return list(self._rows)

    def fetchmany(self, size):
        self.conn.fetch_sizes.append(size)
        return [tuple(r) for r in self._rows[:size]]


class FakeConnection:
    def __init__(self, schema_rows=(), result_columns=(), result_rows=()):
        self.schema_rows = schema_rows
        self.result_columns = result_columns
        self.result_rows = result_rows
        self.executed = []
        self.fetch_sizes = []
        self.closed = False

    def cursor(self):
        return FakeCursor(self)

    def close(self):
        self.closed = True


class FakeConnect:
    def __init__(self, conn):
        self.conn = conn
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return self.conn


def password_settings():
    return SnowflakeSettings.from_env({**BASE_ENV, "SNOWFLAKE_PASSWORD": "pw-secret"})


# --- connection settings ---------------------------------------------------- #


def test_settings_from_env_password():
    s = password_settings()
    kwargs = s.connect_kwargs()
    for key in ("account", "user", "role", "warehouse", "database", "schema"):
        assert kwargs[key] == BASE_ENV[f"SNOWFLAKE_{key.upper()}"]
    assert kwargs["password"] == "pw-secret"
    assert "authenticator" not in kwargs
    assert "private_key" not in kwargs


def test_settings_repr_hides_secrets():
    text = repr(password_settings())
    assert "pw-secret" not in text


def test_settings_missing_vars_are_named_without_values():
    env = {k: v for k, v in BASE_ENV.items() if k != "SNOWFLAKE_ROLE"}
    env["SNOWFLAKE_USER"] = "   "
    env["SNOWFLAKE_PASSWORD"] = "pw-secret"
    with pytest.raises(SnowflakeConfigError) as err:
        SnowflakeSettings.from_env(env)
    message = str(err.value)
    assert "SNOWFLAKE_ROLE" in message and "SNOWFLAKE_USER" in message
    assert "pw-secret" not in message


def test_settings_require_an_auth_method():
    with pytest.raises(SnowflakeConfigError, match="PRIVATE_KEY_PATH"):
        SnowflakeSettings.from_env(BASE_ENV)


def _write_test_key(path, passphrase=None):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    encryption = (
        serialization.BestAvailableEncryption(passphrase.encode())
        if passphrase
        else serialization.NoEncryption()
    )
    path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            encryption,
        )
    )
    return key.private_bytes(
        serialization.Encoding.DER,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


@pytest.mark.parametrize("passphrase", [None, "key-pass"])
def test_settings_key_pair_auth_preferred(tmp_path, passphrase):
    key_file = tmp_path / "rsa_key.p8"
    expected_der = _write_test_key(key_file, passphrase)
    env = {
        **BASE_ENV,
        "SNOWFLAKE_PRIVATE_KEY_PATH": str(key_file),
        "SNOWFLAKE_PASSWORD": "ignored-when-key-set",
    }
    if passphrase:
        env["SNOWFLAKE_PRIVATE_KEY_PASSPHRASE"] = passphrase
    kwargs = SnowflakeSettings.from_env(env).connect_kwargs()
    assert kwargs["authenticator"] == "SNOWFLAKE_JWT"
    assert kwargs["private_key"] == expected_der
    assert "password" not in kwargs


def test_settings_key_wrong_passphrase(tmp_path):
    key_file = tmp_path / "rsa_key.p8"
    _write_test_key(key_file, "right")
    settings = SnowflakeSettings.from_env(
        {
            **BASE_ENV,
            "SNOWFLAKE_PRIVATE_KEY_PATH": str(key_file),
            "SNOWFLAKE_PRIVATE_KEY_PASSPHRASE": "wrong",
        }
    )
    with pytest.raises(SnowflakeConfigError, match="Could not load"):
        settings.connect_kwargs()


def test_settings_key_missing_file(tmp_path):
    settings = SnowflakeSettings.from_env(
        {**BASE_ENV, "SNOWFLAKE_PRIVATE_KEY_PATH": str(tmp_path / "nope.p8")}
    )
    with pytest.raises(SnowflakeConfigError, match="existing file"):
        settings.connect_kwargs()


# --- laziness --------------------------------------------------------------- #


def test_provider_is_lazy(monkeypatch):
    for var in list(BASE_ENV) + ["SNOWFLAKE_PASSWORD", "SNOWFLAKE_PRIVATE_KEY_PATH"]:
        monkeypatch.delenv(var, raising=False)
    sys.modules.pop("snowflake.connector", None)
    provider = SnowflakeProvider()  # no env, no connector import
    assert "snowflake.connector" not in sys.modules
    with pytest.raises(SnowflakeConfigError):
        provider.get_schema()


def test_unsafe_sql_rejected_before_connecting():
    connect = FakeConnect(FakeConnection())
    provider = SnowflakeProvider(password_settings(), connect=connect)
    for sql in ["DROP TABLE sales", "SELECT 1; DELETE FROM sales", "USE ROLE ACCOUNTADMIN"]:
        with pytest.raises(UnsafeQueryError):
            provider.run_query(sql)
    assert connect.calls == []


# --- schema discovery ------------------------------------------------------- #


def test_get_schema_groups_columns_and_closes():
    conn = FakeConnection(
        schema_rows=[
            ("SALES", "ORDER_ID", "NUMBER", "NO"),
            ("SALES", "PRODUCT", "TEXT", "YES"),
            ("STORES", "STORE_ID", "NUMBER", "NO"),
        ]
    )
    connect = FakeConnect(conn)
    schema = SnowflakeProvider(password_settings(), connect=connect).get_schema()
    assert schema == {
        "SALES": [
            {"name": "ORDER_ID", "type": "NUMBER", "nullable": False},
            {"name": "PRODUCT", "type": "TEXT", "nullable": True},
        ],
        "STORES": [{"name": "STORE_ID", "type": "NUMBER", "nullable": False}],
    }
    assert connect.calls[0]["password"] == "pw-secret"
    sql, params = conn.executed[-1]
    assert "information_schema.columns" in sql
    assert params == ("PUBLIC",)  # bound parameter, upper-cased
    assert conn.executed[0][0].startswith("ALTER SESSION SET STATEMENT_TIMEOUT")
    assert "MULTI_STATEMENT_COUNT = 1" in conn.executed[0][0]
    assert conn.closed


def test_get_schema_closes_connection_on_error():
    class BoomCursor(FakeCursor):
        def execute(self, sql, params=None):
            if "information_schema" in sql:
                raise RuntimeError("no access")
            return super().execute(sql, params)

    class BoomConnection(FakeConnection):
        def cursor(self):
            return BoomCursor(self)

    conn = BoomConnection()
    with pytest.raises(RuntimeError):
        SnowflakeProvider(password_settings(), connect=FakeConnect(conn)).get_schema()
    assert conn.closed


def test_run_query_normalizes_snowflake_types():
    import datetime as dt
    import json
    from decimal import Decimal

    conn = FakeConnection(
        result_columns=["ID", "AMOUNT", "DAY", "TS", "TS_TZ", "MISSING", "RATIO"],
        result_rows=[
            (
                Decimal("38"),  # NUMBER(38,0)
                Decimal("1234.50"),  # NUMBER(10,2)
                dt.date(2025, 3, 1),
                dt.datetime(2025, 3, 1, 9, 30),
                dt.datetime(2025, 3, 1, 9, 30, tzinfo=dt.timezone(dt.timedelta(hours=5, minutes=30))),
                None,
                float("nan"),
            )
        ],
    )
    result = SnowflakeProvider(password_settings(), connect=FakeConnect(conn)).run_query(
        "SELECT * FROM t"
    )
    assert result["rows"] == [
        [38, 1234.5, "2025-03-01", "2025-03-01T09:30:00", "2025-03-01T09:30:00+05:30", None, "NaN"]
    ]
    json.dumps(result, allow_nan=False)  # strictly JSON-serializable


# --- query execution -------------------------------------------------------- #


def test_run_query_result_format():
    conn = FakeConnection(
        result_columns=["CATEGORY", "REVENUE"],
        result_rows=[("Electronics", 166000.0), ("Furniture", 36000.0)],
    )
    provider = SnowflakeProvider(password_settings(), connect=FakeConnect(conn))
    result = provider.run_query("SELECT category, SUM(quantity * unit_price) FROM sales;")
    assert result == {
        "columns": ["CATEGORY", "REVENUE"],
        "rows": [["Electronics", 166000.0], ["Furniture", 36000.0]],
        "truncated": False,
    }
    # Trailing semicolon stripped by the validator before execution.
    assert conn.executed[-1][0] == "SELECT category, SUM(quantity * unit_price) FROM sales"
    assert conn.closed


def test_run_query_limits_rows():
    conn = FakeConnection(result_columns=["N"], result_rows=[(i,) for i in range(MAX_ROWS + 50)])
    provider = SnowflakeProvider(password_settings(), connect=FakeConnect(conn))
    result = provider.run_query("SELECT n FROM big")
    assert len(result["rows"]) == MAX_ROWS
    assert result["truncated"] is True
    assert conn.fetch_sizes == [MAX_ROWS + 1]  # never fetches everything


def test_run_query_exactly_max_rows_not_truncated():
    conn = FakeConnection(result_columns=["N"], result_rows=[(i,) for i in range(MAX_ROWS)])
    result = SnowflakeProvider(password_settings(), connect=FakeConnect(conn)).run_query(
        "SELECT n FROM t"
    )
    assert len(result["rows"]) == MAX_ROWS
    assert result["truncated"] is False


def test_connection_closed_when_query_fails():
    class BoomConnection(FakeConnection):
        def cursor(self):
            cur = FakeCursor(self)
            original = cur.execute

            def execute(sql, params=None):
                if not sql.startswith("ALTER SESSION"):
                    raise RuntimeError("snowflake error")
                return original(sql, params)

            cur.execute = execute
            return cur

    conn = BoomConnection()
    provider = SnowflakeProvider(password_settings(), connect=FakeConnect(conn))
    with pytest.raises(RuntimeError):
        provider.run_query("SELECT 1")
    assert conn.closed


# --- provider selection ----------------------------------------------------- #


def test_get_provider_selection():
    assert isinstance(get_provider({}), DuckDBProvider)
    assert isinstance(get_provider({"DATAMIND_PROVIDER": "Snowflake"}), SnowflakeProvider)
    with pytest.raises(ValueError):
        get_provider({"DATAMIND_PROVIDER": "postgres"})


def test_default_connect_uses_real_connector(monkeypatch):
    """The default path calls snowflake.connector.connect (patched: no network)."""
    import snowflake.connector

    captured = {}

    def fake(**kwargs):
        captured.update(kwargs)
        return FakeConnection()

    monkeypatch.setattr(snowflake.connector, "connect", fake)
    SnowflakeProvider(password_settings()).get_schema()
    assert captured["account"] == "myorg-myacct"


def test_connect_kwargs_are_known_to_installed_connector(tmp_path):
    """Guard against connector upgrades renaming the options we pass."""
    from dataclasses import fields

    from snowflake.connector.connection_config import ConnectionConfig

    known = {f.name for f in fields(ConnectionConfig)}
    key_file = tmp_path / "k.p8"
    _write_test_key(key_file)
    key_settings = SnowflakeSettings.from_env(
        {**BASE_ENV, "SNOWFLAKE_PRIVATE_KEY_PATH": str(key_file)}
    )
    for settings in (password_settings(), key_settings):
        assert set(settings.connect_kwargs()) <= known


def test_run_query_keeps_snowflake_query_id():
    class IdCursor(FakeCursor):
        sfqid = "01b2-query-id"

    class IdConnection(FakeConnection):
        def cursor(self):
            return IdCursor(self)

    conn = IdConnection(result_columns=["N"], result_rows=[(1,)])
    result = SnowflakeProvider(password_settings(), connect=FakeConnect(conn)).run_query("SELECT 1")
    assert result["provider_query_id"] == "01b2-query-id"


def test_location_is_non_secret_and_lazy(monkeypatch):
    loc = SnowflakeProvider(password_settings()).location()
    assert loc == {"database": "DATAMIND", "schema": "public", "warehouse": "DATAMIND_WH"}
    assert "pw-secret" not in repr(loc)
    for var in BASE_ENV:
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(SnowflakeConfigError):
        SnowflakeProvider().location()
