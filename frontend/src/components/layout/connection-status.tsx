"use client";

import { StatusDot, type Tone } from "@/components/ui/badge";
import { useWorkspace } from "@/components/workspace-provider";

export function useConnectionSummary(): { tone: Tone; label: string; detail: string; pulse: boolean } {
  const { health, provider, mode } = useWorkspace();
  if (health.state === "loading" && !health.data) return { tone: "neutral", label: "Checking…", detail: "Contacting the backend", pulse: true };
  if (health.state === "error") return { tone: "danger", label: "Backend offline", detail: health.error.message, pulse: false };
  if (mode === "demo") return { tone: "warning", label: "Demo mode", detail: "Sample fixtures, not live results", pulse: false };
  if (!provider) return { tone: "warning", label: "No data source", detail: "The backend reported no providers", pulse: false };
  if (!provider.connected)
    return { tone: "danger", label: `${provider.label ?? provider.id} disconnected`, detail: provider.detail ?? "Provider not reachable", pulse: false };
  const degraded = health.state === "ok" && health.data.status !== "ok";
  return {
    tone: degraded ? "warning" : "success",
    label: `${provider.label ?? provider.id} connected`,
    detail: degraded ? "Backend reports degraded status" : [provider.database, provider.schema].filter(Boolean).join(".") || "Connected",
    pulse: false,
  };
}

export function ConnectionStatus({ compact }: { compact?: boolean }) {
  const s = useConnectionSummary();
  return (
    <div className="flex min-w-0 items-center gap-2" title={`${s.label}: ${s.detail}`}>
      <StatusDot tone={s.tone} pulse={s.pulse} />
      {!compact && (
        <div className="min-w-0 leading-tight">
          <div className="truncate text-xs font-medium text-fg">{s.label}</div>
          <div className="truncate text-[11px] text-faint">{s.detail}</div>
        </div>
      )}
      {compact && <span className="sr-only">{`${s.label}: ${s.detail}`}</span>}
    </div>
  );
}
