"use client";

import { ArrowRight, Code2, FlaskConical, MessageSquareText, Plus, RotateCcw, ShieldCheck } from "lucide-react";
import { ResultsSkeleton } from "@/components/results/results-skeleton";
import { RequestFailedPanel } from "@/components/results/state-panels";
import { ResultView } from "@/components/results/result-view";
import { Button } from "@/components/ui/button";
import { useWorkspace } from "@/components/workspace-provider";
import { API_BASE_URL } from "@/lib/api-client";
import { QueryPending } from "./query-status";
import { QuestionComposer } from "./question-composer";
import { SuggestedQuestions } from "./suggested-questions";

const STEPS = [
  { icon: MessageSquareText, title: "Ask in plain language", body: "No SQL needed. Ask the way you would ask a colleague." },
  { icon: Code2, title: "Read-only SQL, validated", body: "The backend writes SQL, checks it is safe and read-only, then runs it." },
  { icon: ShieldCheck, title: "Answers with evidence", body: "See the exact query, the returned rows and how the answer was derived." },
];

function OfflineCallout() {
  const { health, refreshHealth, setMode, mode } = useWorkspace();
  if (health.state !== "error" || mode === "demo") return null;
  return (
    <div role="alert" className="enter mt-5 flex flex-col gap-3 rounded-xl border border-danger/25 bg-danger-soft px-4 py-3 sm:flex-row sm:items-center">
      <div className="min-w-0 flex-1 text-sm">
        <p className="font-medium text-fg">The DataMind backend is not reachable.</p>
        <p className="mt-0.5 text-xs text-muted">
          Start the API at <code className="font-mono text-fg">{API_BASE_URL}</code>, or explore the interface with labeled sample data.
        </p>
      </div>
      <div className="flex shrink-0 gap-2">
        <Button size="sm" variant="secondary" icon={<RotateCcw className="size-3.5" />} onClick={refreshHealth}>
          Retry
        </Button>
        <Button size="sm" variant="ghost" icon={<FlaskConical className="size-3.5" />} onClick={() => setMode("demo")}>
          Demo mode
        </Button>
      </div>
    </div>
  );
}

function Welcome() {
  return (
    <div className="relative mx-auto flex w-full max-w-3xl flex-col px-4 pt-[clamp(2rem,9vh,6rem)] pb-16 sm:px-6">
      <div className="pointer-events-none absolute inset-x-0 -top-10 h-80 [background:var(--glow)]" aria-hidden="true" />
      <div className="relative">
        <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-line bg-surface/70 py-1 pr-3 pl-1.5 text-xs text-muted">
          <span className="rounded-full bg-accent-soft px-2 py-0.5 font-medium text-accent">PS1</span>
          Natural language <ArrowRight className="size-3" /> SQL <ArrowRight className="size-3" /> evidence
        </div>
        <h1 className="text-[clamp(2rem,5vw,3.25rem)] leading-[1.05] font-semibold tracking-[-0.03em] text-fg">
          Your data,{" "}
          <span className="bg-gradient-to-r from-accent-strong via-accent to-cyan bg-clip-text text-transparent">understood.</span>
        </h1>
        <p className="mt-4 max-w-xl text-[15px] leading-relaxed text-muted">
          Ask a question in everyday language. DataMind queries your data at question time and shows the answer together with the SQL it ran and
          the rows behind it.
        </p>
        <div className="mt-8">
          <QuestionComposer variant="hero" autoFocus />
        </div>
        <OfflineCallout />
        <div className="mt-8">
          <SuggestedQuestions />
        </div>
        <ol className="mt-14 grid gap-px overflow-hidden rounded-xl border border-line bg-line sm:grid-cols-3">
          {STEPS.map(({ icon: Icon, title, body }, i) => (
            <li key={title} className="bg-bg p-4">
              <div className="flex items-center gap-2">
                <span className="tnum text-[11px] font-medium text-faint">0{i + 1}</span>
                <Icon className="size-4 text-accent" />
              </div>
              <h2 className="mt-3 text-[13px] font-semibold text-fg">{title}</h2>
              <p className="mt-1 text-xs leading-relaxed text-muted">{body}</p>
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}

export function AskDataWorkspace() {
  const { query, resetQuery, setDraft } = useWorkspace();

  if (query.phase === "idle") return <Welcome />;

  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-5 sm:px-6 sm:py-6">
      <div className="mb-5 flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <QuestionComposer variant="compact" />
        </div>
        <div className="mt-1.5 hidden sm:block">
        <Button
          variant="ghost"
          size="md"
          icon={<Plus className="size-4" />}
          onClick={() => {
            resetQuery();
            setDraft("");
          }}
        >
          New
        </Button>
        </div>
      </div>

      {query.phase === "running" && (
        <div className="space-y-4">
          <QueryPending question={query.question} startedAt={query.startedAt} />
          <ResultsSkeleton />
        </div>
      )}
      {query.phase === "failed" && <RequestFailedPanel question={query.question} error={query.error} />}
      {query.phase === "done" && (
        <ResultView
          key={query.result.response.query_id}
          result={query.result}
          fromHistory={query.fromHistory}
          rowsTrimmed={query.rowsTrimmed}
        />
      )}
      {query.phase === "done" && (
        <div className="mt-8 border-t border-line pt-6">
          <SuggestedQuestions layout="inline" />
        </div>
      )}
    </div>
  );
}
