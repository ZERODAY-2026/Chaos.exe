"use client";

import { ArrowRight } from "lucide-react";
import { useSuggestions } from "@/hooks/use-suggestions";
import { useWorkspace } from "@/components/workspace-provider";
import { cn } from "@/lib/utils";

const SOURCE_LABEL = {
  backend: "Suggested from your dataset",
  schema: "Based on the connected schema",
  none: "",
} as const;

export function SuggestedQuestions({ layout = "grid" }: { layout?: "grid" | "inline" }) {
  const { questions, source, loading } = useSuggestions();
  const { runQuery, setDraft, query, mode, health } = useWorkspace();
  const disabled = query.phase === "running" || health.state !== "ok";

  if (loading) {
    return (
      <div className="space-y-2" aria-hidden="true">
        {[0, 1, 2].map((i) => (
          <div key={i} className="skeleton h-4 w-2/3" />
        ))}
      </div>
    );
  }
  if (!questions.length) return null;

  const label = mode === "demo" ? "Sample questions (demo mode)" : SOURCE_LABEL[source];
  const inline = layout === "inline";

  return (
    <div>
      <h2 className="eyebrow mb-2">{inline ? "Ask next" : label || "Try asking"}</h2>
      <ul className={cn(inline ? "flex flex-wrap gap-2" : "-mx-2 divide-y divide-line")}>
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
                "group flex w-full min-w-0 items-center gap-3 text-left text-[13px] text-muted transition-colors duration-100",
                "hover:text-fg disabled:cursor-not-allowed disabled:opacity-50",
                inline ? "h-7 rounded-md border border-line-strong px-2.5 hover:bg-surface-2" : "rounded-md px-2 py-2 hover:bg-surface",
              )}
            >
              <span className="truncate">{q}</span>
              {!inline && (
                <ArrowRight className="ml-auto size-3.5 shrink-0 text-faint opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100" />
              )}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
