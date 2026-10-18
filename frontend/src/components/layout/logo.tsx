import { cn } from "@/lib/utils";

/** Three bars of a column chart. Single colour so it sits quietly next to the wordmark. */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={cn("size-6", className)} aria-hidden="true">
      <rect x="1" y="1" width="30" height="30" rx="6" style={{ fill: "var(--surface-3)" }} />
      <path d="M10 22V12M16 22V9M22 22v-6" style={{ stroke: "var(--text)" }} strokeWidth="2.6" strokeLinecap="round" />
    </svg>
  );
}
