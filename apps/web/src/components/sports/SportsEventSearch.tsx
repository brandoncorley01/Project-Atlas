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

export function SportsEventSearch({
  onBetLogged,
}: {
  onBetLogged?: () => void | Promise<void>;
}) {
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
      const params = new URLSearchParams({ limit: "36" });
      if (q) params.set("q", q);
      const res = await fetch(`${apiUrl}/signals/sports/events?${params}`, {
        headers: apiRequestHeaders(token),
        credentials: usesBffProxy() ? "include" : "same-origin",
        cache: "no-store",
      });
      const body = await res.json();
      if (!res.ok) {
        setMessage(typeof body.detail === "string" ? body.detail : "Search failed");
        setItems([]);
        setMarkets([]);
        return;
      }
      setItems((body.items as SportsEventHit[]) ?? []);
      setMarkets((body.markets as SportsMarketHit[]) ?? []);
      if (body.message) {
        setMessage(body.message as string);
      }
    } catch {
      setMessage("Could not reach the API for event search");
      setItems([]);
      setMarkets([]);
    } finally {
      setLoading(false);
    }
  }, []);

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    setSelected(null);
    setManualMode(false);
    void loadEvents(query.trim());
  }

  function pickEvent(event: SportsEventHit) {
    setSelected(event);
    setManualMode(false);
    const first = event.markets[0] ?? null;
    setMarket(first);
    setCustomSelection(first?.selection ?? "");
    setCustomOdds(first ? String(first.odds_american) : "");
    setCustomBetType(first?.bet_type ?? "moneyline");
    setNotes("");
    setStake("");
  }

  function pickMarketHit(hit: SportsMarketHit) {
    const event: SportsEventHit = {
      event_id: hit.event_id || "",
      sport: hit.sport || "Sports",
      sport_key: hit.sport_key,
      home_team: hit.home_team || "",
      away_team: hit.away_team || "",
      event_name: hit.event_name || "Event",
      event_start: hit.event_start,
      hours_until_start: hit.hours_until_start,
      markets: [hit],
    };
    setSelected(event);
    setManualMode(false);
    setMarket(hit);
    setCustomSelection(hit.selection);
    setCustomOdds(String(hit.odds_american));
    setCustomBetType(hit.bet_type || "player_prop");
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
      const body = {
        event_id: event?.event_id || undefined,
        sport: event?.sport || "Sports",
        sport_key: event?.sport_key,
        home_team: event?.home_team,
        away_team: event?.away_team,
        event_name: event?.event_name || (manualMode ? `Manual · ${selection}` : eventName),
        event_start: event?.event_start,
        bet_type: market?.bet_type || customBetType,
        selection,
        odds_american: odds,
        book_key: market?.book_key || "fanduel",
        book_title: market?.book_title || "FanDuel",
        notes: notes.trim() || undefined,
        stake: stake.trim() || undefined,
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
      setMessage((data.message as string) || "Bet logged for Atlas learning");
      setSelected(null);
      setMarket(null);
      setManualMode(false);
      setNotes("");
      setStake("");
      await onBetLogged?.();
      globalThis.dispatchEvent(new Event("atlas:dashboard-refresh"));
    } catch {
      setMessage("Backend not responding — restart the API and try again");
    } finally {
      setSaving(false);
    }
  }

  const showResults = hasSearched && !selected && !manualMode;

  return (
    <section className="mb-6 rounded-xl border border-orange-500/25 bg-orange-500/5 p-4">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="text-sm font-semibold text-foreground">Search & log my bet</h2>
          <p className="mt-1 text-xs text-muted">
            Search teams or players on verified FanDuel/DraftKings lines (0 Odds credits). Log picks
            so Atlas can track and learn.
          </p>
        </div>
        <button
          type="button"
          onClick={openManual}
          className="rounded-lg border border-border bg-background px-3 py-1.5 text-xs font-medium text-foreground hover:border-orange-400/50"
        >
          Log custom pick
        </button>
      </div>

      <form className="mt-3 flex gap-2" onSubmit={onSubmit}>
        <label className="sr-only" htmlFor="sports-event-search">
          Search teams or players
        </label>
        <input
          id="sports-event-search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Team or player — e.g. Yankees, Judge, Aces…"
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

      {loading && <p className="mt-3 text-xs text-muted">Searching verified book markets…</p>}

      {showResults && markets.length > 0 && (
        <div className="mt-3">
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted">
            Verified markets
          </p>
          <ul className="max-h-56 space-y-2 overflow-y-auto">
            {markets.slice(0, 24).map((hit, idx) => (
              <li key={`${hit.event_id}-${hit.selection}-${hit.bet_type}-${idx}`}>
                <button
                  type="button"
                  onClick={() => pickMarketHit(hit)}
                  className="flex w-full flex-col rounded-lg border border-border/80 bg-background/80 px-3 py-2 text-left hover:border-orange-400/50"
                >
                  <span className="text-sm font-semibold text-foreground">{hit.selection}</span>
                  <span className="mt-0.5 text-xs text-muted">
                    {hit.event_name} · {hit.sport} · {oddsLabel(hit.odds_american)}
                  </span>
                  <span className="mt-1 text-[11px] text-orange-200/90">
                    On {booksLabel(hit)}
                  </span>
                </button>
              </li>
            ))}
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
            <p className="mt-2 text-[11px] text-orange-200/90">Selected line: {booksLabel(market)}</p>
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
            className="mt-3 rounded-lg bg-orange-500 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
          >
            {saving ? "Saving…" : "Log bet for Atlas learning"}
          </button>
        </div>
      )}
    </section>
  );
}
