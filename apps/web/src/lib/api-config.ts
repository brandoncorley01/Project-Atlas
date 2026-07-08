/** Single source of truth for API URL (must match apps/web/.env.local). */
export const DEFAULT_API_BASE = "http://127.0.0.1:8012/api/v1";

/** Normalize Vercel/Render API base — fixes missing /api/v1 suffix. */
export function resolveApiBase(): string {
  let base = (process.env.NEXT_PUBLIC_API_URL ?? DEFAULT_API_BASE).trim().replace(/\/+$/, "");
  if (!base.endsWith("/api/v1")) {
    if (!/\/api\/v\d+/.test(base)) {
      base = `${base}/api/v1`;
    }
  }
  return base;
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
