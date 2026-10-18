"""Compare query results with expected rows, tolerant of column order and aliases.

The model may name columns differently or add extra columns, so expected
columns are matched against any subset/permutation of the returned columns.
Numbers are compared with a small tolerance; strings case-insensitively.
"""

from __future__ import annotations

import math
from itertools import permutations
from typing import Any

REL_TOL = 1e-4
ABS_TOL = 0.01
MAX_COLUMNS_TO_ALIGN = 7  # permutations stay small for realistic result widths


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def values_equal(expected: Any, actual: Any, scale: float = 1.0) -> bool:
    if expected is None or actual is None:
        return expected is None and actual is None
    if _is_number(expected):
        if isinstance(actual, str):
            try:
                actual = float(actual)
            except ValueError:
                return False
        if not _is_number(actual):
            return False
        return math.isclose(float(expected) * scale, float(actual), rel_tol=REL_TOL, abs_tol=ABS_TOL)
    return str(expected).strip().casefold() == str(actual).strip().casefold()


def _sort_key(row: tuple) -> tuple:
    return tuple((0, round(float(v), 2)) if _is_number(v) else (1, str(v).strip().casefold()) for v in row)


def _rows_equal(expected: list[tuple], actual: list[tuple], ordered: bool, scale: float) -> bool:
    if len(expected) != len(actual):
        return False
    if not ordered:
        expected, actual = sorted(expected, key=_sort_key), sorted(actual, key=_sort_key)
    return all(
        all(values_equal(e, a, scale) for e, a in zip(er, ar)) for er, ar in zip(expected, actual)
    )


def rows_match(
    expected: list[list[Any]],
    actual: list[list[Any]],
    *,
    ordered: bool = False,
    accept_percent: bool = False,
) -> bool:
    """True if some choice of ``len(expected[0])`` returned columns reproduces ``expected``."""
    if not expected:
        return not actual
    width = len(expected[0])
    if not actual or len(actual) != len(expected):
        return False
    actual_width = len(actual[0])
    if actual_width < width or actual_width > MAX_COLUMNS_TO_ALIGN:
        return False
    exp_rows = [tuple(r) for r in expected]
    scales = (1.0, 100.0) if accept_percent else (1.0,)
    for cols in permutations(range(actual_width), width):
        projected = [tuple(row[c] for c in cols) for row in actual]
        if any(_rows_equal(exp_rows, projected, ordered, s) for s in scales):
            return True
    return False


def first_row_matches(expected_row: list[Any], actual: list[list[Any]]) -> bool:
    """For "which is the most ..." questions: only the top-ranked row must match."""
    return bool(actual) and rows_match([expected_row], [actual[0]])
