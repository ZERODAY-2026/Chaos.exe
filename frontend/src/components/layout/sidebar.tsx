"use client";

import { CircleAlert, CircleCheck, CircleHelp, PanelLeftClose, PanelLeftOpen, ShieldOff, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { IconButton } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useWorkspace } from "@/components/workspace-provider";
import type { HistoryEntry } from "@/lib/history";
import { cn } from "@/lib/utils";
import { ConnectionStatus } from "./connection-status";
import { LogoMark } from "./logo";
import { NAV_ITEMS } from "./nav-items";

export function StatusIcon({ status, className }: { status: HistoryEntry["status"]; className?: string }) {
  const c = cn("size-3.5 shrink-0", className);
  if (status === "success") return <CircleCheck className={cn(c, "text-success")} aria-label="Succeeded" />;
  if (status === "clarification_needed") return <CircleHelp className={cn(c, "text-cyan")} aria-label="Needs clarification" />;
  if (status === "refused") return <ShieldOff className={cn(c, "text-warning")} aria-label="Refused" />;
  return <CircleAlert className={cn(c, "text-danger")} aria-label="Failed" />;
}

export function SidebarContent({ collapsed, onNavigate, onClose }: { collapsed: boolean; onNavigate?: () => void; onClose?: () => void }) {
  const pathname = usePathname();
  const router = useRouter();
  const { history, openHistoryEntry, mode, provider, setSidebarCollapsed } = useWorkspace();
  const recent = history.slice(0, 6);

  return (
    <div className="flex h-full flex-col">
      <div className={cn("flex h-14 shrink-0 items-center gap-2.5 px-3.5", collapsed && "justify-center px-0")}>
        <Link href="/" onClick={onNavigate} className="flex min-w-0 items-center gap-2.5 rounded-md" aria-label="DataMind home">
          <LogoMark />
          {!collapsed && (
            <span className="truncate text-[15px] font-semibold tracking-tight text-fg">
              DataMind
            </span>
          )}
        </Link>
        {onClose && (
          <IconButton label="Close navigation" onClick={onClose} className="ml-auto">
            <X className="size-4" />
          </IconButton>
        )}
      </div>

      {!collapsed && (
        <div className="mx-3 mb-2 flex items-center justify-between rounded-lg border border-line bg-surface px-2.5 py-2">
          <div className="min-w-0">
            <div className="eyebrow !text-[10px]">Data source</div>
            <div className="truncate text-xs font-medium text-fg">{provider ? (provider.label ?? provider.id) : "Not connected"}</div>
          </div>
          {mode === "demo" ? <Badge tone="warning">Demo</Badge> : provider?.database ? <Badge>{provider.schema ?? provider.database}</Badge> : null}
        </div>
      )}

      <nav aria-label="Main" className={cn("px-2", collapsed && "px-2")}>
        <ul className="space-y-0.5">
          {NAV_ITEMS.map((item) => {
            const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            const Icon = item.icon;
            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  onClick={onNavigate}
                  aria-current={active ? "page" : undefined}
                  title={collapsed ? item.label : undefined}
                  className={cn(
                    "group relative flex h-9 items-center gap-2.5 rounded-lg px-2.5 text-[13px] font-medium transition-colors duration-150",
                    active ? "bg-surface-2 text-fg" : "text-muted hover:bg-surface hover:text-fg",
                    collapsed && "justify-center px-0",
                  )}
                >
                  {active && <span className="absolute top-2 bottom-2 left-0 w-0.5 rounded-full bg-accent" aria-hidden="true" />}
                  <Icon className={cn("size-4 shrink-0", active ? "text-accent" : "text-faint group-hover:text-muted")} />
                  {!collapsed && <span className="truncate">{item.label}</span>}
                  {collapsed && <span className="sr-only">{item.label}</span>}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      {!collapsed && (
        <div className="mt-6 min-h-0 flex-1 overflow-y-auto px-2">
          <div className="eyebrow mb-1.5 px-2.5">Recent questions</div>
          {recent.length === 0 ? (
            <p className="px-2.5 text-xs leading-relaxed text-faint">Questions you ask will appear here.</p>
          ) : (
            <ul className="space-y-0.5">
              {recent.map((e) => (
                <li key={e.id}>
                  <button
                    type="button"
                    disabled={!e.result}
                    onClick={() => {
                      openHistoryEntry(e);
                      router.push("/");
                      onNavigate?.();
                    }}
                    className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-xs text-muted transition-colors hover:bg-surface hover:text-fg disabled:cursor-default disabled:hover:bg-transparent disabled:hover:text-muted"
                    title={e.question}
                  >
                    <StatusIcon status={e.status} />
                    <span className="truncate">{e.question}</span>
                    {e.source === "demo" && <span className="ml-auto text-[10px] text-warning">demo</span>}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      {collapsed && <div className="flex-1" />}

      <div className={cn("mt-2 shrink-0 border-t border-line p-3", collapsed && "flex flex-col items-center gap-3 px-0")}>
        <ConnectionStatus compact={collapsed} />
        {!onClose && (
          <div className={cn("mt-2.5 flex items-center justify-between", collapsed && "mt-0")}>
            {!collapsed && <span className="text-[11px] text-faint">History is stored in this browser</span>}
            <IconButton
              size="sm"
              label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
              onClick={() => setSidebarCollapsed(!collapsed)}
            >
              {collapsed ? <PanelLeftOpen className="size-4" /> : <PanelLeftClose className="size-4" />}
            </IconButton>
          </div>
        )}
      </div>
    </div>
  );
}

export function Sidebar() {
  const { sidebarCollapsed } = useWorkspace();
  return (
    <aside
      className={cn(
        "sticky top-0 hidden h-dvh shrink-0 border-r border-line bg-bg-subtle transition-[width] duration-200 ease-out lg:block",
        sidebarCollapsed ? "w-[60px]" : "w-64",
      )}
    >
      <SidebarContent collapsed={sidebarCollapsed} />
    </aside>
  );
}
