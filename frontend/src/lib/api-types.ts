/**
 * DataMind API contract (frontend side).
 *
 * These Zod schemas are the single source of truth for what the frontend expects
 * from the FastAPI backend. They are documented in docs/API_CONTRACT.md. Fields are
 * optional wherever the backend may legitimately omit them, so the UI degrades to
 * "not available" instead of inventing values.
 */
import { z } from "zod";

/* ---------- /api/health ---------- */

export const ProviderStatusSchema = z.object({
  id: z.string(),
  label: z.string().optional(),
  connected: z.boolean(),
  is_default: z.boolean().optional(),
  detail: z.string().nullish(),
  database: z.string().nullish(),
  schema: z.string().nullish(),
  warehouse: z.string().nullish(),
});
export type ProviderStatus = z.infer<typeof ProviderStatusSchema>;

export const ModelStatusSchema = z.object({
  name: z.string(),
  runtime: z.string().nullish(),
  available: z.boolean(),
  detail: z.string().nullish(),
});
export type ModelStatus = z.infer<typeof ModelStatusSchema>;

export const HealthResponseSchema = z.object({
  status: z.enum(["ok", "degraded", "down"]),
  version: z.string().nullish(),
  providers: z.array(ProviderStatusSchema).default([]),
  model: ModelStatusSchema.nullish(),
  row_limit: z.number().int().positive().nullish(),
});
export type HealthResponse = z.infer<typeof HealthResponseSchema>;

/* ---------- /api/schema ---------- */

export const ColumnInfoSchema = z.object({
  name: z.string(),
  data_type: z.string().default("UNKNOWN"),
  nullable: z.boolean().nullish(),
  description: z.string().nullish(),
});
export type ColumnInfo = z.infer<typeof ColumnInfoSchema>;

export const TableInfoSchema = z.object({
  name: z.string(),
  description: z.string().nullish(),
  row_count: z.number().nullish(),
  columns: z.array(ColumnInfoSchema).default([]),
});
export type TableInfo = z.infer<typeof TableInfoSchema>;

export const SchemaInfoSchema = z.object({
  name: z.string(),
  tables: z.array(TableInfoSchema).default([]),
});
export type SchemaInfo = z.infer<typeof SchemaInfoSchema>;

export const SchemaResponseSchema = z.object({
  provider: z.string(),
  database: z.string().nullish(),
  schemas: z.array(SchemaInfoSchema).default([]),
});
export type SchemaResponse = z.infer<typeof SchemaResponseSchema>;

/* ---------- /api/suggestions (optional endpoint) ---------- */

export const SuggestionsResponseSchema = z.object({
  questions: z.array(z.string()).default([]),
});
export type SuggestionsResponse = z.infer<typeof SuggestionsResponseSchema>;

/* ---------- /api/query ---------- */

export type QueryRequest = {
  question: string;
  provider?: string;
};

export const QueryStatusSchema = z.enum(["success", "clarification_needed", "refused", "error"]);
export type QueryStatus = z.infer<typeof QueryStatusSchema>;

export const ErrorStageSchema = z.enum(["generation", "validation", "execution", "internal"]);
export type ErrorStage = z.infer<typeof ErrorStageSchema>;

export const ResultColumnSchema = z.object({
  name: z.string(),
  data_type: z.string().nullish(),
});
export type ResultColumn = z.infer<typeof ResultColumnSchema>;

export const ChartHintSchema = z.object({
  type: z.enum(["bar", "horizontal_bar", "line", "pie", "kpi", "none"]),
  x: z.string().nullish(),
  y: z.array(z.string()).nullish(),
});
export type ChartHint = z.infer<typeof ChartHintSchema>;

const RowSchema = z.record(z.string(), z.unknown());

export const QueryResponseSchema = z.object({
  query_id: z.string(),
  status: QueryStatusSchema,
  question: z.string().nullish(),
  provider: z.string().nullish(),
  answer: z.string().nullish(),
  explanation: z
    .object({
      summary: z.string().nullish(),
      tables: z.array(z.string()).nullish(),
      filters: z.array(z.string()).nullish(),
      assumptions: z.array(z.string()).nullish(),
    })
    .nullish(),
  sql: z.string().nullish(),
  /** True only when the backend actually ran `sql` against the provider. */
  executed: z.boolean().nullish(),
  validation: z
    .object({
      passed: z.boolean(),
      read_only: z.boolean().nullish(),
      limit_applied: z.number().nullish(),
      messages: z.array(z.string()).nullish(),
    })
    .nullish(),
  columns: z.array(ResultColumnSchema).nullish(),
  rows: z.array(RowSchema).nullish(),
  row_count: z.number().int().nonnegative().nullish(),
  truncated: z.boolean().nullish(),
  execution: z
    .object({
      provider_query_id: z.string().nullish(),
      duration_ms: z.number().nullish(),
      started_at: z.string().nullish(),
      database: z.string().nullish(),
      schema: z.string().nullish(),
      warehouse: z.string().nullish(),
    })
    .nullish(),
  model: z
    .object({
      name: z.string().nullish(),
      duration_ms: z.number().nullish(),
    })
    .nullish(),
  chart: ChartHintSchema.nullish(),
  warnings: z.array(z.string()).nullish(),
  clarification: z
    .object({
      question: z.string(),
      options: z.array(z.string()).nullish(),
    })
    .nullish(),
  error: z
    .object({
      stage: ErrorStageSchema.nullish(),
      code: z.string().nullish(),
      message: z.string(),
    })
    .nullish(),
});
export type QueryResponse = z.infer<typeof QueryResponseSchema>;

/** Where a response came from. Demo responses are fixtures and are always labeled in the UI. */
export type ResponseSource = "live" | "demo";

export type QueryResult = {
  response: QueryResponse;
  source: ResponseSource;
  question: string;
  provider: string | null;
  receivedAt: string;
  /** Round-trip time measured in the browser (includes network + model + execution). */
  clientDurationMs: number;
};
