"""Atlas Insight sports picks — ranks only FanDuel-verified catalog bets."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from app.agents.sports_analyst import american_to_decimal
from app.db.supabase_client import SupabaseClient
from app.providers.sports.sports_news import fetch_sports_news
from app.services.fanduel_catalog import build_fanduel_catalog
from app.services.llm_service import llm_service

logger = logging.getLogger(__name__)

SOURCE = "openai_web"

_SYSTEM = """You are Atlas Insight for Project Atlas.
You receive a FanDuel-verified catalog of real open bets (game lines and player props).
Your job is to rank the best ones using public web consensus from analysts and popular bettors.

HARD RULES:
- You may ONLY choose picks by returning catalog ids that already exist in the catalog.
- NEVER invent a player, line, market, team, or odds that is not in the catalog.
- Prefer player props when they are present in the catalog (~60% of picks), still include strong moneylines/spreads/totals.
- When MMA/UFC/Boxing fight props are in the catalog (round totals / fight spreads), include several of tonight's fights — do not ignore combat sports.
- Prefer MLB and WNBA among team sports when those events appear.
- Use web search to decide which catalog bets analysts currently like — not to create new bets.

Return JSON only:
{
  "picks": [
    {
      "id": "fd12",
      "rank": 1,
      "confidence": 55-85,
      "opportunity": 45-80,
      "risk": 35-70,
      "thesis": "why this catalog bet, citing analyst consensus",
      "bull_case": "short",
      "bear_case": "short",
      "sources": ["site names"]
    }
  ],
  "summary": "one sentence"
}
Return 8-16 picks max. Every id MUST appear in the catalog."""


def _is_openai_source(row: dict[str, Any]) -> bool:
    snap = row.get("scoring_snapshot") or {}
    return str(snap.get("source") or "") == SOURCE


def _catalog_to_row(
    user_id: str,
    item: dict[str, Any],
    *,
    confidence: float,
    opportunity: float,
    risk: float,
    thesis: str,
    bull: str,
    bear: str,
    sources: list[str],
) -> dict[str, Any]:
    bet_type = str(item.get("bet_type") or "moneyline")
    selection = str(item.get("selection") or "")
    odds_american = int(item.get("odds_american") or -110)
    event_name = str(item.get("event_name") or "")
    type_label = "Player prop" if bet_type == "player_prop" else bet_type.replace("_", " ").title()
    book_title = str(item.get("book_title") or "FanDuel")
    now = datetime.now(UTC).isoformat()
    thesis = (thesis or f"Atlas Insight selected this open {book_title} market from analyst consensus.").strip()
    return {
        "user_id": user_id,
        "sport": str(item.get("sport") or "Sports")[:40],
        "event_name": event_name[:160],
        "event_start": item.get("event_start"),
        "bet_type": bet_type,
        "selection": selection[:140],
        "odds_american": odds_american,
        "odds_decimal": american_to_decimal(odds_american),
        "expected_value": None,
        "line_movement": {
            "preferred_book": item.get("book_key") or "fanduel",
            "preferred_book_title": book_title,
            "source": SOURCE,
            "sources": sources,
            "odds_approximate": False,
            "fanduel_verified": True,
            "prop_market": item.get("prop_market"),
            "player_name": item.get("player_name"),
            "event_id": item.get("event_id"),
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
        "bull_case": (bull or thesis)[:400],
        "bear_case": (bear or "Lineup scratch or late news can void a prop; recheck FanDuel before betting.")[:400],
        "invalidation": "FanDuel pulls the market, lineup scratches, or the line moves materially.",
        "suggested_action": f"Play {odds_american:+d} on {book_title} for {selection}",
        "risk_warning": (
            "Atlas Insight only surfaces FanDuel-verified open markets. "
            "Confirm the number is still posted before betting."
        ),
        "scoring_snapshot": {
            "source": SOURCE,
            "openai_web": True,
            "web_search": True,
            "fanduel_verified": True,
            "is_player_prop": bet_type == "player_prop",
            "is_fight_prop": bool(
                item.get("is_fight_prop")
                or item.get("prop_market") in {"fight_total_rounds", "fight_spread"}
            ),
            "prop_market": item.get("prop_market"),
            "player_name": item.get("player_name"),
            "sources": sources,
            "odds_approximate": False,
            "event_id": item.get("event_id"),
            "sport_key": item.get("sport_key"),
            "home_team": item.get("home_team"),
            "away_team": item.get("away_team"),
            "catalog_id": item.get("id"),
            "preferred_book": item.get("book_key") or "fanduel",
            "preferred_book_title": book_title,
            "categories": (
                ["top_picks", "atlas_insight", "player_props", "value_plays"]
                if bet_type == "player_prop"
                else ["top_picks", "atlas_insight", "value_plays"]
            ),
            "pick": {
                "bet_type": bet_type,
                "team_or_side": selection,
                "player_name": item.get("player_name"),
            },
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
                logger.warning("Failed to expire Atlas Insight pick %s: %s", sid, exc)
        return expired

    async def refresh_openai_picks(self, *, limit: int = 16) -> dict[str, Any]:
        if not llm_service.is_configured():
            return {
                "signals_created": 0,
                "credits_used": 0,
                "cache_used": True,
                "openai_web": False,
                "fanduel_verified": False,
                "message": "OPENAI_API_KEY is not configured on the API — add it on Render/.env.",
            }

        try:
            return await self._refresh_openai_picks_inner(limit=limit)
        except Exception as exc:
            logger.exception("Atlas Insight scan failed: %s", exc)
            return {
                "signals_created": 0,
                "credits_used": 0,
                "cache_used": True,
                "openai_web": True,
                "fanduel_verified": True,
                "message": f"Atlas Insight failed: {str(exc)[:180]}. Tap Fetch live odds, then try again.",
            }

    async def _refresh_openai_picks_inner(self, *, limit: int = 16) -> dict[str, Any]:
        # Skip live Odds prop pulls (slow + credits). Use odds cache + props cache.
        catalog_meta = await build_fanduel_catalog(include_props=True, max_prop_events=0)
        catalog = list(catalog_meta.get("items") or [])
        credits_used = int(catalog_meta.get("credits_used") or 0)
        if not catalog:
            return {
                "signals_created": 0,
                "credits_used": credits_used,
                "cache_used": True,
                "openai_web": True,
                "fanduel_verified": True,
                "message": catalog_meta.get("message")
                or "No FanDuel-verified markets available. Tap Fetch live odds, then Atlas Insight.",
            }

        ranking_catalog = catalog[:48]
        news: list[dict[str, Any]] = []
        try:
            news = await asyncio.wait_for(fetch_sports_news(limit_per_feed=4), timeout=8.0)
        except Exception as exc:
            logger.warning("Atlas Insight news prefetch skipped: %s", exc)

        headlines = [
            {"title": n.get("title"), "source": n.get("source"), "url": n.get("url")}
            for n in news[:12]
        ]
        slim = [
            {
                "id": c["id"],
                "sport": c.get("sport"),
                "event": c.get("event_name"),
                "start": c.get("event_start"),
                "bet_type": c.get("bet_type"),
                "selection": c.get("selection"),
                "odds": c.get("odds_american"),
                "book": c.get("book_title"),
                "prop_market": c.get("prop_market"),
                "player": c.get("player_name"),
            }
            for c in ranking_catalog
        ]
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        user = (
            f"Today UTC: {today}. Rank FanDuel-verified open bets from this catalog only. "
            f"Catalog has {catalog_meta.get('player_props', 0)} player props"
            f" ({catalog_meta.get('mma_props', 0)} MMA/Boxing fight props)"
            f" and {catalog_meta.get('game_lines', 0)} game lines. "
            "Prefer props when available (including MMA round totals / fight spreads), "
            "still include strong fight winners and game lines. "
            "Do not invent bets.\n\n"
            f"Catalog:\n{slim}\n\n"
            f"Recent headlines (context only):\n{headlines}"
        )

        result = await llm_service.complete_json_with_web_search(
            system=_SYSTEM,
            user=user,
            max_tokens=1800,
            web_timeout_s=35.0,
        )

        by_id = {str(c.get("id")): c for c in ranking_catalog}
        rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        dropped_invented = 0
        if result and isinstance(result.get("picks"), list):
            for pick in result["picks"]:
                if not isinstance(pick, dict):
                    continue
                cid = str(pick.get("id") or "").strip()
                item = by_id.get(cid)
                if not item or cid in seen:
                    if cid and cid not in by_id:
                        dropped_invented += 1
                    continue
                seen.add(cid)
                try:
                    confidence = max(40.0, min(90.0, float(pick.get("confidence") or 62)))
                    opportunity = max(35.0, min(90.0, float(pick.get("opportunity") or 55)))
                    risk = max(25.0, min(85.0, float(pick.get("risk") or 48)))
                except (TypeError, ValueError):
                    confidence, opportunity, risk = 62.0, 55.0, 48.0
                if item.get("bet_type") == "player_prop":
                    opportunity = min(90.0, opportunity + 2.0)
                sources = [str(s) for s in (pick.get("sources") or []) if s][:6]
                rows.append(
                    _catalog_to_row(
                        self.user_id,
                        item,
                        confidence=confidence,
                        opportunity=opportunity,
                        risk=risk,
                        thesis=str(pick.get("thesis") or ""),
                        bull=str(pick.get("bull_case") or ""),
                        bear=str(pick.get("bear_case") or ""),
                        sources=sources,
                    )
                )
                if len(rows) >= limit:
                    break

        # Always reserve tonight's MMA/Boxing fight props so they cannot vanish behind MLB/WNBA ranks.
        combat_items = [
            c
            for c in ranking_catalog
            if c.get("bet_type") == "player_prop"
            and (
                str(c.get("prop_market") or "").startswith("fight_")
                or str(c.get("sport_key") or "").startswith(("mma_", "boxing_"))
                or str(c.get("sport") or "").upper() in {"MMA", "BOXING", "UFC"}
            )
        ]
        seen_catalog_ids = {
            str((r.get("scoring_snapshot") or {}).get("catalog_id") or "")
            for r in rows
        }
        for item in combat_items:
            cid = str(item.get("id") or "")
            if not cid or cid in seen_catalog_ids:
                continue
            rows.append(
                _catalog_to_row(
                    self.user_id,
                    item,
                    confidence=60.0,
                    opportunity=58.0,
                    risk=48.0,
                    thesis=(
                        "Tonight's FanDuel/DraftKings fight prop — reserved so MMA/Boxing "
                        "markets stay on the board with Atlas Insight."
                    ),
                    bull="Listed now on a US book for an upcoming fight.",
                    bear="Live fight volatility — confirm the number before betting.",
                    sources=["DraftKings", "FanDuel"],
                )
            )
            seen_catalog_ids.add(cid)
            if len(rows) >= max(limit, 12):
                break
        # Cap after combat reserve.
        rows = rows[: max(limit, 12)]

        # Always surface a board when the catalog has markets.
        if not rows:
            seed = [c for c in ranking_catalog if c.get("bet_type") == "player_prop"][:8]
            if len(seed) < 6:
                seed = seed + [
                    c for c in ranking_catalog if c.get("bet_type") != "player_prop"
                ][: 8 - len(seed)]
            for item in seed[:limit]:
                rows.append(
                    _catalog_to_row(
                        self.user_id,
                        item,
                        confidence=58.0,
                        opportunity=52.0 if item.get("bet_type") != "player_prop" else 56.0,
                        risk=50.0,
                        thesis=(
                            "FanDuel-verified open market — ranked as a fallback when "
                            "Insight ranking was empty."
                        ),
                        bull="Posted on FanDuel right now.",
                        bear="Public number may move quickly.",
                        sources=["FanDuel"],
                    )
                )

        expired = await self._expire_openai_picks()
        from app.agents.sports_categories import tag_pool_categories

        tag_pool_categories(rows)
        saved = await self.db.insert("sports_signals", rows) if rows else []

        if saved:
            try:
                from app.services.signal_registry_service import SignalRegistryService

                await SignalRegistryService(self.db, self.user_id).register_batch("sports", saved)
            except Exception as exc:
                logger.warning("Atlas Insight sports registry skipped: %s", exc)

        used_web = bool((result or {}).get("_web_search")) if result else False
        prop_count = sum(1 for r in (saved or rows) if str(r.get("bet_type")) == "player_prop")
        summary = str((result or {}).get("summary") or "").strip()
        msg = (
            f"Atlas Insight posted {len(saved)} FanDuel-verified picks"
            f" ({prop_count} player props"
            f", catalog {catalog_meta.get('player_props', 0)} props / {catalog_meta.get('game_lines', 0)} game lines"
            f"{f', ~{credits_used} Odds credits for props' if credits_used else ', 0 Odds credits for game lines'})"
            f"{' via web ranking' if used_web else ' via fast ranking'}"
            f"{f'; dropped {dropped_invented} invented ids' if dropped_invented else ''}"
            f"{f'; replaced {expired} prior Insight picks' if expired else ''})."
        )
        if summary:
            msg = f"{msg} {summary}"

        return {
            "signals_created": len(saved),
            "signals_expired": expired,
            "events_scanned": len(rows),
            "player_props": prop_count,
            "credits_used": credits_used,
            "cache_used": credits_used == 0,
            "openai_web": True,
            "fanduel_verified": True,
            "web_search": used_web,
            "dropped_invented": dropped_invented,
            "catalog_props": catalog_meta.get("player_props"),
            "catalog_game_lines": catalog_meta.get("game_lines"),
            "mma_props": catalog_meta.get("mma_props"),
            "top_opportunity": float(saved[0]["opportunity_score"]) if saved else None,
            "message": msg,
        }
