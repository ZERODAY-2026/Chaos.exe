import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export type Tone = "neutral" | "accent" | "cyan" | "success" | "warning" | "danger";

const tones: Record<Tone, string> = {
  neutral: "bg-surface-2 text-muted border-line",
  accent: "bg-accent-soft text-accent border-transparent",
  cyan: "bg-cyan-soft text-cyan border-transparent",
  success: "bg-success-soft text-success border-transparent",
  warning: "bg-warning-soft text-warning border-transparent",
  danger: "bg-danger-soft text-danger border-transparent",
};

export function Badge({ tone = "neutral", icon, children, className }: { tone?: Tone; icon?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex h-5.5 items-center gap-1 rounded-md border px-1.5 text-[11px] leading-none font-medium whitespace-nowrap",
        tones[tone],
        className,
      )}
    >
      {icon}
      {children}
    </span>
  );
}

const dotTones: Record<Tone, string> = {
  neutral: "bg-faint",
  accent: "bg-accent",
  cyan: "bg-cyan",
  success: "bg-success",
  warning: "bg-warning",
  danger: "bg-danger",
};

export function StatusDot({ tone, pulse }: { tone: Tone; pulse?: boolean }) {
  return (
    <span className="relative inline-flex size-2 shrink-0" aria-hidden="true">
      {tone === "success" && <span className="absolute inset-0 rounded-full bg-success opacity-30 blur-[3px]" />}
      <span className={cn("relative inline-flex size-2 rounded-full", dotTones[tone], pulse && "pulse-dot")} />
    </span>
  );
}

export function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd className="inline-flex h-5 min-w-5 items-center justify-center rounded border border-line-strong bg-surface-2 px-1 font-sans text-[10px] font-medium text-muted">
      {children}
    </kbd>
  );
}
