import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiClient } from "./api-client";

function mockFetch(status: number, body: unknown, raw = false) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(raw ? (body as string) : JSON.stringify(body), { status })),
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("apiClient.query", () => {
  it("parses a valid response and normalises array rows", async () => {
    mockFetch(200, {
      query_id: "q1",
      status: "success",
      columns: [{ name: "A" }, { name: "B" }],
      rows: [
        [1, "x"],
        [2, "y"],
      ],
    });
    const res = await apiClient.query({ question: "hi" });
    expect(res.rows).toEqual([
      { A: 1, B: "x" },
      { A: 2, B: "y" },
    ]);
  });

  it("rejects malformed responses", async () => {
    mockFetch(200, { hello: "world" });
    await expect(apiClient.query({ question: "hi" })).rejects.toMatchObject({ kind: "malformed" });
  });

  it("rejects non-JSON bodies", async () => {
    mockFetch(200, "<html>oops</html>", true);
    await expect(apiClient.query({ question: "hi" })).rejects.toMatchObject({ kind: "malformed" });
  });

  it("accepts a contract-shaped error body on a 4xx/5xx", async () => {
    mockFetch(500, { query_id: "q2", status: "error", error: { stage: "execution", message: "boom" } });
    const res = await apiClient.query({ question: "hi" });
    expect(res.error?.stage).toBe("execution");
  });

  it("surfaces HTTP errors with the FastAPI detail", async () => {
    mockFetch(422, { detail: "question must not be empty" });
    const err = await apiClient.query({ question: "" }).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ kind: "http", status: 422, detail: "question must not be empty" });
  });

  it("maps fetch failures to network errors", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("Failed to fetch"))));
    await expect(apiClient.health()).rejects.toMatchObject({ kind: "network" });
  });

  it("treats a missing suggestions endpoint as optional", async () => {
    mockFetch(404, { detail: "Not Found" });
    await expect(apiClient.suggestions(null)).resolves.toBeNull();
  });
});
