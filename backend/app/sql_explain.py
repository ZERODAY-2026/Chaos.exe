"""Deterministic, SQL-grounded explanations (PS1 M4).

Everything here is derived by parsing the SQL that was actually executed, so an
explanation can never mention a table, filter or calculation that did not run.
The language model is not involved.

Output matches the ``explanation`` object in frontend/docs/API_CONTRACT.md:
``tables``, ``filters`` and ``assumptions`` (lists of short strings).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp

SQLGLOT_DIALECTS = {"duckdb": "duckdb", "snowflake": "snowflake"}


@dataclass
class SqlExplanation:
    tables: list[str] = field(default_factory=list)
    filters: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    parsed: bool = True

    def as_contract(self) -> dict[str, list[str]]:
        return {"tables": self.tables, "filters": self.filters, "assumptions": self.assumptions}


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    return [x for x in items if not (x in seen or seen.add(x))]


def _split_and(condition: exp.Expression) -> list[exp.Expression]:
    if isinstance(condition, exp.And):
        return _split_and(condition.left) + _split_and(condition.right)
    if isinstance(condition, exp.Paren) and isinstance(condition.this, exp.And):
        return _split_and(condition.this)
    return [condition]


def _table_name(table: exp.Table) -> str:
    return ".".join(part for part in (table.catalog, table.db, table.name) if part)


def explain_sql(sql: str, provider_id: str, row_limit: int) -> SqlExplanation:
    """Describe what ``sql`` does. Returns ``parsed=False`` if it cannot be parsed."""
    dialect = SQLGLOT_DIALECTS.get(provider_id)
    try:
        tree = sqlglot.parse_one(sql, read=dialect)
    except (sqlglot.errors.ParseError, sqlglot.errors.TokenError, ValueError):
        return SqlExplanation(parsed=False, assumptions=[f"At most {row_limit} rows are returned."])

    def render(node: exp.Expression) -> str:
        return node.sql(dialect=dialect)

    cte_names = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
    tables = _unique(
        [_table_name(t) for t in tree.find_all(exp.Table) if t.name and t.name.lower() not in cte_names]
    )

    filters: list[str] = []
    for where in tree.find_all(exp.Where):
        filters += [render(c) for c in _split_and(where.this)]
    for having in tree.find_all(exp.Having):
        filters += [f"HAVING {render(c)}" for c in _split_and(having.this)]

    assumptions: list[str] = []
    for join in tree.find_all(exp.Join):  # every join that runs, including inside CTEs
        on = join.args.get("on")
        target = render(join.this)
        assumptions.append(f"Joined {target} on {render(on)}" if on is not None else f"Joined {target}")
    select = tree if isinstance(tree, exp.Select) else tree.find(exp.Select)
    if select is not None:
        for projection in select.expressions:
            inner = projection.this if isinstance(projection, exp.Alias) else projection
            if isinstance(inner, (exp.Column, exp.Star)):
                continue
            label = projection.alias if isinstance(projection, exp.Alias) else render(inner)
            assumptions.append(f"{label} = {render(inner)}")
        if select.args.get("distinct"):
            assumptions.append("Duplicate rows removed (DISTINCT)")
        group = select.args.get("group")
        if group is not None and group.expressions:
            assumptions.append("Grouped by " + ", ".join(render(g) for g in group.expressions))
        order = tree.args.get("order") or select.args.get("order")
        if order is not None and order.expressions:
            parts = [
                f"{render(o.this)} {'descending' if o.args.get('desc') else 'ascending'}"
                for o in order.expressions
            ]
            assumptions.append("Sorted by " + ", ".join(parts))
        limit = tree.args.get("limit") or select.args.get("limit")
        if limit is not None:
            value = limit.args.get("expression") or limit.this
            if value is not None:
                assumptions.append(f"Only the first {render(value)} row(s) are shown (LIMIT)")

    assumptions.append(f"At most {row_limit} rows are returned.")
    return SqlExplanation(tables=tables, filters=filters, assumptions=_unique(assumptions))


def summarize(explanation: SqlExplanation, row_count: int | None, truncated: bool) -> str:
    """One factual sentence about what ran (no model wording)."""
    if not explanation.parsed:
        return "The SQL ran; its structure could not be analysed automatically, so check the SQL below."
    tables = ", ".join(explanation.tables) if explanation.tables else "no table"
    filt = (
        f"{len(explanation.filters)} filter{'s' if len(explanation.filters) != 1 else ''}"
        if explanation.filters
        else "no filters"
    )
    if truncated:
        rows = f"more than the {row_count} rows shown"
    else:
        rows = f"{row_count} row{'s' if row_count != 1 else ''}"
    return f"Read {tables} with {filt} and returned {rows}."
