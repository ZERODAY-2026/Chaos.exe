/** Safe localStorage helpers: storage may be unavailable (private mode, quotas, SSR). */

export function readStorage<T>(key: string, fallback: T): T {
  if (typeof window === "undefined") return fallback;
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

export function writeStorage(key: string, value: unknown): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Quota exceeded or storage disabled: the app keeps working without persistence.
  }
}

export const STORAGE_KEYS = {
  mode: "datamind.mode",
  provider: "datamind.provider",
  history: "datamind.history.v1",
  sidebar: "datamind.sidebar",
  theme: "datamind.theme",
} as const;
