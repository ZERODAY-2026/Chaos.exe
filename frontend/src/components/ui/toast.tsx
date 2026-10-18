"use client";

import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import { StatusDot } from "./badge";

type Toast = { id: number; message: string; tone: "success" | "error" };
const ToastContext = createContext<(message: string, tone?: Toast["tone"]) => void>(() => {});

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((message: string, tone: Toast["tone"] = "success") => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t.slice(-2), { id, message, tone }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 3200);
  }, []);
  return (
    <ToastContext.Provider value={push}>
      {children}
      <div aria-live="polite" role="status" className="pointer-events-none fixed right-4 bottom-4 z-[60] flex flex-col items-end gap-2">
        {toasts.map((t) => (
          <div
            key={t.id}
            className="enter pointer-events-auto flex items-center gap-2.5 rounded-md bg-surface-2 px-3 py-2 text-[13px] text-fg shadow-elevated"
          >
            <StatusDot tone={t.tone === "success" ? "success" : "danger"} />
            {t.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export const useToast = () => useContext(ToastContext);
