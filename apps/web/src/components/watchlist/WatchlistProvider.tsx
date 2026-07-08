"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { fetchWatchlist } from "@/lib/watchlist-api";
import type { WatchlistItem } from "@/lib/watchlist-types";
import { watchlistItemKey } from "@/lib/watchlist-types";

interface WatchlistContextValue {
  items: WatchlistItem[];
  savedKeys: Set<string>;
  isSaved: (symbol: string, itemType: string) => boolean;
  markSaved: (item: WatchlistItem) => void;
  markRemoved: (itemId: string) => void;
  refresh: () => Promise<void>;
  loading: boolean;
}

const WatchlistContext = createContext<WatchlistContextValue | null>(null);

export function WatchlistProvider({
  children,
  initialItems = [],
}: {
  children: React.ReactNode;
  initialItems?: WatchlistItem[];
}) {
  const [items, setItems] = useState<WatchlistItem[]>(initialItems);
  const [loading, setLoading] = useState(initialItems.length === 0);

  const savedKeys = useMemo(
    () => new Set(items.map((item) => watchlistItemKey(item))),
    [items],
  );

  const refresh = useCallback(async () => {
    setLoading(true);
    const data = await fetchWatchlist();
    if (data?.items) {
      setItems(data.items);
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    const onUpdate = () => {
      void refresh();
    };
    window.addEventListener("atlas:watchlist-updated", onUpdate);
    return () => window.removeEventListener("atlas:watchlist-updated", onUpdate);
  }, [refresh]);

  const markSaved = useCallback((item: WatchlistItem) => {
    setItems((prev) => {
      const key = watchlistItemKey(item);
      const without = prev.filter((row) => watchlistItemKey(row) !== key);
      return [item, ...without];
    });
  }, []);

  const markRemoved = useCallback((itemId: string) => {
    setItems((prev) => prev.filter((item) => item.id !== itemId));
  }, []);

  const isSaved = useCallback(
    (symbol: string, itemType: string) => savedKeys.has(`${itemType}:${symbol}`),
    [savedKeys],
  );

  const value = useMemo(
    () => ({
      items,
      savedKeys,
      isSaved,
      markSaved,
      markRemoved,
      refresh,
      loading,
    }),
    [items, savedKeys, isSaved, markSaved, markRemoved, refresh, loading],
  );

  return <WatchlistContext.Provider value={value}>{children}</WatchlistContext.Provider>;
}

export function useWatchlist() {
  const ctx = useContext(WatchlistContext);
  if (!ctx) {
    throw new Error("useWatchlist must be used within WatchlistProvider");
  }
  return ctx;
}

export function useWatchlistOptional() {
  return useContext(WatchlistContext);
}
