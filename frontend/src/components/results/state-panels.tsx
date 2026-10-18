"use client";

import { ArrowRight, CircleHelp, FileWarning, FlaskConical, PlugZap, RotateCcw, ServerCrash, ShieldOff, TimerOff, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { useWorkspace } from "@/components/workspace-provider";
import { API_BASE_URL, type ApiError } from "@/lib/api-client";
import type { QueryResult } from "@/lib/api-types";
import { cn } from "@/lib/utils";
import { SourceBadge } from "./answer-summary";
import { PipelineBadges } from "./pipeline-badges";
import { SqlBlock } from "./sql-inspector";

function StatePanel({
  tone,
  icon,
  eyebrow,
  title,
  children,
  actions,
}: {
  tone: "danger" | "warning" | "cyan";
  icon: ReactNode;
  eyebrow: ReactNode;
  title: string;
  children?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <section role={tone === "danger" ? "alert" : "status"} className="panel px-5 py-4 sm:px-6 sm:py-5">
      <div className="mb-1.5 flex flex-wrap items-center gap-2 text-xs text-faint">
        <span
          className={cn(
            "inline-flex [&>svg]:size-3.5",
            tone === "danger" && "text-danger",
            tone === "warning" && "text-warning",
            tone === "cyan" && "text-cyan",
          )}
          aria-hidden="true"
        >
          {icon}
        </span>
        {eyebrow}
      </div>
      <h2 className="max-w-3xl text-[15px] leading-snug font-semibold text-balance text-fg">{title}</h2>
      {children && <div className="mt-2 max-w-3xl space-y-3 text-[13px] leading-relaxed text-muted">{children}</div>}
      {actions && <div className="mt-4 flex flex-wrap gap-2">{actions}</div>}
    </section>
  );
}

export function ClarificationPanel({ result }: { result: QueryResult }) {
  const { runQuery, setDraft } = useWorkspace();
  const c = result.response.clarification;
  return (
    <StatePanel
      tone="cyan"
      icon={<CircleHelp />}
      eyebrow={
        <>
          <span>Needs clarification</span>
          <SourceBadge source={result.source} />
        </>
      }
      title={c?.question ?? "The question is ambiguous. Can you make it more specific?"}
    >
      <p>
        You asked: <span className="text-fg">“{result.question}”</span>. No SQL was run.
      </p>
      {c?.options?.length ? (
        <ul className="-mx-1 flex flex-col pt-1">
          {c.options.map((o) => (
            <li key={o}>
              <button
                type="button"
                onClick={() => {
                  setDraft(o);
                  runQuery(o);
                }}
                className="group flex w-full items-center gap-2 rounded-md px-1 py-1.5 text-left text-[13px] text-fg transition-colors hover:bg-surface-2"
              >
                <ArrowRight className="size-3.5 shrink-0 text-faint group-hover:text-fg" />
                {o}
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p>Rephrase your question in the box above with more detail.</p>
      )}
    </StatePanel>
  );
}

export function RefusedPanel({ result }: { result: QueryResult }) {
  const r = result.response;
  return (
    <StatePanel
      tone="warning"
      icon={<ShieldOff />}
      eyebrow={
        <>
          <span>Request not answered</span>
          <SourceBadge source={result.source} />
        </>
      }
      title={r.answer ?? r.error?.message ?? "DataMind declined this request."}
    >
      <p>
        You asked: <span className="text-fg">“{result.question}”</span>
      </p>
      {r.validation?.messages?.length ? (
        <ul className="list-inside list-disc text-[13px]">
          {r.validation.messages.map((m) => (
            <li key={m}>{m}</li>
          ))}
        </ul>
      ) : null}
      <p className="text-[13px]">DataMind answers read-only questions that the connected data can support. Try asking about what the data contains.</p>
    </StatePanel>
  );
}

const STAGE_COPY: Record<string, { title: string; hint: string }> = {
  generation: {
    title: "DataMind could not turn this question into SQL.",
    hint: "Try naming the measure and grouping you want, for example “total revenue by region”.",
  },
  validation: {
    title: "The generated SQL failed validation, so it was not run.",
    hint: "Validation blocks anything that is not a safe, read-only query. Rephrasing usually helps.",
  },
  execution: {
    title: "The query failed while running on the data source.",
    hint: "The SQL below is what was attempted. Check the message, then try again or rephrase.",
  },
  internal: {
    title: "The backend hit an internal error.",
    hint: "This is not caused by your question. Try again in a moment.",
  },
};

export function ResponseErrorPanel({ result }: { result: QueryResult }) {
  const { runQuery, setMode } = useWorkspace();
  const r = result.response;

  if (r.error?.code === "DEMO_UNSUPPORTED") {
    return (
      <StatePanel
        tone="warning"
        icon={<FlaskConical />}
        eyebrow={<SourceBadge source="demo" />}
        title="Demo mode only knows the sample questions."
        actions={
          <Button size="sm" onClick={() => setMode("live")}>
            Switch to live backend
          </Button>
        }
      >
        <p>{r.error.message}</p>
      </StatePanel>
    );
  }

  const stage = r.error?.stage ?? "internal";
  const copy = STAGE_COPY[stage] ?? STAGE_COPY.internal!;
  return (
    <StatePanel
      tone="danger"
      icon={stage === "execution" ? <ServerCrash /> : <TriangleAlert />}
      eyebrow={
        <>
          <span className="capitalize">{stage} error</span>
          {r.error?.code && <span className="font-mono">{r.error.code}</span>}
          <SourceBadge source={result.source} />
        </>
      }
      title={copy.title}
      actions={
        <Button size="sm" icon={<RotateCcw className="size-3.5" />} onClick={() => runQuery(result.question)}>
          Try again
        </Button>
      }
    >
      {r.error?.message && <p className="rounded-md border border-line bg-bg px-3 py-2 font-mono text-xs break-words text-fg">{r.error.message}</p>}
      <p>{copy.hint}</p>
      {r.sql && (
        <div className="space-y-2 pt-1">
          <PipelineBadges response={r} />
          <SqlBlock sql={r.sql} collapsedLines={8} />
        </div>
      )}
    </StatePanel>
  );
}

export function RequestFailedPanel({ question, error }: { question: string; error: ApiError }) {
  const { runQuery, refreshHealth, setMode } = useWorkspace();
  const retry = (
    <Button size="sm" icon={<RotateCcw className="size-3.5" />} onClick={() => runQuery(question)}>
      Try again
    </Button>
  );

  if (error.kind === "network") {
    return (
      <StatePanel
        tone="danger"
        icon={<PlugZap />}
        eyebrow="Backend unavailable"
        title="DataMind could not reach the backend."
        actions={
          <>
            {retry}
            <Button variant="ghost" size="sm" onClick={refreshHealth}>
              Check connection
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setMode("demo")}>
              Explore demo mode
            </Button>
          </>
        }
      >
        <p>
          Your question was not run. Make sure the API is running at <code className="font-mono text-xs text-fg">{API_BASE_URL}</code>.
        </p>
      </StatePanel>
    );
  }
  if (error.kind === "timeout") {
    return (
      <StatePanel tone="warning" icon={<TimerOff />} eyebrow="Timed out" title="The backend took too long to answer." actions={retry}>
        <p>{error.message} The query may still be running on the backend. Try again, or ask a narrower question.</p>
      </StatePanel>
    );
  }
  if (error.kind === "malformed") {
    return (
      <StatePanel tone="danger" icon={<FileWarning />} eyebrow="Unexpected response" title="The backend answered in a format DataMind does not understand." actions={retry}>
        <p>To avoid showing something misleading, the response was not displayed.</p>
        {error.detail && <p className="font-mono text-xs break-words text-fg">{error.detail}</p>}
      </StatePanel>
    );
  }
  return (
    <StatePanel
      tone="danger"
      icon={<ServerCrash />}
      eyebrow={error.status ? `HTTP ${error.status}` : "Request failed"}
      title={error.status === 422 ? "The backend rejected the request as invalid." : "The request failed."}
      actions={retry}
    >
      <p>{error.message}</p>
      {error.detail && <p className="font-mono text-xs break-words text-fg">{error.detail}</p>}
    </StatePanel>
  );
}
