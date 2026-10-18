/**
 * Contract tests for the response shapes the DataMind backend actually sends
 * (backend/app/api.py): grounded explanations, clarification, screened refusals,
 * bounded-retry metadata and the specific error codes.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "./api-client";
import { QueryResponseSchema } from "./api-types";

afterEach(() => vi.unstubAllGlobals());

function mockFetch(body: unknown, status = 200) {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { status })));
}

const success = {
  query_id: "q_1a2b3c4d5e6f",
  question: "Revenue by category in 2025, highest first",
  provider: "snowflake",
  executed: true,
  generation_attempts: 2,
  model: { name: "gemma3:1b", duration_ms: 2469.0 },
  status: "success",
  answer: "The query returned 2 rows. First row: CATEGORY = Electronics, REVENUE = 66000.0.",
  explanation: {
    summary: "Gemma (gemma3:1b) wrote this SQL ... Read SALES with 1 filter and returned 2 rows.",
    tables: ["SALES"],
    filters: ["YEAR = 2025"],
    assumptions: ["REVENUE = SUM(QUANTITY * UNIT_PRICE)", "Grouped by CATEGORY", "At most 1000 rows are returned."],
  },
  sql: "SELECT CATEGORY, SUM(QUANTITY * UNIT_PRICE) AS REVENUE FROM SALES WHERE YEAR = 2025 GROUP BY CATEGORY",
  validation: { passed: true, read_only: true, limit_applied: 1000, messages: [] },
  columns: [{ name: "CATEGORY" }, { name: "REVENUE" }],
  rows: [
    ["Electronics", 66000.0],
    ["Furniture", 10000.0],
  ],
  truncated: false,
  row_count: 2,
  execution: {
    duration_ms: 874.2,
    started_at: "2026-10-18T08:03:42Z",
    database: "DATAMIND",
    schema: "PUBLIC",
    warehouse: "DATAMIND_WH",
    provider_query_id: "01c7cf87-0002-d8ce-000f-2bea00012c06",
  },
  warnings: ["Attempt 1 failed and was not used (invalid identifier 'REVENUE'); Gemma corrected the SQL ..."],
};

describe("backend response contract", () => {
  it("parses grounded explanation fields and evidence", async () => {
    mockFetch(success);
    const r = await apiClient.query({ question: success.question });
    expect(r.explanation?.tables).toEqual(["SALES"]);
    expect(r.explanation?.filters).toEqual(["YEAR = 2025"]);
    expect(r.explanation?.assumptions).toContain("Grouped by CATEGORY");
    expect(r.execution?.provider_query_id).toBe("01c7cf87-0002-d8ce-000f-2bea00012c06");
    expect(r.rows).toEqual([
      { CATEGORY: "Electronics", REVENUE: 66000 },
      { CATEGORY: "Furniture", REVENUE: 10000 },
    ]);
    expect(r.row_count).toBe(2);
    expect(r.executed).toBe(true);
  });

  it("tolerates the extra generation_attempts field (compatible addition)", () => {
    // apiClient normalises array rows to objects before validation; mirror that here.
    const normalised = {
      ...success,
      rows: success.rows.map(([category, revenue]) => ({ CATEGORY: category, REVENUE: revenue })),
    };
    const parsed = QueryResponseSchema.safeParse(normalised);
    expect(parsed.success).toBe(true);
    if (parsed.success) expect("generation_attempts" in parsed.data).toBe(false); // stripped, not an error
  });

  it("parses a clarification request without SQL or rows", async () => {
    mockFetch({
      query_id: "q_c",
      status: "clarification_needed",
      executed: false,
      answer: "Do you mean revenue or units sold?",
      clarification: {
        question: "Do you mean revenue or units sold?",
        options: ["Which product has the highest revenue?", "Which product sold the most units?"],
      },
      model: { name: "gemma3:1b", duration_ms: 900 },
    });
    const r = await apiClient.query({ question: "What is the best product?" });
    expect(r.status).toBe("clarification_needed");
    expect(r.clarification?.options).toHaveLength(2);
    expect(r.sql).toBeUndefined();
  });

  it("parses a screened refusal (blocked before SQL generation)", async () => {
    mockFetch({
      query_id: "q_r",
      status: "refused",
      executed: false,
      answer: "DataMind is read-only: it can look up and summarise data, but it never deletes ...",
      validation: { passed: false, read_only: true, messages: ["Blocked before SQL generation (modify request)."] },
    });
    const r = await apiClient.query({ question: "Delete all the sales records" });
    expect(r.status).toBe("refused");
    expect(r.validation?.passed).toBe(false);
    expect(r.executed).toBe(false);
  });

  it.each([
    ["generation", "model_unavailable"],
    ["generation", "model_timeout"],
    ["generation", "model_bad_output"],
    ["generation", "schema_unavailable"],
    ["validation", "syntax"],
    ["execution", "unknown_object"],
    ["execution", "permission_denied"],
    ["execution", "query_timeout"],
    ["execution", "provider_not_configured"],
  ])("parses %s error with code %s", (stage, code) => {
    const parsed = QueryResponseSchema.safeParse({
      query_id: "q_e",
      status: "error",
      executed: false,
      error: { stage, code, message: "details" },
    });
    expect(parsed.success).toBe(true);
    if (parsed.success) expect(parsed.data.error?.code).toBe(code);
  });

  it("parses an empty result with its warning", () => {
    const parsed = QueryResponseSchema.safeParse({
      ...success,
      rows: [],
      row_count: 0,
      warnings: ["No rows matched. The data may not contain matching records ..."],
    });
    expect(parsed.success).toBe(true);
    if (parsed.success) expect(parsed.data.rows).toEqual([]);
  });
});
