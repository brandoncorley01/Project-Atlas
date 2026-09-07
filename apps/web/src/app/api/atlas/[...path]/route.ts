import { NextRequest, NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { resolveApiBase } from "@/lib/api-config";
import { enrichSportsItemsWithKalshi } from "@/lib/kalshi-public-pulse";

const API_BASE = resolveApiBase();
const PROXY_TIMEOUT_MS = 60_000;
const DASHBOARD_PROXY_TIMEOUT_MS = 50_000;
const AI_PROXY_TIMEOUT_MS = 90_000;
const INSIGHT_SEARCH_PROXY_TIMEOUT_MS = 150_000;
/** Render free-tier cold start often needs ~20–40s before /health answers. */
const API_WAKE_TIMEOUT_MS = 25_000;
/** Engine scans / Fix all — leave headroom under Vercel maxDuration (300s) for wake ping. */
const ENGINE_LONG_PROXY_TIMEOUT_MS = 250_000;

/** Vercel Pro allows up to 300s; Hobby caps at 60s regardless. */
export const maxDuration = 300;
export const dynamic = "force-dynamic";

function proxyTimeoutFor(subpath: string): number {
  if (subpath.startsWith("ai/")) return AI_PROXY_TIMEOUT_MS;
  if (subpath === "signals/sports/events") return INSIGHT_SEARCH_PROXY_TIMEOUT_MS;
  if (subpath === "dashboard") return DASHBOARD_PROXY_TIMEOUT_MS;
  // Heavy Market/Options Intelligence paths need Yahoo time; keep lighter MI routes shorter.
  if (
    subpath === "market-intelligence/heatmap"
    || subpath === "market-intelligence/options/flow"
    || subpath === "market-intelligence/options/heatmap"
    || subpath === "market-intelligence/options/smart-money"
    || subpath === "market-intelligence/earnings/desk"
    || subpath === "market-intelligence/dark-pool"
    || subpath === "market-intelligence/congress-trades"
    || subpath === "market-intelligence/weather"
    || subpath === "market-intelligence/sector-rotation"
    || subpath === "market-intelligence/smart-money-heatmap"
  ) {
    return 90_000;
  }
  if (subpath.startsWith("market-intelligence")) return 45_000;
  if (
    subpath === "engine/fix-all"
    || subpath === "engine/refresh-options"
    || subpath === "engine/refresh-stocks"
    || subpath === "engine/refresh-sports-openai"
    || subpath === "engine/refresh-sports"
    || subpath === "engine/repair-sports"
    || subpath.startsWith("engine/refresh-sports")
    || subpath.startsWith("engine/repair-sports")
  ) {
    // Fix all / sports Scan / Repair / Fetch need the full budget (news + Odds + save).
    return ENGINE_LONG_PROXY_TIMEOUT_MS;
  }
  return PROXY_TIMEOUT_MS;
}

function isEngineLongPath(subpath: string): boolean {
  return (
    subpath === "engine/fix-all"
    || subpath === "engine/refresh-options"
    || subpath === "engine/refresh-stocks"
    || subpath === "engine/refresh-sports"
    || subpath === "engine/repair-sports"
    || subpath.startsWith("engine/refresh-sports")
    || subpath.startsWith("engine/repair-sports")
  );
}

function isUnreachableError(err: unknown): boolean {
  const message = err instanceof Error ? err.message : String(err);
  return (
    message.includes("fetch failed")
    || message.includes("ECONNREFUSED")
    || message.includes("ECONNRESET")
    || message.includes("ENOTFOUND")
    || message.includes("socket")
    || message.includes("network")
    || message.includes("timeout")
    || message.includes("aborted")
    || message.includes("TimeoutError")
    || message.includes("AbortError")
  );
}

/** Ping /health so a sleeping Render free-tier instance is awake before Scan. */
async function wakeApiIfNeeded(subpath: string): Promise<void> {
  if (!isEngineLongPath(subpath)) return;
  const healthUrl = `${API_BASE}/health`;
  try {
    await fetch(healthUrl, {
      method: "GET",
      cache: "no-store",
      headers: { Connection: "close" },
      signal: AbortSignal.timeout(API_WAKE_TIMEOUT_MS),
    });
  } catch (err) {
    console.warn("[atlas proxy] API wake ping failed (will still try Scan)", healthUrl, err);
  }
}

async function upstreamFetch(
  target: string,
  init: RequestInit,
  *,
  retries = 0,
): Promise<Response> {
  try {
    return await fetch(target, init);
  } catch (err) {
    if (retries > 0 && isUnreachableError(err)) {
      // Brief pause then retry — wakeApiIfNeeded already ran; avoid burning the 300s budget.
      await new Promise((r) => setTimeout(r, 2000));
      return upstreamFetch(target, init, { retries: retries - 1 });
    }
    throw err;
  }
}

async function proxyRequest(request: NextRequest, pathSegments: string[]) {
  try {
    const supabase = await createClient();
    const {
      data: { session },
      error: sessionError,
    } = await supabase.auth.getSession();

    if (sessionError || !session?.user) {
      return NextResponse.json({ detail: "Not signed in" }, { status: 401 });
    }

    const token = session.access_token;
    if (!token) {
      return NextResponse.json({ detail: "No access token — sign out and sign in again" }, { status: 401 });
    }

    const subpath = pathSegments.join("/");
    const target = `${API_BASE}/${subpath}${request.nextUrl.search}`;
    const timeoutMs = proxyTimeoutFor(subpath);

    const hasBody = request.method !== "GET" && request.method !== "HEAD";
    const body = hasBody ? await request.text() : undefined;

    await wakeApiIfNeeded(subpath);

    const upstream = await upstreamFetch(
      target,
      {
        method: request.method,
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
          Connection: "close",
        },
        body: body || undefined,
        cache: "no-store",
        signal: AbortSignal.timeout(timeoutMs),
      },
      { retries: isEngineLongPath(subpath) ? 1 : 0 },
    );

    const text = await upstream.text();
    if (!upstream.ok) {
      console.error("[atlas proxy]", target, upstream.status, text.slice(0, 300));
      if (upstream.status === 404) {
        return NextResponse.json(
          {
            detail:
              "Backend route not found. On Vercel, set NEXT_PUBLIC_API_URL to your Render URL "
              + "including /api/v1 (example: https://atlas-api-xxxx.onrender.com/api/v1). "
              + "Then redeploy.",
            proxy_target: target,
          },
          { status: 502 },
        );
      }
    }

    // Attach Kalshi public-probability pulse on sports list/detail even when the
    // Render API build does not yet include server-side enrichment.
    if (
      upstream.ok
      && request.method === "GET"
      && (subpath === "signals/sports" || /^signals\/sports\/[^/]+$/.test(subpath))
    ) {
      try {
        const payload = JSON.parse(text) as Record<string, unknown>;
        if (subpath === "signals/sports" && Array.isArray(payload.items)) {
          payload.items = await enrichSportsItemsWithKalshi(
            payload.items as Record<string, unknown>[],
            { maxRows: Math.min(payload.items.length, 48) },
          );
          return NextResponse.json(payload, { status: upstream.status });
        }
        if (
          /^signals\/sports\/[^/]+$/.test(subpath)
          && payload
          && typeof payload === "object"
          && !Array.isArray(payload)
        ) {
          const [enriched] = await enrichSportsItemsWithKalshi(
            [payload as Record<string, unknown>],
            { maxRows: 1 },
          );
          return NextResponse.json(enriched ?? payload, { status: upstream.status });
        }
      } catch (err) {
        console.warn("[atlas proxy] Kalshi enrich skipped", err);
      }
    }

    return new NextResponse(text, {
      status: upstream.status,
      headers: {
        "Content-Type": upstream.headers.get("Content-Type") ?? "application/json",
      },
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Proxy request failed";
    const unreachable = isUnreachableError(err);
    return NextResponse.json(
      {
        detail: unreachable
          ? process.env.NODE_ENV === "development"
            ? `Cannot reach API at ${API_BASE}. Tap Restart in the top-right header (~60 seconds).`
            : message.includes("timeout") || message.includes("aborted")
              ? "Scan timed out while the API was waking up — tap Scan again (second try usually works)."
              : "Atlas API is waking up (Render). Tap Scan again in a few seconds."
          : message,
        api_waking: unreachable,
      },
      { status: unreachable ? 503 : 500 },
    );
  }
}

type RouteContext = { params: Promise<{ path: string[] }> };

export async function GET(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  return proxyRequest(request, path);
}

export async function POST(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  return proxyRequest(request, path);
}

export async function PUT(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  return proxyRequest(request, path);
}

export async function PATCH(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  return proxyRequest(request, path);
}

export async function DELETE(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  return proxyRequest(request, path);
}
