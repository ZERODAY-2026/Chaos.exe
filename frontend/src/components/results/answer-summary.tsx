import { Badge } from "@/components/ui/badge";
import type { QueryResult } from "@/lib/api-types";
import { formatRelativeTime } from "@/lib/formatters";

function ExplainList({ label, items }: { label: string; items?: string[] | null }) {
  if (!items?.length) return null;
  return (
    <div className="min-w-0">
      <dt className="eyebrow mb-1">{label}</dt>
      <dd>
        <ul className="space-y-0.5">
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
  return source === "demo" ? <Badge tone="warning">Demo fixture</Badge> : <Badge>Live</Badge>;
}

export function AnswerSummary({ result, fromHistory }: { result: QueryResult; fromHistory?: boolean }) {
  const r = result.response;
  const ex = r.explanation;
  const warnings = r.warnings?.filter(Boolean) ?? [];
  const rowCount = r.row_count ?? r.rows?.length ?? 0;

  return (
    <section aria-labelledby="answer-heading">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <SourceBadge source={result.source} />
        {fromHistory && <span className="text-xs text-faint">Saved {formatRelativeTime(result.receivedAt)}</span>}
      </div>
      <h1 id="answer-heading" className="text-lg leading-snug font-semibold tracking-tight text-balance text-fg">
        {result.question}
      </h1>
      {r.answer ? (
        <p className="mt-2 max-w-3xl text-[15px] leading-relaxed text-pretty text-fg">{r.answer}</p>
      ) : rowCount === 0 ? (
        <p className="mt-2 max-w-3xl text-[15px] leading-relaxed text-muted">The query ran and returned no rows.</p>
      ) : (
        <p className="mt-2 max-w-3xl text-[15px] leading-relaxed text-muted">
          The backend returned results without a written summary. See the rows and SQL below.
        </p>
      )}
      {ex?.summary && (
        <p className="mt-1.5 max-w-3xl text-[13px] leading-relaxed text-muted">
          <span className="text-faint">How it was computed: </span>
          {ex.summary}
        </p>
      )}

      {ex?.tables?.length || ex?.filters?.length || ex?.assumptions?.length ? (
        <dl className="mt-4 grid gap-x-8 gap-y-3 sm:grid-cols-3">
          <ExplainList label="Tables" items={ex?.tables} />
          <ExplainList label="Filters" items={ex?.filters} />
          <ExplainList label="Assumptions" items={ex?.assumptions} />
        </dl>
      ) : null}

      {warnings.length > 0 && (
        <div role="note" className="mt-4 max-w-3xl border-l-2 border-warning py-0.5 pl-3 text-[13px]">
          <p className="font-medium text-warning">{warnings.length === 1 ? "Warning" : "Warnings"}</p>
          <ul className="mt-0.5 space-y-0.5 text-muted">
            {warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
