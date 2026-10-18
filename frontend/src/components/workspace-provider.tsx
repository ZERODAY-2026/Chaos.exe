"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { ApiError, apiClient, type DataClient } from "@/lib/api-client";
import type { HealthResponse, ProviderStatus, QueryResult, ResponseSource } from "@/lib/api-types";
import { demoClient } from "@/lib/demo/demo-client";
import { addToHistory, makeFailedEntry, makeHistoryEntry, type HistoryEntry } from "@/lib/history";
import { readStorage, STORAGE_KEYS, writeStorage } from "@/lib/storage";

export type Mode = ResponseSource; // "live" | "demo"
export type Theme = "dark" | "light";

export type HealthState =
  | { state: "loading"; data: HealthResponse | null; checkedAt: string | null }
  | { state: "ok"; data: HealthResponse; checkedAt: string }
  | { state: "error"; data: null; error: ApiError; checkedAt: string };

export type QueryState =
  | { phase: "idle" }
  | { phase: "running"; question: string; startedAt: number }
  | { phase: "done"; result: QueryResult; fromHistory?: boolean; rowsTrimmed?: boolean }
  | { phase: "failed"; question: string; error: ApiError };


type WorkspaceContextValue = {
  mode: Mode;
  setMode: (m: Mode) => void;
  client: DataClient;
  theme: Theme;
  setTheme: (t: Theme) => void;
  health: HealthState;
  refreshHealth: () => void;
  providers: ProviderStatus[];
  provider: ProviderStatus | null;
  setProviderId: (id: string) => void;
  query: QueryState;
  runQuery: (question: string) => void;
  cancelQuery: () => void;
  resetQuery: () => void;
  openHistoryEntry: (entry: HistoryEntry) => void;
  history: HistoryEntry[];
  clearHistory: () => void;
  removeHistoryEntry: (id: string) => void;
  draft: string;
  setDraft: (v: string) => void;
  sidebarCollapsed: boolean;
  setSidebarCollapsed: (v: boolean) => void;
  hydrated: boolean;
};

const WorkspaceContext = createContext<WorkspaceContextValue | null>(null);

const ENV_DEMO = process.env.NEXT_PUBLIC_DEMO_MODE === "true";

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [hydrated, setHydrated] = useState(false);
  const [mode, setModeState] = useState<Mode>(ENV_DEMO ? "demo" : "live");
  const [theme, setThemeState] = useState<Theme>("dark");
  const [health, setHealth] = useState<HealthState>({ state: "loading", data: null, checkedAt: null });
  const [providerId, setProviderIdState] = useState<string | null>(null);
  const [query, setQuery] = useState<QueryState>({ phase: "idle" });
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [draft, setDraft] = useState("");
  const [sidebarCollapsed, setSidebarCollapsedState] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const healthAbortRef = useRef<AbortController | null>(null);

  // Hydrate persisted preferences after mount to avoid SSR mismatches.
  useEffect(() => {
    setModeState(readStorage<Mode>(STORAGE_KEYS.mode, ENV_DEMO ? "demo" : "live"));
    setProviderIdState(readStorage<string | null>(STORAGE_KEYS.provider, null));
    setHistory(readStorage<HistoryEntry[]>(STORAGE_KEYS.history, []));
    setSidebarCollapsedState(readStorage<boolean>(STORAGE_KEYS.sidebar, false));
    const attr = document.documentElement.getAttribute("data-theme");
    setThemeState(attr === "light" ? "light" : "dark");
    setHydrated(true);
  }, []);

  const client: DataClient = mode === "demo" ? demoClient : apiClient;

  const refreshHealth = useCallback(() => {
    healthAbortRef.current?.abort();
    const ctrl = new AbortController();
    healthAbortRef.current = ctrl;
    setHealth((prev) => ({ state: "loading", data: prev.data, checkedAt: prev.checkedAt }));
    client
      .health(ctrl.signal)
      .then((data) => {
        if (!ctrl.signal.aborted) setHealth({ state: "ok", data, checkedAt: new Date().toISOString() });
      })
      .catch((e: unknown) => {
        if (ctrl.signal.aborted) return;
        const err = e instanceof ApiError ? e : new ApiError("network", "Could not check the backend connection.");
        setHealth({ state: "error", data: null, error: err, checkedAt: new Date().toISOString() });
      });
  }, [client]);

  useEffect(() => {
    if (!hydrated) return;
    refreshHealth();
    return () => healthAbortRef.current?.abort();
  }, [hydrated, refreshHealth]);

  const providers = useMemo(() => (health.state === "ok" ? health.data.providers : []), [health]);

  const provider = useMemo<ProviderStatus | null>(() => {
    if (!providers.length) return null;
    return (
      providers.find((p) => p.id === providerId) ??
      providers.find((p) => p.is_default && p.connected) ??
      providers.find((p) => p.connected) ??
      providers[0] ??
      null
    );
  }, [providers, providerId]);

  const setMode = useCallback((m: Mode) => {
    abortRef.current?.abort();
    setModeState(m);
    writeStorage(STORAGE_KEYS.mode, m);
    setQuery({ phase: "idle" });
  }, []);

  const setTheme = useCallback((t: Theme) => {
    setThemeState(t);
    document.documentElement.setAttribute("data-theme", t);
    writeStorage(STORAGE_KEYS.theme, t);
  }, []);

  const setProviderId = useCallback((id: string) => {
    setProviderIdState(id);
    writeStorage(STORAGE_KEYS.provider, id);
  }, []);

  const setSidebarCollapsed = useCallback((v: boolean) => {
    setSidebarCollapsedState(v);
    writeStorage(STORAGE_KEYS.sidebar, v);
  }, []);

  const pushHistory = useCallback((entry: HistoryEntry) => {
    setHistory((prev) => {
      const next = addToHistory(prev, entry);
      writeStorage(STORAGE_KEYS.history, next);
      return next;
    });
  }, []);

  const runQuery = useCallback(
    (raw: string) => {
      const question = raw.trim();
      if (!question) return;
      abortRef.current?.abort();
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      const startedAt = performance.now();
      const providerAtStart = provider?.id ?? null;
      setQuery({ phase: "running", question, startedAt: Date.now() });

      client
        .query({ question, provider: providerAtStart ?? undefined }, ctrl.signal)
        .then((response) => {
          if (ctrl.signal.aborted) return;
          const result: QueryResult = {
            response,
            source: mode,
            question,
            provider: response.provider ?? providerAtStart,
            receivedAt: new Date().toISOString(),
            clientDurationMs: performance.now() - startedAt,
          };
          setQuery({ phase: "done", result });
          pushHistory(makeHistoryEntry(result));
        })
        .catch((e: unknown) => {
          if (ctrl.signal.aborted) return;
          const err = e instanceof ApiError ? e : new ApiError("network", "The request failed unexpectedly.");
          setQuery({ phase: "failed", question, error: err });
          pushHistory(makeFailedEntry(question, providerAtStart, mode, err.message));
        });
    },
    [client, mode, provider, pushHistory],
  );

  const cancelQuery = useCallback(() => {
    abortRef.current?.abort();
    setQuery({ phase: "idle" });
  }, []);

  const resetQuery = useCallback(() => {
    abortRef.current?.abort();
    setQuery({ phase: "idle" });
  }, []);

  const openHistoryEntry = useCallback((entry: HistoryEntry) => {
    if (!entry.result) return;
    abortRef.current?.abort();
    setQuery({ phase: "done", result: entry.result, fromHistory: true, rowsTrimmed: entry.rowsTrimmed });
  }, []);

  const clearHistory = useCallback(() => {
    setHistory([]);
    writeStorage(STORAGE_KEYS.history, []);
  }, []);

  const removeHistoryEntry = useCallback((id: string) => {
    setHistory((prev) => {
      const next = prev.filter((e) => e.id !== id);
      writeStorage(STORAGE_KEYS.history, next);
      return next;
    });
  }, []);

  const value: WorkspaceContextValue = {
    mode,
    setMode,
    client,
    theme,
    setTheme,
    health,
    refreshHealth,
    providers,
    provider,
    setProviderId,
    query,
    runQuery,
    cancelQuery,
    resetQuery,
    openHistoryEntry,
    history,
    clearHistory,
    removeHistoryEntry,
    draft,
    setDraft,
    sidebarCollapsed,
    setSidebarCollapsed,
    hydrated,
  };

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

export function useWorkspace(): WorkspaceContextValue {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) throw new Error("useWorkspace must be used inside <WorkspaceProvider>");
  return ctx;
}
