import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/** A titled, bordered block for data: tables, SQL, details. The title sits in a slim header row. */
export function Panel({
  title,
  actions,
  meta,
  children,
  className,
  bodyClassName,
  id,
}: {
  title: ReactNode;
  actions?: ReactNode;
  meta?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
  id?: string;
}) {
  const headingId = id ? `${id}-heading` : undefined;
  return (
    <section id={id} aria-labelledby={headingId} className={cn("panel min-w-0 overflow-hidden", className)}>
      <header className="flex min-h-10 flex-wrap items-center gap-x-3 gap-y-1 border-b border-line px-4 py-1.5">
        <h2 id={headingId} className="text-[13px] font-medium text-fg">
          {title}
        </h2>
        {meta && <div className="flex min-w-0 items-center gap-1.5 text-xs text-faint">{meta}</div>}
        {actions && <div className="-mr-2 ml-auto flex items-center gap-0.5">{actions}</div>}
      </header>
      {/* bodyClassName replaces the default padding rather than competing with it. */}
      <div className={bodyClassName ?? "p-4"}>{children}</div>
    </section>
  );
}
