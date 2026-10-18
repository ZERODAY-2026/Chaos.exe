import { useId } from "react";
import { cn } from "@/lib/utils";

export function LogoMark({ className }: { className?: string }) {
  const id = `dm-g-${useId().replace(/[^a-zA-Z0-9_-]/g, "")}`;
  return (
    <svg viewBox="0 0 32 32" className={cn("size-7", className)} aria-hidden="true">
      <defs>
        <linearGradient id={id} gradientUnits="userSpaceOnUse" x1="0" y1="8" x2="0" y2="24">
          <stop offset="0" style={{ stopColor: "var(--accent-strong)" }} />
          <stop offset="1" style={{ stopColor: "var(--cyan)" }} />
        </linearGradient>
      </defs>
      <rect x="1" y="1" width="30" height="30" rx="8" style={{ fill: "var(--surface-3)", stroke: "var(--border-strong)" }} />
      <path d="M9 22V10" stroke={`url(#${id})`} strokeWidth="2.6" strokeLinecap="round" />
      <path d="M14.5 22v-7" stroke={`url(#${id})`} strokeWidth="2.6" strokeLinecap="round" />
      <path d="M20 22v-4" stroke={`url(#${id})`} strokeWidth="2.6" strokeLinecap="round" />
      <circle cx="23.5" cy="10.5" r="2.4" style={{ fill: "var(--cyan)" }} />
    </svg>
  );
}
