/**
 * Builds starter questions from real schema metadata when the backend has no
 * /api/suggestions endpoint. Only tables and columns that exist are referenced.
 */
import type { SchemaResponse, TableInfo } from "./api-types";
import { isNumericType, isTemporalType, looksLikeIdentifier } from "./formatters";

const readable = (name: string) =>
  name
    .replace(/^[a-z]{1,2}_(?=[a-z])/i, "")
    .replace(/_/g, " ")
    .toLowerCase()
    .trim();

function measureOf(t: TableInfo) {
  return t.columns.find((c) => isNumericType(c.data_type) && !looksLikeIdentifier(c.name));
}
function dimensionOf(t: TableInfo) {
  return t.columns.find(
    (c) =>
      /char|string|text/i.test(c.data_type) &&
      !/(comment|address|phone|desc|name$|clerk)/i.test(c.name),
  ) ?? t.columns.find((c) => /name$/i.test(c.name) && /char|string|text/i.test(c.data_type));
}
function dateOf(t: TableInfo) {
  return t.columns.find((c) => isTemporalType(c.data_type));
}

export function suggestionsFromSchema(schema: SchemaResponse | null, max = 4): string[] {
  if (!schema) return [];
  const tables = schema.schemas.flatMap((s) => s.tables);
  const out: string[] = [];
  for (const t of tables) {
    const m = measureOf(t);
    const d = dimensionOf(t);
    const dt = dateOf(t);
    const table = readable(t.name);
    if (m && dt) out.push(`How has total ${readable(m.name)} in ${table} changed by year?`);
    if (m && d) out.push(`Which ${readable(d.name)} has the highest total ${readable(m.name)}?`);
    if (out.length >= max * 2) break;
  }
  const biggest = [...tables].sort((a, b) => (b.row_count ?? 0) - (a.row_count ?? 0))[0];
  if (biggest) out.push(`How many rows are in ${readable(biggest.name)}?`);
  return Array.from(new Set(out)).slice(0, max);
}
