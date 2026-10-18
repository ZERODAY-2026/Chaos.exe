"use client";

import { useEffect, useState } from "react";
import { Spinner } from "@/components/ui/spinner";
import { useWorkspace } from "@/components/workspace-provider";

/** Honest pending state: shows the real elapsed time, no invented stages or percentages. */
export function QueryPending({ question, startedAt }: { question: string; startedAt: number }) {
  const { provider, mode } = useWorkspace();
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 100);
    return () => clearInterval(t);
  }, []);
  const elapsed = Math.max(0, now - startedAt);
  return (
    <div role="status" aria-live="polite" className="enter flex flex-wrap items-center gap-x-3 gap-y-1 rounded-xl border border-accent/25 bg-accent-soft px-4 py-3">
      <Spinner className="size-4 text-accent" />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-fg">{question}</p>
        <p className="text-xs text-muted">
          {mode === "demo" ? "Loading sample response…" : `Waiting for DataMind to answer using ${provider?.label ?? "the backend"}…`}
        </p>
      </div>
      <span className="tnum text-xs text-muted" aria-label="Elapsed time">
        {(elapsed / 1000).toFixed(1)} s
      </span>
    </div>
  );
}
