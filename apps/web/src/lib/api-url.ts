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
