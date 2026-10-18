import datetime as dt
import json
import uuid
from decimal import Decimal

import pytest

from app.results import MAX_ROWS, build_schema, format_result, to_json_value


@pytest.mark.parametrize(
    "value, expected",
    [
        (None, None),
        (True, True),
        (False, False),
        (7, 7),
        (2**100, 2**100),
        (1.25, 1.25),
        ("text", "text"),
        (float("nan"), "NaN"),
        (float("inf"), "Infinity"),
        (float("-inf"), "-Infinity"),
        (Decimal("42"), 42),
        (Decimal("1E+3"), 1000),
        (Decimal("-7"), -7),
        (Decimal("12345678901234567890123456789012345678"), 12345678901234567890123456789012345678),
        (Decimal("166000.00"), 166000.0),
        (Decimal("0.1"), 0.1),
        (Decimal("NaN"), "NaN"),
        (Decimal("-Infinity"), "-Infinity"),
        (dt.date(2024, 2, 29), "2024-02-29"),
        (dt.datetime(2024, 1, 2, 3, 4, 5, 600000), "2024-01-02T03:04:05.600000"),
        (dt.datetime(2024, 1, 2, 3, 4, 5, tzinfo=dt.timezone.utc), "2024-01-02T03:04:05+00:00"),
        (dt.time(13, 45), "13:45:00"),
        (dt.timedelta(minutes=90), 5400.0),
        (b"\xaa\x01", "aa01"),
        (bytearray(b"\x00\xff"), "00ff"),
        (memoryview(b"\x10"), "10"),
        (uuid.UUID("12345678-1234-5678-1234-567812345678"), "12345678-1234-5678-1234-567812345678"),
        ([Decimal("1.5"), None, dt.date(2024, 1, 1)], [1.5, None, "2024-01-01"]),
        ((1, 2), [1, 2]),
        ({"a": Decimal("2"), 3: [b"\x01"]}, {"a": 2, "3": ["01"]}),
    ],
)
def test_to_json_value(value, expected):
    result = to_json_value(value)
    assert result == expected
    assert type(result) is type(expected)
    json.dumps(result, allow_nan=False)


def test_decimal_type_depends_on_scale_not_value():
    # A NUMBER(10,2) column keeps returning floats even for whole amounts.
    assert isinstance(to_json_value(Decimal("5.00")), float)
    assert isinstance(to_json_value(Decimal("5.25")), float)
    assert isinstance(to_json_value(Decimal("5")), int)


def test_unknown_types_fall_back_to_str():
    class Custom:
        def __str__(self):
            return "custom"

    assert to_json_value(Custom()) == "custom"


class ListCursor:
    def __init__(self, columns, rows):
        self.description = None if columns is None else [(c, None) for c in columns]
        self._rows = rows
        self.fetch_sizes = []

    def fetchmany(self, size):
        self.fetch_sizes.append(size)
        return self._rows[:size]


def test_format_result_no_result_set():
    assert format_result(ListCursor(None, [])) == {
        "columns": [],
        "rows": [],
        "truncated": False,
    }


def test_format_result_zero_rows():
    assert format_result(ListCursor(["A"], [])) == {
        "columns": ["A"],
        "rows": [],
        "truncated": False,
    }


@pytest.mark.parametrize(
    "count, kept, truncated",
    [(1, 1, False), (MAX_ROWS - 1, MAX_ROWS - 1, False), (MAX_ROWS, MAX_ROWS, False),
     (MAX_ROWS + 1, MAX_ROWS, True), (MAX_ROWS * 3, MAX_ROWS, True)],
)
def test_format_result_row_limit(count, kept, truncated):
    cursor = ListCursor(["N"], [(i,) for i in range(count)])
    result = format_result(cursor)
    assert len(result["rows"]) == kept
    assert result["truncated"] is truncated
    assert result["rows"][-1] == [kept - 1]
    assert cursor.fetch_sizes == [MAX_ROWS + 1]


def test_format_result_custom_limit_and_duplicate_columns():
    cursor = ListCursor(["X", "X"], [(1, 2), (3, 4), (5, 6)])
    assert format_result(cursor, max_rows=2) == {
        "columns": ["X", "X"],
        "rows": [[1, 2], [3, 4]],
        "truncated": True,
    }


def test_build_schema_structure_and_ordering():
    rows = [
        ("orders", "id", "INTEGER", "NO"),
        ("orders", "note", "VARCHAR", "YES"),
        ("Accounts", "zeta", "TEXT", True),
        ("Accounts", "alpha", "TEXT", False),
    ]
    schema = build_schema(rows)
    assert list(schema) == ["Accounts", "orders"]  # tables sorted
    assert [c["name"] for c in schema["Accounts"]] == ["zeta", "alpha"]  # ordinal kept
    assert schema["orders"] == [
        {"name": "id", "type": "INTEGER", "nullable": False},
        {"name": "note", "type": "VARCHAR", "nullable": True},
    ]


@pytest.mark.parametrize(
    "flag, expected",
    [("YES", True), ("yes", True), ("Y", True), (" YES ", True), (True, True),
     ("NO", False), ("N", False), (False, False), (None, False)],
)
def test_build_schema_nullable_flags(flag, expected):
    assert build_schema([("t", "c", "INT", flag)])["t"][0]["nullable"] is expected


def test_build_schema_empty():
    assert build_schema([]) == {}
