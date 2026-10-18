"use client";

import { Inbox } from "lucide-react";
import dynamic from "next/dynamic";
import { useMemo } from "react";
import { EmptyState } from "@/components/ui/empty-state";
import type { QueryResult } from "@/lib/api-types";
import { inferChart } from "@/lib/chart-inference";
import { AnswerSummary } from "./answer-summary";
import { EvidencePanel } from "./evidence-panel";
import { MetricGrid } from "./metric-grid";
import { ResultsTable } from "./results-table";
import { SqlInspector } from "./sql-inspector";
import { ClarificationPanel, RefusedPanel, ResponseErrorPanel } from "./state-panels";

// Recharts is only needed once a result has a chart, so it loads on demand.
const ChartView = dynamic(() => import("./chart-view").then((m) => m.ChartView), {
  ssr: false,
  loading: () => <div className="panel skeleton h-[360px]" aria-hidden="true" />,
});

export function ResultView({ result, fromHistory, rowsTrimmed }: { result: QueryResult; fromHistory?: boolean; rowsTrimmed?: boolean }) {
  const r = result.response;
  const rows = useMemo(() => r.rows ?? [], [r.rows]);
  const columns = useMemo(
    () => r.columns ?? (rows[0] ? Object.keys(rows[0]).map((name) => ({ name, data_type: null })) : []),
    [r.columns, rows],
  );
  const spec = useMemo(() => inferChart(columns, rows, r.chart), [columns, rows, r.chart]);
  const truncated = !!r.truncated || !!rowsTrimmed || (r.row_count ?? rows.length) > rows.length;

  if (r.status === "clarification_needed") return <ClarificationPanel result={result} />;
  if (r.status === "refused") return <RefusedPanel result={result} />;
  if (r.status === "error") return <ResponseErrorPanel result={result} />;

  const stem = `datamind-${r.query_id}`.replace(/[^a-z0-9-]/gi, "-").slice(0, 60);

  return (
    <div className="space-y-4">
      <AnswerSummary result={result} fromHistory={fromHistory} />
      <MetricGrid spec={spec} rows={rows} columns={columns} truncated={truncated} />
      {spec && spec.kind !== "kpi" && <ChartView spec={spec} rows={rows} />}
      {rows.length > 0 ? (
        <ResultsTable
          columns={columns}
          rows={rows}
          totalRowCount={r.row_count}
          truncated={r.truncated}
          rowLimit={r.validation?.limit_applied}
          trimmedForHistory={rowsTrimmed}
          fileStem={stem}
        />
      ) : (
        <section className="panel enter">
          <EmptyState icon={<Inbox />} title={result.source === "demo" ? "This sample response has no rows" : "The query returned no rows"}>
            {r.executed === true
              ? "The SQL ran without errors, but nothing matched. Check the filters in the SQL below, or broaden the question."
              : "No rows came back for this question. Check the filters in the SQL below, or broaden the question."}
          </EmptyState>
        </section>
      )}
      <div className="grid items-start gap-4 xl:grid-cols-5">
        <div className="min-w-0 xl:col-span-3">
          <SqlInspector response={r} isDemo={result.source === "demo"} />
        </div>
        <div className="min-w-0 xl:col-span-2">
          <EvidencePanel result={result} />
        </div>
      </div>
    </div>
  );
}
