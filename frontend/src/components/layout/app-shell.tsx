"use client";

import { useCallback, useState, type ReactNode } from "react";
import { DemoBanner } from "./demo-banner";
import { MobileNavigation } from "./mobile-navigation";
import { Sidebar } from "./sidebar";
import { Topbar } from "./topbar";

export function AppShell({ children }: { children: ReactNode }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const close = useCallback(() => setMenuOpen(false), []);
  return (
    <div className="flex min-h-dvh">
      <a
        href="#main"
        className="sr-only z-[70] rounded-md bg-accent px-3 py-2 text-sm text-accent-fg focus:not-sr-only focus:fixed focus:top-3 focus:left-3"
      >
        Skip to content
      </a>
      <Sidebar />
      <MobileNavigation open={menuOpen} onClose={close} />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar onOpenMenu={() => setMenuOpen(true)} />
        <DemoBanner />
        <main id="main" className="relative min-w-0 flex-1">
          {children}
        </main>
      </div>
    </div>
  );
}
