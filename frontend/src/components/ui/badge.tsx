import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export type Tone = "neutral" | "accent" | "cyan" | "success" | "warning" | "danger";

const tones: Record<Tone, string> = {
  neutral: "text-muted",
  accent: "text-accent",
  cyan: "text-cyan",
  success: "text-success",
  warning: "text-warning",
  danger: "text-danger",
};

/** A quiet label: thin border, coloured text, no fill. */
export function Badge({ tone = "neutral", icon, children, className }: { tone?: Tone; icon?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex h-5 items-center gap-1 rounded-sm border border-line-strong px-1.5 text-[11px] leading-none font-medium whitespace-nowrap",
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
  return <span className={cn("inline-flex size-1.5 shrink-0 rounded-full", dotTones[tone], pulse && "pulse-dot")} aria-hidden="true" />;
}

export function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd className="inline-flex h-[18px] min-w-[18px] items-center justify-center rounded-sm border border-line-strong px-1 font-sans text-[10px] font-medium text-faint">
      {children}
    </kbd>
  );
}
