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
    <div role="status" aria-live="polite" className="flex items-start gap-3">
      <Spinner className="mt-1 size-3.5 text-muted" />
      <div className="min-w-0 flex-1">
        <p className="text-[15px] leading-snug font-medium break-words text-fg">{question}</p>
        <p className="mt-0.5 text-xs text-muted">
          {mode === "demo" ? "Loading sample response…" : `Waiting for an answer from ${provider?.label ?? "the backend"}…`}
        </p>
      </div>
      <span className="tnum shrink-0 font-mono text-xs text-faint" aria-label="Elapsed time">
        {(elapsed / 1000).toFixed(1)}s
      </span>
    </div>
  );
}
