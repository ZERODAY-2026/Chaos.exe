/** Shared, locale-stable formatting helpers for result values and metadata. */

const NUMERIC_TYPE = /^(number|numeric|decimal|int|integer|bigint|smallint|tinyint|byteint|float|float4|float8|double|real|hugeint|ubigint|uinteger)/i;
const TEMPORAL_TYPE = /^(date|time|timestamp|datetime)/i;
const ISO_DATE = /^\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?$/;
const CURRENCY_NAME = /(price|revenue|sales|amount|cost|spend|spent|total_?price|acctbal|balance|profit|income)/i;
const ID_NAME = /(^id$|_id$|key$|^.._?key$|code$|zip|phone|year$)/i;

export function isNumericType(dataType?: string | null): boolean {
  return !!dataType && NUMERIC_TYPE.test(dataType.trim());
}

export function isTemporalType(dataType?: string | null): boolean {
  return !!dataType && TEMPORAL_TYPE.test(dataType.trim());
}

export function isIsoDateString(value: unknown): value is string {
  return typeof value === "string" && ISO_DATE.test(value.trim());
}

/** Accepts numbers and numeric strings (DECIMALs often arrive as strings from Python). */
export function toNumber(value: unknown): number | null {
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (typeof value === "bigint") return Number(value);
  if (typeof value === "string" && value.trim() !== "" && /^-?\d+(\.\d+)?(e[+-]?\d+)?$/i.test(value.trim())) {
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

export function looksLikeCurrency(columnName: string): boolean {
  return CURRENCY_NAME.test(columnName);
}

export function looksLikeIdentifier(columnName: string): boolean {
  return ID_NAME.test(columnName);
}

const integerFmt = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const decimalFmt = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });
const currencyFmt = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const compactFmt = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 });

export function formatNumber(n: number, opts: { compact?: boolean; currency?: boolean } = {}): string {
  const prefix = opts.currency ? "$" : "";
  const sign = n < 0 ? "-" : "";
  const abs = Math.abs(n);
  if (opts.compact && abs >= 10_000) return `${sign}${prefix}${compactFmt.format(abs)}`;
  const body = Number.isInteger(abs) ? integerFmt.format(abs) : (opts.currency ? currencyFmt : decimalFmt).format(abs);
  return `${sign}${prefix}${body}`;
}

export function formatDate(value: string): string {
  const v = value.trim();
  // Pure dates are rendered as-is to avoid timezone shifts.
  if (/^\d{4}-\d{2}-\d{2}$/.test(v)) return v;
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return v;
  return d.toISOString().replace("T", " ").replace(/\.\d+Z$/, " UTC").replace(/Z$/, " UTC");
}

export type CellDisplay = { text: string; kind: "null" | "number" | "date" | "boolean" | "text" | "json" };

export function formatCell(value: unknown, column: { name: string; data_type?: string | null }): CellDisplay {
  if (value === null || value === undefined) return { text: "null", kind: "null" };
  if (typeof value === "boolean") return { text: value ? "true" : "false", kind: "boolean" };
  const num = toNumber(value);
  const declaredText = column.data_type && !isNumericType(column.data_type);
  if (num !== null && !declaredText) {
    if (looksLikeIdentifier(column.name)) return { text: String(value), kind: "number" };
    return { text: formatNumber(num, { currency: looksLikeCurrency(column.name) }), kind: "number" };
  }
  if (isIsoDateString(value)) return { text: formatDate(value), kind: "date" };
  if (typeof value === "object") {
    try {
      return { text: JSON.stringify(value), kind: "json" };
    } catch {
      return { text: String(value), kind: "json" };
    }
  }
  return { text: String(value), kind: "text" };
}

export function formatDuration(ms?: number | null): string | null {
  if (ms === null || ms === undefined || !Number.isFinite(ms)) return null;
  if (ms < 1000) return `${Math.round(ms)} ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(ms < 10_000 ? 2 : 1)} s`;
  return `${Math.floor(ms / 60_000)}m ${Math.round((ms % 60_000) / 1000)}s`;
}

export function formatRelativeTime(iso: string, now: number = Date.now()): string {
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return iso;
  const s = Math.round((now - t) / 1000);
  if (s < 45) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86_400) return `${Math.round(s / 3600)} h ago`;
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

/** Turns SNAKE_CASE / prefixed column names into readable labels: "L_EXTENDEDPRICE" → "Extendedprice". */
export function humanizeColumn(name: string): string {
  const cleaned = name.replace(/^[a-z]{1,2}_(?=[a-z])/i, "").replace(/_/g, " ").trim().toLowerCase();
  return cleaned.charAt(0).toUpperCase() + cleaned.slice(1);
}

export function pluralize(n: number, word: string, plural = `${word}s`): string {
  return `${formatNumber(n)} ${n === 1 ? word : plural}`;
}
