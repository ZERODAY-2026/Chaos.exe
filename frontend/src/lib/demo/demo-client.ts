/** Demo-mode stand-in for apiClient. Answers only the bundled fixtures; never pretends to execute. */
import type { DataClient } from "../api-client";
import type { HealthResponse, QueryRequest, QueryResponse, SchemaResponse } from "../api-types";
import { DEMO_PROVIDER, demoFixtures, demoHealth, demoSchema, demoSuggestions } from "./fixtures";

const wait = (ms: number, signal?: AbortSignal) =>
  new Promise<void>((resolve, reject) => {
    const t = setTimeout(resolve, ms);
    signal?.addEventListener("abort", () => {
      clearTimeout(t);
      reject(new DOMException("Aborted", "AbortError"));
    });
  });

let counter = 0;

export const demoClient: DataClient = {
  async health(): Promise<HealthResponse> {
    return demoHealth;
  },
  async schema(): Promise<SchemaResponse> {
    return demoSchema;
  },
  async suggestions(): Promise<string[]> {
    return demoSuggestions;
  },
  async query(body: QueryRequest, signal?: AbortSignal): Promise<QueryResponse> {
    // A short pause so loading states are visible; not a measured execution time.
    await wait(700, signal);
    counter += 1;
    const query_id = `demo-${Date.now().toString(36)}-${counter}`;
    const fixture = demoFixtures.find((f) => f.match.test(body.question));
    if (fixture) return { query_id, ...fixture.build(body.question) };
    return {
      query_id,
      status: "error",
      provider: DEMO_PROVIDER,
      question: body.question,
      executed: false,
      error: {
        code: "DEMO_UNSUPPORTED",
        message: "Demo mode can only answer the sample questions. Connect the DataMind backend to ask anything about your data.",
      },
    };
  },
};
