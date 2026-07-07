import Link from "next/link";
import { Suspense } from "react";
import { WatchlistView, type WatchlistItem } from "@/components/watchlist/WatchlistView";
import { getSupabaseEnv } from "@/lib/env";
import { createClient } from "@/lib/supabase/server";
import { apiFetch } from "@/lib/api";

interface WatchlistResponse {
  id: string;
  name: string;
  items: WatchlistItem[];
}

export default async function WatchlistPage() {
  let items: WatchlistItem[] = [];
  let watchlistId: string | null = null;

  if (getSupabaseEnv()) {
    const supabase = await createClient();
    const session = await supabase.auth.getSession();
    const token = session.data.session?.access_token;
    if (token) {
      try {
        const data = await apiFetch<WatchlistResponse>("/watchlist", token);
        items = data.items;
        watchlistId = data.id;
      } catch {
        items = [];
      }
    }
  }

  return (
    <>
      <div className="mb-6">
        <h1 className="text-2xl font-bold">Watchlist</h1>
        <p className="mt-1 text-sm text-muted">
          Your command center — saved stocks, options plays, sports bets, and parlays in one place.
        </p>
      </div>
      <Suspense fallback={<div className="text-sm text-muted">Loading watchlist…</div>}>
        <WatchlistView initialItems={items} watchlistId={watchlistId} />
      </Suspense>
    </>
  );
}
