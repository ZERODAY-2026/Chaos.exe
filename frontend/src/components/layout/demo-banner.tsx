"use client";

import { useWorkspace } from "@/components/workspace-provider";

export function DemoBanner() {
  const { mode, setMode } = useWorkspace();
  if (mode !== "demo") return null;
  return (
    <div role="note" className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-line bg-warning-soft px-4 py-1.5 text-xs sm:px-5">
      <span className="font-medium text-warning">Demo mode</span>
      <span className="text-muted">Answers come from bundled sample fixtures. Nothing is queried and values are illustrative.</span>
      <button type="button" onClick={() => setMode("live")} className="font-medium text-fg underline decoration-line-strong underline-offset-2 hover:decoration-fg">
        Switch to live backend
      </button>
    </div>
  );
}
