"use client";

import { Plus } from "lucide-react";
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
  { title: "Ask", body: "Write the question the way you would ask a colleague." },
  { title: "Validate", body: "The backend writes SQL and checks it is a single read-only SELECT before running it." },
  { title: "Verify", body: "Every answer shows the SQL that ran, the rows it returned and where they came from." },
];

function OfflineCallout() {
  const { health, refreshHealth, setMode, mode } = useWorkspace();
  if (health.state !== "error" || mode === "demo") return null;
  return (
    <div role="alert" className="mt-4 flex flex-col gap-3 rounded-md border border-danger/30 px-4 py-3 sm:flex-row sm:items-center">
      <div className="min-w-0 flex-1">
        <p className="text-[13px] font-medium text-danger">The DataMind backend is not reachable.</p>
        <p className="mt-0.5 text-xs text-muted">
          Start the API at <code className="font-mono text-fg">{API_BASE_URL}</code>, or explore the interface with labelled sample data.
        </p>
      </div>
      <div className="flex shrink-0 gap-2">
        <Button size="sm" onClick={refreshHealth}>
          Retry
        </Button>
        <Button size="sm" variant="ghost" onClick={() => setMode("demo")}>
          Use demo mode
        </Button>
      </div>
    </div>
  );
}

function Welcome() {
  return (
    <div className="mx-auto w-full max-w-3xl px-4 pt-[clamp(2rem,10vh,6rem)] pb-16 sm:px-8">
      <h1 className="text-2xl font-semibold tracking-tight text-fg">Ask a question about your data</h1>
      <p className="mt-2 max-w-xl text-[14px] leading-relaxed text-muted">
        DataMind turns plain-language questions into read-only SQL, runs it against the connected source and shows you exactly what ran.
      </p>
      <div className="mt-6">
        <QuestionComposer variant="hero" autoFocus />
      </div>
      <OfflineCallout />
      <div className="mt-8">
        <SuggestedQuestions />
      </div>
      <ol className="mt-12 grid gap-6 border-t border-line pt-6 sm:grid-cols-3">
        {STEPS.map(({ title, body }, i) => (
          <li key={title}>
            <h2 className="text-[13px] font-medium text-fg">
              <span className="tnum mr-2 text-faint">{i + 1}</span>
              {title}
            </h2>
            <p className="mt-1 text-[13px] leading-relaxed text-muted">{body}</p>
          </li>
        ))}
      </ol>
    </div>
  );
}

export function AskDataWorkspace() {
  const { query, resetQuery, setDraft } = useWorkspace();

  if (query.phase === "idle") return <Welcome />;

  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-5 sm:px-8 sm:py-6">
      <div className="mb-6 flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <QuestionComposer variant="compact" />
        </div>
        <div className="mt-1 hidden sm:block">
          <Button
            variant="ghost"
            icon={<Plus className="size-3.5" />}
            onClick={() => {
              resetQuery();
              setDraft("");
            }}
          >
            New question
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
        <div className="mt-10 border-t border-line pt-5">
          <SuggestedQuestions layout="inline" />
        </div>
      )}
    </div>
  );
}
