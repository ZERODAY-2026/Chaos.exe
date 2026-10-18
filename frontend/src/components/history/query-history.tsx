"use client";

import { RotateCcw, Search, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { PageFrame } from "@/components/layout/page-frame";
import { StatusIcon } from "@/components/layout/sidebar";
import { Badge } from "@/components/ui/badge";
import { Button, IconButton, buttonClass } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { useWorkspace } from "@/components/workspace-provider";
import { formatDuration, formatNumber, formatRelativeTime } from "@/lib/formatters";
import type { HistoryEntry } from "@/lib/history";
import { cn } from "@/lib/utils";

const STATUS_LABEL: Record<HistoryEntry["status"], string> = {
  success: "Answered",
  clarification_needed: "Needed clarification",
  refused: "Refused",
  error: "Failed",
  network_error: "Backend unreachable",
};

type Filter = "all" | "answered" | "attention";

export function QueryHistory() {
  const { history, hydrated, openHistoryEntry, runQuery, setDraft, removeHistoryEntry, clearHistory, health } = useWorkspace();
  const router = useRouter();
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const [confirmClear, setConfirmClear] = useState(false);
  const [, setTick] = useState(0);

  useEffect(() => {
    const t = setInterval(() => setTick((n) => n + 1), 30_000);
    return () => clearInterval(t);
  }, []);
  useEffect(() => {
    if (!confirmClear) return;
    const t = setTimeout(() => setConfirmClear(false), 4000);
    return () => clearTimeout(t);
  }, [confirmClear]);

  const list = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return history.filter((e) => {
      if (needle && !e.question.toLowerCase().includes(needle)) return false;
      if (filter === "answered") return e.status === "success";
      if (filter === "attention") return e.status !== "success";
      return true;
    });
  }, [history, q, filter]);

  const open = (e: HistoryEntry) => {
    openHistoryEntry(e);
    router.push("/");
  };
  const rerun = (e: HistoryEntry) => {
    setDraft(e.question);
    runQuery(e.question);
    router.push("/");
  };

  return (
    <PageFrame
      title="Query History"
      subtitle="Questions asked in this browser, newest first. History is stored locally and never sent anywhere."
      actions={
        history.length > 0 && (
          <Button
            size="sm"
            variant={confirmClear ? "danger" : "ghost"}
            icon={<Trash2 className="size-3.5" />}
            onClick={() => (confirmClear ? (clearHistory(), setConfirmClear(false)) : setConfirmClear(true))}
          >
            {confirmClear ? "Click again to clear all" : "Clear history"}
          </Button>
        )
      }
    >
      {!hydrated ? (
        <div className="panel divide-y divide-line overflow-hidden" aria-busy="true">
          {[0, 1, 2].map((i) => (
            <div key={i} className="p-4">
              <div className="skeleton h-4 w-2/3" />
              <div className="skeleton mt-2 h-3 w-1/3" />
            </div>
          ))}
        </div>
      ) : history.length === 0 ? (
        <div className="panel">
          <EmptyState
            title="No questions yet"
            action={
              <Link href="/" className={buttonClass("primary")}>
                Ask your first question
              </Link>
            }
          >
            Every question you ask is saved here with its status, so you can reopen the answer or run it again.
          </EmptyState>
        </div>
      ) : (
        <>
          <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center">
            <label className="relative block flex-1">
              <span className="sr-only">Search history</span>
              <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-faint" />
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Search questions"
                className="input pl-8 sm:max-w-sm"
              />
            </label>
            <div role="radiogroup" aria-label="Filter by status" className="flex rounded-md border border-line-strong p-0.5 sm:ml-auto">
              {(
                [
                  ["all", "All"],
                  ["answered", "Answered"],
                  ["attention", "Not answered"],
                ] as const
              ).map(([v, label]) => (
                <button
                  key={v}
                  type="button"
                  role="radio"
                  aria-checked={filter === v}
                  onClick={() => setFilter(v)}
                  className={cn(
                    "h-6 flex-1 rounded-sm px-2.5 text-xs font-medium transition-colors sm:flex-none",
                    filter === v ? "bg-surface-2 text-fg" : "text-muted hover:text-fg",
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
          {list.length === 0 ? (
            <div className="panel">
              <EmptyState title="Nothing matches">
                No saved questions match this search or filter.
              </EmptyState>
            </div>
          ) : (
            <ul className="panel divide-y divide-line overflow-hidden">
              {list.map((e) => (
                <li key={e.id} className="group flex flex-col gap-2 px-4 py-3 transition-colors hover:bg-surface-2/40 sm:flex-row sm:items-center">
                  <div className="flex min-w-0 flex-1 gap-3">
                    <StatusIcon status={e.status} className="mt-[3px]" />
                    <div className="min-w-0 flex-1">
                      <p className="text-[13px] leading-snug break-words text-fg">{e.question}</p>
                      <div className="mt-1 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-xs text-faint">
                        <span className={cn(e.status === "success" ? "text-success" : e.status === "clarification_needed" ? "text-cyan" : e.status === "refused" ? "text-warning" : "text-danger")}>
                          {STATUS_LABEL[e.status]}
                        </span>
                        {e.source === "demo" && <Badge tone="warning">Demo</Badge>}
                        {e.provider && <span>{e.provider}</span>}
                        {e.rowCount !== null && <span className="tnum">{formatNumber(e.rowCount)} rows</span>}
                        {e.durationMs !== null && <span className="tnum">{formatDuration(e.durationMs)}</span>}
                        <time dateTime={e.createdAt} title={new Date(e.createdAt).toLocaleString()}>
                          {formatRelativeTime(e.createdAt)}
                        </time>
                      </div>
                      {e.errorMessage && e.status !== "success" && <p className="mt-1 line-clamp-2 text-xs text-muted">{e.errorMessage}</p>}
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-0.5 pl-6 sm:pl-0 sm:opacity-70 sm:group-hover:opacity-100 sm:group-focus-within:opacity-100">
                    {e.result && (
                      <Button size="sm" variant="ghost" onClick={() => open(e)}>
                        Open
                      </Button>
                    )}
                    <Button size="sm" variant="ghost" icon={<RotateCcw className="size-3.5" />} onClick={() => rerun(e)} disabled={health.state !== "ok"}>
                      Ask again
                    </Button>
                    <IconButton size="sm" label="Remove from history" onClick={() => removeHistoryEntry(e.id)}>
                      <Trash2 className="size-3.5" />
                    </IconButton>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </PageFrame>
  );
}
