"""Common data-provider interface shared by DuckDB (dev) and Snowflake (final).

The agent / API layer should depend only on ``DataProvider`` so the backend can
switch from DuckDB to Snowflake via configuration without code changes.

``DuckDBProvider`` is for local development only. ``SnowflakeProvider`` is the
provider required for the final PS1 submission.

Both providers inherit ``run_query`` from ``_SQLProvider``, so SQL validation,
the ``MAX_ROWS`` limit and JSON-safe value conversion are identical. Schema and
result structures are documented in ``app/results.py``.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from . import database
from .results import MAX_ROWS, QueryResult, Schema, build_schema, format_result

__all__ = [
    "MAX_ROWS",
    "DataProvider",
    "DuckDBProvider",
    "SnowflakeConfigError",
    "SnowflakeProvider",
    "SnowflakeSettings",
    "UnsafeQueryError",
    "get_provider",
    "validate_read_only_sql",
]

SNOWFLAKE_STATEMENT_TIMEOUT_SECONDS = 60

# Keywords that must never appear in agent-generated SQL. This is a first line
# of defence; the real guarantee comes from read-only connections (DuckDB) and
# a read-only role (Snowflake).
_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|UPSERT|CREATE|ALTER|DROP|UNDROP|TRUNCATE|"
    r"REPLACE|GRANT|REVOKE|COPY|PUT|GET|ATTACH|DETACH|INSTALL|LOAD|PRAGMA|SET|"
    r"RESET|CALL|EXECUTE|EXPORT|IMPORT|USE|BEGIN|COMMIT|ROLLBACK|VACUUM|"
    r"CHECKPOINT|INTO)\b"
    # Snowflake SYSTEM$ functions can have side effects (cancel queries, etc.).
    r"|\bSYSTEM\$",
    re.IGNORECASE,
)


class UnsafeQueryError(ValueError):
    """Raised when SQL is not a single read-only SELECT statement.

    ``code`` is machine-readable: ``forbidden_keyword``, ``not_select`` and
    ``multiple_statements`` mean the query asks for something DataMind never
    runs; ``syntax``, ``ambiguous_literal`` and ``empty`` mean it is malformed.
    """

    REFUSAL_CODES = frozenset({"forbidden_keyword", "not_select", "multiple_statements"})

    def __init__(self, message: str, code: str = "invalid") -> None:
        super().__init__(message)
        self.code = code

    @property
    def is_refusal(self) -> bool:
        return self.code in self.REFUSAL_CODES


def _quoted_end(sql: str, start: int, quote: str, backslash_escapes: bool) -> int:
    """Return the index just past the quoted token starting at ``start``."""
    i = start + 1
    while i < len(sql):
        char = sql[i]
        if backslash_escapes and char == "\\":
            i += 2
            continue
        if char == quote:
            if sql[i + 1 : i + 2] == quote:  # doubled quote = escaped quote
                i += 2
                continue
            return i + 1
        i += 1
    raise UnsafeQueryError("Unterminated quoted string or identifier.", "syntax")


def _lex(sql: str, backslash_escapes: bool) -> tuple[str, str]:
    """Split SQL into ``(executable, skeleton)``.

    ``executable`` is the SQL with comments replaced by a space; string
    literals and quoted identifiers are kept intact. ``skeleton`` is the same
    text with the contents of literals and quoted identifiers removed, so
    keywords inside them (``'drop'``, ``"set"``) are not mistaken for SQL.
    """
    executable: list[str] = []
    skeleton: list[str] = []
    i = 0
    while i < len(sql):
        pair = sql[i : i + 2]
        char = sql[i]
        if pair == "--":
            end = sql.find("\n", i)
            i = len(sql) if end == -1 else end
            executable.append(" ")
            skeleton.append(" ")
        elif pair == "/*":
            end = sql.find("*/", i + 2)
            if end == -1:
                raise UnsafeQueryError("Unterminated block comment.", "syntax")
            i = end + 2
            executable.append(" ")
            skeleton.append(" ")
        elif char in ("'", '"'):
            end = _quoted_end(sql, i, char, backslash_escapes and char == "'")
            executable.append(sql[i:end])
            skeleton.append(char * 2)
            i = end
        else:
            executable.append(char)
            skeleton.append(char)
            i += 1
    return "".join(executable), "".join(skeleton)


def validate_read_only_sql(sql: str) -> str:
    """Return executable SQL if it is a single SELECT/WITH query, else raise.

    Comments are removed and one trailing semicolon is stripped. String
    literals are parsed both with standard SQL escaping (DuckDB) and with
    backslash escaping (Snowflake); a query whose meaning differs between the
    two is rejected, so a crafted literal cannot hide a second statement.
    """
    lexed = {_lex(sql, backslash_escapes=False), _lex(sql, backslash_escapes=True)}
    if len(lexed) != 1:
        raise UnsafeQueryError(
            "Ambiguous string literal (backslash before a quote).", "ambiguous_literal"
        )
    executable, skeleton = (part.strip() for part in lexed.pop())
    if skeleton.endswith(";"):
        skeleton = skeleton[:-1].rstrip()
        executable = executable.rstrip()[:-1].rstrip()
    if not skeleton:
        raise UnsafeQueryError("Query is empty.", "empty")
    if ";" in skeleton:
        raise UnsafeQueryError("Only a single statement is allowed.", "multiple_statements")
    if not re.match(r"^(SELECT|WITH)\b", skeleton, re.IGNORECASE):
        raise UnsafeQueryError("Only SELECT or WITH queries are allowed.", "not_select")
    match = _FORBIDDEN.search(skeleton)
    if match:
        raise UnsafeQueryError(
            f"Forbidden keyword: {match.group(0).upper()}", "forbidden_keyword"
        )
    return executable


@runtime_checkable
class DataProvider(Protocol):
    """Interface every backend data source must implement."""

    name: str

    def get_schema(self) -> Schema:
        """Return tables and columns; see ``app.results`` for the structure."""
        ...

    def run_query(self, sql: str) -> QueryResult:
        """Validate and execute read-only SQL, returning at most ``MAX_ROWS`` rows."""
        ...

    def location(self) -> dict[str, str]:
        """Non-secret context: ``database``, ``schema`` and optionally ``warehouse``."""
        ...


class _SQLProvider:
    """Shared ``run_query`` so every provider validates, limits and converts alike."""

    name: str

    @contextmanager
    def _query_cursor(self) -> Iterator[Any]:
        """Yield a DB-API cursor on a read-only connection, closed afterwards."""
        raise NotImplementedError
        yield  # pragma: no cover

    def get_schema(self) -> Schema:
        raise NotImplementedError

    def run_query(self, sql: str) -> QueryResult:
        executable = validate_read_only_sql(sql)  # before any connection opens
        with self._query_cursor() as cursor:
            cursor.execute(executable)
            result = format_result(cursor, MAX_ROWS)
            # Snowflake exposes the server-side query id; keep it as evidence.
            query_id = getattr(cursor, "sfqid", None)
            if isinstance(query_id, str) and query_id:
                result["provider_query_id"] = query_id
            return result

    def location(self) -> dict[str, str]:
        raise NotImplementedError


class DuckDBProvider(_SQLProvider):
    """Local provider backed by ``backend/app/database.py``.

    ``db_path`` selects a specific DuckDB file (e.g. an evaluation fixture or an
    isolated demo database). By default the dev database from
    ``DATAMIND_DUCKDB_PATH`` / ``data/datamind_dev.duckdb`` is used.
    """

    name = "duckdb"

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path is not None else None

    def _path(self) -> Path:
        return self.db_path if self.db_path is not None else database.get_db_path()

    @contextmanager
    def _query_cursor(self) -> Iterator[Any]:
        with database._connect(read_only=True, path=self._path()) as con:
            yield con

    def get_schema(self) -> Schema:
        return database.get_schema(self._path())

    def get_relationships(self) -> list[tuple[str, str, str, str]]:
        """Declared foreign keys as ``(fk_table, fk_column, pk_table, pk_column)``."""
        with database._connect(read_only=True, path=self._path()) as con:
            rows = con.execute(
                "SELECT table_name, constraint_column_names, referenced_table, referenced_column_names "
                "FROM duckdb_constraints() WHERE constraint_type = 'FOREIGN KEY' AND schema_name = 'main' "
                "ORDER BY table_name, constraint_index"
            ).fetchall()
        return [
            (table, fk_col, ref_table, pk_col)
            for table, fk_cols, ref_table, pk_cols in rows
            for fk_col, pk_col in zip(fk_cols, pk_cols)
        ]

    def location(self) -> dict[str, str]:
        return {"database": self._path().stem, "schema": "main"}


# --------------------------------------------------------------------------- #
# Snowflake
# --------------------------------------------------------------------------- #


class SnowflakeConfigError(RuntimeError):
    """Raised when Snowflake settings are missing or invalid.

    Messages name environment variables only, never their values.
    """


_REQUIRED_ENV = {
    "account": "SNOWFLAKE_ACCOUNT",
    "user": "SNOWFLAKE_USER",
    "role": "SNOWFLAKE_ROLE",
    "warehouse": "SNOWFLAKE_WAREHOUSE",
    "database": "SNOWFLAKE_DATABASE",
    "schema": "SNOWFLAKE_SCHEMA",
}


@dataclass(frozen=True)
class SnowflakeSettings:
    """Connection settings. Secrets are excluded from ``repr`` to avoid leaks in logs."""

    account: str
    user: str
    role: str
    warehouse: str
    database: str
    schema: str
    password: str | None = field(default=None, repr=False)
    private_key_path: str | None = None
    private_key_passphrase: str | None = field(default=None, repr=False)

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> SnowflakeSettings:
        env = os.environ if env is None else env

        def get(name: str) -> str | None:
            value = env.get(name, "").strip()
            return value or None

        values = {attr: get(var) for attr, var in _REQUIRED_ENV.items()}
        missing = [_REQUIRED_ENV[a] for a, v in values.items() if v is None]
        if missing:
            raise SnowflakeConfigError(
                "Missing Snowflake settings: " + ", ".join(missing)
            )

        settings = cls(
            **values,
            password=get("SNOWFLAKE_PASSWORD"),
            private_key_path=get("SNOWFLAKE_PRIVATE_KEY_PATH"),
            private_key_passphrase=get("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE"),
        )
        if not settings.private_key_path and not settings.password:
            raise SnowflakeConfigError(
                "Set SNOWFLAKE_PRIVATE_KEY_PATH (preferred) or SNOWFLAKE_PASSWORD."
            )
        return settings

    def connect_kwargs(self) -> dict[str, Any]:
        """Keyword arguments for ``snowflake.connector.connect``.

        Key-pair auth is used when a key path is set; otherwise password auth.
        """
        kwargs: dict[str, Any] = {
            "account": self.account,
            "user": self.user,
            "role": self.role,
            "warehouse": self.warehouse,
            "database": self.database,
            "schema": self.schema,
            "application": "DataMind",
            "login_timeout": 30,
        }
        if self.private_key_path:
            kwargs["authenticator"] = "SNOWFLAKE_JWT"
            kwargs["private_key"] = _load_private_key_der(
                self.private_key_path, self.private_key_passphrase
            )
        else:
            kwargs["password"] = self.password
        return kwargs


def _load_private_key_der(path: str, passphrase: str | None) -> bytes:
    """Read a PEM (PKCS#8) private key and return unencrypted DER bytes."""
    # ``cryptography`` is installed as a dependency of snowflake-connector-python.
    from cryptography.hazmat.primitives import serialization

    key_file = Path(path).expanduser()
    if not key_file.is_file():
        raise SnowflakeConfigError(
            "SNOWFLAKE_PRIVATE_KEY_PATH does not point to an existing file."
        )
    try:
        key = serialization.load_pem_private_key(
            key_file.read_bytes(),
            password=passphrase.encode() if passphrase else None,
        )
    except (ValueError, TypeError):
        # Do not chain the original error: it may describe key contents.
        raise SnowflakeConfigError(
            "Could not load the private key. Check the file format (PEM/PKCS#8) "
            "and SNOWFLAKE_PRIVATE_KEY_PASSPHRASE."
        ) from None
    return key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def _default_snowflake_connect(**kwargs: Any) -> Any:
    # Imported lazily so DuckDB-only development does not need the connector.
    import snowflake.connector

    return snowflake.connector.connect(**kwargs)


class SnowflakeProvider(_SQLProvider):
    """Provider that runs validated read-only SQL against real Snowflake.

    Application-side validation is NOT a security boundary. The configured
    ``SNOWFLAKE_ROLE`` must be a dedicated role granted only USAGE and SELECT.

    Settings are read and the connector is imported on first use, so creating
    this object never requires credentials or network access.
    """

    name = "snowflake"

    def __init__(
        self,
        settings: SnowflakeSettings | None = None,
        connect: Callable[..., Any] | None = None,
    ) -> None:
        self._settings = settings
        self._connect_fn = connect or _default_snowflake_connect

    @property
    def settings(self) -> SnowflakeSettings:
        if self._settings is None:
            self._settings = SnowflakeSettings.from_env()
        return self._settings

    def location(self) -> dict[str, str]:
        s = self.settings  # raises SnowflakeConfigError when not configured
        return {"database": s.database, "schema": s.schema, "warehouse": s.warehouse}

    def _connect(self) -> Any:
        con = self._connect_fn(**self.settings.connect_kwargs())
        try:
            # Trusted, fixed statement issued by the app, not by generated SQL.
            # MULTI_STATEMENT_COUNT = 1 makes Snowflake itself refuse batches.
            con.cursor().execute(
                "ALTER SESSION SET "
                f"STATEMENT_TIMEOUT_IN_SECONDS = {SNOWFLAKE_STATEMENT_TIMEOUT_SECONDS}, "
                "MULTI_STATEMENT_COUNT = 1, "
                "QUERY_TAG = 'datamind'"
            )
        except Exception:
            con.close()
            raise
        return con

    @contextmanager
    def _query_cursor(self) -> Iterator[Any]:
        con = self._connect()
        try:
            yield con.cursor()
        finally:
            con.close()

    def get_schema(self) -> Schema:
        with self._query_cursor() as cursor:
            cursor.execute(
                """
                SELECT table_name, column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_schema = %s
                ORDER BY table_name, ordinal_position
                """,
                (self.settings.schema.upper(),),
            )
            rows = cursor.fetchall()
        return build_schema(rows)

    def get_relationships(self) -> list[tuple[str, str, str, str]]:
        """Declared foreign keys via ``SHOW IMPORTED KEYS`` (a fixed, read-only
        metadata statement issued by the app, never by generated SQL)."""
        s = self.settings

        def ident(name: str) -> str:
            return '"' + name.upper().replace('"', '""') + '"'

        with self._query_cursor() as cursor:
            cursor.execute(f"SHOW IMPORTED KEYS IN SCHEMA {ident(s.database)}.{ident(s.schema)}")
            names = [d[0].lower() for d in cursor.description or []]
            rows = [dict(zip(names, r)) for r in cursor.fetchall()]
        return [
            (r["fk_table_name"], r["fk_column_name"], r["pk_table_name"], r["pk_column_name"])
            for r in rows
            if r.get("fk_table_name") and r.get("pk_table_name")
        ]


def get_provider(env: Mapping[str, str] | None = None) -> DataProvider:
    """Return the provider selected by ``DATAMIND_PROVIDER`` (default ``duckdb``)."""
    env = os.environ if env is None else env
    choice = env.get("DATAMIND_PROVIDER", "duckdb").strip().lower()
    if choice == "duckdb":
        return DuckDBProvider()
    if choice == "snowflake":
        return SnowflakeProvider()
    raise ValueError("DATAMIND_PROVIDER must be 'duckdb' or 'snowflake'.")
