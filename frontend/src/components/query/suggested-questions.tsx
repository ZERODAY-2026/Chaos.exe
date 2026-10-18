"use client";

import { CornerDownRight, Sparkles } from "lucide-react";
import { useSuggestions } from "@/hooks/use-suggestions";
import { useWorkspace } from "@/components/workspace-provider";
import { cn } from "@/lib/utils";

const SOURCE_LABEL = {
  backend: "Suggested from your dataset",
  schema: "Generated from the connected schema",
  none: "",
} as const;

export function SuggestedQuestions({ layout = "grid" }: { layout?: "grid" | "inline" }) {
  const { questions, source, loading } = useSuggestions();
  const { runQuery, setDraft, query, mode, health } = useWorkspace();
  const disabled = query.phase === "running" || health.state !== "ok";

  if (loading) {
    return (
      <div className={cn(layout === "grid" ? "grid gap-2 sm:grid-cols-2" : "flex flex-wrap gap-2")} aria-hidden="true">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className={cn("skeleton", layout === "grid" ? "h-12" : "h-8 w-56")} />
        ))}
      </div>
    );
  }
  if (!questions.length) return null;

  const label = mode === "demo" ? "Sample questions available in demo mode" : SOURCE_LABEL[source];

  return (
    <div>
      <div className="mb-2.5 flex items-center gap-1.5 text-xs text-faint">
        <Sparkles className="size-3.5 text-accent" />
        <span>{label}</span>
        <span className="hidden sm:inline">· select one to ask it</span>
      </div>
      <ul className={cn(layout === "grid" ? "grid gap-2 sm:grid-cols-2" : "flex flex-wrap gap-2")}>
        {questions.map((q) => (
          <li key={q} className="min-w-0">
            <button
              type="button"
              disabled={disabled}
              onClick={() => {
                setDraft(q);
                runQuery(q);
              }}
              className={cn(
                "group flex w-full min-w-0 items-center gap-2.5 text-left text-[13px] text-muted transition-all duration-150",
                "border border-line bg-surface/60 hover:border-accent/40 hover:bg-surface hover:text-fg",
                "disabled:cursor-not-allowed disabled:opacity-50",
                layout === "grid" ? "rounded-xl px-3.5 py-3" : "rounded-lg px-3 py-1.5",
              )}
            >
              <CornerDownRight className="size-3.5 shrink-0 text-faint transition-colors group-hover:text-accent" />
              <span className={cn(layout === "grid" ? "line-clamp-2" : "truncate")}>{q}</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
