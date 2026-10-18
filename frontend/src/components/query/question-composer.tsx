"use client";

import { ArrowUp, Database, Square } from "lucide-react";
import { useEffect, useId, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { Kbd } from "@/components/ui/badge";
import { useWorkspace } from "@/components/workspace-provider";
import { cn } from "@/lib/utils";

export const MAX_QUESTION_LENGTH = 1000;
const MIN_QUESTION_LENGTH = 3;

export function validateQuestion(q: string): string | null {
  const t = q.trim();
  if (!t) return "Type a question first.";
  if (t.length < MIN_QUESTION_LENGTH) return "That question is too short to interpret.";
  if (t.length > MAX_QUESTION_LENGTH) return `Questions can be at most ${MAX_QUESTION_LENGTH} characters.`;
  return null;
}

export function QuestionComposer({ variant = "hero", autoFocus }: { variant?: "hero" | "compact"; autoFocus?: boolean }) {
  const { draft, setDraft, runQuery, cancelQuery, query, provider, health, mode } = useWorkspace();
  const [error, setError] = useState<string | null>(null);
  const ref = useRef<HTMLTextAreaElement>(null);
  const errorId = useId();
  const hintId = useId();
  const running = query.phase === "running";
  const backendDown = health.state === "error";
  const providerDown = !!provider && !provider.connected;
  const blocked = backendDown || providerDown;

  // Auto-grow the textarea up to a limit.
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, variant === "hero" ? 240 : 180)}px`;
  }, [draft, variant]);

  useEffect(() => {
    if (autoFocus) ref.current?.focus({ preventScroll: true });
  }, [autoFocus]);

  const submit = (e?: FormEvent) => {
    e?.preventDefault();
    if (running) return;
    const problem = validateQuestion(draft);
    setError(problem);
    if (problem || blocked) return;
    runQuery(draft);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  };

  const sourceLabel = provider
    ? [provider.label ?? provider.id, provider.schema ?? provider.database].filter(Boolean).join(" · ")
    : backendDown
      ? "Backend offline"
      : "Connecting…";

  const length = draft.trim().length;
  const nearLimit = length > MAX_QUESTION_LENGTH * 0.85;
  const hero = variant === "hero";

  return (
    <form onSubmit={submit} className="w-full" noValidate>
      <div
        className={cn(
          "rounded-md border bg-surface transition-[border-color,box-shadow] duration-100",
          "focus-within:border-accent focus-within:shadow-[0_0_0_1px_var(--accent)]",
          error ? "border-danger/60" : "border-line-strong hover:border-faint",
        )}
      >
        <label htmlFor="dm-question" className="sr-only">
          Ask a question about your data
        </label>
        <textarea
          id="dm-question"
          ref={ref}
          value={draft}
          onChange={(e) => {
            setDraft(e.target.value);
            if (error) setError(null);
          }}
          onKeyDown={onKeyDown}
          rows={hero ? 2 : 1}
          maxLength={MAX_QUESTION_LENGTH + 200}
          placeholder={hero ? "e.g. Which product category had the highest revenue last quarter?" : "Ask another question…"}
          aria-invalid={!!error}
          aria-describedby={cn(error && errorId, hintId) || undefined}
          className={cn(
            "block w-full resize-none bg-transparent text-fg placeholder:text-faint focus:outline-none",
            hero ? "px-3.5 pt-3 pb-1 text-[15px] leading-relaxed" : "px-3 pt-2.5 pb-1 text-[14px] leading-relaxed",
          )}
        />
        <div className="flex items-center gap-3 px-3 pb-2">
          <span id={hintId} className="inline-flex min-w-0 items-center gap-1.5 text-[11px] text-faint" title="Questions run against this data source">
            <Database className="size-3 shrink-0" />
            <span className="truncate font-mono">{sourceLabel}</span>
            {mode === "demo" && <span className="text-warning">demo</span>}
          </span>
          {nearLimit && (
            <span className={cn("tnum text-[11px]", length > MAX_QUESTION_LENGTH ? "text-danger" : "text-faint")}>
              {length}/{MAX_QUESTION_LENGTH}
            </span>
          )}
          <span className="ml-auto hidden items-center gap-1 text-[11px] text-faint md:inline-flex">
            <Kbd>Enter</Kbd> to ask, <Kbd>Shift</Kbd>+<Kbd>Enter</Kbd> for a new line
          </span>
          {running ? (
            <button
              type="button"
              onClick={cancelQuery}
              className="ml-auto inline-flex h-7 items-center gap-1.5 rounded-md border border-line-strong px-2.5 text-xs font-medium text-fg transition-colors hover:bg-surface-2 md:ml-0"
            >
              <Square className="size-2.5 fill-current" />
              Stop
            </button>
          ) : (
            <button
              type="submit"
              disabled={blocked}
              aria-label="Ask question"
              title={blocked ? "The data source is not connected" : "Ask (Enter)"}
              className={cn(
                "ml-auto inline-flex size-7 items-center justify-center rounded-md transition-colors duration-100 md:ml-0",
                "bg-primary text-primary-fg hover:bg-primary-hover disabled:cursor-not-allowed disabled:opacity-35",
                length === 0 && "opacity-50",
              )}
            >
              <ArrowUp className="size-4" strokeWidth={2.25} />
            </button>
          )}
        </div>
      </div>
      <div aria-live="polite" className="min-h-0">
        {error && (
          <p id={errorId} className="mt-1.5 text-xs text-danger">
            {error}
          </p>
        )}
        {!error && blocked && !running && (
          <p className="mt-1.5 text-xs text-muted">
            {backendDown ? "The backend is not reachable, so questions cannot run right now." : "The selected data source is not connected."}
          </p>
        )}
      </div>
    </form>
  );
}
