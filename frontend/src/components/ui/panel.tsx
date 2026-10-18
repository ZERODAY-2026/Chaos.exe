import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/** A titled section. Used selectively for result blocks, not as a wrapper for everything. */
export function Panel({
  title,
  icon,
  actions,
  meta,
  children,
  className,
  bodyClassName,
  id,
}: {
  title: ReactNode;
  icon?: ReactNode;
  actions?: ReactNode;
  meta?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
  id?: string;
}) {
  const headingId = id ? `${id}-heading` : undefined;
  return (
    <section id={id} aria-labelledby={headingId} className={cn("panel enter min-w-0 overflow-hidden", className)}>
      <header className="flex min-h-12 flex-wrap items-center gap-x-3 gap-y-1 border-b border-line px-4 py-2">
        <div className="flex min-w-0 items-center gap-2">
          {icon && <span className="text-faint [&>svg]:size-4">{icon}</span>}
          <h2 id={headingId} className="text-[13px] font-semibold tracking-tight text-fg">
            {title}
          </h2>
          {meta && <div className="flex min-w-0 items-center gap-1.5 text-xs text-faint">{meta}</div>}
        </div>
        {actions && <div className="ml-auto flex items-center gap-1">{actions}</div>}
      </header>
      <div className={cn("p-4", bodyClassName)}>{children}</div>
    </section>
  );
}
