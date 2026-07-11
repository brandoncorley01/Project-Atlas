"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { apiRequestHeaders, getApiUrl, usesBffProxy } from "@/lib/api-url";

export interface SportsEventMarket {
  bet_type: string;
  selection: string;
  odds_american: number;
  point?: number | null;
  book_key?: string;
  book_title?: string;
  team_or_side?: string;
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

export function SportsEventSearch({
  onBetLogged,
}: {
  onBetLogged?: () => void | Promise<void>;
}) {
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [items, setItems] = useState<SportsEventHit[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [selected, setSelected] = useState<SportsEventHit | null>(null);
  const [market, setMarket] = useState<SportsEventMarket | null>(null);
  const [customOdds, setCustomOdds] = useState("");
  const [customSelection, setCustomSelection] = useState("");
  const [customBetType, setCustomBetType] = useState("moneyline");
  const [notes, setNotes] = useState("");
  const [stake, setStake] = useState("");
  const [manualMode, setManualMode] = useState(false);

  useEffect(() => {
    const t = window.setTimeout(() => setDebounced(query.trim()), 280);
    return () => window.clearTimeout(t);
  }, [query]);

  const loadEvents = useCallback(async (q: string) => {
    setLoading(true);
    setMessage(null);
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
        return;
      }
      setItems((body.items as SportsEventHit[]) ?? []);
      if (body.message && !(body.items as SportsEventHit[] | undefined)?.length) {
        setMessage(body.message as string);
      }
    } catch {
      setMessage("Could not reach the API for event search");
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadEvents(debounced);
  }, [debounced, loadEvents]);

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

  async function submitBet(eventOverride?: Partial<SportsEventHit>) {
    const event = selected;
    const eventName =
      event?.event_name ||
      (eventOverride?.event_name as string | undefined) ||
      (manualMode ? customSelection.split(" ").slice(0, 3).join(" ") : "");
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

  return (
    <section className="mb-6 rounded-xl border border-orange-500/25 bg-orange-500/5 p-4">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="text-sm font-semibold text-foreground">Search events & log my bet</h2>
          <p className="mt-1 text-xs text-muted">
            FanDuel-style search over cached lines (0 Odds credits). Log picks so Atlas can track,
            grade, and learn.
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

      <div className="mt-3">
        <label className="sr-only" htmlFor="sports-event-search">
          Search sports events
        </label>
        <input
          id="sports-event-search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search teams or events — e.g. Yankees, Lakers, Chiefs…"
          className="w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm text-foreground outline-none focus:border-orange-400"
        />
      </div>

      {message && (
        <p className="mt-2 rounded-lg border border-border bg-surface-elevated px-3 py-2 text-xs text-muted">
          {message}
        </p>
      )}

      {loading && <p className="mt-3 text-xs text-muted">Searching cached events…</p>}

      {!loading && items.length > 0 && !selected && !manualMode && (
        <ul className="mt-3 max-h-64 space-y-2 overflow-y-auto">
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
                  {event.markets?.length ? ` · ${event.markets.length} lines` : ""}
                </span>
              </button>
            </li>
          ))}
        </ul>
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
                    className={`rounded-full border px-2.5 py-1 text-xs font-medium ${
                      active
                        ? "border-orange-400 bg-orange-500/20 text-orange-100"
                        : "border-border text-muted hover:border-orange-400/40"
                    }`}
                  >
                    {m.bet_type.slice(0, 2).toUpperCase()} {m.selection} {oddsLabel(m.odds_american)}
                  </button>
                );
              })}
            </div>
          )}

          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            <label className="flex flex-col gap-1 text-xs text-muted">
              Selection
              <input
                value={customSelection}
                onChange={(e) => setCustomSelection(e.target.value)}
                className="rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground"
                placeholder="Team / Over 8.5 / etc."
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
