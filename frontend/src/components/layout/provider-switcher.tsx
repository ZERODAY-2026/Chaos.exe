"use client";

import { Check, ChevronsUpDown } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { StatusDot } from "@/components/ui/badge";
import { useWorkspace } from "@/components/workspace-provider";
import { cn } from "@/lib/utils";

/** Lists only providers the backend reports. Disconnected providers are shown but cannot be selected. */
export function ProviderSwitcher() {
  const { providers, provider, setProviderId, query, mode } = useWorkspace();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => !ref.current?.contains(e.target as Node) && setOpen(false);
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (!provider) return null;
  const label = provider.label ?? provider.id;
  const single = providers.length < 2;

  const trigger = (
    <>
      <StatusDot tone={!provider.connected ? "danger" : mode === "demo" ? "warning" : "success"} />
      <span className="max-w-[9rem] truncate">{label}</span>
      <span className="sr-only">{provider.connected ? "connected" : "disconnected"}</span>
      {!single && <ChevronsUpDown className="size-3.5 text-faint" />}
    </>
  );

  const cls = "flex h-8 items-center gap-2 rounded-lg border border-line bg-surface px-2.5 text-xs font-medium text-fg";

  if (single) return <div className={cls} title={`Data source: ${label}`}>{trigger}</div>;

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        className={cn(cls, "transition-colors hover:border-line-strong hover:bg-surface-2")}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={`Data source: ${label}. Change data source`}
        onClick={() => setOpen((o) => !o)}
        disabled={query.phase === "running"}
      >
        {trigger}
      </button>
      {open && (
        <ul
          role="listbox"
          aria-label="Data sources"
          className="enter absolute right-0 z-40 mt-1.5 w-64 rounded-xl border border-line-strong bg-surface-2 p-1 shadow-elevated"
        >
          {providers.map((p) => (
            <li key={p.id} role="option" aria-selected={p.id === provider.id} aria-disabled={!p.connected}>
              <button
                type="button"
                disabled={!p.connected}
                onClick={() => {
                  setProviderId(p.id);
                  setOpen(false);
                }}
                className="flex w-full items-start gap-2.5 rounded-lg px-2.5 py-2 text-left transition-colors hover:bg-surface-3 disabled:cursor-not-allowed disabled:opacity-55 disabled:hover:bg-transparent"
              >
                <span className="mt-1">
                  <StatusDot tone={p.connected ? "success" : "danger"} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-[13px] font-medium text-fg">{p.label ?? p.id}</span>
                  <span className="block truncate text-[11px] text-faint">
                    {p.connected ? [p.database, p.schema].filter(Boolean).join(".") || "Connected" : (p.detail ?? "Not connected")}
                  </span>
                </span>
                {p.id === provider.id && <Check className="mt-0.5 size-4 text-accent" />}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
