import { ArrowDownRight, ArrowUpRight } from "lucide-react";
import type { ResultColumn } from "@/lib/api-types";
import { deriveExtremes, type ChartSpec } from "@/lib/chart-inference";
import { formatCell, humanizeColumn } from "@/lib/formatters";

type Props = { spec: ChartSpec | null; rows: Array<Record<string, unknown>>; columns: ResultColumn[]; truncated: boolean };

/** Figures derived directly from returned rows. Nothing is aggregated beyond what the rows say. */
export function MetricGrid({ spec, rows, columns, truncated }: Props) {
  const colOf = (name: string) => columns.find((c) => c.name === name) ?? { name };

  if (spec?.kind === "kpi" && rows[0]) {
    const row = rows[0];
    return (
      <section aria-label="Key figures" className="enter grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {spec.y.map((m) => (
          <div key={m} className="rounded-xl border border-line bg-surface px-5 py-4">
            <div className="truncate text-xs font-medium text-muted">{humanizeColumn(m)}</div>
            <div className="tnum mt-1.5 truncate text-[28px] leading-tight font-semibold tracking-tight text-fg">
              {formatCell(row[m], colOf(m)).text}
            </div>
            <div className="mt-1 truncate font-mono text-[11px] text-faint">{m}</div>
          </div>
        ))}
      </section>
    );
  }

  const ext = deriveExtremes(spec, rows, truncated);
  if (!ext) return null;
  const tiles = [
    { label: "Highest", row: ext.max, Icon: ArrowUpRight },
    { label: "Lowest", row: ext.min, Icon: ArrowDownRight },
  ];
  return (
    <section aria-label="Highest and lowest values in the result" className="enter grid grid-cols-1 gap-3 sm:grid-cols-2">
      {tiles.map(({ label, row, Icon }) => (
        <div key={label} className="flex items-center gap-4 rounded-xl border border-line bg-surface px-5 py-3.5">
          <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-surface-2 text-muted">
            <Icon className="size-4" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-xs text-muted">
              {label} {humanizeColumn(ext.measure).toLowerCase()} in these rows
            </div>
            <div className="truncate text-sm font-medium text-fg" title={String(row[ext.dimension] ?? "")}>
              {formatCell(row[ext.dimension], colOf(ext.dimension)).text}
            </div>
          </div>
          <div className="tnum shrink-0 text-lg font-semibold tracking-tight text-fg">{formatCell(row[ext.measure], colOf(ext.measure)).text}</div>
        </div>
      ))}
    </section>
  );
}
