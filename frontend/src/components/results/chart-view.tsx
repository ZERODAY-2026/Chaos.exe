"use client";

import { useMemo } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipProps,
} from "recharts";
import { Panel } from "@/components/ui/panel";
import { useMediaQuery } from "@/hooks/use-media-query";
import { toChartData, type ChartSpec } from "@/lib/chart-inference";
import { formatNumber, humanizeColumn, looksLikeCurrency } from "@/lib/formatters";

const SERIES = ["var(--chart-1)", "var(--chart-2)", "var(--chart-3)"];
const axisTick = { fill: "var(--text-faint)", fontSize: 11 };

function ChartTooltip({ active, payload, label, currencyCols }: TooltipProps<number, string> & { currencyCols: Set<string> }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-md bg-surface-2 px-3 py-2 text-xs shadow-elevated">
      {label !== undefined && <div className="mb-1 font-medium text-fg">{String(label)}</div>}
      <ul className="space-y-0.5">
        {payload.map((p) => (
          <li key={String(p.dataKey)} className="flex items-center gap-2">
            <span className="size-2 rounded-[2px]" style={{ background: p.color ?? (p.payload as { fill?: string })?.fill }} />
            <span className="text-muted">{humanizeColumn(String(p.name ?? p.dataKey))}</span>
            <span className="tnum ml-auto pl-3 font-medium text-fg">
              {typeof p.value === "number" ? formatNumber(p.value, { currency: currencyCols.has(String(p.dataKey)) }) : "null"}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function truncateLabel(v: unknown, max = 18): string {
  const s = String(v ?? "");
  return s.length > max ? `${s.slice(0, max - 1)}…` : s;
}

export function ChartView({ spec: inferred, rows }: { spec: ChartSpec; rows: Array<Record<string, unknown>> }) {
  // Vertical category labels collide on phones, so bars turn horizontal there.
  const narrow = useMediaQuery("(max-width: 639px)");
  const spec = useMemo<ChartSpec>(
    () => (narrow && inferred.kind === "bar" ? { ...inferred, kind: "horizontal_bar" } : inferred),
    [narrow, inferred],
  );
  const data = useMemo(() => toChartData(spec, rows), [spec, rows]);
  const currencyCols = useMemo(() => new Set(spec.y.filter(looksLikeCurrency)), [spec.y]);
  const tickFmt = (v: number) => formatNumber(v, { compact: true, currency: spec.y.length === 1 && currencyCols.size === 1 });
  const x = spec.x ?? "";
  const multi = spec.y.length > 1;
  const legend = multi ? (
    <Legend
      verticalAlign="top"
      align="right"
      height={28}
      iconType="square"
      iconSize={8}
      formatter={(v: string) => <span className="text-xs text-muted">{humanizeColumn(v)}</span>}
    />
  ) : null;

  const description = `${spec.kind.replace("_", " ")} chart of ${spec.y.map(humanizeColumn).join(", ")}${spec.x ? ` by ${humanizeColumn(spec.x)}` : ""}, ${rows.length} data points. The full values are in the results table below.`;

  let chart: React.ReactElement;
  if (spec.kind === "line") {
    chart = (
      <LineChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: 4 }}>
        <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
        <XAxis dataKey={x} tick={axisTick} tickLine={false} axisLine={{ stroke: "var(--border-strong)" }} minTickGap={24} />
        <YAxis tick={axisTick} tickLine={false} axisLine={false} tickFormatter={tickFmt} width={64} />
        <Tooltip content={<ChartTooltip currencyCols={currencyCols} />} cursor={{ stroke: "var(--border-strong)" }} />
        {legend}
        {spec.y.map((y, i) => (
          <Line
            key={y}
            type="monotone"
            dataKey={y}
            name={y}
            stroke={SERIES[i]}
            strokeWidth={1.75}
            dot={data.length <= 24 ? { r: 2.5, strokeWidth: 0, fill: SERIES[i] } : false}
            activeDot={{ r: 5, strokeWidth: 2, stroke: "var(--surface)" }}
            connectNulls={false}
            isAnimationActive={data.length < 200}
          />
        ))}
      </LineChart>
    );
  } else if (spec.kind === "horizontal_bar") {
    const longest = Math.max(...data.map((d) => String(d[x] ?? "").length));
    chart = (
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 16, bottom: 4, left: 4 }} barCategoryGap={4}>
        <CartesianGrid stroke="var(--chart-grid)" horizontal={false} />
        <XAxis type="number" tick={axisTick} tickLine={false} axisLine={false} tickFormatter={tickFmt} />
        <YAxis
          type="category"
          dataKey={x}
          tick={axisTick}
          tickLine={false}
          axisLine={{ stroke: "var(--border-strong)" }}
          width={Math.min(170, Math.max(60, longest * 6.6))}
          tickFormatter={(v) => truncateLabel(v, 24)}
          interval={0}
        />
        <Tooltip content={<ChartTooltip currencyCols={currencyCols} />} cursor={{ fill: "var(--surface-2)" }} />
        {legend}
        {spec.y.map((y, i) => (
          <Bar key={y} dataKey={y} name={y} fill={SERIES[i]} radius={[0, 2, 2, 0]} maxBarSize={22} isAnimationActive={data.length < 60} />
        ))}
      </BarChart>
    );
  } else if (spec.kind === "pie") {
    const y = spec.y[0] ?? "";
    const pieColors = ["var(--chart-1)", "var(--chart-2)", "var(--chart-3)", "var(--text-muted)", "var(--cyan)", "var(--text-faint)"];
    chart = (
      <PieChart>
        <Tooltip content={<ChartTooltip currencyCols={currencyCols} />} />
        <Legend iconType="square" iconSize={8} formatter={(v: string) => <span className="text-xs text-muted">{v}</span>} />
        <Pie data={data} dataKey={y} nameKey={x} innerRadius="55%" outerRadius="85%" paddingAngle={1.5} stroke="var(--surface)" strokeWidth={2}>
          {data.map((_, i) => (
            <Cell key={i} fill={pieColors[i % pieColors.length]} />
          ))}
        </Pie>
      </PieChart>
    );
  } else {
    chart = (
      <BarChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: 4 }} barCategoryGap="22%">
        <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
        <XAxis dataKey={x} tick={axisTick} tickLine={false} axisLine={{ stroke: "var(--border-strong)" }} interval={0} tickFormatter={(v) => truncateLabel(v, 14)} />
        <YAxis tick={axisTick} tickLine={false} axisLine={false} tickFormatter={tickFmt} width={64} />
        <Tooltip content={<ChartTooltip currencyCols={currencyCols} />} cursor={{ fill: "var(--surface-2)" }} />
        {legend}
        {spec.y.map((y, i) => (
          <Bar key={y} dataKey={y} name={y} fill={SERIES[i]} radius={[2, 2, 0, 0]} maxBarSize={56} isAnimationActive={data.length < 60} />
        ))}
      </BarChart>
    );
  }

  const height = spec.kind === "horizontal_bar" ? Math.max(220, Math.min(720, data.length * 30 + 48)) : 300;

  return (
    <Panel
      id="chart"
      title="Chart"
      meta={<span className="hidden truncate sm:inline">{spec.reason}</span>}
      bodyClassName="px-2 pt-3 pb-2 sm:px-3"
    >
      {!multi && (
        <p className="mb-1 px-2 text-xs font-medium text-muted">
          {humanizeColumn(spec.y[0] ?? "")}
          {spec.x && <span className="text-faint"> by {humanizeColumn(spec.x)}</span>}
        </p>
      )}
      <figure role="img" aria-label={description} style={{ height }} className="w-full">
        <ResponsiveContainer width="100%" height="100%">
          {chart}
        </ResponsiveContainer>
      </figure>
    </Panel>
  );
}
