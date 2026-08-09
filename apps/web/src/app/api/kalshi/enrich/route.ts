import { NextRequest, NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { enrichSportsItemsWithKalshi } from "@/lib/kalshi-public-pulse";

export const dynamic = "force-dynamic";
export const maxDuration = 30;

/**
 * POST { items: SportsSignal[] } → same items with public_market attached when matched.
 * Used by the sports board so Kalshi shows even if the Render API lacks enrichment.
 */
export async function POST(request: NextRequest) {
  try {
    const supabase = await createClient();
    const {
      data: { session },
    } = await supabase.auth.getSession();
    if (!session?.user) {
      return NextResponse.json({ detail: "Not signed in" }, { status: 401 });
    }

    const body = (await request.json().catch(() => null)) as {
      items?: Record<string, unknown>[];
    } | null;
    const items = Array.isArray(body?.items) ? body!.items! : [];
    if (!items.length) {
      return NextResponse.json({ items: [], matched: 0 });
    }

    const enriched = await enrichSportsItemsWithKalshi(items, {
      maxRows: Math.min(items.length, 60),
    });
    const matched = enriched.filter((row) => row.public_market).length;
    return NextResponse.json({ items: enriched, matched });
  } catch (err) {
    console.error("[kalshi enrich]", err);
    return NextResponse.json(
      { detail: err instanceof Error ? err.message : "Kalshi enrich failed", items: [] },
      { status: 500 },
    );
  }
}
