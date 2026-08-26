import { DEFAULT_API_BASE } from "@/lib/api-config";

/**
 * Browser calls go through the Next.js BFF (/api/atlas → FastAPI).
 * Server-side calls hit the API directly.
 */
export function getApiUrl(): string {
  if (typeof window !== "undefined") {
    return "/api/atlas";
  }
  return process.env.NEXT_PUBLIC_API_URL ?? DEFAULT_API_BASE;
}

export function usesBffProxy(): boolean {
  return getApiUrl().startsWith("/api/atlas");
}

export function apiRequestHeaders(accessToken?: string): Record<string, string> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (!usesBffProxy() && accessToken) {
    headers.Authorization = `Bearer ${accessToken}`;
  }
  return headers;
}

/** User-facing copy when Scan/Repair/Fetch cannot reach the API. */
export function sportsEngineErrorMessage(
  err: unknown,
  action: "Scan" | "Repair" | "Fetch" | "Atlas Insight",
): string {
  const timedOut =
    err instanceof DOMException && (err.name === "TimeoutError" || err.name === "AbortError");
  if (timedOut) {
    return `${action} timed out — try again. Scan and Rescore stay free on cached odds.`;
  }
  if (usesBffProxy()) {
    return `${action} could not reach the API — Render may be waking up. Tap ${action} again, or use Restart in the header (~60s).`;
  }
  return `Backend not responding — run .\\scripts\\start-dev.ps1`;
}
