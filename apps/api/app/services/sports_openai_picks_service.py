"""OpenAI web-search sports picks — analyst / popular-bettor consensus, no Odds API credits."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from app.agents.sports_analyst import american_to_decimal
from app.db.supabase_client import SupabaseClient
from app.providers.sports.sports_news import fetch_sports_news
from app.services.llm_service import llm_service

logger = logging.getLogger(__name__)

SOURCE = "openai_web"

_SYSTEM = """You are Atlas Insight, the Project Atlas sports desk. Search the public internet for today's
most-talked-about sports bets from betting analysts, touts, and popular sports bettors
(MLB, WNBA, NFL, NBA, NHL, MLS, UFC when in season). Prefer FanDuel/DraftKings boards.

PRIMARY FOCUS — Player props (majority of the slate, about 60–75%):
- MLB: batter hits / home runs / total bases / RBIs / runs, pitcher strikeouts / outs / earned runs
- NBA/WNBA: points, rebounds, assists, threes, PRA, steals/blocks
- NFL (in season): pass yards/TDs, rush yards, receptions, anytime TD
- NHL: shots, points, goals; UFC: method / rounds when relevant
Write prop selections like "Aaron Judge Over 1.5 Hits" or "A'ja Wilson Over 22.5 Points".

SECONDARY — Still include strong moneyline / spread / total consensus plays (about 25–40%).
Do not return props-only if the slate has clear game-line steam.

Rules:
- Use live web results. Cite sources in each pick's sources array (site names or URLs).
- Do NOT invent final scores. Odds may be approximate consensus if cited; otherwise use null.
- Focus on games happening today or in the next 48 hours (US Eastern).
- Return JSON only:
{
  "picks": [
    {
      "sport": "MLB",
      "event_name": "Away @ Home",
      "event_start": "2026-07-11T23:10:00Z or null",
      "bet_type": "player_prop|moneyline|spread|total",
      "selection": "Player Over/Under line OR team/side",
      "prop_market": "batter_hits|player_points|pitcher_strikeouts|null",
      "player_name": "Aaron Judge or null",
      "odds_american": -110 or null,
      "confidence": 55-85,
      "opportunity": 45-80,
      "risk": 35-70,
      "thesis": "why analysts/bettors like it",
      "bull_case": "short",
      "bear_case": "short",
      "sources": ["Action Network", "Covers", "..."],
      "suggested_action": "Play on FanDuel/DraftKings ..."
    }
  ],
  "summary": "one sentence noting prop vs game-line mix"
}
Return 8-16 picks max. Prefer MLB and WNBA when those slates are active.
At least half should be player_prop when those markets are being discussed online today."""


def _is_openai_source(row: dict[str, Any]) -> bool:
    snap = row.get("scoring_snapshot") or {}
    return str(snap.get("source") or "") == SOURCE


def _normalize_bet_type(raw: str | None, selection: str) -> str:
    bet_type = str(raw or "").strip().lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "prop": "player_prop",
        "props": "player_prop",
        "player": "player_prop",
        "playerprops": "player_prop",
        "player_props": "player_prop",
        "outright": "futures",
        "ml": "moneyline",
        "h2h": "moneyline",
        "over_under": "total",
        "ou": "total",
    }
    if bet_type:
        bet_type = aliases.get(bet_type, bet_type)
    if bet_type.startswith(("batter_", "pitcher_", "player_")) and bet_type != "player_prop":
        return "player_prop"
    if bet_type == "player_prop":
        return "player_prop"

    sel = f" {(selection or '').lower()} "
    looks_like_prop = (" over " in sel or " under " in sel) and any(
        token in sel
        for token in (
            " hit",
            " hits",
            " home run",
            " hr ",
            " strikeout",
            " k's",
            " point",
            " rebound",
            " assist",
            " three",
            " 3pt",
            " yard",
            " reception",
            " goal",
            " shot",
            " rbi",
            " base",
            " pra",
            " fantasy",
        )
    )
    if looks_like_prop:
        return "player_prop"
    if bet_type in {"moneyline", "spread", "total", "futures"}:
        return bet_type
    return "moneyline"


def _pick_to_row(user_id: str, pick: dict[str, Any]) -> dict[str, Any] | None:
    sport = str(pick.get("sport") or "").strip() or "Sports"
    event_name = str(pick.get("event_name") or "").strip()
    selection = str(pick.get("selection") or "").strip()
    bet_type = _normalize_bet_type(pick.get("bet_type"), selection)
    if not event_name or not selection:
        return None

    odds_raw = pick.get("odds_american")
    try:
        odds_american = int(odds_raw) if odds_raw is not None else -110
    except (TypeError, ValueError):
        odds_american = -110

    confidence = max(40.0, min(90.0, float(pick.get("confidence") or 62)))
    opportunity = max(35.0, min(90.0, float(pick.get("opportunity") or 55)))
    risk = max(25.0, min(85.0, float(pick.get("risk") or 48)))
    # Slight board boost for props so they aren't buried under game lines.
    if bet_type == "player_prop":
        opportunity = min(90.0, opportunity + 2.0)
    sources = [str(s) for s in (pick.get("sources") or []) if s][:6]
    thesis = str(pick.get("thesis") or pick.get("explanation") or "").strip()
    if not thesis:
        thesis = "Atlas Insight consensus from public analyst / bettor coverage."
    bull = str(pick.get("bull_case") or thesis)[:400]
    bear = str(pick.get("bear_case") or "Public consensus can be late; lines may already be steamed.")[:400]
    action = str(pick.get("suggested_action") or f"Check FanDuel/DraftKings for {selection}")[:240]
    now = datetime.now(UTC).isoformat()
    event_start = pick.get("event_start")
    if event_start is not None:
        event_start = str(event_start).strip() or None
    player_name = str(pick.get("player_name") or "").strip() or None
    prop_market = str(pick.get("prop_market") or "").strip() or None
    type_label = "Player prop" if bet_type == "player_prop" else bet_type.replace("_", " ").title()

    return {
        "user_id": user_id,
        "sport": sport[:40],
        "event_name": event_name[:160],
        "event_start": event_start,
        "bet_type": bet_type,
        "selection": selection[:140],
        "odds_american": odds_american,
        "odds_decimal": american_to_decimal(odds_american),
        "expected_value": None,
        "line_movement": {
            "preferred_book": "fanduel",
            "preferred_book_title": "FanDuel",
            "source": SOURCE,
            "sources": sources,
            "odds_approximate": odds_raw is None,
            "prop_market": prop_market,
            "player_name": player_name,
        },
        "injury_impact": None,
        "weather_impact": None,
        "travel_rest_impact": None,
        "public_betting_pct": None,
        "sharp_indicator": "consensus",
        "confidence_score": confidence,
        "risk_score": risk,
        "opportunity_score": opportunity,
        "recommendation": f"Atlas Insight · {type_label} — {selection} · {event_name}",
        "explanation": thesis[:800],
        "bull_case": bull,
        "bear_case": bear,
        "invalidation": "Consensus flips, lineup scratch, or key injury news after this scan.",
        "suggested_action": action,
        "risk_warning": (
            "Atlas Insight picks are analyst/public consensus, not Odds API +EV math. "
            "Verify the live FanDuel/DraftKings number before betting."
        ),
        "scoring_snapshot": {
            "source": SOURCE,
            "openai_web": True,
            "web_search": True,
            "is_player_prop": bet_type == "player_prop",
            "prop_market": prop_market,
            "player_name": player_name,
            "sources": sources,
            "odds_approximate": odds_raw is None,
            "pick": {"bet_type": bet_type, "team_or_side": selection, "player_name": player_name},
        },
        "status": "active",
        "data_as_of": now,
    }


class SportsOpenAiPicksService:
    def __init__(self, db: SupabaseClient, user_id: str) -> None:
        self.db = db
        self.user_id = user_id

    async def _expire_openai_picks(self) -> int:
        rows = await self.db.select(
            "sports_signals",
            filters={"user_id": f"eq.{self.user_id}", "status": "eq.active"},
            limit=300,
        )
        expired = 0
        for row in rows:
            if not _is_openai_source(row):
                continue
            sid = row.get("id")
            if not sid:
                continue
            try:
                await self.db.update(
                    "sports_signals",
                    {"id": f"eq.{sid}"},
                    {"status": "expired"},
                )
                expired += 1
            except Exception as exc:
                logger.warning("Failed to expire OpenAI sports pick %s: %s", sid, exc)
        return expired

    async def refresh_openai_picks(self, *, limit: int = 16) -> dict[str, Any]:
        if not llm_service.is_configured():
            return {
                "signals_created": 0,
                "credits_used": 0,
                "cache_used": True,
                "openai_web": False,
                "message": "OPENAI_API_KEY is not configured on the API — add it on Render/.env.",
            }

        news: list[dict[str, Any]] = []
        try:
            news = await fetch_sports_news(limit_per_feed=8)
        except Exception as exc:
            logger.warning("Atlas Insight picks news prefetch skipped: %s", exc)

        headlines = [
            {
                "title": n.get("title"),
                "source": n.get("source"),
                "url": n.get("url"),
                "published_at": n.get("published_at"),
            }
            for n in news[:24]
        ]
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        # Anchor undated picks to "today" so list/window filters keep them visible.
        today_iso = datetime.now(UTC).replace(hour=23, minute=0, second=0, microsecond=0).isoformat()
        user = (
            f"Today's UTC date: {today}. Search the web for today's FanDuel/DraftKings "
            "consensus bets from analysts and popular sports bettors. "
            "PRIMARY: player props (hits, HRs, Ks, points, rebounds, assists, threes, PRA, etc.). "
            "SECONDARY: strong moneylines, spreads, and totals. "
            "Prioritize MLB and WNBA if those games are on the slate. "
            "Return a mixed slate — mostly props, not props-only. "
            "Always include event_start as an ISO UTC timestamp when the game time is known.\n\n"
            f"Recent headlines (extra context, may be incomplete):\n{headlines}"
        )

        result = await llm_service.complete_json_with_web_search(
            system=_SYSTEM,
            user=user,
            max_tokens=2200,
        )
        if not result or not isinstance(result.get("picks"), list):
            return {
                "signals_created": 0,
                "credits_used": 0,
                "cache_used": True,
                "openai_web": True,
                "web_search": False,
                "message": "OpenAI returned no web picks — try again in a minute.",
            }

        rows: list[dict[str, Any]] = []
        for pick in result["picks"]:
            if not isinstance(pick, dict):
                continue
            if not str(pick.get("event_start") or "").strip():
                pick = {**pick, "event_start": today_iso}
            row = _pick_to_row(self.user_id, pick)
            if row:
                rows.append(row)
            if len(rows) >= limit:
                break

        expired = await self._expire_openai_picks()
        saved = await self.db.insert("sports_signals", rows) if rows else []

        if saved:
            try:
                from app.services.signal_registry_service import SignalRegistryService

                await SignalRegistryService(self.db, self.user_id).register_batch("sports", saved)
            except Exception as exc:
                logger.warning("Atlas Insight sports registry skipped: %s", exc)

        used_web = bool(result.get("_web_search"))
        prop_count = sum(1 for r in (saved or rows) if str(r.get("bet_type")) == "player_prop")
        summary = str(result.get("summary") or "").strip()
        msg = (
            f"Atlas Insight found {len(saved)} picks"
            f" ({prop_count} player props)"
            f"{' via live web search' if used_web else ' from model + headlines'} "
            f"(0 Odds API credits"
            f"{f'; replaced {expired} prior Atlas Insight picks' if expired else ''})."
        )
        if summary:
            msg = f"{msg} {summary}"

        return {
            "signals_created": len(saved),
            "signals_expired": expired,
            "events_scanned": len(rows),
            "player_props": prop_count,
            "credits_used": 0,
            "cache_used": True,
            "openai_web": True,
            "web_search": used_web,
            "top_opportunity": float(saved[0]["opportunity_score"]) if saved else None,
            "message": msg,
        }
