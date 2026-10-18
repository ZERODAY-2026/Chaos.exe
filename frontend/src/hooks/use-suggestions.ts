"use client";

import { useEffect, useState } from "react";
import { useWorkspace } from "@/components/workspace-provider";
import { suggestionsFromSchema } from "@/lib/suggestions";
import { useSchema } from "./use-schema";

export type Suggestions = { questions: string[]; source: "backend" | "schema" | "none"; loading: boolean };

export function useSuggestions(): Suggestions {
  const { client, mode, provider, health } = useWorkspace();
  const schema = useSchema();
  const providerId = provider?.id ?? null;
  const [backend, setBackend] = useState<string[] | null | undefined>(undefined);

  useEffect(() => {
    if (health.state !== "ok") {
      setBackend(undefined);
      return;
    }
    const ctrl = new AbortController();
    setBackend(undefined);
    client
      .suggestions(providerId, ctrl.signal)
      .then((q) => !ctrl.signal.aborted && setBackend(q))
      .catch(() => !ctrl.signal.aborted && setBackend(null));
    return () => ctrl.abort();
  }, [client, mode, providerId, health.state]);

  if (backend && backend.length) return { questions: backend.slice(0, 6), source: "backend", loading: false };
  if (backend === undefined && health.state === "ok") return { questions: [], source: "none", loading: true };
  const derived = suggestionsFromSchema(schema.data);
  if (derived.length) return { questions: derived, source: "schema", loading: false };
  return { questions: [], source: "none", loading: schema.status === "loading" };
}
