/**
 * The only module that talks to the DataMind backend.
 *
 * Every response is validated with Zod; anything that does not match the contract
 * becomes an ApiError of kind "malformed" instead of reaching the UI half-parsed.
 */
import { z } from "zod";
import {
  HealthResponseSchema,
  QueryResponseSchema,
  SchemaResponseSchema,
  SuggestionsResponseSchema,
  type HealthResponse,
  type QueryRequest,
  type QueryResponse,
  type SchemaResponse,
} from "./api-types";

export const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000").replace(/\/+$/, "");

export type ApiErrorKind = "network" | "timeout" | "aborted" | "http" | "malformed" | "not_found";

export class ApiError extends Error {
  constructor(
    public kind: ApiErrorKind,
    message: string,
    public status?: number,
    public detail?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

const DEFAULT_TIMEOUT_MS = 15_000;
export const QUERY_TIMEOUT_MS = 120_000;

async function request<T>(
  path: string,
  schema: z.ZodType<T, z.ZodTypeDef, unknown>,
  init: RequestInit & { timeoutMs?: number } = {},
): Promise<T> {
  const { timeoutMs = DEFAULT_TIMEOUT_MS, signal: outerSignal, ...rest } = init;
  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  const onOuterAbort = () => controller.abort();
  outerSignal?.addEventListener("abort", onOuterAbort);

  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      ...rest,
      signal: controller.signal,
      headers: { Accept: "application/json", ...(rest.body ? { "Content-Type": "application/json" } : {}), ...rest.headers },
    });
  } catch {
    if (timedOut) throw new ApiError("timeout", `The backend did not respond within ${Math.round(timeoutMs / 1000)} seconds.`);
    if (outerSignal?.aborted) throw new ApiError("aborted", "Request cancelled.");
    throw new ApiError("network", `Could not reach the DataMind backend at ${API_BASE_URL}.`);
  } finally {
    clearTimeout(timer);
    outerSignal?.removeEventListener("abort", onOuterAbort);
  }

  let body: unknown = null;
  const text = await res.text();
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      if (!res.ok) throw new ApiError("http", `The backend returned HTTP ${res.status}.`, res.status, text.slice(0, 300));
      throw new ApiError("malformed", "The backend returned a response that is not valid JSON.", res.status);
    }
  }

  if (!res.ok) {
    // A query endpoint may return a contract-shaped error body with a non-2xx status.
    const asContract = schema.safeParse(body);
    if (asContract.success && res.status !== 404) return asContract.data;
    if (res.status === 404) throw new ApiError("not_found", `Endpoint ${path} is not available on this backend.`, 404);
    throw new ApiError("http", `The backend returned HTTP ${res.status}.`, res.status, extractDetail(body));
  }

  const parsed = schema.safeParse(body);
  if (!parsed.success) {
    const issue = parsed.error.issues[0];
    throw new ApiError(
      "malformed",
      "The backend response did not match the expected format.",
      res.status,
      issue ? `${issue.path.join(".") || "(root)"}: ${issue.message}` : undefined,
    );
  }
  return parsed.data;
}

function extractDetail(body: unknown): string | undefined {
  if (body && typeof body === "object" && "detail" in body) {
    const d = (body as { detail: unknown }).detail;
    if (typeof d === "string") return d;
    try {
      return JSON.stringify(d).slice(0, 300);
    } catch {
      return undefined;
    }
  }
  return undefined;
}

/**
 * Some backends return rows as arrays aligned with `columns`. Normalise them to
 * objects before validation so the rest of the UI sees one shape.
 */
const NormalisedQueryResponseSchema = z.preprocess((raw) => {
  if (!raw || typeof raw !== "object") return raw;
  const r = raw as { rows?: unknown; columns?: unknown };
  if (Array.isArray(r.rows) && Array.isArray(r.columns) && r.rows.every(Array.isArray)) {
    const names = (r.columns as Array<{ name?: unknown }>).map((c) => String(c?.name ?? ""));
    return {
      ...r,
      rows: (r.rows as unknown[][]).map((row) => Object.fromEntries(names.map((n, i) => [n, row[i]]))),
    };
  }
  return raw;
}, QueryResponseSchema);

/** The surface both the live client and the demo client implement. */
export type DataClient = {
  health(signal?: AbortSignal): Promise<HealthResponse>;
  schema(provider: string | null, signal?: AbortSignal): Promise<SchemaResponse>;
  suggestions(provider: string | null, signal?: AbortSignal): Promise<string[] | null>;
  query(body: QueryRequest, signal?: AbortSignal): Promise<QueryResponse>;
};

export const apiClient: DataClient = {
  health(signal?: AbortSignal): Promise<HealthResponse> {
    return request("/api/health", HealthResponseSchema, { signal, timeoutMs: 8_000 });
  },
  schema(provider: string | null, signal?: AbortSignal): Promise<SchemaResponse> {
    const qs = provider ? `?provider=${encodeURIComponent(provider)}` : "";
    return request(`/api/schema${qs}`, SchemaResponseSchema, { signal });
  },
  async suggestions(provider: string | null, signal?: AbortSignal): Promise<string[] | null> {
    const qs = provider ? `?provider=${encodeURIComponent(provider)}` : "";
    try {
      const res = await request(`/api/suggestions${qs}`, SuggestionsResponseSchema, { signal });
      return res.questions;
    } catch (e) {
      if (e instanceof ApiError && e.kind === "not_found") return null; // optional endpoint
      throw e;
    }
  },
  query(body: QueryRequest, signal?: AbortSignal): Promise<QueryResponse> {
    return request("/api/query", NormalisedQueryResponseSchema, {
      method: "POST",
      body: JSON.stringify(body),
      signal,
      timeoutMs: QUERY_TIMEOUT_MS,
    });
  },
};
