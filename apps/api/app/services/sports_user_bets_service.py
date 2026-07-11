"""Cache-backed sports event search + user-entered bets for Atlas learning."""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Any

from app.agents.sports_analyst import (
    PREFERRED_BOOK_KEY,
    US_PREFERRED_BOOK_KEYS,
    american_to_decimal,
)
from app.db.supabase_client import SupabaseClient
from app.providers.sports.odds_api import _cache_age_minutes, _read_cache
from app.services.freshness import filter_upcoming_events, hours_until_event

logger = logging.getLogger(__name__)

SOURCE = "user_entry"


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _tokens(query: str) -> list[str]:
    return [t for t in _norm(query).split() if len(t) >= 2]


def _event_haystack(event: dict[str, Any]) -> str:
    parts = [
        str(event.get("home_team") or ""),
        str(event.get("away_team") or ""),
        str(event.get("_sport_label") or event.get("sport_title") or ""),
        str(event.get("_sport_key") or ""),
        str(event.get("id") or ""),
    ]
    return _norm(" ".join(parts))


def _match_score(haystack: str, tokens: list[str]) -> float:
    if not tokens:
        return 1.0
    hits = sum(1 for t in tokens if t in haystack)
    if hits == 0:
        return 0.0
    # Prefer full-token matches; bonus when all tokens hit.
    score = hits / len(tokens)
    if hits == len(tokens):
        score += 0.25
    return score


def _pick_book_markets(event: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten FanDuel/DraftKings markets into searchable bet chips."""
    books = list(event.get("bookmakers") or [])
    preferred = [b for b in books if str(b.get("key") or "") in US_PREFERRED_BOOK_KEYS]
    ordered = preferred or books
    # FanDuel first when present.
    ordered.sort(key=lambda b: 0 if b.get("key") == PREFERRED_BOOK_KEY else 1)

    markets_out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for book in ordered[:2]:
        book_key = str(book.get("key") or "")
        book_title = str(book.get("title") or book_key)
        for market in book.get("markets") or []:
            mkey = str(market.get("key") or "")
            bet_type = {"h2h": "moneyline", "spreads": "spread", "totals": "total"}.get(mkey)
            if not bet_type:
                continue
            for outcome in market.get("outcomes") or []:
                name = str(outcome.get("name") or "").strip()
                if not name:
                    continue
                try:
                    american = int(outcome.get("price"))
                except (TypeError, ValueError):
                    continue
                point = outcome.get("point")
                try:
                    point_f = float(point) if point is not None else None
                except (TypeError, ValueError):
                    point_f = None
                if bet_type == "spread" and point_f is not None:
                    sign = "+" if point_f > 0 else ""
                    selection = f"{name} {sign}{point_f:g}"
                elif bet_type == "total" and point_f is not None:
                    selection = f"{name} {point_f:g}"
                else:
                    selection = name
                dedupe = f"{bet_type}|{selection}|{american}"
                if dedupe in seen:
                    continue
                seen.add(dedupe)
                markets_out.append(
                    {
                        "bet_type": bet_type,
                        "selection": selection,
                        "odds_american": american,
                        "point": point_f,
                        "book_key": book_key,
                        "book_title": book_title,
                        "team_or_side": name,
                    }
                )
    return markets_out


def _serialize_event(event: dict[str, Any]) -> dict[str, Any]:
    home = str(event.get("home_team") or "")
    away = str(event.get("away_team") or "")
    start = event.get("commence_time")
    hours = hours_until_event(start)
    return {
        "event_id": str(event.get("id") or ""),
        "sport": str(event.get("_sport_label") or event.get("sport_title") or "Sports"),
        "sport_key": str(event.get("_sport_key") or ""),
        "home_team": home,
        "away_team": away,
        "event_name": f"{away} @ {home}" if home and away else (home or away or "Event"),
        "event_start": start,
        "hours_until_start": round(hours, 1) if hours is not None else None,
        "markets": _pick_book_markets(event),
    }


def search_cached_events(
    *,
    query: str = "",
    sport: str | None = None,
    limit: int = 40,
) -> dict[str, Any]:
    """Verified FanDuel/DraftKings search — teams, events, and player props (0 credits)."""
    from app.services.fanduel_catalog import search_verified_markets

    return search_verified_markets(query=query, sport=sport, limit=limit)


class SportsUserBetsService:
    def __init__(self, db: SupabaseClient, user_id: str) -> None:
        self.db = db
        self.user_id = user_id

    async def create_user_bet(self, payload: dict[str, Any]) -> dict[str, Any]:
        sport = str(payload.get("sport") or "Sports").strip()[:40] or "Sports"
        event_name = str(payload.get("event_name") or "").strip()[:160]
        selection = str(payload.get("selection") or "").strip()[:120]
        bet_type = str(payload.get("bet_type") or "moneyline").strip().lower()
        if bet_type not in {"moneyline", "spread", "total", "futures", "player_prop"}:
            bet_type = "moneyline"
        if not event_name or not selection:
            return {"ok": False, "message": "Event and selection are required."}

        try:
            odds_american = int(payload.get("odds_american"))
        except (TypeError, ValueError):
            return {"ok": False, "message": "Enter American odds (e.g. -110 or +145)."}

        event_start = payload.get("event_start")
        if event_start is not None:
            event_start = str(event_start).strip() or None
        event_id = str(payload.get("event_id") or "").strip() or None
        home = str(payload.get("home_team") or "").strip() or None
        away = str(payload.get("away_team") or "").strip() or None
        sport_key = str(payload.get("sport_key") or "").strip() or None
        book_key = str(payload.get("book_key") or PREFERRED_BOOK_KEY)
        book_title = str(payload.get("book_title") or "FanDuel")
        notes = str(payload.get("notes") or "").strip()[:400]
        stake = payload.get("stake")
        try:
            stake_f = float(stake) if stake is not None and str(stake).strip() != "" else None
        except (TypeError, ValueError):
            stake_f = None

        now = datetime.now(UTC).isoformat()
        confidence = 55.0
        risk = 50.0
        opportunity = 50.0
        explanation = notes or (
            f"Your logged bet: {selection} on {event_name} at {odds_american:+d}. "
            "Atlas will track and grade this pick to improve learning."
        )

        row = {
            "user_id": self.user_id,
            "sport": sport,
            "event_name": event_name,
            "event_start": event_start,
            "bet_type": bet_type,
            "selection": selection,
            "odds_american": odds_american,
            "odds_decimal": american_to_decimal(odds_american),
            "expected_value": None,
            "line_movement": {
                "preferred_book": book_key,
                "preferred_book_title": book_title,
                "source": SOURCE,
                "event_id": event_id,
                "stake": stake_f,
            },
            "injury_impact": None,
            "weather_impact": None,
            "travel_rest_impact": None,
            "public_betting_pct": None,
            "sharp_indicator": None,
            "confidence_score": confidence,
            "risk_score": risk,
            "opportunity_score": opportunity,
            "recommendation": f"My bet · {bet_type.title()} — {selection} · {event_name}",
            "explanation": explanation,
            "bull_case": "You logged this play for tracking and learning.",
            "bear_case": "Lines move — recheck FanDuel/DraftKings before betting more.",
            "invalidation": "Scratch if the game is postponed or the wrong market was logged.",
            "suggested_action": f"Track {selection} at {odds_american:+d} on {book_title}",
            "risk_warning": (
                "User-entered picks feed Atlas learning. Verify live odds on your book before wagering."
            ),
            "scoring_snapshot": {
                "source": SOURCE,
                "user_entry": True,
                "pick_origin": "user",
                "user_tracked": True,
                "event_id": event_id,
                "sport_key": sport_key,
                "home_team": home,
                "away_team": away,
                "preferred_book": book_key,
                "preferred_book_title": book_title,
                "stake": stake_f,
                "notes": notes or None,
                "pick": {
                    "bet_type": bet_type,
                    "team_or_side": selection,
                },
            },
            "status": "active",
            "data_as_of": now,
        }

        saved = await self.db.insert("sports_signals", [row])
        if not saved:
            return {"ok": False, "message": "Could not save bet — try again."}

        item = saved[0]
        try:
            from app.services.signal_registry_service import SignalRegistryService

            await SignalRegistryService(self.db, self.user_id).register_batch("sports", saved)
        except Exception as exc:
            logger.warning("User bet registry skipped: %s", exc)

        return {
            "ok": True,
            "signals_created": 1,
            "item": item,
            "credits_used": 0,
            "message": (
                f"Logged {selection} on {event_name} — Atlas is tracking this pick for learning "
                "(0 Odds API credits)."
            ),
        }
