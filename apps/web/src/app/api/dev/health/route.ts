import { NextResponse } from "next/server";
import { DEFAULT_API_BASE } from "@/lib/api-config";

export const dynamic = "force-dynamic";

function healthUrl(): string {
  const base = process.env.NEXT_PUBLIC_API_URL ?? DEFAULT_API_BASE;
  const trimmed = base.replace(/\/$/, "");
  return trimmed.endsWith("/api/v1") ? `${trimmed}/health` : `${trimmed}/api/v1/health`;
}

/** Dev-only: ping FastAPI without auth (for connection banner + mobile restart flow). */
export async function GET() {
  if (process.env.NODE_ENV !== "development") {
    return NextResponse.json({ ok: true, dev: false }, { status: 200 });
  }

  const url = healthUrl();
  const port = (() => {
    try {
      return new URL(url).port || "8012";
    } catch {
      return "8012";
    }
  })();

  try {
    const upstream = await fetch(url, {
      cache: "no-store",
      headers: { Connection: "close" },
      signal: AbortSignal.timeout(6000),
    });
    const body = (await upstream.json().catch(() => ({}))) as Record<string, unknown>;
    return NextResponse.json(
      {
        ok: upstream.ok,
        dev: true,
        api_url: process.env.NEXT_PUBLIC_API_URL ?? DEFAULT_API_BASE,
        port,
        version: body.version ?? null,
        database: body.database ?? null,
      },
      { status: upstream.ok ? 200 : 503 },
    );
  } catch {
    return NextResponse.json(
      {
        ok: false,
        dev: true,
        api_url: process.env.NEXT_PUBLIC_API_URL ?? DEFAULT_API_BASE,
        port,
        error: "unreachable",
      },
      { status: 503 },
    );
  }
}
