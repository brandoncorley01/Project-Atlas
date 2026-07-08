"use client";

import { WatchlistProvider } from "@/components/watchlist/WatchlistProvider";

export function DashboardProviders({ children }: { children: React.ReactNode }) {
  return <WatchlistProvider>{children}</WatchlistProvider>;
}
