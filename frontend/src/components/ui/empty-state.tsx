import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function EmptyState({
  icon,
  title,
  children,
  action,
  tone = "neutral",
  className,
}: {
  icon: ReactNode;
  title: string;
  children?: ReactNode;
  action?: ReactNode;
  tone?: "neutral" | "danger" | "warning";
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center justify-center px-6 py-12 text-center", className)}>
      <div
        className={cn(
          "mb-4 flex size-11 items-center justify-center rounded-xl border [&>svg]:size-5",
          tone === "danger" && "border-transparent bg-danger-soft text-danger",
          tone === "warning" && "border-transparent bg-warning-soft text-warning",
          tone === "neutral" && "border-line-strong bg-surface-2 text-muted",
        )}
      >
        {icon}
      </div>
      <h3 className="text-sm font-semibold text-fg">{title}</h3>
      {children && <div className="mt-1.5 max-w-md text-sm leading-relaxed text-muted">{children}</div>}
      {action && <div className="mt-5 flex flex-wrap justify-center gap-2">{action}</div>}
    </div>
  );
}
