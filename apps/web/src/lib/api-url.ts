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
    return `${action} timed out while the API was busy — tap ${action} again (second try usually works after Render wakes).`;
  }
  if (usesBffProxy()) {
    return `${action} could not reach the API — Render may be waking up. Tap ${action} again in a few seconds.`;
  }
  return `Backend not responding — run .\\scripts\\start-dev.ps1`;
}

/** True when a Scan/Repair response means the API was cold / unreachable. */
export function isApiWakingResponse(status: number, body: Record<string, unknown>): boolean {
  if (status !== 503 && status !== 502) return false;
  if (body.api_waking === true) return true;
  const detail = typeof body.detail === "string" ? body.detail : "";
  const message = typeof body.message === "string" ? body.message : "";
  return /waking|unavailable|timed out|timeout|Render/i.test(`${detail} ${message}`);
}
