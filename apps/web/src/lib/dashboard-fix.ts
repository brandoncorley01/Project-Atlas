import { apiRequestHeaders, getApiUrl, usesBffProxy } from "@/lib/api-url";

export interface FixAllStep {
  step: string;
  ok: boolean;
  error?: string;
  message?: string;
  signals_created?: number;
  [key: string]: unknown;
}

export interface FixAllResult {
  ok: boolean;
  status?: string;
  message: string;
  steps: FixAllStep[];
  modules_scanned?: string[];
  needs_refresh_after?: Record<string, boolean>;
  fail_count?: number;
}

/** Run proactive Home repair (maintain + scan empty boards). */
export async function runDashboardFixAll(opts?: {
  scanEmpty?: boolean;
  timeoutMs?: number;
}): Promise<FixAllResult> {
  const scanEmpty = opts?.scanEmpty ?? true;
  const timeoutMs = opts?.timeoutMs ?? 300_000;

  let token: string | undefined;
  if (!usesBffProxy()) {
    const { createClient } = await import("@/lib/supabase/client");
    const { data } = await createClient().auth.getSession();
    token = data.session?.access_token;
    if (!token) {
      return { ok: false, message: "Not signed in", steps: [] };
    }
  }

  const apiUrl = getApiUrl();
  const qs = scanEmpty ? "scan_empty=true" : "scan_empty=false";
  try {
    const res = await fetch(`${apiUrl}/engine/fix-all?${qs}`, {
      method: "POST",
      headers: apiRequestHeaders(token),
      credentials: usesBffProxy() ? "include" : "same-origin",
      signal: AbortSignal.timeout(timeoutMs),
    });
    let data: Record<string, unknown> = {};
    try {
      data = (await res.json()) as Record<string, unknown>;
    } catch {
      return { ok: false, message: "Invalid response from Fix all", steps: [] };
    }
    if (!res.ok) {
      const detail = data.detail;
      return {
        ok: false,
        message: typeof detail === "string" ? detail : `Fix all failed (${res.status})`,
        steps: Array.isArray(data.steps) ? (data.steps as FixAllStep[]) : [],
      };
    }
    return {
      ok: (data.fail_count as number | undefined) === 0 || data.status === "ok",
      status: typeof data.status === "string" ? data.status : undefined,
      message: typeof data.message === "string" ? data.message : "Fix all finished",
      steps: Array.isArray(data.steps) ? (data.steps as FixAllStep[]) : [],
      modules_scanned: Array.isArray(data.modules_scanned)
        ? (data.modules_scanned as string[])
        : undefined,
      needs_refresh_after:
        data.needs_refresh_after && typeof data.needs_refresh_after === "object"
          ? (data.needs_refresh_after as Record<string, boolean>)
          : undefined,
      fail_count: typeof data.fail_count === "number" ? data.fail_count : undefined,
    };
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Fix all failed";
    if (msg.includes("timeout") || msg.includes("aborted")) {
      return {
        ok: false,
        message: "Fix all timed out — some steps may still finish. Retry Home in a minute.",
        steps: [],
      };
    }
    return { ok: false, message: msg, steps: [] };
  }
}
