# DataMind API contract (frontend ⇄ FastAPI backend)

This is the contract the frontend is built against. It is a **proposal for the backend team**: the shapes are enforced in the browser by the Zod schemas in [`src/lib/api-types.ts`](../src/lib/api-types.ts), so if the backend changes a field, change it in both places.

Base URL comes from `NEXT_PUBLIC_API_BASE_URL` (default `http://localhost:8000`). All bodies are JSON. The backend must allow CORS from the frontend origin (for local dev: `http://localhost:3000`).

Rules that keep the UI honest:

- Omit a field rather than send a made-up value. The UI shows "Not reported" for anything missing.
- `executed: true` only when the SQL actually ran on the provider at question time.
- Never send credentials, connection strings or env values in any response.

---

## `GET /api/health` (required)

```json
{
  "status": "ok",                       // "ok" | "degraded" | "down"
  "version": "0.1.0",                   // optional
  "row_limit": 1000,                    // optional, max rows returned per query
  "providers": [
    {
      "id": "snowflake",                // sent back as `provider` in /api/query
      "label": "Snowflake",
      "connected": true,                // true only if a real check (e.g. SELECT 1) succeeded
      "is_default": true,
      "database": "SNOWFLAKE_SAMPLE_DATA",
      "schema": "TPCH_SF1",
      "warehouse": "COMPUTE_WH",        // optional
      "detail": null                    // optional, short human reason when not connected
    },
    { "id": "duckdb", "label": "DuckDB (local)", "connected": true }
  ],
  "model": { "name": "gemma3n:e4b", "runtime": "Ollama", "available": true }  // optional
}
```

The provider switcher only appears when more than one provider is listed. Disconnected providers are shown but cannot be selected.

## `GET /api/schema?provider=<id>` (required for Schema Explorer)

```json
{
  "provider": "snowflake",
  "database": "SNOWFLAKE_SAMPLE_DATA",
  "schemas": [
    {
      "name": "TPCH_SF1",
      "tables": [
        {
          "name": "ORDERS",
          "description": null,
          "row_count": 1500000,
          "columns": [
            { "name": "O_ORDERKEY", "data_type": "NUMBER(38,0)", "nullable": false, "description": null }
          ]
        }
      ]
    }
  ]
}
```

## `GET /api/suggestions?provider=<id>` (optional)

```json
{ "questions": ["Which regions generate the most revenue?", "..."] }
```

If this returns 404, the frontend builds starter questions from `/api/schema` instead. Implementing it gives nicer wording (and removes a 404 line from the browser console).

## `POST /api/query` (required)

Request:

```json
{ "question": "Which regions generate the most revenue?", "provider": "snowflake" }
```

Response (HTTP 200 for every outcome the backend handled, including refusals and SQL errors):

```json
{
  "query_id": "q_8f2c1a",                         // required, unique
  "status": "success",                            // "success" | "clarification_needed" | "refused" | "error"
  "question": "Which regions generate the most revenue?",
  "provider": "snowflake",
  "answer": "Europe leads revenue ...",           // plain-language answer grounded in the rows
  "explanation": {                                // M4: how the answer was obtained
    "summary": "Joined LINEITEM ... summed discounted revenue per region.",
    "tables": ["TPCH_SF1.LINEITEM", "TPCH_SF1.REGION"],
    "filters": ["None (all years)"],
    "assumptions": ["Revenue = L_EXTENDEDPRICE × (1 − L_DISCOUNT)"]
  },
  "sql": "SELECT ...",                            // exactly what was (or would have been) run
  "executed": true,
  "validation": { "passed": true, "read_only": true, "limit_applied": 1000, "messages": [] },
  "columns": [{ "name": "REGION", "data_type": "VARCHAR" }, { "name": "REVENUE", "data_type": "NUMBER" }],
  "rows": [{ "REGION": "EUROPE", "REVENUE": 43750214321.47 }],   // objects, or arrays aligned with `columns`
  "row_count": 5,                                 // total rows the query produced
  "truncated": false,                             // true if `rows` holds fewer than `row_count`
  "execution": {
    "provider_query_id": "01b2c3d4-...",          // Snowflake QUERY_ID, for query-history evidence
    "duration_ms": 412,                           // measured by the backend
    "started_at": "2026-10-18T07:01:53Z",
    "database": "SNOWFLAKE_SAMPLE_DATA",
    "schema": "TPCH_SF1",
    "warehouse": "COMPUTE_WH"
  },
  "model": { "name": "gemma3n:e4b", "duration_ms": 1520 },
  "chart": { "type": "bar", "x": "REGION", "y": ["REVENUE"] },   // optional hint: bar | horizontal_bar | line | pie | kpi | none
  "warnings": ["1998 is a partial year"]
}
```

Status-specific fields:

| status | also send | UI |
|---|---|---|
| `success` | `answer`, `sql`, `rows`, `columns` | Answer, figures, chart, table, SQL, evidence. Zero rows shows a designed empty state. |
| `clarification_needed` | `clarification: { "question": "...", "options": ["full question 1", "full question 2"] }` | Options are clickable and each is sent as a new question, so make them complete questions. |
| `refused` | `answer` (the reason), optional `validation.messages` | Calm "not answered" panel. Use for write/DDL intent and data the dataset does not contain (M6). |
| `error` | `error: { "stage": "generation" \| "validation" \| "execution" \| "internal", "code": "...", "message": "..." }`, plus `sql` if one exists | Stage-specific message, the attempted SQL marked "Not executed", and a retry button. |

Transport-level failures (FastAPI `422`, `500`, timeouts, invalid JSON, a body that does not match this contract) are handled separately and shown as "request failed" or "unexpected response", never as an answer.
