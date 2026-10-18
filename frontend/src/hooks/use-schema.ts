"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError } from "@/lib/api-client";
import type { SchemaResponse } from "@/lib/api-types";
import { useWorkspace } from "@/components/workspace-provider";

type SchemaState =
  | { status: "idle" | "loading"; data: SchemaResponse | null; error: null }
  | { status: "ready"; data: SchemaResponse; error: null }
  | { status: "error"; data: null; error: ApiError };

// Small in-memory cache so moving between pages does not refetch metadata.
const cache = new Map<string, SchemaResponse>();

export function useSchema() {
  const { client, mode, provider, health } = useWorkspace();
  const providerId = provider?.id ?? null;
  const key = `${mode}:${providerId ?? "default"}`;
  const connected = health.state === "ok" && (provider?.connected ?? true);
  const [state, setState] = useState<SchemaState>(() => {
    const hit = cache.get(key);
    return hit ? { status: "ready", data: hit, error: null } : { status: "idle", data: null, error: null };
  });
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    if (!connected) {
      setState({ status: "idle", data: null, error: null });
      return;
    }
    const hit = nonce === 0 ? cache.get(key) : undefined;
    if (hit) {
      setState({ status: "ready", data: hit, error: null });
      return;
    }
    const ctrl = new AbortController();
    setState({ status: "loading", data: null, error: null });
    client
      .schema(providerId, ctrl.signal)
      .then((data) => {
        cache.set(key, data);
        setState({ status: "ready", data, error: null });
      })
      .catch((e: unknown) => {
        if (ctrl.signal.aborted) return;
        setState({
          status: "error",
          data: null,
          error: e instanceof ApiError ? e : new ApiError("network", "Could not load the schema."),
        });
      });
    return () => ctrl.abort();
  }, [client, key, providerId, connected, nonce]);

  const reload = useCallback(() => {
    cache.delete(key);
    setNonce((n) => n + 1);
  }, [key]);

  return { ...state, reload, connected };
}
