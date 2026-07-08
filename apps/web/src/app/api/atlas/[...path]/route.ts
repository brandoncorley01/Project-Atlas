import { NextRequest, NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { resolveApiBase } from "@/lib/api-config";

const API_BASE = resolveApiBase();
const PROXY_TIMEOUT_MS = 60_000;
const DASHBOARD_PROXY_TIMEOUT_MS = 50_000;

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
    const timeoutMs = subpath === "dashboard" ? DASHBOARD_PROXY_TIMEOUT_MS : PROXY_TIMEOUT_MS;

    const hasBody = request.method !== "GET" && request.method !== "HEAD";
    const body = hasBody ? await request.text() : undefined;

    const upstream = await fetch(target, {
      method: request.method,
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
        Connection: "close",
      },
      body: body || undefined,
      cache: "no-store",
      signal: AbortSignal.timeout(timeoutMs),
    });

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

    return new NextResponse(text, {
      status: upstream.status,
      headers: {
        "Content-Type": upstream.headers.get("Content-Type") ?? "application/json",
      },
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Proxy request failed";
    const unreachable =
      message.includes("fetch failed") ||
      message.includes("ECONNREFUSED") ||
      message.includes("timeout") ||
      message.includes("aborted");
    return NextResponse.json(
      {
        detail: unreachable
          ? process.env.NODE_ENV === "development"
            ? `Cannot reach API at ${API_BASE}. Tap Restart in the top-right header (~60 seconds).`
            : "Atlas API is temporarily unavailable. Try again in a moment."
          : message,
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
