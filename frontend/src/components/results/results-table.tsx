"use client";

import { ClipboardCopy, Download, Info, Table2 } from "lucide-react";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Panel } from "@/components/ui/panel";
import { useToast } from "@/components/ui/toast";
import type { ResultColumn } from "@/lib/api-types";
import { formatCell, formatNumber, isNumericType, toNumber } from "@/lib/formatters";
import { cn, copyText, downloadFile, toCsv } from "@/lib/utils";

const PAGE_SIZE = 50;

type Props = {
  columns: ResultColumn[];
  rows: Array<Record<string, unknown>>;
  totalRowCount?: number | null;
  truncated?: boolean | null;
  rowLimit?: number | null;
  trimmedForHistory?: boolean;
  fileStem?: string;
};

export function ResultsTable({ columns, rows, totalRowCount, truncated, rowLimit, trimmedForHistory, fileStem = "datamind-result" }: Props) {
  const [visible, setVisible] = useState(PAGE_SIZE);
  const toast = useToast();

  const numericCols = useMemo(() => {
    const set = new Set<string>();
    for (const c of columns) {
      if (isNumericType(c.data_type)) set.add(c.name);
      else if (!c.data_type) {
        const sample = rows.slice(0, 20).map((r) => r[c.name]).filter((v) => v !== null && v !== undefined);
        if (sample.length && sample.every((v) => toNumber(v) !== null)) set.add(c.name);
      }
    }
    return set;
  }, [columns, rows]);

  const names = columns.map((c) => c.name);
  const shown = rows.slice(0, visible);
  const backendTotal = totalRowCount ?? rows.length;
  const partial = !!truncated || backendTotal > rows.length;

  const copyCsv = async () => {
    const ok = await copyText(toCsv(names, rows));
    toast(ok ? `Copied ${formatNumber(rows.length)} rows as CSV` : "Copy failed. Your browser blocked clipboard access.", ok ? "success" : "error");
  };

  return (
    <Panel
      id="table"
      title="Results"
      icon={<Table2 />}
      meta={
        <span className="tnum">
          {formatNumber(rows.length)} {rows.length === 1 ? "row" : "rows"} · {columns.length} {columns.length === 1 ? "column" : "columns"}
        </span>
      }
      actions={
        rows.length > 0 && (
          <>
            <Button size="sm" variant="ghost" icon={<ClipboardCopy className="size-3.5" />} onClick={copyCsv}>
              <span className="hidden sm:inline">Copy CSV</span>
              <span className="sm:hidden">Copy</span>
            </Button>
            <Button
              size="sm"
              variant="ghost"
              icon={<Download className="size-3.5" />}
              onClick={() => downloadFile(`${fileStem}.csv`, toCsv(names, rows))}
            >
              <span className="hidden sm:inline">Download</span>
              <span className="sr-only sm:hidden">Download CSV</span>
            </Button>
          </>
        )
      }
      bodyClassName="p-0"
    >
      {(partial || trimmedForHistory) && (
        <div className="flex items-start gap-2 border-b border-line bg-warning-soft px-4 py-2 text-xs text-warning">
          <Info className="mt-px size-3.5 shrink-0" />
          <span>
            {trimmedForHistory
              ? `This saved result keeps the first ${formatNumber(rows.length)} rows. Ask the question again to load the full result.`
              : `Showing the ${formatNumber(rows.length)} rows the backend returned${
                  totalRowCount && totalRowCount > rows.length ? ` out of ${formatNumber(totalRowCount)}` : ""
                }${rowLimit ? ` (row limit ${formatNumber(rowLimit)})` : ""}. The full result is larger, so totals over these rows may be incomplete.`}
          </span>
        </div>
      )}
      <div className="max-h-[560px] overflow-auto" tabIndex={0} role="region" aria-label="Result rows">
        <table className="w-full border-collapse text-[13px]">
          <thead className="sticky top-0 z-10 bg-surface-2">
            <tr>
              <th scope="col" className="w-10 border-b border-line px-3 py-2 text-right text-[11px] font-medium text-faint">
                #
              </th>
              {columns.map((c) => (
                <th
                  key={c.name}
                  scope="col"
                  className={cn(
                    "border-b border-line px-3 py-2 text-[11px] font-semibold tracking-wide whitespace-nowrap text-muted",
                    numericCols.has(c.name) ? "text-right" : "text-left",
                  )}
                >
                  <span className="font-mono">{c.name}</span>
                  {c.data_type && <span className="ml-1.5 font-normal text-faint">{c.data_type.toLowerCase()}</span>}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {shown.map((row, i) => (
              <tr key={i} className="transition-colors hover:bg-surface-2/70">
                <td className="tnum border-b border-line px-3 py-2 text-right text-[11px] text-faint">{i + 1}</td>
                {columns.map((c) => {
                  const cell = formatCell(row[c.name], c);
                  const numeric = numericCols.has(c.name);
                  return (
                    <td
                      key={c.name}
                      className={cn(
                        "border-b border-line px-3 py-2 align-top",
                        numeric ? "tnum text-right whitespace-nowrap" : "max-w-[28rem] min-w-[6rem] break-words",
                        cell.kind === "null" ? "text-faint italic" : "text-fg",
                        cell.kind === "json" && "font-mono text-xs",
                      )}
                    >
                      {cell.text}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rows.length > visible && (
        <div className="flex items-center justify-between gap-2 border-t border-line px-4 py-2 text-xs text-muted">
          <span className="tnum">
            Showing {formatNumber(visible)} of {formatNumber(rows.length)} returned rows
          </span>
          <Button size="sm" variant="secondary" onClick={() => setVisible((v) => v + PAGE_SIZE * 4)}>
            Show more
          </Button>
        </div>
      )}
    </Panel>
  );
}
