"""Shared schema and query-result formatting used by every data provider.

Keeping this in one place guarantees DuckDB and Snowflake return identical
structures, the same row limit and the same JSON-safe value conversions.

Schema structure (``Schema``)::

    {
        "<table name>": [
            {"name": "<column>", "type": "<engine type name>", "nullable": bool},
            ...  # in column (ordinal) order
        ],
        ...  # tables sorted by name
    }

Names are returned exactly as the engine stores them (DuckDB usually
lower-case, Snowflake usually upper-case) so generated SQL can reference them.
``type`` is the engine's native type name (e.g. ``INTEGER`` / ``NUMBER``).

Query result structure (``QueryResult``)::

    {"columns": [str, ...], "rows": [[value, ...], ...], "truncated": bool}

Every value in ``rows`` is JSON-serializable; see ``to_json_value``.
"""

from __future__ import annotations

import datetime as dt
import math
import uuid
from collections.abc import Iterable
from decimal import Decimal
from typing import Any, NotRequired, TypedDict

MAX_ROWS = 1000

JSONValue = Any  # None | bool | int | float | str | list | dict


class ColumnInfo(TypedDict):
    name: str
    type: str
    nullable: bool


Schema = dict[str, list[ColumnInfo]]


class QueryResult(TypedDict):
    columns: list[str]
    rows: list[list[JSONValue]]
    truncated: bool
    # Server-side query id (Snowflake QUERY_ID); absent when the engine has none.
    provider_query_id: NotRequired[str]


def _non_finite(value: float) -> str:
    if math.isnan(value):
        return "NaN"
    return "Infinity" if value > 0 else "-Infinity"


def to_json_value(value: Any) -> JSONValue:
    """Convert a database value into a strictly JSON-serializable value.

    - ``None`` stays ``None`` (SQL NULL); ``bool``/``int``/``str`` unchanged.
    - ``float``: unchanged if finite, else ``"NaN"``/``"Infinity"``/``"-Infinity"``
      (strict JSON has no NaN/Infinity).
    - ``Decimal``: ``int`` when it has no fractional digits (scale 0, e.g.
      ``NUMBER(38,0)``), otherwise ``float``. The choice depends on the
      column's scale, not the value, so a column never mixes int and float.
    - ``datetime``/``date``/``time``: ISO 8601 string (timezone offset kept).
    - ``timedelta`` (intervals): total seconds as ``float``.
    - ``bytes``: lower-case hex string. ``UUID``: canonical string.
    - lists/tuples/dicts (DuckDB LIST/STRUCT/MAP): converted recursively.
    - anything else: ``str(value)``.
    """
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else _non_finite(value)
    if isinstance(value, Decimal):
        if value.is_nan():
            return "NaN"
        if value.is_infinite():
            return _non_finite(float(value))
        if value.as_tuple().exponent >= 0:
            return int(value)
        return float(value)
    if isinstance(value, (dt.datetime, dt.date, dt.time)):
        return value.isoformat()
    if isinstance(value, dt.timedelta):
        return value.total_seconds()
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).hex()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(k): to_json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_json_value(v) for v in value]
    return str(value)


def format_result(cursor: Any, max_rows: int = MAX_ROWS) -> QueryResult:
    """Fetch at most ``max_rows`` rows from a DB-API cursor as a ``QueryResult``.

    Fetches one extra row only to detect truncation; never fetches everything.
    """
    if cursor.description is None:
        return {"columns": [], "rows": [], "truncated": False}
    columns = [str(d[0]) for d in cursor.description]
    fetched = cursor.fetchmany(max_rows + 1)
    return {
        "columns": columns,
        "rows": [[to_json_value(v) for v in row] for row in fetched[:max_rows]],
        "truncated": len(fetched) > max_rows,
    }


def _is_nullable(flag: Any) -> bool:
    if isinstance(flag, bool):
        return flag
    return str(flag).strip().upper() in {"YES", "Y", "TRUE"}


def build_schema(rows: Iterable[tuple[Any, Any, Any, Any]]) -> Schema:
    """Build a ``Schema`` from ``(table, column, data_type, is_nullable)`` rows.

    Rows must already be in column ordinal order within each table.
    """
    schema: Schema = {}
    for table, column, dtype, nullable in rows:
        schema.setdefault(str(table), []).append(
            {"name": str(column), "type": str(dtype), "nullable": _is_nullable(nullable)}
        )
    return dict(sorted(schema.items()))
