# DataMind frontend: implementation notes

## Scope and source requirements

Built for PS1 "DataMind — Talk to Your Data" (ZeroDay OSS Hacktoberfest 2026 participant guide, pp. 2–5). The guide leaves the UI framework open ("UI, language, framework, agent design: Flexible"). The frontend-relevant requirements it does state, and where they live in the UI:

| Guide item | What the frontend does |
|---|---|
| M1 everyday-language questions | Large composer, Enter to ask, schema-based starter questions |
| M3 no unsupported claims | Every number shown comes from returned rows; missing metadata shows "Not reported" |
| M4 explanation (filters, tables, assumptions) | Answer section lists `explanation.tables / filters / assumptions` |
| M5 inspectable evidence (query + rows) | SQL inspector, full results table with CSV copy/download, evidence panel with warehouse query ID |
| M6 ambiguous / missing / empty / unsupported | Clarification panel with clickable options, refusal panel, designed zero-row state, stage-specific error panels |
| G3 no mock-ups or hard-coded answers | Live mode only shows backend responses. Demo mode is off by default, opt-in, and labeled on every screen |
| G5 no secrets | Only `NEXT_PUBLIC_API_BASE_URL` and `NEXT_PUBLIC_DEMO_MODE` are read; no credential fields exist in the UI |
| Rubric 8 "visual polish alone earns little" | Polish is in service of traceability: the evidence and SQL are first-class, not hidden |

Decisions made where nothing was specified (all reversible):

- Stack: Next.js 15 App Router, React 19, TypeScript strict (`noUncheckedIndexedAccess`), Tailwind CSS 4, Recharts 2, Zod 3, lucide-react, Geist fonts bundled locally (no Google Fonts fetch at build time). No shadcn/ui: the handful of primitives needed are in `src/components/ui`.
- No repository existed yet, so this is a standalone `frontend/` folder meant to sit next to the team's `backend/`.
- Query history is stored in `localStorage` (newest 40, rows capped at 200 per entry). If the backend later adds `GET /api/history`, swap the source in `workspace-provider.tsx`.
- Follow-up questions with context are not implemented; each question is sent on its own.

## Screens

| Route | Screen | Notes |
|---|---|---|
| `/` | Ask Data | Welcome state (headline, composer, suggestions, three-step explainer, offline callout) → results workspace |
| `/schema` | Schema Explorer | Two-pane table list + column table, search across tables and columns, "Use in question" inserts names into the composer |
| `/history` | Query History | Search, status filter, Open (restores the saved result), Ask again, remove, clear all (two-step confirm) |
| `/settings` | Settings | Live/demo mode, backend health, reported data sources, model status, theme, local data |

Shell: collapsible sidebar on desktop (state remembered), slide-in drawer under 1024px with Escape/backdrop close and focus moved into it; header with breadcrumb, provider switcher (only when the backend reports more than one provider), connection check, theme toggle. A skip link jumps to content.

Results workspace order: answer + explanation + warnings → key figures → chart → results table → SQL inspector and evidence side by side (stacked below 1280px).

## Architecture

```
src/
  app/                    routes (server components that render client views), globals.css (design tokens)
  components/
    workspace-provider.tsx   single client context: mode, theme, health, provider, query state machine, history, draft
    layout/                  app-shell, sidebar, mobile-navigation, topbar, provider-switcher, connection-status, demo-banner, page-frame, logo
    query/                   ask-data-workspace, question-composer, suggested-questions, query-status
    results/                 result-view (status router), answer-summary, metric-grid, chart-view, results-table,
                             sql-inspector, pipeline-badges, evidence-panel, state-panels, results-skeleton
    schema/ history/ settings/
    ui/                      button, badge/status-dot/kbd, panel, empty-state, spinner, toast
  hooks/                  use-schema (cached per mode+provider), use-suggestions, use-media-query
  lib/
    api-types.ts          Zod schemas = the contract
    api-client.ts         fetch wrapper: timeouts, cancellation, error kinds, validation, array-row normalisation
    demo/                 fixtures + demo client (isolated; never imported by api-client)
    chart-inference.ts    chart selection heuristic (tested)
    formatters.ts         numbers, currency, dates, nulls, durations (tested)
    sql-highlight.ts      tiny SQL tokenizer for highlighting (display only)
    history.ts storage.ts suggestions.ts utils.ts
```

Query state machine (`workspace-provider.tsx`): `idle → running → done | failed`. A new question aborts the previous request. `done` holds a `QueryResult` (`response`, `source: "live" | "demo"`, provider, client-measured round trip). `failed` holds an `ApiError` with `kind`: `network | timeout | http | malformed | not_found | aborted`.

## Backend integration

See [API_CONTRACT.md](./API_CONTRACT.md). Endpoints used: `GET /api/health`, `GET /api/schema`, `GET /api/suggestions` (optional), `POST /api/query`. Every response goes through Zod; a response that does not match is shown as "unexpected response" and never rendered as an answer. Timeouts: 8 s health, 15 s metadata, 120 s query; the user can stop a running query.

Pipeline badges (Generated / Validated read-only / Executed) are derived only from `sql`, `validation` and `executed` in the response. If a field is missing the badge says "not reported" instead of assuming success.

## Chart selection

`lib/chart-inference.ts`, in priority order:

1. A backend `chart` hint, if its columns exist in the result and it is sensible (pie ≤ 6 non-negative slices, ≤ 30 categories, ≤ 500 points).
2. Heuristic: one row → KPI figures; a date/time column (by type, by `year/month/date` names, or ISO values) → line, sorted by time; a text column → bars (horizontal when > 8 rows or long labels, and always on phones); otherwise no chart.
3. Key/ID columns (`*_KEY`, `*_ID`, codes) are never treated as measures. Extra measures are only plotted together when within 10× of the first, so one axis never flattens a series; the rest stay in the table.

Y axes start at zero. Pie is never chosen by the heuristic. "Highest / lowest" figures are only shown when the result is not truncated.

## Design system

Tokens in `src/app/globals.css` (`:root` / `[data-theme]`), exposed to Tailwind via `@theme inline`: surfaces `bg → surface → surface-2 → surface-3`, two border strengths, three text levels, indigo-violet accent with cyan secondary, status colors used only for state (always with an icon or label). Chart palette validated for contrast and colour-vision separation in both themes (dark: `#8b7dff #1fa5be #c2801f`, light: `#5b4cf0 #0e8fae #c27a12`). Radii 6/8/12/16 px. Motion: 150–320 ms ease-out entrances, shimmer skeletons; all disabled under `prefers-reduced-motion`. Dark is the default; light is complete.

## Demo mode

Opt-in from Settings, the offline callout, or `NEXT_PUBLIC_DEMO_MODE=true`. Uses the TPC-H SF1 table and column names. **Result values are illustrative and the SQL is not executed.** Every demo surface says so: a page-wide banner, "Demo fixture" badges, "Sample, not executed" on SQL, "Not executed (demo fixture)" in evidence, and demo tags in history. Questions outside the fixtures get an explicit "demo mode only knows the sample questions" message. Do not record the judged demo in demo mode.

## Quality checks run

- `npm run typecheck` (tsc strict): clean
- `npm run lint` (next/core-web-vitals + next/typescript): clean
- `npm test` (Vitest): 26 tests over chart inference, formatters and the API client (array-row normalisation, malformed JSON, contract-shaped error bodies, HTTP detail, network failure, optional suggestions 404)
- `npm run build`: succeeds; `/` first-load JS 144 kB (Recharts is loaded only when a chart is shown)
- Rendered with headless Chromium against a contract mock and in demo mode at 1440, 820 and 390 px, dark and light: success, zero rows, long SQL, 1,000 long rows with truncation, clarification, refusal, generation/validation/execution errors, malformed response, 6 s pending state, backend offline, provider switcher, mobile drawer. No horizontal overflow at 390 px. The only console errors were expected ones (404 from the optional suggestions endpoint on the mock, connection refused while the backend is deliberately offline).

## Remaining work (needs the backend)

1. Implement `/api/health`, `/api/schema`, `/api/query` per the contract, with CORS for the frontend origin.
2. Return `execution.provider_query_id` (Snowflake `QUERY_ID`) so evidence links to Snowflake query history (G2 recorded evidence).
3. Send `explanation.tables / filters / assumptions` from the pipeline so M4 is visible on every answer.
4. Optional: `/api/suggestions` with dataset-aware wording; a `chart` hint; `GET /api/history` if history should be shared across browsers.
5. Follow-up questions with context (send prior `query_id`), if the backend supports it.
6. Run a real-backend pass of the states above and record screenshots for the README.

## Screenshots

In `docs/screenshots/`. Files marked `demo` show labeled demo fixtures; `contract-mock` shows the UI against a local test mock of the API contract, not a real database. Neither is evidence of real query results. Some were captured before the final logo fix.
