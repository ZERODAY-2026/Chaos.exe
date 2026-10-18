"use client";

import { Check, Copy, ShieldCheck } from "lucide-react";
import { useState, type ReactNode } from "react";
import { IconButton } from "@/components/ui/button";
import { Panel } from "@/components/ui/panel";
import type { QueryResult } from "@/lib/api-types";
import { formatDuration, formatNumber } from "@/lib/formatters";
import { copyText } from "@/lib/utils";

function Row({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <div className="grid grid-cols-[minmax(0,9rem)_minmax(0,1fr)] gap-3 border-b border-line py-2 last:border-0">
      <dt className="text-xs text-faint" title={hint}>
        {label}
      </dt>
      <dd className="min-w-0 text-[13px] break-words text-fg">{children}</dd>
    </div>
  );
}

const NotReported = () => <span className="text-faint">Not reported</span>;

function CopyableId({ value }: { value: string }) {
  const [done, setDone] = useState(false);
  return (
    <span className="flex items-center gap-1">
      <span className="truncate font-mono text-xs" title={value}>
        {value}
      </span>
      <IconButton
        size="sm"
        label={done ? "Copied" : "Copy ID"}
        className="size-6"
        onClick={async () => {
          if (await copyText(value)) {
            setDone(true);
            setTimeout(() => setDone(false), 1400);
          }
        }}
      >
        {done ? <Check className="size-3 text-success" /> : <Copy className="size-3" />}
      </IconButton>
    </span>
  );
}

export function EvidencePanel({ result }: { result: QueryResult }) {
  const r = result.response;
  const ex = r.execution;
  const isDemo = result.source === "demo";
  const location = [ex?.database, ex?.schema].filter(Boolean).join(".");
  const tables = r.explanation?.tables?.filter(Boolean) ?? [];
  const hasEvidence = !!(ex || r.validation || tables.length || r.row_count !== undefined || r.sql);

  return (
    <Panel id="evidence" title="Evidence" icon={<ShieldCheck />} bodyClassName="px-4 py-1">
      {!hasEvidence ? (
        <p className="py-3 text-sm text-muted">Evidence details are not available for this response.</p>
      ) : (
        <dl>
          <Row label="Data source">
            {result.provider ?? r.provider ?? <NotReported />}
            {location && <span className="mt-0.5 block font-mono text-xs text-muted">{location}</span>}
          </Row>
          <Row label="Tables used">
            {tables.length ? (
              <ul className="flex flex-wrap gap-1">
                {tables.map((t) => (
                  <li key={t} className="rounded bg-surface-2 px-1.5 py-0.5 font-mono text-[11px] text-muted">
                    {t}
                  </li>
                ))}
              </ul>
            ) : (
              <NotReported />
            )}
          </Row>
          <Row label="Execution">
            {isDemo ? (
              <span className="text-warning">Not executed (demo fixture)</span>
            ) : r.executed === true ? (
              <span className="text-success">Executed</span>
            ) : r.executed === false ? (
              <span className="text-warning">Not executed</span>
            ) : (
              <NotReported />
            )}
          </Row>
          <Row label="Rows returned">
            {r.row_count !== null && r.row_count !== undefined ? (
              <span className="tnum">
                {formatNumber(r.row_count)}
                {r.truncated && <span className="text-warning"> (truncated)</span>}
              </span>
            ) : r.rows ? (
              <span className="tnum">{formatNumber(r.rows.length)}</span>
            ) : (
              <NotReported />
            )}
          </Row>
          <Row label="Row limit">
            {r.validation?.limit_applied ? <span className="tnum">{formatNumber(r.validation.limit_applied)}</span> : <NotReported />}
          </Row>
          <Row label="Query time" hint="Measured by the backend">
            {formatDuration(ex?.duration_ms) ?? <NotReported />}
          </Row>
          <Row label="Round trip" hint="Measured in this browser, including network and model time">
            <span className="tnum">{formatDuration(result.clientDurationMs)}</span>
            {isDemo && <span className="text-faint"> (simulated delay)</span>}
          </Row>
          {(r.model?.name || r.model?.duration_ms) && (
            <Row label="Model">
              {r.model?.name ?? <NotReported />}
              {r.model?.duration_ms ? <span className="text-muted"> · {formatDuration(r.model.duration_ms)}</span> : null}
            </Row>
          )}
          {ex?.warehouse && <Row label="Warehouse">{ex.warehouse}</Row>}
          <Row label="Warehouse query ID" hint="Lets you find this query in the provider's query history">
            {ex?.provider_query_id ? <CopyableId value={ex.provider_query_id} /> : <NotReported />}
          </Row>
          {ex?.started_at && <Row label="Started at">{new Date(ex.started_at).toLocaleString()}</Row>}
          <Row label="DataMind query ID">
            <CopyableId value={r.query_id} />
          </Row>
        </dl>
      )}
    </Panel>
  );
}
