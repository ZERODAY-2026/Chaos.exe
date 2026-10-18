"use client";

import { RotateCcw, Trash2 } from "lucide-react";
import type { ReactNode } from "react";
import { useState } from "react";
import { PageFrame } from "@/components/layout/page-frame";
import { useConnectionSummary } from "@/components/layout/connection-status";
import { Badge, StatusDot } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useWorkspace } from "@/components/workspace-provider";
import { API_BASE_URL } from "@/lib/api-client";
import { formatNumber, formatRelativeTime } from "@/lib/formatters";
import { cn } from "@/lib/utils";

function Section({ title, description, children }: { title: string; description: string; children: ReactNode }) {
  return (
    <section className="grid gap-3 border-t border-line py-6 md:grid-cols-[220px_minmax(0,1fr)] md:gap-10">
      <div>
        <h2 className="text-[13px] font-medium text-fg">{title}</h2>
        <p className="mt-0.5 text-[13px] leading-relaxed text-muted">{description}</p>
      </div>
      <div className="min-w-0">{children}</div>
    </section>
  );
}

function Segmented<T extends string>({ value, onChange, options, label }: { value: T; onChange: (v: T) => void; options: Array<{ value: T; label: string }>; label: string }) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex rounded-md border border-line-strong p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={value === o.value}
          onClick={() => onChange(o.value)}
          className={cn(
            "inline-flex h-6 items-center rounded-sm px-3 text-xs font-medium transition-colors",
            value === o.value ? "bg-surface-2 text-fg" : "text-muted hover:text-fg",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

function KV({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[minmax(0,10rem)_minmax(0,1fr)] gap-x-4 border-b border-line py-2 text-[13px] last:border-0">
      <dt className="text-muted">{label}</dt>
      <dd className="min-w-0 break-all text-fg">{children}</dd>
    </div>
  );
}

export function SettingsView() {
  const { mode, setMode, theme, setTheme, health, refreshHealth, providers, provider, history, clearHistory } = useWorkspace();
  const summary = useConnectionSummary();
  const [cleared, setCleared] = useState(false);
  const data = health.state === "ok" ? health.data : null;

  return (
    <PageFrame title="Settings" subtitle="Connection, data sources and appearance for this browser.">
      <div className="max-w-4xl">
        <Section title="Mode" description="Live mode sends questions to the DataMind backend. Demo mode uses bundled, labeled sample fixtures and queries nothing.">
          <Segmented
            label="Mode"
            value={mode}
            onChange={setMode}
            options={[
              { value: "live", label: "Live backend" },
              { value: "demo", label: "Demo fixtures" },
            ]}
          />
        </Section>

        <Section title="Backend connection" description="Status reported by the backend health endpoint.">
          <dl className="panel px-4 py-0.5">
            <KV label="Status">
              <span className="inline-flex items-center gap-2">
                <StatusDot tone={summary.tone} pulse={summary.pulse} />
                {summary.label}
              </span>
            </KV>
            <KV label="API base URL">
              <code className="font-mono text-xs">{mode === "demo" ? "not used in demo mode" : API_BASE_URL}</code>
            </KV>
            {data?.version && <KV label="Backend version">{data.version}</KV>}
            {data?.row_limit && <KV label="Row limit per query">{formatNumber(data.row_limit)}</KV>}
            {health.state === "error" && <KV label="Error">{health.error.message}</KV>}
            {health.checkedAt && <KV label="Last checked">{formatRelativeTime(health.checkedAt)}</KV>}
          </dl>
          <div className="mt-3">
            <Button size="sm" icon={<RotateCcw className="size-3.5" />} loading={health.state === "loading"} onClick={refreshHealth}>
              Check connection
            </Button>
          </div>
        </Section>

        <Section title="Data sources" description="Providers the backend reports. Credentials live in the backend's .env file and are never entered or stored in the browser.">
          {providers.length === 0 ? (
            <p className="text-[13px] text-muted">{health.state === "error" ? "Unavailable while the backend is offline." : "No data sources reported."}</p>
          ) : (
            <ul className="panel divide-y divide-line">
              {providers.map((p) => (
                <li key={p.id} className="flex items-start gap-3 px-4 py-3">
                  <span className="mt-[7px]">
                    <StatusDot tone={p.connected ? "success" : "danger"} />
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2 text-[13px] font-medium text-fg">
                      {p.label ?? p.id}
                      {p.id === provider?.id && <Badge tone="accent">Active</Badge>}
                      {p.is_default && <Badge>Default</Badge>}
                    </div>
                    <div className="mt-0.5 font-mono text-xs break-all text-muted">
                      {[p.database, p.schema].filter(Boolean).join(".") || "No database reported"}
                      {p.warehouse && ` · ${p.warehouse}`}
                    </div>
                    {p.detail && <div className="mt-1 text-xs text-faint">{p.detail}</div>}
                  </div>
                  <span className={cn("text-xs", p.connected ? "text-success" : "text-danger")}>{p.connected ? "Connected" : "Not connected"}</span>
                </li>
              ))}
            </ul>
          )}
        </Section>

        <Section title="Model" description="The language model the backend uses to interpret questions and write SQL.">
          {data?.model ? (
            <dl className="panel px-4 py-0.5">
              <KV label="Model">{data.model.name}</KV>
              {data.model.runtime && <KV label="Runtime">{data.model.runtime}</KV>}
              <KV label="Availability">
                <span className="inline-flex items-center gap-2">
                  <StatusDot tone={data.model.available ? "success" : "danger"} />
                  {data.model.available ? "Available" : "Unavailable"}
                </span>
              </KV>
              {data.model.detail && <KV label="Detail">{data.model.detail}</KV>}
            </dl>
          ) : (
            <p className="text-[13px] text-muted">{mode === "demo" ? "No model is used in demo mode." : "The backend did not report model details."}</p>
          )}
        </Section>

        <Section title="Appearance" description="Saved in this browser.">
          <Segmented
            label="Theme"
            value={theme}
            onChange={setTheme}
            options={[
              { value: "dark", label: "Dark" },
              { value: "light", label: "Light" },
            ]}
          />
        </Section>

        <Section title="Local data" description="Query history is kept only in this browser's storage.">
          <div className="flex flex-wrap items-center gap-3">
            <span className="text-[13px] text-muted">
              {cleared ? "History cleared." : `${history.length} saved ${history.length === 1 ? "question" : "questions"}`}
            </span>
            <Button
              size="sm"
              variant="danger"
              disabled={history.length === 0}
              icon={<Trash2 className="size-3.5" />}
              onClick={() => {
                clearHistory();
                setCleared(true);
              }}
            >
              Clear history
            </Button>
          </div>
        </Section>
      </div>
    </PageFrame>
  );
}
