"use client";

import { Check, ChevronDown, Copy } from "lucide-react";
import { useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button, IconButton } from "@/components/ui/button";
import { Panel } from "@/components/ui/panel";
import { useToast } from "@/components/ui/toast";
import type { QueryResponse } from "@/lib/api-types";
import { tokenizeSql } from "@/lib/sql-highlight";
import { cn, copyText } from "@/lib/utils";
import { PipelineBadges } from "./pipeline-badges";

const tokenClass: Record<string, string> = {
  keyword: "text-[var(--code-keyword)]",
  function: "text-[var(--code-func)]",
  string: "text-[var(--code-string)]",
  number: "text-[var(--code-number)]",
  comment: "text-[var(--code-comment)] italic",
  operator: "text-muted",
  identifier: "text-fg",
  space: "",
};

export function SqlBlock({ sql, collapsedLines = 14 }: { sql: string; collapsedLines?: number }) {
  const [expanded, setExpanded] = useState(false);
  const tokens = useMemo(() => tokenizeSql(sql), [sql]);
  const lineCount = sql.split("\n").length;
  const long = lineCount > collapsedLines || sql.length > 900;

  return (
    <div className="relative">
      <pre
        className={cn(
          "overflow-x-auto rounded-md border border-line bg-bg p-3.5 font-mono text-[12.5px] leading-[1.65] whitespace-pre-wrap break-words",
          long && !expanded && "max-h-[260px] overflow-hidden",
        )}
      >
        <code>
          {tokens.map((t, i) => (
            <span key={i} className={tokenClass[t.type]}>
              {t.text}
            </span>
          ))}
        </code>
      </pre>
      {long && (
        <div className={cn("flex justify-center", !expanded && "absolute inset-x-px bottom-px rounded-b-md border-t border-line bg-bg py-1")}>
          <button
            type="button"
            onClick={() => setExpanded((e) => !e)}
            aria-expanded={expanded}
            className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-muted hover:bg-surface-2 hover:text-fg"
          >
            <ChevronDown className={cn("size-3.5 transition-transform", expanded && "rotate-180")} />
            {expanded ? "Collapse" : `Show all ${lineCount} lines`}
          </button>
        </div>
      )}
    </div>
  );
}

export function SqlInspector({ response, isDemo }: { response: QueryResponse; isDemo: boolean }) {
  const [copied, setCopied] = useState(false);
  const [open, setOpen] = useState(true);
  const toast = useToast();
  const sql = response.sql?.trim();
  const messages = response.validation?.messages?.filter(Boolean) ?? [];

  const copy = async () => {
    if (!sql) return;
    const ok = await copyText(sql);
    if (ok) {
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } else toast("Copy failed. Your browser blocked clipboard access.", "error");
  };

  return (
    <Panel
      id="sql"
      title="SQL"
      meta={isDemo ? <Badge tone="warning">Sample, not executed</Badge> : null}
      actions={
        <>
          {sql && (
            <Button
              size="sm"
              variant="ghost"
              onClick={copy}
              icon={copied ? <Check className="size-3.5 text-success" /> : <Copy className="size-3.5" />}
            >
              {copied ? "Copied" : "Copy"}
            </Button>
          )}
          <IconButton label={open ? "Hide SQL" : "Show SQL"} onClick={() => setOpen((o) => !o)} size="sm" aria-expanded={open}>
            <ChevronDown className={cn("size-4 transition-transform", !open && "-rotate-90")} />
          </IconButton>
        </>
      }
    >
      <span className="sr-only" aria-live="polite">
        {copied ? "SQL copied to clipboard" : ""}
      </span>
      <PipelineBadges response={response} />
      {open && (
        <div className="mt-3 space-y-3">
          {sql ? <SqlBlock sql={sql} /> : <p className="text-sm text-muted">The backend did not return SQL for this response.</p>}
          {messages.length > 0 && (
            <ul className="space-y-0.5 border-l-2 border-line-strong pl-3 text-xs text-muted">
              {messages.map((m) => (
                <li key={m}>{m}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </Panel>
  );
}
