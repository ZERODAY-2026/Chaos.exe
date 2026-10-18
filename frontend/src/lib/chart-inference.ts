/**
 * Chart selection from the real result shape.
 *
 * Order of precedence:
 *   1. A valid backend hint (`response.chart`) whose columns exist in the result.
 *   2. A small heuristic over column types and values (below).
 *   3. No chart — the table is the honest view.
 *
 * The heuristic never invents values: every plotted point is a returned row.
 */
import type { ChartHint, ResultColumn } from "./api-types";
import { isIsoDateString, isNumericType, isTemporalType, looksLikeIdentifier, toNumber } from "./formatters";

export type ChartKind = "bar" | "horizontal_bar" | "line" | "pie" | "kpi";

export type ChartSpec = {
  kind: ChartKind;
  /** Dimension column (absent for kpi). */
  x?: string;
  /** Measure columns, max 3. */
  y: string[];
  /** Why this chart was chosen, shown in the UI for transparency. */
  reason: string;
  source: "backend" | "heuristic";
};

export const MAX_CATEGORIES = 30;
export const MAX_POINTS = 500;
const MAX_SERIES = 3;
const PIE_MAX_SLICES = 6;

type Row = Record<string, unknown>;

export type ColumnRole = "measure" | "temporal" | "category";

export function classifyColumn(col: ResultColumn, rows: Row[]): ColumnRole {
  const sample = rows.slice(0, 50).map((r) => r[col.name]).filter((v) => v !== null && v !== undefined);
  if (isTemporalType(col.data_type)) return "temporal";
  if (/(^|_)(year|month|date|day|week|quarter)$/i.test(col.name) && sample.length > 0) return "temporal";
  if (sample.length > 0 && sample.every(isIsoDateString)) return "temporal";
  const declaredNumeric = isNumericType(col.data_type);
  const valuesNumeric = sample.length > 0 && sample.every((v) => toNumber(v) !== null);
  if ((declaredNumeric || (!col.data_type && valuesNumeric)) && valuesNumeric && !looksLikeIdentifier(col.name)) {
    return "measure";
  }
  if (declaredNumeric && sample.length === 0) return "measure";
  return "category";
}

function columnsExist(names: (string | null | undefined)[], columns: ResultColumn[]): boolean {
  const set = new Set(columns.map((c) => c.name));
  return names.every((n) => !n || set.has(n));
}

export function inferChart(columns: ResultColumn[], rows: Row[], hint?: ChartHint | null): ChartSpec | null {
  if (!columns.length || !rows.length) return null;

  if (hint) {
    if (hint.type === "none") return null;
    const y = (hint.y ?? []).slice(0, MAX_SERIES);
    if (columnsExist([hint.x, ...y], columns) && (hint.type === "kpi" ? y.length > 0 : !!hint.x && y.length > 0)) {
      const tooMany = hint.type !== "kpi" && rows.length > (hint.type === "line" ? MAX_POINTS : MAX_CATEGORIES);
      const badPie = hint.type === "pie" && (rows.length > PIE_MAX_SLICES || hasNegative(rows, y));
      if (!tooMany && !badPie) {
        return { kind: hint.type, x: hint.x ?? undefined, y, reason: "Chart type suggested by the backend.", source: "backend" };
      }
    }
  }

  const roles = columns.map((c) => ({ name: c.name, role: classifyColumn(c, rows) }));
  const measures = roles.filter((r) => r.role === "measure").map((r) => r.name);
  const temporal = roles.find((r) => r.role === "temporal")?.name;
  const category = roles.find((r) => r.role === "category")?.name;

  if (measures.length === 0) return null;

  if (rows.length === 1) {
    return {
      kind: "kpi",
      y: measures.slice(0, 4),
      reason: "A single row is clearer as figures than as a chart.",
      source: "heuristic",
    };
  }

  const y = comparableMeasures(measures, rows).slice(0, MAX_SERIES);

  if (temporal && rows.length >= 2) {
    if (rows.length > MAX_POINTS) return null;
    return { kind: "line", x: temporal, y, reason: `Line chart because "${temporal}" is a time dimension.`, source: "heuristic" };
  }

  if (category) {
    if (rows.length > MAX_CATEGORIES) return null;
    const labels = rows.map((r) => String(r[category] ?? ""));
    const avgLen = labels.reduce((a, l) => a + l.length, 0) / labels.length;
    const horizontal = rows.length > 8 || avgLen > 12;
    return {
      kind: horizontal ? "horizontal_bar" : "bar",
      x: category,
      y,
      reason: horizontal
        ? `Horizontal bars to keep ${rows.length} "${category}" labels readable.`
        : `Bar chart comparing "${category}" categories.`,
      source: "heuristic",
    };
  }

  return null;
}

/**
 * Keeps only measures on a similar scale to the first one (within 10x), so several
 * series can share one axis without flattening each other. Others stay in the table.
 */
export function comparableMeasures(measures: string[], rows: Row[]): string[] {
  const peak = (m: string) => rows.reduce((mx, r) => Math.max(mx, Math.abs(toNumber(r[m]) ?? 0)), 0);
  const first = measures[0];
  if (!first) return [];
  const base = peak(first);
  return measures.filter((m, i) => {
    if (i === 0) return true;
    const p = peak(m);
    return base > 0 && p > 0 && Math.max(base, p) / Math.min(base, p) <= 10;
  });
}

function hasNegative(rows: Row[], cols: string[]): boolean {
  return rows.some((r) => cols.some((c) => (toNumber(r[c]) ?? 0) < 0));
}

/** Rows ready for Recharts: measures coerced to numbers, line charts sorted by time. */
export function toChartData(spec: ChartSpec, rows: Row[]): Row[] {
  const data = rows.map((r) => {
    const out: Row = { ...r };
    for (const m of spec.y) out[m] = toNumber(r[m]);
    if (spec.x) out[spec.x] = r[spec.x] === null || r[spec.x] === undefined ? "null" : r[spec.x];
    return out;
  });
  if (spec.kind === "line" && spec.x) {
    const x = spec.x;
    data.sort((a, b) => String(a[x]).localeCompare(String(b[x]), undefined, { numeric: true }));
  }
  return data;
}

/**
 * Highest / lowest facts derived from returned rows only. Returns null when the result
 * is truncated, because extremes over a partial result could be wrong.
 */
export function deriveExtremes(spec: ChartSpec | null, rows: Row[], truncated: boolean) {
  if (!spec || spec.kind === "kpi" || !spec.x || truncated || rows.length < 2) return null;
  const measure = spec.y[0];
  if (!measure) return null;
  let max: Row | null = null;
  let min: Row | null = null;
  for (const r of rows) {
    const v = toNumber(r[measure]);
    if (v === null) continue;
    if (!max || v > (toNumber(max[measure]) ?? -Infinity)) max = r;
    if (!min || v < (toNumber(min[measure]) ?? Infinity)) min = r;
  }
  if (!max || !min) return null;
  return { measure, dimension: spec.x, max, min };
}
