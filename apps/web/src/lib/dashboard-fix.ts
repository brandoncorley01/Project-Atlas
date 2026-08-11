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

function humanStepName(step: string): string {
  const labels: Record<string, string> = {
    refresh_sports: "Sports scan",
    refresh_options: "Options scan",
    refresh_stocks: "Stocks scan",
    expire_stale: "Cleanup",
    signal_backfill: "Tracking backfill",
    resolve_outcomes: "Auto-grade",
    refresh_news: "News refresh",
    recover_sports_user_bets: "Recover Search bets",
    build_parlays: "Build parlays",
  };
  return labels[step] || step.replaceAll("_", " ");
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
      return {
        ok: false,
        message: "Fix all returned an invalid response — retry in a moment",
        steps: [],
      };
    }
    if (!res.ok) {
      const detail = data.detail;
      return {
        ok: false,
        message: typeof detail === "string" ? detail : `Fix all failed (${res.status})`,
        steps: Array.isArray(data.steps) ? (data.steps as FixAllStep[]) : [],
      };
    }
    const steps = Array.isArray(data.steps) ? (data.steps as FixAllStep[]) : [];
    const failCount =
      typeof data.fail_count === "number" ? data.fail_count : steps.filter((s) => !s.ok).length;
    let message = typeof data.message === "string" ? data.message : "Fix all finished";
    if (failCount > 0) {
      const failed = steps.filter((s) => !s.ok).slice(0, 2);
      if (failed.length && !failed.some((s) => message.includes(String(s.step)))) {
        const extra = failed
          .map(
            (s) =>
              `${humanStepName(s.step)}: ${String(s.error || s.message || "failed").slice(0, 120)}`,
          )
          .join(" · ");
        message = `${message} · ${extra}`;
      }
    }
    return {
      ok: failCount === 0 || data.status === "ok",
      status: typeof data.status === "string" ? data.status : undefined,
      message,
      steps,
      modules_scanned: Array.isArray(data.modules_scanned)
        ? (data.modules_scanned as string[])
        : undefined,
      needs_refresh_after:
        data.needs_refresh_after && typeof data.needs_refresh_after === "object"
          ? (data.needs_refresh_after as Record<string, boolean>)
          : undefined,
      fail_count: failCount,
    };
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Fix all failed";
    const timedOut =
      msg.includes("timeout") ||
      msg.includes("aborted") ||
      (err instanceof DOMException && (err.name === "TimeoutError" || err.name === "AbortError"));
    if (timedOut) {
      return {
        ok: false,
        message:
          "Fix all timed out — Sports may still need a scan. Open Sports → Fetch live odds, then retry Home.",
        steps: [],
      };
    }
    return { ok: false, message: msg || "Fix all failed — retry Home", steps: [] };
  }
}

export { humanStepName };
