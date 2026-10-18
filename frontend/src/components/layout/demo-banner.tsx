"use client";

import { FlaskConical } from "lucide-react";
import { useWorkspace } from "@/components/workspace-provider";

export function DemoBanner() {
  const { mode, setMode } = useWorkspace();
  if (mode !== "demo") return null;
  return (
    <div role="note" className="flex flex-wrap items-center justify-center gap-x-3 gap-y-1 border-b border-warning/20 bg-warning-soft px-4 py-1.5 text-center text-xs text-warning">
      <span className="inline-flex items-center gap-1.5 font-medium">
        <FlaskConical className="size-3.5" />
        Demo mode
      </span>
      <span className="text-fg/80">Answers come from bundled sample fixtures. Nothing is queried and values are illustrative.</span>
      <button type="button" onClick={() => setMode("live")} className="font-medium underline underline-offset-2 hover:text-fg">
        Switch to live backend
      </button>
    </div>
  );
}
