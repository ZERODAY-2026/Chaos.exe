import type { ResultColumn } from "@/lib/api-types";
import { deriveExtremes, type ChartSpec } from "@/lib/chart-inference";
import { formatCell, humanizeColumn } from "@/lib/formatters";
import { cn } from "@/lib/utils";

type Props = { spec: ChartSpec | null; rows: Array<Record<string, unknown>>; columns: ResultColumn[]; truncated: boolean };

/** Figures derived directly from returned rows. Nothing is aggregated beyond what the rows say. */
export function MetricGrid({ spec, rows, columns, truncated }: Props) {
  const colOf = (name: string) => columns.find((c) => c.name === name) ?? { name };
  const strip = "panel grid divide-y divide-line sm:divide-x sm:divide-y-0";

  if (spec?.kind === "kpi" && rows[0]) {
    const row = rows[0];
    return (
      <section aria-label="Key figures" className={cn(strip, spec.y.length > 1 && "sm:grid-cols-2", spec.y.length > 2 && "lg:grid-cols-4")}>
        {spec.y.map((m) => (
          <div key={m} className="min-w-0 px-4 py-3">
            <div className="truncate text-xs text-muted">{humanizeColumn(m)}</div>
            <div className="tnum mt-0.5 truncate text-2xl font-semibold tracking-tight text-fg">{formatCell(row[m], colOf(m)).text}</div>
            <div className="truncate font-mono text-[11px] text-faint">{m}</div>
          </div>
        ))}
      </section>
    );
  }

  const ext = deriveExtremes(spec, rows, truncated);
  if (!ext) return null;
  const tiles = [
    { label: "Highest", row: ext.max },
    { label: "Lowest", row: ext.min },
  ];
  return (
    <section aria-label="Highest and lowest values in the result" className={cn(strip, "sm:grid-cols-2")}>
      {tiles.map(({ label, row }) => (
        <div key={label} className="flex min-w-0 items-baseline gap-4 px-4 py-3">
          <div className="min-w-0 flex-1">
            <div className="text-xs text-muted">
              {label} {humanizeColumn(ext.measure).toLowerCase()} in these rows
            </div>
            <div className="mt-0.5 truncate text-[13px] font-medium text-fg" title={String(row[ext.dimension] ?? "")}>
              {formatCell(row[ext.dimension], colOf(ext.dimension)).text}
            </div>
          </div>
          <div className="tnum shrink-0 text-lg font-semibold tracking-tight text-fg">{formatCell(row[ext.measure], colOf(ext.measure)).text}</div>
        </div>
      ))}
    </section>
  );
}
