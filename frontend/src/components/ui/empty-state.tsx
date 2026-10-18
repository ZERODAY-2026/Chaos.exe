import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/** Text-first empty and error states. Left-aligned so they line up with the content around them. */
export function EmptyState({
  title,
  children,
  action,
  tone = "neutral",
  className,
}: {
  title: string;
  children?: ReactNode;
  action?: ReactNode;
  tone?: "neutral" | "danger" | "warning";
  className?: string;
}) {
  return (
    <div className={cn("px-5 py-8", className)}>
      <h3 className={cn("text-sm font-medium", tone === "danger" ? "text-danger" : tone === "warning" ? "text-warning" : "text-fg")}>{title}</h3>
      {children && <div className="mt-1 max-w-lg text-[13px] leading-relaxed text-muted">{children}</div>}
      {action && <div className="mt-4 flex flex-wrap gap-2">{action}</div>}
    </div>
  );
}
