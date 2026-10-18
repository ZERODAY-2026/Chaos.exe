import { AlertTriangle, Filter, Lightbulb, Sparkles, Table } from "lucide-react";
import type { ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import type { QueryResult } from "@/lib/api-types";
import { formatRelativeTime } from "@/lib/formatters";

function ExplainList({ icon, label, items }: { icon: ReactNode; label: string; items?: string[] | null }) {
  if (!items?.length) return null;
  return (
    <div className="min-w-0">
      <dt className="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold tracking-wide text-faint uppercase">
        {icon}
        {label}
      </dt>
      <dd>
        <ul className="space-y-1">
          {items.map((t) => (
            <li key={t} className="text-[13px] leading-snug break-words text-muted">
              {t}
            </li>
          ))}
        </ul>
      </dd>
    </div>
  );
}

export function SourceBadge({ source }: { source: QueryResult["source"] }) {
  return source === "demo" ? <Badge tone="warning">Demo fixture</Badge> : <Badge tone="accent">Live</Badge>;
}

export function AnswerSummary({ result, fromHistory }: { result: QueryResult; fromHistory?: boolean }) {
  const r = result.response;
  const ex = r.explanation;
  const warnings = r.warnings?.filter(Boolean) ?? [];
  const rowCount = r.row_count ?? r.rows?.length ?? 0;

  return (
    <section aria-labelledby="answer-heading" className="enter relative overflow-hidden rounded-xl border border-line bg-surface">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-32 [background:var(--glow)]" aria-hidden="true" />
      <div className="relative p-5 sm:p-6">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <span className="inline-flex items-center gap-1.5 text-xs font-medium text-accent">
            <Sparkles className="size-3.5" />
            Answer
          </span>
          <SourceBadge source={result.source} />
          {fromHistory && <Badge>Saved {formatRelativeTime(result.receivedAt)}</Badge>}
        </div>
        <h1 id="answer-heading" className="text-lg leading-snug font-semibold tracking-tight text-balance text-fg sm:text-xl">
          {result.question}
        </h1>
        {r.answer ? (
          <p className="mt-3 max-w-3xl text-[15px] leading-relaxed text-pretty text-fg/90">{r.answer}</p>
        ) : rowCount === 0 ? (
          <p className="mt-3 max-w-3xl text-[15px] leading-relaxed text-muted">The query ran and returned no rows.</p>
        ) : (
          <p className="mt-3 max-w-3xl text-[15px] leading-relaxed text-muted">
            The backend returned results without a written summary. See the rows and SQL below.
          </p>
        )}
        {ex?.summary && <p className="mt-2 max-w-3xl text-[13px] leading-relaxed text-muted">How it was computed: {ex.summary}</p>}

        {(ex?.tables?.length || ex?.filters?.length || ex?.assumptions?.length) ? (
          <dl className="mt-5 grid gap-x-6 gap-y-4 border-t border-line pt-4 sm:grid-cols-3">
            <ExplainList icon={<Table className="size-3" />} label="Tables" items={ex?.tables} />
            <ExplainList icon={<Filter className="size-3" />} label="Filters" items={ex?.filters} />
            <ExplainList icon={<Lightbulb className="size-3" />} label="Assumptions" items={ex?.assumptions} />
          </dl>
        ) : null}

        {warnings.length > 0 && (
          <div role="note" className="mt-4 flex gap-2 rounded-lg border border-warning/20 bg-warning-soft px-3 py-2.5 text-[13px] text-warning">
            <AlertTriangle className="mt-0.5 size-4 shrink-0" />
            <ul className="space-y-0.5">
              {warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </section>
  );
}
