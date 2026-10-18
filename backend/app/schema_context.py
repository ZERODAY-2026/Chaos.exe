"""Schema context for the model, built only from discovered metadata.

What Gemma sees for each question:

* every table with its columns listed underneath it, so a column is never
  attributed to the wrong table;
* example values for low-cardinality text columns (exact spellings for filters),
  read through the provider's validated, read-only ``run_query`` on a bounded
  row sample;
* **declared** foreign keys (DuckDB constraints / Snowflake ``SHOW IMPORTED KEYS``)
  and, separately and clearly labelled, join keys **inferred** from matching
  column names (never presented as real relationships);
* measure hints derived from column names (e.g. revenue = quantity x unit price
  when both columns exist), so "revenue" is not computed as a bare price sum.

Nothing here is dataset-specific; another schema produces its own context.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from .gemma import _key_base
from .results import Schema

log = logging.getLogger("datamind.schema")

MAX_CONTEXT_CHARS = 9000
MAX_VALUES = 10
MAX_VALUE_CHARS = 40
VALUE_SAMPLE_ROWS = 10000
_TEXT_TYPES = ("char", "text", "string", "varchar")
_SKIP_VALUE_COLUMNS = re.compile(r"comment|description|address|phone|email|note", re.I)

_QTY = re.compile(r"(^|_)(quantity|qty|units?)$", re.I)
_UNIT_PRICE = re.compile(r"(^|_)(unit_?price|price)$", re.I)
_AMOUNT = re.compile(r"(amount|revenue|extendedprice|total_?price|sales_?value|spend)$", re.I)


@dataclass(frozen=True)
class Relationship:
    from_table: str
    from_column: str
    to_table: str
    to_column: str
    declared: bool

    def text(self) -> str:
        return f"{self.from_table}.{self.from_column} -> {self.to_table}.{self.to_column}"


@dataclass
class SchemaContext:
    schema: Schema
    relationships: list[Relationship] = field(default_factory=list)
    values: dict[tuple[str, str], list[str]] = field(default_factory=dict)
    measures: list[str] = field(default_factory=list)
    measure_options: dict[str, bool] = field(default_factory=dict)  # revenue / units / orders available
    text: str = ""


# --------------------------------------------------------------------------- #
# Relationships
# --------------------------------------------------------------------------- #


def declared_relationships(provider: Any) -> list[Relationship]:
    fn = getattr(provider, "get_relationships", None)
    if fn is None:
        return []
    try:
        return [Relationship(a, b, c, d, True) for a, b, c, d in fn()]
    except Exception as exc:  # metadata is optional; never block a question on it
        log.info("Foreign-key discovery unavailable: %s", type(exc).__name__)
        return []


def inferred_relationships(schema: Schema, declared: list[Relationship]) -> list[Relationship]:
    """Key-like columns with the same base name in several tables (``O_CUSTKEY`` ~
    ``C_CUSTKEY``), pointing at the table the key most likely belongs to. Pairs
    already covered by a declared foreign key are skipped."""
    covered = {(r.from_table.lower(), r.from_column.lower()) for r in declared} | {
        (r.to_table.lower(), r.to_column.lower()) for r in declared
    }
    owners: dict[str, list[tuple[str, str]]] = {}
    for table, columns in schema.items():
        for c in columns:
            base = _key_base(c["name"])
            if base:
                owners.setdefault(base, []).append((table, c["name"]))
    found = []
    for key, places in owners.items():
        if len(places) < 2:
            continue
        stem = re.sub(r"(_id|_key|key)$", "", key)
        places.sort(key=lambda p: (
            p[0].lower() not in (stem, f"{stem}s", f"{stem}es"),
            not p[0].lower().startswith(stem),
            p[0].lower(),
        ))
        target_table, target_col = places[0]
        for table, col in places[1:]:
            pair = {(table.lower(), col.lower()), (target_table.lower(), target_col.lower())}
            if pair <= covered:
                continue
            found.append(Relationship(table, col, target_table, target_col, False))
    return found


# --------------------------------------------------------------------------- #
# Example values (bounded, read-only, through the validated provider path)
# --------------------------------------------------------------------------- #


def _q(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def discover_values(provider: Any, schema: Schema) -> dict[tuple[str, str], list[str]]:
    """Distinct values of low-cardinality text columns, from a row sample.

    Two SELECT queries per table at most. Every query goes through
    ``provider.run_query`` and therefore through ``validate_read_only_sql``.
    """
    values: dict[tuple[str, str], list[str]] = {}
    for table, columns in schema.items():
        text_cols = [
            c["name"] for c in columns
            if any(t in c["type"].lower() for t in _TEXT_TYPES) and not _SKIP_VALUE_COLUMNS.search(c["name"])
        ]
        if not text_cols:
            continue
        sample = f"(SELECT {', '.join(_q(c) for c in text_cols)} FROM {_q(table)} LIMIT {VALUE_SAMPLE_ROWS}) s"
        try:
            counts = provider.run_query(
                "SELECT " + ", ".join(f"COUNT(DISTINCT {_q(c)})" for c in text_cols) + f" FROM {sample}"
            )["rows"][0]
            small = [c for c, n in zip(text_cols, counts) if n is not None and 0 < int(n) <= MAX_VALUES]
            if not small:
                continue
            union = " UNION ALL ".join(
                f"SELECT '{c.replace(chr(39), chr(39) * 2)}' AS col_name, CAST({_q(c)} AS VARCHAR) AS val "
                f"FROM {sample} WHERE {_q(c)} IS NOT NULL GROUP BY {_q(c)}"
                for c in small
            )
            for col_name, val in provider.run_query(f"SELECT col_name, val FROM ({union}) u")["rows"]:
                values.setdefault((table, col_name), []).append(str(val)[:MAX_VALUE_CHARS])
        except Exception as exc:  # values are a hint only
            log.info("Value discovery skipped for %s: %s", table, type(exc).__name__)
    return {k: sorted(v) for k, v in values.items()}


# --------------------------------------------------------------------------- #
# Measures
# --------------------------------------------------------------------------- #


def measure_hints(schema: Schema, relationships: list[Relationship]) -> tuple[list[str], dict[str, bool]]:
    """Formulas implied by column names. Returns (hint lines, available measure kinds)."""
    qty = [(t, c["name"]) for t, cols in schema.items() for c in cols if _QTY.search(c["name"])]
    price = [(t, c["name"]) for t, cols in schema.items() for c in cols if _UNIT_PRICE.search(c["name"])]
    amount = [(t, c["name"]) for t, cols in schema.items() for c in cols if _AMOUNT.search(c["name"])]
    linked = {(r.from_table.lower(), r.to_table.lower()) for r in relationships}
    linked |= {(b, a) for a, b in linked}

    hints: list[str] = []
    revenue = False
    for qt, qc in qty:
        for pt, pc in price:
            if qt == pt:
                hints.append(f"revenue / sales amount / money spent = SUM({qt}.{qc} * {pt}.{pc})")
                revenue = True
            elif (qt.lower(), pt.lower()) in linked:
                hints.append(
                    f"revenue / sales amount / money spent = SUM({qt}.{qc} * {pt}.{pc}) "
                    f"(join {qt} to {pt})"
                )
                revenue = True
    if amount:
        cols = ", ".join(f"{t}.{c}" for t, c in amount)
        hints.append(f"money amount column(s) already stored per row: {cols}")
        revenue = True
    for qt, qc in qty:
        hints.append(f"units / items sold = SUM({qt}.{qc}), not COUNT")
    orders = any("order" in t.lower() for t in schema) or any(
        re.search(r"order_?(id|key)$", c["name"], re.I) for cols in schema.values() for c in cols
    )
    hints.append("number of <things> = COUNT(DISTINCT <that table's key column>)")
    return hints, {"revenue": revenue, "units": bool(qty), "orders": bool(orders)}


# --------------------------------------------------------------------------- #
# Assembly
# --------------------------------------------------------------------------- #


def render(ctx: SchemaContext) -> str:
    lines = ["Tables (each column belongs to the table it is listed under):"]
    for table, columns in ctx.schema.items():
        lines.append(f"TABLE {table}")
        for c in columns:
            line = f"  - {c['name']} ({c['type'].lower()})"
            vals = ctx.values.get((table, c["name"]))
            if vals:
                line += " values: " + ", ".join(f"'{v}'" for v in vals)
            lines.append(line)
    declared = [r for r in ctx.relationships if r.declared]
    inferred = [r for r in ctx.relationships if not r.declared]
    if declared:
        lines.append("Declared foreign keys (join on these):")
        lines += [f"  - {r.text()}" for r in declared]
    if inferred:
        lines.append("Possible join keys (inferred from matching column names, not declared):")
        lines += [f"  - {r.text()}" for r in inferred]
    if ctx.measures:
        lines.append("Measure hints (from column names):")
        lines += [f"  - {m}" for m in ctx.measures]
    text = "\n".join(lines)
    if len(text) > MAX_CONTEXT_CHARS:
        text = text[:MAX_CONTEXT_CHARS].rsplit("\n", 1)[0] + "\n-- (schema truncated)"
    return text


def build_context(provider: Any, schema: Schema, include_values: bool = True) -> SchemaContext:
    declared = declared_relationships(provider)
    relationships = declared + inferred_relationships(schema, declared)
    values = discover_values(provider, schema) if include_values else {}
    measures, options = measure_hints(schema, relationships)
    ctx = SchemaContext(schema, relationships, values, measures, options)
    ctx.text = render(ctx)
    return ctx
