"use client";

import { CircleAlert, CircleCheck, CircleHelp, PanelLeftClose, PanelLeftOpen, ShieldOff, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { IconButton } from "@/components/ui/button";
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
  const { history, openHistoryEntry, setSidebarCollapsed } = useWorkspace();
  const recent = history.slice(0, 8);

  return (
    <div className="flex h-full flex-col">
      <div className={cn("flex h-12 shrink-0 items-center gap-2 px-4", collapsed && "justify-center px-0")}>
        <Link href="/" onClick={onNavigate} className="flex min-w-0 items-center gap-2 rounded-md" aria-label="DataMind home">
          <LogoMark className="size-5" />
          {!collapsed && <span className="truncate text-sm font-semibold text-fg">DataMind</span>}
        </Link>
        {onClose && (
          <IconButton label="Close navigation" onClick={onClose} className="ml-auto">
            <X className="size-4" />
          </IconButton>
        )}
      </div>

      <nav aria-label="Main" className="mt-1 px-2">
        <ul className="space-y-px">
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
                    "flex h-8 items-center gap-2.5 rounded-md px-2 text-[13px] transition-colors duration-100",
                    active ? "bg-surface-2 font-medium text-fg" : "text-muted hover:bg-surface hover:text-fg",
                    collapsed && "justify-center px-0",
                  )}
                >
                  <Icon className={cn("size-4 shrink-0", active ? "text-fg" : "text-faint")} strokeWidth={1.75} />
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
          <h2 className="eyebrow mb-1 px-2">Recent</h2>
          {recent.length === 0 ? (
            <p className="px-2 text-xs leading-relaxed text-faint">Questions you ask will appear here.</p>
          ) : (
            <ul className="space-y-px">
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
                    className="flex h-7 w-full items-center gap-2 rounded-md px-2 text-left text-xs text-muted transition-colors hover:bg-surface hover:text-fg disabled:cursor-default disabled:hover:bg-transparent disabled:hover:text-muted"
                    title={e.question}
                  >
                    <StatusIcon status={e.status} className="size-3" />
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

      <div className={cn("mt-2 flex shrink-0 items-center gap-2 border-t border-line px-4 py-3", collapsed && "flex-col px-0")}>
        <div className="min-w-0 flex-1">
          <ConnectionStatus compact={collapsed} />
        </div>
        {!onClose && (
          <IconButton size="sm" label={collapsed ? "Expand sidebar" : "Collapse sidebar"} onClick={() => setSidebarCollapsed(!collapsed)}>
            {collapsed ? <PanelLeftOpen className="size-4" /> : <PanelLeftClose className="size-4" />}
          </IconButton>
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
        "sticky top-0 hidden h-dvh shrink-0 border-r border-line bg-bg-subtle transition-[width] duration-150 ease-out lg:block",
        sidebarCollapsed ? "w-[52px]" : "w-56",
      )}
    >
      <SidebarContent collapsed={sidebarCollapsed} />
    </aside>
  );
}
