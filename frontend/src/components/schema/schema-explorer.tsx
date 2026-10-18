"use client";

import { ChevronRight, CornerDownLeft, Database, RotateCcw, Search, Table2, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button, IconButton } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { useToast } from "@/components/ui/toast";
import { useWorkspace } from "@/components/workspace-provider";
import { useSchema } from "@/hooks/use-schema";
import type { TableInfo } from "@/lib/api-types";
import { formatNumber } from "@/lib/formatters";
import { cn } from "@/lib/utils";
import { PageFrame } from "@/components/layout/page-frame";
import { TypeIcon } from "./type-icon";

type Entry = { schema: string; table: TableInfo };

function Highlight({ text, q }: { text: string; q: string }) {
  if (!q) return <>{text}</>;
  const i = text.toLowerCase().indexOf(q.toLowerCase());
  if (i < 0) return <>{text}</>;
  return (
    <>
      {text.slice(0, i)}
      <mark className="rounded-sm bg-accent-soft text-fg">{text.slice(i, i + q.length)}</mark>
      {text.slice(i + q.length)}
    </>
  );
}

export function SchemaExplorer() {
  const schema = useSchema();
  const { mode, health, refreshHealth, setDraft, draft, resetQuery } = useWorkspace();
  const router = useRouter();
  const toast = useToast();
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<string | null>(null);

  const entries = useMemo<Entry[]>(
    () => schema.data?.schemas.flatMap((s) => s.tables.map((t) => ({ schema: s.name, table: t }))) ?? [],
    [schema.data],
  );

  const query = q.trim().toLowerCase();
  const filtered = useMemo(() => {
    if (!query) return entries;
    return entries.filter(
      (e) => e.table.name.toLowerCase().includes(query) || e.table.columns.some((c) => c.name.toLowerCase().includes(query)),
    );
  }, [entries, query]);

  const keyOf = (e: Entry) => `${e.schema}.${e.table.name}`;
  const active = filtered.find((e) => keyOf(e) === selected) ?? filtered[0] ?? null;
  const columnCount = entries.reduce((n, e) => n + e.table.columns.length, 0);

  const insert = (text: string) => {
    const next = draft.trim() ? `${draft.trimEnd()} ${text}` : text;
    setDraft(next);
    resetQuery();
    toast(`Added “${text}” to your question`);
    router.push("/");
  };

  if (health.state === "error") {
    return (
      <PageFrame title="Schema Explorer">
        <div className="panel">
          <EmptyState
            tone="danger"
            icon={<Database />}
            title="Schema unavailable"
            action={
              <Button variant="secondary" size="sm" icon={<RotateCcw className="size-3.5" />} onClick={refreshHealth}>
                Retry connection
              </Button>
            }
          >
            The backend is not reachable, so no table metadata can be shown.
          </EmptyState>
        </div>
      </PageFrame>
    );
  }

  return (
    <PageFrame title="Schema Explorer"
      subtitle={
        schema.data ? (
          <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="font-mono text-fg/80">{[schema.data.database, ...schema.data.schemas.map((s) => s.name)].filter(Boolean).join(" · ")}</span>
            <span className="tnum">
              {entries.length} tables · {formatNumber(columnCount)} columns
            </span>
            {mode === "demo" && <Badge tone="warning">Demo schema</Badge>}
          </span>
        ) : null
      }
    >
      {schema.status === "error" ? (
        <div className="panel">
          <EmptyState
            tone="danger"
            icon={<Database />}
            title="Could not load the schema"
            action={
              <Button variant="secondary" size="sm" icon={<RotateCcw className="size-3.5" />} onClick={schema.reload}>
                Try again
              </Button>
            }
          >
            {schema.error.message}
          </EmptyState>
        </div>
      ) : schema.status !== "ready" ? (
        <div className="grid gap-4 lg:grid-cols-[300px_1fr]" aria-busy="true" aria-label="Loading schema">
          <div className="panel space-y-2 p-3">
            {Array.from({ length: 7 }).map((_, i) => (
              <div key={i} className="skeleton h-9" />
            ))}
          </div>
          <div className="panel space-y-3 p-4">
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="skeleton h-6" />
            ))}
          </div>
        </div>
      ) : entries.length === 0 ? (
        <div className="panel">
          <EmptyState icon={<Table2 />} title="No tables found">
            The data source responded but reported no tables this account can read.
          </EmptyState>
        </div>
      ) : (
        <div className="grid items-start gap-4 lg:grid-cols-[300px_minmax(0,1fr)]">
          <div className="panel lg:sticky lg:top-20">
            <div className="border-b border-line p-2.5">
              <label className="relative block">
                <span className="sr-only">Search tables and columns</span>
                <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-faint" />
                <input
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  placeholder="Search tables and columns"
                  className="h-8 w-full rounded-md border border-line bg-surface-2 pr-8 pl-8 text-[13px] text-fg placeholder:text-faint focus:border-accent/50 focus:outline-none"
                />
                {q && (
                  <IconButton label="Clear search" size="sm" className="absolute top-1/2 right-1 size-6 -translate-y-1/2" onClick={() => setQ("")}>
                    <X className="size-3.5" />
                  </IconButton>
                )}
              </label>
            </div>
            {filtered.length === 0 ? (
              <p className="p-4 text-center text-xs text-muted">No tables or columns match “{q}”.</p>
            ) : (
              <ul className="max-h-[60vh] overflow-y-auto p-1.5" aria-label="Tables">
                {filtered.map((e) => {
                  const isActive = active && keyOf(active) === keyOf(e);
                  const colHits = query ? e.table.columns.filter((c) => c.name.toLowerCase().includes(query)).length : 0;
                  return (
                    <li key={keyOf(e)}>
                      <button
                        type="button"
                        onClick={() => setSelected(keyOf(e))}
                        aria-current={isActive ? "true" : undefined}
                        className={cn(
                          "flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left transition-colors",
                          isActive ? "bg-surface-2 text-fg" : "text-muted hover:bg-surface-2/60 hover:text-fg",
                        )}
                      >
                        <Table2 className={cn("size-3.5 shrink-0", isActive ? "text-accent" : "text-faint")} />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate font-mono text-[12.5px]">
                            <Highlight text={e.table.name} q={query} />
                          </span>
                          <span className="block text-[11px] text-faint">
                            {e.table.columns.length} columns
                            {colHits > 0 && <span className="text-accent"> · {colHits} match</span>}
                          </span>
                        </span>
                        {e.table.row_count !== null && e.table.row_count !== undefined && (
                          <span className="tnum text-[11px] text-faint">{formatNumber(e.table.row_count, { compact: true })}</span>
                        )}
                        <ChevronRight className={cn("size-3.5 shrink-0 text-faint", !isActive && "opacity-0")} />
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>

          {active && (
            <section className="panel enter min-w-0" key={keyOf(active)} aria-labelledby="table-heading">
              <header className="flex flex-wrap items-center gap-3 border-b border-line px-4 py-3">
                <div className="min-w-0">
                  <div className="text-[11px] text-faint">{active.schema}</div>
                  <h2 id="table-heading" className="truncate font-mono text-[15px] font-semibold text-fg">
                    {active.table.name}
                  </h2>
                </div>
                <div className="flex flex-wrap items-center gap-1.5">
                  <Badge>{active.table.columns.length} columns</Badge>
                  {active.table.row_count !== null && active.table.row_count !== undefined && (
                    <Badge>{formatNumber(active.table.row_count)} rows</Badge>
                  )}
                </div>
                <Button size="sm" variant="secondary" className="ml-auto" icon={<CornerDownLeft className="size-3.5" />} onClick={() => insert(active.table.name)}>
                  Use in question
                </Button>
              </header>
              {active.table.description && <p className="border-b border-line px-4 py-2.5 text-[13px] text-muted">{active.table.description}</p>}
              <div className="overflow-x-auto">
                <table className="w-full text-[13px]">
                  <thead>
                    <tr className="text-left text-[11px] font-semibold tracking-wide text-faint uppercase">
                      <th scope="col" className="px-4 py-2 font-semibold">Column</th>
                      <th scope="col" className="px-4 py-2 font-semibold">Type</th>
                      <th scope="col" className="hidden px-4 py-2 font-semibold md:table-cell">Description</th>
                      <th scope="col" className="w-10 px-2 py-2">
                        <span className="sr-only">Actions</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {active.table.columns.map((c) => {
                      const hit = query && c.name.toLowerCase().includes(query);
                      return (
                        <tr key={c.name} className={cn("group border-t border-line transition-colors hover:bg-surface-2/60", hit && "bg-accent-soft/50")}>
                          <td className="px-4 py-2">
                            <span className="flex items-center gap-2 font-mono text-[12.5px] text-fg">
                              <TypeIcon dataType={c.data_type} />
                              <Highlight text={c.name} q={query} />
                              {c.nullable === false && <span className="text-[10px] text-faint">not null</span>}
                            </span>
                          </td>
                          <td className="px-4 py-2 font-mono text-xs whitespace-nowrap text-muted">{c.data_type}</td>
                          <td className="hidden px-4 py-2 text-xs text-muted md:table-cell">{c.description ?? <span className="text-faint">—</span>}</td>
                          <td className="px-2 py-1.5 text-right">
                            <IconButton
                              size="sm"
                              label={`Add ${c.name} to question`}
                              className="opacity-60 group-hover:opacity-100 focus-visible:opacity-100"
                              onClick={() => insert(c.name)}
                            >
                              <CornerDownLeft className="size-3.5" />
                            </IconButton>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </section>
          )}
        </div>
      )}
    </PageFrame>
  );
}
