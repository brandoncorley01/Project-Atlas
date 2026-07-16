"use client";

import { useCallback, useMemo, useState, type FormEvent } from "react";
import { apiRequestHeaders, getApiUrl, usesBffProxy } from "@/lib/api-url";

export interface BookAvailability {
  book_key: string;
  book_title: string;
  odds_american?: number | null;
}

export interface SportsEventMarket {
  bet_type: string;
  selection: string;
  odds_american: number;
  point?: number | null;
  book_key?: string;
  book_title?: string;
  team_or_side?: string;
  player_name?: string | null;
  available_on?: BookAvailability[];
  available_books?: string[];
  insight_rank?: number | null;
  hit_probability?: number | null;
  confidence?: number | null;
  opportunity?: number | null;
  risk?: number | null;
  value_grade?: string | null;
  thesis?: string | null;
  bull_case?: string | null;
  bear_case?: string | null;
  best_odds_american?: number | null;
  best_book_title?: string | null;
  is_top_pick?: boolean;
  is_best_odds?: boolean;
  is_most_likely?: boolean;
}

export interface SportsEventHit {
  event_id: string;
  sport: string;
  sport_key?: string;
  home_team: string;
  away_team: string;
  event_name: string;
  event_start?: string | null;
  hours_until_start?: number | null;
  markets: SportsEventMarket[];
}

export interface SportsMarketHit extends SportsEventMarket {
  event_id?: string;
  sport?: string;
  sport_key?: string;
  home_team?: string;
  away_team?: string;
  event_name?: string;
  event_start?: string | null;
  hours_until_start?: number | null;
  prop_market?: string | null;
  fanduel_verified?: boolean;
  insight_rank?: number | null;
  hit_probability?: number | null;
  confidence?: number | null;
  opportunity?: number | null;
  risk?: number | null;
  value_grade?: string | null;
  thesis?: string | null;
  bull_case?: string | null;
  bear_case?: string | null;
  best_odds_american?: number | null;
  best_book_title?: string | null;
  is_top_pick?: boolean;
  is_best_odds?: boolean;
  is_most_likely?: boolean;
}

/** Signal payload returned when adding a FanDuel market as a parlay leg. */
export interface ParlayLegSignal {
  id: string;
  sport: string;
  event_name: string;
  bet_type: string;
  selection: string;
  odds_american: number;
  event_start?: string | null;
}

async function getToken() {
  if (usesBffProxy()) return undefined;
  const { createClient } = await import("@/lib/supabase/client");
  const { data } = await createClient().auth.getSession();
  return data.session?.access_token ?? undefined;
}

function formatStart(iso?: string | null) {
  if (!iso) return "Time TBD";
  try {
    return new Date(iso).toLocaleString(undefined, {
      weekday: "short",
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function oddsLabel(n: number) {
  return n > 0 ? `+${n}` : `${n}`;
}

function truthy(v: unknown) {
  return v === true || v === "true" || v === 1 || v === "1";
}

function rankLabel(hit: SportsMarketHit, idx: number) {
  return typeof hit.insight_rank === "number" ? hit.insight_rank : idx + 1;
}

function booksLabel(m: SportsEventMarket | SportsMarketHit) {
  const books = m.available_on?.length
    ? m.available_on
    : m.book_title
      ? [{ book_key: m.book_key || "", book_title: m.book_title, odds_american: m.odds_american }]
      : [];
  if (!books.length) return "Unverified";
  return books
    .map((b) => {
      const odds =
        typeof b.odds_american === "number" ? ` ${oddsLabel(b.odds_american)}` : "";
      return `${b.book_title}${odds}`;
    })
    .join(" · ");
}

function hasFanDuel(m: SportsEventMarket | SportsMarketHit) {
  if (m.book_key === "fanduel") return true;
  if (truthy((m as SportsMarketHit).fanduel_verified)) return true;
  return Boolean(
    m.available_on?.some(
      (b) => b.book_key === "fanduel" && typeof b.odds_american === "number",
    ),
  );
}

function withFanDuelLine<T extends SportsEventMarket | SportsMarketHit>(m: T): T {
  const fd = m.available_on?.find(
    (b) => b.book_key === "fanduel" && typeof b.odds_american === "number",
  );
  if (fd && typeof fd.odds_american === "number") {
    return {
      ...m,
      book_key: "fanduel",
      book_title: "FanDuel",
      odds_american: fd.odds_american,
    };
  }
  return {
    ...m,
    book_key: m.book_key || "fanduel",
    book_title: m.book_title || "FanDuel",
  };
}

export function SportsEventSearch({
  onBetLogged,
  intent = "log",
  onParlayLegAdded,
  embedded = false,
}: {
  onBetLogged?: () => void | Promise<void>;
  /** `parlay` = FanDuel-only search that adds legs to a ticket builder. */
  intent?: "log" | "parlay";
  onParlayLegAdded?: (leg: ParlayLegSignal) => void | Promise<void>;
  /** Tighter layout when nested inside a parlay card. */
  embedded?: boolean;
}) {
  const isParlay = intent === "parlay";
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<SportsEventHit[]>([]);
  const [markets, setMarkets] = useState<SportsMarketHit[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const [selected, setSelected] = useState<SportsEventHit | null>(null);
  const [market, setMarket] = useState<SportsEventMarket | null>(null);
  const [customOdds, setCustomOdds] = useState("");
  const [customSelection, setCustomSelection] = useState("");
  const [customBetType, setCustomBetType] = useState("moneyline");
  const [notes, setNotes] = useState("");
  const [stake, setStake] = useState("");
  const [manualMode, setManualMode] = useState(false);

  const loadEvents = useCallback(async (q: string) => {
    setLoading(true);
    setMessage(null);
    setHasSearched(true);
    try {
      const token = await getToken();
      const apiUrl = getApiUrl();
      const params = new URLSearchParams({
        limit: isParlay ? "80" : "36",
        all_sports: "true",
      });
      if (q) params.set("q", q);
      const res = await fetch(`${apiUrl}/signals/sports/events?${params}`, {
        headers: apiRequestHeaders(token),
        credentials: usesBffProxy() ? "include" : "same-origin",
        cache: "no-store",
        signal: AbortSignal.timeout(150_000),
      });
      let body: Record<string, unknown> = {};
      try {
        body = (await res.json()) as Record<string, unknown>;
      } catch {
        body = {};
      }
      if (!res.ok) {
        const detail =
          typeof body.detail === "string"
            ? body.detail
            : res.status === 503
              ? "Search timed out — tap Fetch live odds, then try again."
              : res.status === 401
                ? "Sign in again to search FanDuel markets."
                : "Search failed — try Fetch live odds, then search again.";
        setMessage(detail);
        setItems([]);
        setMarkets([]);
        return;
      }
      const rawEvents = ((body.items as SportsEventHit[]) ?? []).map((event) => ({
        ...event,
        markets: (event.markets ?? []).map((m) => withFanDuelLine(m)),
      }));
      let nextMarkets = ((body.markets as SportsMarketHit[]) ?? []).map((m, idx) => ({
        ...withFanDuelLine(m),
        insight_rank: typeof m.insight_rank === "number" ? m.insight_rank : idx + 1,
        is_top_pick: truthy(m.is_top_pick) || idx === 0,
        is_best_odds: truthy(m.is_best_odds),
        is_most_likely: truthy(m.is_most_likely),
        thesis:
          m.thesis ||
          `Atlas Insight ranked this #${typeof m.insight_rank === "number" ? m.insight_rank : idx + 1} for your search.`,
      }));
      if (isParlay) {
        nextMarkets = nextMarkets.filter(hasFanDuel);
      }
      // Guarantee badge coverage even if API omitted flags.
      if (nextMarkets.length && !nextMarkets.some((m) => m.is_best_odds)) {
        let bestIdx = 0;
        let best = Number.NEGATIVE_INFINITY;
        nextMarkets.forEach((m, i) => {
          const odds = m.best_odds_american ?? m.odds_american;
          const score = odds > 0 ? 1 + odds / 100 : 1 + 100 / Math.abs(odds || 110);
          if (score > best) {
            best = score;
            bestIdx = i;
          }
        });
        nextMarkets[bestIdx] = { ...nextMarkets[bestIdx], is_best_odds: true };
      }
      if (nextMarkets.length && !nextMarkets.some((m) => m.is_most_likely)) {
        let likelyIdx = 0;
        let likely = -1;
        nextMarkets.forEach((m, i) => {
          const p = typeof m.hit_probability === "number" ? m.hit_probability : -1;
          if (p > likely) {
            likely = p;
            likelyIdx = i;
          }
        });
        nextMarkets[likelyIdx] = { ...nextMarkets[likelyIdx], is_most_likely: true };
      }
      setItems(
        isParlay
          ? rawEvents
              .map((event) => ({
                ...event,
                markets: (event.markets ?? []).filter(hasFanDuel),
              }))
              .filter((event) => (event.markets?.length ?? 0) > 0)
          : rawEvents,
      );
      setMarkets(nextMarkets);
      if (typeof body.message === "string" && body.message.trim()) {
        setMessage(body.message);
      } else if (nextMarkets.length === 0) {
        setMessage(
          isParlay
            ? "No FanDuel markets matched that search. Try another team or player, or Fetch live odds first."
            : "No verified markets found. Tap Fetch live odds once, then search a team nickname or player name.",
        );
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "";
      setMessage(
        msg.includes("timeout") || msg.includes("Timeout") || msg.includes("aborted")
          ? "Search timed out — tap Fetch live odds, then try a shorter team/player name."
          : "Could not reach the API for event search — check that the backend is running.",
      );
      setItems([]);
      setMarkets([]);
    } finally {
      setLoading(false);
    }
  }, [isParlay]);

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    const q = query.trim();
    if (!q) {
      setMessage("Type a team or player name, then press Search.");
      setHasSearched(true);
      setItems([]);
      setMarkets([]);
      return;
    }
    setSelected(null);
    setManualMode(false);
    void loadEvents(q);
  }

  function pickEvent(event: SportsEventHit) {
    setSelected(event);
    setManualMode(false);
    const firstRaw = event.markets[0] ?? null;
    const first = firstRaw ? withFanDuelLine(firstRaw) : null;
    setMarket(first);
    setCustomSelection(first?.selection ?? "");
    setCustomOdds(first ? String(first.odds_american) : "");
    setCustomBetType(first?.bet_type ?? "moneyline");
    setNotes("");
    setStake("");
  }

  function pickMarketHit(hit: SportsMarketHit) {
    const fdHit = withFanDuelLine(hit);
    const event: SportsEventHit = {
      event_id: fdHit.event_id || "",
      sport: fdHit.sport || "Sports",
      sport_key: fdHit.sport_key,
      home_team: fdHit.home_team || "",
      away_team: fdHit.away_team || "",
      event_name: fdHit.event_name || "Event",
      event_start: fdHit.event_start,
      hours_until_start: fdHit.hours_until_start,
      markets: [fdHit],
    };
    setSelected(event);
    setManualMode(false);
    setMarket(fdHit);
    setCustomSelection(fdHit.selection);
    setCustomOdds(String(fdHit.odds_american));
    setCustomBetType(fdHit.bet_type || "player_prop");
    setNotes("");
    setStake("");
  }

  function openManual() {
    setManualMode(true);
    setSelected(null);
    setMarket(null);
    setCustomSelection("");
    setCustomOdds("-110");
    setCustomBetType("moneyline");
    setNotes("");
    setStake("");
  }

  const previewSelection = useMemo(() => {
    if (manualMode) return customSelection.trim();
    return (market?.selection || customSelection).trim();
  }, [manualMode, market, customSelection]);

  async function submitBet() {
    const event = selected;
    const eventName =
      event?.event_name || (manualMode ? customSelection.split(" ").slice(0, 3).join(" ") : "");
    const selection = previewSelection;
    const oddsRaw = customOdds.trim() || (market ? String(market.odds_american) : "");
    const odds = Number.parseInt(oddsRaw, 10);
    if (!selection || Number.isNaN(odds)) {
      setMessage("Enter a selection and American odds (e.g. -110).");
      return;
    }

    setSaving(true);
    setMessage(null);
    try {
      const token = await getToken();
      const apiUrl = getApiUrl();
      const fdMarket = market ? withFanDuelLine(market) : null;
      const body = {
        event_id: event?.event_id || undefined,
        sport: event?.sport || "Sports",
        sport_key: event?.sport_key,
        home_team: event?.home_team,
        away_team: event?.away_team,
        event_name: event?.event_name || (manualMode ? `Manual · ${selection}` : eventName),
        event_start: event?.event_start,
        bet_type: fdMarket?.bet_type || customBetType,
        selection,
        odds_american: odds,
        book_key: isParlay ? "fanduel" : fdMarket?.book_key || "fanduel",
        book_title: isParlay ? "FanDuel" : fdMarket?.book_title || "FanDuel",
        notes: notes.trim() || undefined,
        stake: isParlay ? undefined : stake.trim() || undefined,
      };
      const res = await fetch(`${apiUrl}/signals/sports/user-bets`, {
        method: "POST",
        headers: {
          ...apiRequestHeaders(token),
          "Content-Type": "application/json",
        },
        credentials: usesBffProxy() ? "include" : "same-origin",
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) {
        setMessage(typeof data.detail === "string" ? data.detail : "Could not save bet");
        return;
      }
      const item = data.item as
        | {
            id?: string;
            sport?: string;
            event_name?: string;
            bet_type?: string;
            selection?: string;
            odds_american?: number;
            event_start?: string | null;
          }
        | undefined;
      if (isParlay && item?.id) {
        await onParlayLegAdded?.({
          id: String(item.id),
          sport: String(item.sport || body.sport || "Sports"),
          event_name: String(item.event_name || body.event_name),
          bet_type: String(item.bet_type || body.bet_type),
          selection: String(item.selection || selection),
          odds_american: Number(item.odds_american ?? odds),
          event_start: item.event_start ?? body.event_start ?? null,
        });
        setMessage(`Added FanDuel leg: ${selection}`);
      } else {
        setMessage((data.message as string) || "Bet logged for Atlas learning");
        await onBetLogged?.();
      }
      setSelected(null);
      setMarket(null);
      setManualMode(false);
      setNotes("");
      setStake("");
      globalThis.dispatchEvent(new Event("atlas:dashboard-refresh"));
    } catch {
      setMessage("Backend not responding — restart the API and try again");
    } finally {
      setSaving(false);
    }
  }

  const showResults = hasSearched && !selected && !manualMode;

  return (
    <section
      className={`rounded-xl border p-4 ${
        embedded ? "mb-0" : "mb-6"
      } ${
        isParlay
          ? "border-fanduel/40 bg-fanduel-muted/30"
          : "border-orange-500/25 bg-orange-500/5"
      }`}
    >
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="text-sm font-semibold text-foreground">
            {isParlay ? "Add a leg" : "Search & log my bet"}
          </h2>
          <p className="mt-1 text-xs text-muted">
            {isParlay
              ? "Search the full FanDuel board (all sports), then add a selection to this parlay."
              : "Search a team or player (e.g. Lakers, Chiefs, Clark). Atlas matches FanDuel/DraftKings lines from your board + cache, then ranks hit odds."}
          </p>
        </div>
        {!isParlay && (
          <button
            type="button"
            onClick={openManual}
            className="rounded-lg border border-border bg-background px-3 py-1.5 text-xs font-medium text-foreground hover:border-orange-400/50"
          >
            Log custom pick
          </button>
        )}
      </div>

      <form className="mt-3 flex gap-2" onSubmit={onSubmit}>
        <label className="sr-only" htmlFor="sports-event-search">
          Search teams or players
        </label>
        <input
          id="sports-event-search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Any FanDuel team or player — NFL, NBA, MLB, soccer, MMA…"
          className="min-w-0 flex-1 rounded-lg border border-border bg-background px-3 py-2.5 text-sm text-foreground outline-none focus:border-orange-400"
          enterKeyHint="search"
        />
        <button
          type="submit"
          disabled={loading}
          className="shrink-0 rounded-lg bg-orange-500 px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50"
        >
          {loading ? "…" : "Search"}
        </button>
      </form>

      {message && (
        <p className="mt-2 rounded-lg border border-border bg-surface-elevated px-3 py-2 text-xs text-muted">
          {message}
        </p>
      )}

      {loading && (
        <p className="mt-3 text-xs text-muted">
          Atlas Insight is searching books and ranking hit likelihood / odds value…
        </p>
      )}

      {showResults && markets.length > 0 && (
        <div className="mt-3">
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted">
            Insight-ranked markets
          </p>
          <ul className="max-h-80 space-y-2 overflow-y-auto">
            {markets.slice(0, 24).map((hit, idx) => {
              const rank = rankLabel(hit, idx);
              const top = truthy(hit.is_top_pick) || rank === 1;
              const mostLikely = truthy(hit.is_most_likely);
              const bestOdds = truthy(hit.is_best_odds);
              return (
              <li key={`${hit.event_id}-${hit.selection}-${hit.bet_type}-${idx}`}>
                <button
                  type="button"
                  onClick={() => pickMarketHit(hit)}
                  className={`flex w-full flex-col rounded-lg border px-3 py-2.5 text-left hover:border-orange-400/50 ${
                    top
                      ? "border-orange-400/60 bg-orange-500/15"
                      : "border-border/80 bg-background/80"
                  }`}
                >
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="rounded bg-orange-500/25 px-1.5 py-0.5 text-[10px] font-semibold text-orange-100">
                      #{rank}
                    </span>
                    {top && (
                      <span className="rounded bg-orange-500 px-1.5 py-0.5 text-[10px] font-semibold text-white">
                        Top pick
                      </span>
                    )}
                    {mostLikely && (
                      <span className="rounded bg-emerald-500/25 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-100">
                        Most likely
                      </span>
                    )}
                    {bestOdds && (
                      <span className="rounded bg-sky-500/25 px-1.5 py-0.5 text-[10px] font-semibold text-sky-100">
                        Best odds
                      </span>
                    )}
                    {hit.value_grade && (
                      <span className="rounded border border-border px-1.5 py-0.5 text-[10px] text-muted">
                        Value {hit.value_grade}
                      </span>
                    )}
                  </div>
                  <span className="mt-1 text-sm font-semibold text-foreground">{hit.selection}</span>
                  <span className="mt-0.5 text-xs text-muted">
                    {hit.event_name} · {hit.sport}
                    {typeof hit.hit_probability === "number"
                      ? ` · ~${Math.round(hit.hit_probability)}% hit`
                      : ""}
                    {typeof hit.best_odds_american === "number"
                      ? ` · best ${oddsLabel(hit.best_odds_american)}`
                      : ` · ${oddsLabel(hit.odds_american)}`}
                    {hit.best_book_title ? ` @ ${hit.best_book_title}` : ""}
                  </span>
                  <span className="mt-1.5 text-[11px] leading-snug text-orange-100/90">
                    {hit.thesis ||
                      `Atlas Insight ranked this #${rank}. Open for full analysis.`}
                  </span>
                  <span className="mt-1 text-[11px] text-muted">
                    {hit.fanduel_verified ? "FanDuel/DK verified · " : ""}
                    On {booksLabel(hit)}
                  </span>
                </button>
              </li>
              );
            })}
          </ul>
        </div>
      )}

      {showResults && items.length > 0 && (
        <div className="mt-3">
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted">Events</p>
          <ul className="max-h-56 space-y-2 overflow-y-auto">
            {items.map((event) => (
              <li key={event.event_id || event.event_name}>
                <button
                  type="button"
                  onClick={() => pickEvent(event)}
                  className="flex w-full flex-col rounded-lg border border-border/80 bg-background/80 px-3 py-2 text-left hover:border-orange-400/50"
                >
                  <span className="text-sm font-semibold text-foreground">{event.event_name}</span>
                  <span className="mt-0.5 text-xs text-muted">
                    {event.sport} · {formatStart(event.event_start)}
                    {event.markets?.length ? ` · ${event.markets.length} verified lines` : ""}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {showResults && !loading && items.length === 0 && markets.length === 0 && !message && (
        <p className="mt-3 text-xs text-muted">No verified markets found for that search.</p>
      )}

      {(selected || manualMode) && (
        <div className="mt-4 rounded-lg border border-orange-500/30 bg-background/70 p-3">
          <div className="flex items-start justify-between gap-2">
            <div>
              <p className="text-sm font-semibold text-foreground">
                {manualMode ? "Custom pick" : selected?.event_name}
              </p>
              {!manualMode && selected && (
                <p className="text-xs text-muted">
                  {selected.sport} · {formatStart(selected.event_start)}
                </p>
              )}
            </div>
            <button
              type="button"
              onClick={() => {
                setSelected(null);
                setManualMode(false);
              }}
              className="text-xs text-muted hover:text-foreground"
            >
              Close
            </button>
          </div>

          {!manualMode && selected && selected.markets.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-2">
              {selected.markets.slice(0, 18).map((m) => {
                const active =
                  market?.selection === m.selection &&
                  market?.bet_type === m.bet_type &&
                  market?.odds_american === m.odds_american;
                return (
                  <button
                    key={`${m.bet_type}-${m.selection}-${m.odds_american}-${m.book_key}`}
                    type="button"
                    onClick={() => {
                      setMarket(m);
                      setCustomSelection(m.selection);
                      setCustomOdds(String(m.odds_american));
                      setCustomBetType(m.bet_type);
                    }}
                    className={`rounded-lg border px-2.5 py-1.5 text-left text-xs font-medium ${
                      active
                        ? "border-orange-400 bg-orange-500/20 text-orange-100"
                        : "border-border text-muted hover:border-orange-400/40"
                    }`}
                  >
                    <span className="block">
                      {m.bet_type === "player_prop" ? "PROP" : m.bet_type.slice(0, 2).toUpperCase()}{" "}
                      {m.selection} {oddsLabel(m.odds_american)}
                    </span>
                    <span className="mt-0.5 block text-[10px] opacity-80">On {booksLabel(m)}</span>
                  </button>
                );
              })}
            </div>
          )}

          {market && !manualMode && (
            <div className="mt-2 rounded-lg border border-orange-500/20 bg-orange-500/10 px-3 py-2 text-xs text-orange-50/95">
              <p className="font-medium text-orange-100">Atlas Insight</p>
              <p className="mt-1 leading-snug">
                {market.thesis ||
                  `Ranked #${typeof market.insight_rank === "number" ? market.insight_rank : "—"} for this search.`}
              </p>
              {(market.bull_case || market.bear_case) && (
                <p className="mt-1.5 text-[11px] text-muted">
                  {market.bull_case ? `Bull: ${market.bull_case}` : ""}
                  {market.bull_case && market.bear_case ? " · " : ""}
                  {market.bear_case ? `Bear: ${market.bear_case}` : ""}
                </p>
              )}
              <p className="mt-1 text-[11px] text-muted">
                {typeof market.hit_probability === "number"
                  ? `~${Math.round(market.hit_probability)}% hit`
                  : "Hit % pending"}
                {" · conf "}
                {typeof market.confidence === "number" ? Math.round(market.confidence) : "—"}
                {market.value_grade ? ` · value ${market.value_grade}` : ""}
                {truthy(market.is_top_pick) ? " · Top pick" : ""}
                {truthy(market.is_most_likely) ? " · Most likely" : ""}
                {truthy(market.is_best_odds) ? " · Best odds" : ""}
              </p>
              <p className="mt-1 text-[11px] text-orange-200/90">Books: {booksLabel(market)}</p>
            </div>
          )}

          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            <label className="flex flex-col gap-1 text-xs text-muted">
              Selection
              <input
                value={customSelection}
                onChange={(e) => setCustomSelection(e.target.value)}
                className="rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground"
                placeholder="Team / Player Over 1.5 / etc."
              />
            </label>
            <label className="flex flex-col gap-1 text-xs text-muted">
              American odds
              <input
                value={customOdds}
                onChange={(e) => setCustomOdds(e.target.value)}
                className="rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground"
                placeholder="-110"
              />
            </label>
            <label className="flex flex-col gap-1 text-xs text-muted">
              Bet type
              <select
                value={customBetType}
                onChange={(e) => setCustomBetType(e.target.value)}
                className="rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground"
              >
                <option value="moneyline">Moneyline</option>
                <option value="spread">Spread</option>
                <option value="total">Total</option>
                <option value="player_prop">Player prop</option>
              </select>
            </label>
            <label className="flex flex-col gap-1 text-xs text-muted">
              Stake (optional)
              <input
                value={stake}
                onChange={(e) => setStake(e.target.value)}
                className="rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground"
                placeholder="25"
              />
            </label>
          </div>
          <label className="mt-2 flex flex-col gap-1 text-xs text-muted">
            Notes (optional)
            <input
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              className="rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground"
              placeholder="Why you like this play…"
            />
          </label>

          <button
            type="button"
            disabled={saving}
            onClick={() => void submitBet()}
            className={`mt-3 rounded-lg px-4 py-2 text-sm font-semibold text-white disabled:opacity-50 ${
              isParlay ? "bg-[var(--fanduel)] hover:brightness-110" : "bg-orange-500"
            }`}
          >
            {saving
              ? isParlay
                ? "Adding…"
                : "Saving…"
              : isParlay
                ? "Add a leg"
                : "Log bet for Atlas learning"}
          </button>
        </div>
      )}
    </section>
  );
}
