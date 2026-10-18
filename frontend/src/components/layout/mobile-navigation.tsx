"use client";

import { useEffect, useRef } from "react";
import { SidebarContent } from "./sidebar";

export function MobileNavigation({ open, onClose }: { open: boolean; onClose: () => void }) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    panelRef.current?.querySelector<HTMLElement>("a,button")?.focus();
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [open, onClose]);

  return (
    <div className={`fixed inset-0 z-50 lg:hidden ${open ? "" : "pointer-events-none"}`} aria-hidden={!open}>
      <div
        className={`absolute inset-0 bg-black/50 transition-opacity duration-150 ${open ? "opacity-100" : "opacity-0"}`}
        onClick={onClose}
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label="Navigation"
        inert={!open}
        className={`absolute inset-y-0 left-0 w-[260px] max-w-[85vw] border-r border-line bg-bg-subtle transition-transform duration-150 ease-out ${open ? "translate-x-0" : "-translate-x-full"}`}
      >
        <SidebarContent collapsed={false} onNavigate={onClose} onClose={onClose} />
      </div>
    </div>
  );
}
