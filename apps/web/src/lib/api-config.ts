/** Single source of truth for API URL (must match apps/web/.env.local). */
export const DEFAULT_API_BASE = "http://127.0.0.1:8012/api/v1";

export function resolveApiBase(): string {
  return process.env.NEXT_PUBLIC_API_URL ?? DEFAULT_API_BASE;
}

export function apiPortLabel(): string {
  try {
    const url = new URL(resolveApiBase());
    return url.port || "8012";
  } catch {
    return "8012";
  }
}

export const API_START_HINT = "Tap Restart in the top-right header (~60 seconds)";
