/**
 * Query history kept in this browser only (localStorage). It records questions the
 * user actually asked and the responses actually received; nothing is pre-seeded.
 */
import type { QueryResult, QueryStatus, ResponseSource } from "./api-types";

export const HISTORY_LIMIT = 40;
/** Rows kept per stored result, so history stays small. Reopened entries say when rows were trimmed. */
export const HISTORY_ROW_CAP = 200;

export type HistoryEntry = {
  id: string;
  question: string;
  provider: string | null;
  source: ResponseSource;
  status: QueryStatus | "network_error";
  rowCount: number | null;
  durationMs: number | null;
  createdAt: string;
  errorMessage?: string;
  result?: QueryResult;
  rowsTrimmed?: boolean;
};

export function makeHistoryEntry(result: QueryResult): HistoryEntry {
  const rows = result.response.rows ?? [];
  const trimmed = rows.length > HISTORY_ROW_CAP;
  const stored: QueryResult = trimmed
    ? { ...result, response: { ...result.response, rows: rows.slice(0, HISTORY_ROW_CAP) } }
    : result;
  return {
    id: result.response.query_id,
    question: result.question,
    provider: result.provider,
    source: result.source,
    status: result.response.status,
    rowCount: result.response.row_count ?? result.response.rows?.length ?? null,
    durationMs: result.response.execution?.duration_ms ?? null,
    createdAt: result.receivedAt,
    errorMessage: result.response.error?.message,
    result: stored,
    rowsTrimmed: trimmed,
  };
}

export function makeFailedEntry(
  question: string,
  provider: string | null,
  source: ResponseSource,
  message: string,
): HistoryEntry {
  return {
    id: `local-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`,
    question,
    provider,
    source,
    status: "network_error",
    rowCount: null,
    durationMs: null,
    createdAt: new Date().toISOString(),
    errorMessage: message,
  };
}

export function addToHistory(list: HistoryEntry[], entry: HistoryEntry): HistoryEntry[] {
  return [entry, ...list.filter((e) => e.id !== entry.id)].slice(0, HISTORY_LIMIT);
}
