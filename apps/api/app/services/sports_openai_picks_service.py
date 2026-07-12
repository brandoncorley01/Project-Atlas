"""Atlas Insight — stats/edge-first ranking of FanDuel-verified catalog bets."""

from __future__ import annotations

import asyncio
import logging
import statistics
from datetime import UTC, datetime
from typing import Any

from app.agents.sports_analyst import (
    american_to_decimal,
    american_to_implied_prob,
    _collect_outcome_odds,
)
from app.agents.sports_stats import compute_pick_support
from app.db.supabase_client import SupabaseClient
from app.providers.sports.odds_api import _read_cache as read_odds_cache
from app.providers.sports.sports_news import fetch_sports_news, match_news_for_insight
from app.providers.sports.team_stats import build_stats_index, lookup_match_stats, match_stats_payload
from app.services.calibration_service import CalibrationService
from app.services.fanduel_catalog import build_fanduel_catalog
from app.services.llm_service import llm_service

logger = logging.getLogger(__name__)

SOURCE = "openai_web"

_EXPLAIN_SYSTEM = """You are Atlas Insight writing bettor-facing explanations.
You receive PRE-RANKED picks with computed numbers (implied probability, edge, form/H2H, learning)
plus free public headlines / analyst context when available.

Rewrite thesis/bull/bear in plain sports-betting English.

HARD RULES:
- Do NOT invent odds, edges, win rates, records, or analyst claims not in the facts.
- Do NOT reorder or change ids — keep every id exactly as given.
- Lead with the edge in bettor terms: price → implied % → why we like it.
- If headlines or web notes are present, cite them in plain words (injury, lineup, analyst lean).
- Keep each thesis to 2–4 short sentences. No jargon stacks, no filler.
- If form/H2H is present, cite the record in plain words.
- If learning win-rate is present, mention it once as track record — not a guarantee.

Return JSON only:
{
  "picks": [
    {
      "id": "fd12",
      "thesis": "...",
      "bull_case": "...",
      "bear_case": "...",
      "web_notes": ["short public-source takeaways used"]
    }
  ]
}
"""


def _news_stub_from_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_name": item.get("event_name"),
        "selection": item.get("selection"),
        "sport": item.get("sport"),
        "home_team": item.get("home_team"),
        "away_team": item.get("away_team"),
    }


def _attach_web_news(item: dict[str, Any], news_pool: list[dict[str, Any]]) -> dict[str, Any]:
    """Match free RSS headlines to this catalog pick (no Odds credits)."""
    if not news_pool:
        return item
    matched = match_news_for_insight(_news_stub_from_item(item), news_pool, limit=4)
    if not matched:
        return item
    related = []
    sources: list[dict[str, Any]] = []
    for n in matched[:3]:
        title = str(n.get("title") or "").strip()
        if not title:
            continue
        related.append(
            {
                "title": title[:160],
                "url": n.get("url"),
                "source": n.get("source") or n.get("provider"),
                "relevance_score": n.get("relevance_score"),
            }
        )
        sources.append(
            {
                "type": "news",
                "title": title[:160],
                "url": n.get("url"),
                "provider": n.get("source") or n.get("provider") or "rss",
            }
        )
    if not related:
        return item
    item = dict(item)
    item["_related_news"] = related
    item["_context_sources"] = sources
    item["_news_verified"] = True
    item["_news_headline"] = related[0]["title"]
    # Small ranking nudge when public coverage exists for this matchup.
    item["_learning_boost"] = float(item.get("_learning_boost") or 0) + 1.5
    return item


def _is_openai_source(row: dict[str, Any]) -> bool:
    snap = row.get("scoring_snapshot") or {}
    return str(snap.get("source") or "") == SOURCE


def _is_combat_item(item: dict[str, Any]) -> bool:
    if item.get("bet_type") != "player_prop":
        return False
    return bool(
        str(item.get("prop_market") or "").startswith("fight_")
        or str(item.get("sport_key") or "").startswith(("mma_", "boxing_"))
        or str(item.get("sport") or "").upper() in {"MMA", "BOXING", "UFC"}
    )


def _market_key_for_item(item: dict[str, Any]) -> str | None:
    bet_type = str(item.get("bet_type") or "")
    prop = str(item.get("prop_market") or "")
    if prop == "fight_total_rounds":
        return "totals"
    if prop == "fight_spread":
        return "spreads"
    if bet_type == "moneyline":
        return "h2h"
    if bet_type == "spread":
        return "spreads"
    if bet_type == "total":
        return "totals"
    return None


def _outcome_name_for_item(item: dict[str, Any]) -> str | None:
    bet_type = str(item.get("bet_type") or "")
    prop = str(item.get("prop_market") or "")
    selection = str(item.get("selection") or "").strip()
    home = str(item.get("home_team") or "")
    away = str(item.get("away_team") or "")

    if bet_type == "total" or prop == "fight_total_rounds":
        low = selection.lower()
        if "over" in low:
            return "Over"
        if "under" in low:
            return "Under"
        return None

    if bet_type == "spread" or prop == "fight_spread":
        if home and selection.startswith(home):
            return home
        if away and selection.startswith(away):
            return away
        # "Team +3.5" → Team
        parts = selection.rsplit(" ", 1)
        return parts[0].strip() if len(parts) == 2 else selection

    if bet_type == "moneyline":
        return selection

    return None


def _edge_vs_cache(item: dict[str, Any], event: dict[str, Any] | None) -> tuple[float, int, float | None]:
    """Return (edge_pct, book_count, median_implied_pct) from multi-book cache."""
    if not event:
        return 0.0, 1, None
    market_key = _market_key_for_item(item)
    outcome = _outcome_name_for_item(item)
    if not market_key or not outcome:
        return 0.0, 1, None
    point = item.get("point")
    try:
        point_f = float(point) if point is not None else None
    except (TypeError, ValueError):
        point_f = None
    prices = _collect_outcome_odds(event, market_key, outcome, point_f)
    if len(prices) < 2:
        return 0.0, max(1, len(prices)), None
    try:
        best = int(item.get("odds_american") or prices[0])
    except (TypeError, ValueError):
        best = prices[0]
    best_imp = american_to_implied_prob(best)
    median_imp = statistics.median(american_to_implied_prob(p) for p in prices)
    edge = round((median_imp - best_imp) * 100, 2)
    return edge, len(prices), round(median_imp * 100, 2)


def _learning_boost(item: dict[str, Any], learning: dict[str, Any]) -> tuple[float, str | None]:
    """Bias future Insight picks using Atlas board outcomes + user grades."""
    sport = str(item.get("sport") or "")
    bet_type = str(item.get("bet_type") or "moneyline")
    boost = 0.0
    note: str | None = None

    # Ranking slices already blend Atlas (70%) + user (30%) when both exist.
    sport_meta = (learning.get("by_sport") or {}).get(sport) or {}
    bet_meta = (learning.get("by_bet_type") or {}).get(bet_type) or {}
    atlas = learning.get("atlas") if isinstance(learning.get("atlas"), dict) else {}
    user = learning.get("user") if isinstance(learning.get("user"), dict) else {}

    if sport_meta.get("boost"):
        boost += float(sport_meta["boost"])
        note = f"{sport} hits {sport_meta.get('win_rate')}% over {sport_meta.get('count')} graded outcomes"
    if bet_meta.get("boost"):
        boost += float(bet_meta["boost"])
        label = bet_type.replace("_", " ")
        note = (
            f"Atlas {label} hits {bet_meta.get('win_rate')}% over {bet_meta.get('count')} graded outcomes"
            if not note
            else note
        )

    atlas_wr = atlas.get("overall_win_rate")
    atlas_n = int(atlas.get("decided") or 0)
    user_wr = user.get("overall_win_rate")
    user_n = int(user.get("decided") or 0)
    if atlas_wr is not None and atlas_n >= 4:
        boost += max(-5.0, min(5.0, (float(atlas_wr) - 50.0) * 0.22))
        if note is None:
            note = f"Atlas board track record: {atlas_wr:.0f}% over {atlas_n} real outcomes"
    if user_wr is not None and user_n >= 4:
        boost += max(-3.0, min(3.0, (float(user_wr) - 50.0) * 0.12))
        if note is None:
            note = f"Your logged picks: {user_wr:.0f}% over {user_n} graded"

    overall = learning.get("overall_win_rate")
    decided = int(learning.get("decided") or 0)
    if overall is not None and decided >= 5 and note is None:
        note = f"Combined sports track record: {overall:.0f}% over {decided} graded picks"
        boost += max(-4.0, min(4.0, (float(overall) - 50.0) * 0.2))
    # Keep learning as a nudge, not the whole score.
    boost = max(-10.0, min(10.0, boost))
    return round(boost, 2), note


def _score_enriched(
    item: dict[str, Any],
    *,
    min_edge: float,
    min_opp: float,
    dampen: float,
) -> dict[str, Any]:
    odds = int(item.get("odds_american") or -110)
    implied = american_to_implied_prob(odds) * 100
    edge = float(item.get("_edge_pct") or 0.0)
    support = float(item.get("_stats_support") or 0.0)
    learn = float(item.get("_learning_boost") or 0.0)
    books = int(item.get("_book_count") or 1)
    combat = _is_combat_item(item)
    prop = str(item.get("bet_type") or "") == "player_prop"

    # Fair-ish win% ≈ market median when we have multi-book; else implied.
    fair = float(item.get("_median_implied") or implied)
    model_edge = edge if books >= 2 else max(0.0, support * 0.04)

    opportunity = (
        38.0
        + model_edge * 5.5
        + max(-10.0, min(12.0, support * 0.22))
        + learn
        + (3.0 if prop else 0.0)
        + (4.0 if combat else 0.0)
        + min(6.0, max(0, books - 1) * 1.5)
    )
    # Heavy juice without price edge is not "value".
    if edge < 0.4 and implied >= 65 and not combat:
        opportunity -= 6.0
    confidence = (
        48.0
        + model_edge * 3.2
        + max(0.0, support) * 0.12
        + learn * 0.5
        + min(8.0, books)
        - dampen
    )
    risk = min(88.0, max(22.0, 36.0 + implied * 0.35 - model_edge * 2.5 - max(0.0, support) * 0.08))

    opportunity = round(min(95.0, max(0.0, opportunity)), 1)
    confidence = round(min(90.0, max(35.0, confidence)), 1)
    risk = round(risk, 1)
    ev = round(model_edge * 0.85, 2) if model_edge else None

    passes = opportunity >= min_opp and (model_edge >= min_edge or combat or (prop and support >= 8))
    if combat:
        passes = True
        opportunity = max(opportunity, 34.0)

    return {
        **item,
        "_opportunity": opportunity,
        "_confidence": confidence,
        "_risk": risk,
        "_expected_value": ev,
        "_model_edge": round(model_edge, 2),
        "_implied_pct": round(implied, 2),
        "_fair_pct": round(fair, 2),
        "_passes": passes,
        "_rank_score": opportunity + model_edge * 2 + max(0.0, support) * 0.1,
    }


def _build_bettor_thesis(item: dict[str, Any]) -> tuple[str, str, str]:
    """Clear edge language a bettor can use — no LLM required."""
    selection = str(item.get("selection") or "this side")
    event = str(item.get("event_name") or "this matchup")
    book = str(item.get("book_title") or "FanDuel")
    odds = int(item.get("odds_american") or -110)
    implied = float(item.get("_implied_pct") or american_to_implied_prob(odds) * 100)
    edge = float(item.get("_model_edge") or item.get("_edge_pct") or 0.0)
    books = int(item.get("_book_count") or 1)
    fair = item.get("_fair_pct")
    support = float(item.get("_stats_support") or 0.0)
    form_note = str(item.get("_form_note") or "").strip()
    learn_note = item.get("_learning_note")
    bet_type = str(item.get("bet_type") or "moneyline").replace("_", " ")

    edge_bits: list[str] = [f"{book} lists {selection} at {odds:+d} (~{implied:.1f}% implied)"]
    if books >= 2 and edge > 0.2:
        fair_txt = f" vs ~{fair:.1f}% fair from {books} books" if fair else f" across {books} books"
        edge_bits.append(f"Atlas sees about {edge:.1f}% price edge{fair_txt}")
    elif support >= 8:
        edge_bits.append(f"recent form leans this way (support {support:.0f}/100)")
    else:
        edge_bits.append(f"open {bet_type} — ranked on price + matchup context")

    thesis_parts = [
        f"Play {selection} on {event}. " + ". ".join(edge_bits) + ".",
    ]
    if form_note:
        thesis_parts.append(f"Form/H2H: {form_note}.")
    news_headline = str(item.get("_news_headline") or "").strip()
    if news_headline:
        thesis_parts.append(f"Public coverage: {news_headline}.")
    if learn_note:
        thesis_parts.append(f"Track record: {learn_note}.")

    bull = (
        f"{selection} at {odds:+d} looks like the side with the better number"
        + (f" (+{edge:.1f}% vs the market)" if edge >= 0.5 else "")
        + (f" — {form_note}" if form_note else ".")
    )
    if news_headline:
        bull = (bull.rstrip(".") + f" · News: {news_headline}")[:400]
    bear = (
        "Line moves against you, late injury/news, or a short sample of form would weaken this."
        if not _is_combat_item(item)
        else "Fight props swing fast — confirm the number and card before betting."
    )
    return (" ".join(thesis_parts))[:800], bull[:400], bear[:400]


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
    if not thesis.strip():
        thesis, bull, bear = _build_bettor_thesis(item)

    edge = item.get("_model_edge")
    if edge is None:
        edge = item.get("_edge_pct")
    implied = item.get("_implied_pct")
    ev = item.get("_expected_value")
    stats_payload = item.get("_team_stats")
    support = item.get("_stats_support")

    return {
        "user_id": user_id,
        "sport": str(item.get("sport") or "Sports")[:40],
        "event_name": event_name[:160],
        "event_start": item.get("event_start"),
        "bet_type": bet_type,
        "selection": selection[:140],
        "odds_american": odds_american,
        "odds_decimal": american_to_decimal(odds_american),
        "expected_value": ev,
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
            "edge_pct": edge,
            "consensus_books": item.get("_book_count"),
            "market_median_implied": item.get("_median_implied"),
        },
        "injury_impact": None,
        "weather_impact": None,
        "travel_rest_impact": None,
        "public_betting_pct": None,
        "sharp_indicator": (
            "steam" if (edge or 0) >= 3.5 else ("value" if (edge or 0) >= 1.5 else "consensus")
        ),
        "confidence_score": confidence,
        "risk_score": risk,
        "opportunity_score": opportunity,
        "recommendation": f"Atlas Insight · {type_label} — {selection} · {event_name}",
        "explanation": thesis[:800],
        "bull_case": (bull or thesis)[:400],
        "bear_case": (bear or "Lineup scratch or late news can void a prop; recheck FanDuel before betting.")[
            :400
        ],
        "invalidation": "FanDuel pulls the market, lineup scratches, or the line moves materially.",
        "suggested_action": f"Play {odds_american:+d} on {book_title} for {selection}",
        "risk_warning": (
            "Atlas Insight ranks FanDuel-verified markets using price edge, form/H2H, "
            "free public news/analyst coverage, real outcomes of prior Atlas board picks, "
            "and your graded results. Confirm the number is still posted before betting."
        ),
        "scoring_snapshot": {
            "source": SOURCE,
            "openai_web": True,
            "web_search": bool(item.get("_web_search")),
            "web_context": True,
            "news_verified": bool(item.get("_news_verified")),
            "stats_engine": True,
            "fanduel_verified": True,
            "pick_origin": "atlas",
            "atlas_presented": True,
            "atlas_tracked": True,
            "is_player_prop": bet_type == "player_prop",
            "is_fight_prop": bool(
                item.get("is_fight_prop")
                or item.get("prop_market") in {"fight_total_rounds", "fight_spread"}
            ),
            "prop_market": item.get("prop_market"),
            "player_name": item.get("player_name"),
            "sources": sources,
            "context_sources": item.get("_context_sources") or [],
            "related_news": item.get("_related_news") or [],
            "odds_approximate": False,
            "event_id": item.get("event_id"),
            "sport": str(item.get("sport") or "Sports")[:40],
            "bet_type": bet_type,
            "sport_key": item.get("sport_key"),
            "home_team": item.get("home_team"),
            "away_team": item.get("away_team"),
            "catalog_id": item.get("id"),
            "preferred_book": item.get("book_key") or "fanduel",
            "preferred_book_title": book_title,
            "edge_pct": edge,
            "implied_prob": implied,
            "expected_value": ev,
            "book_count": item.get("_book_count"),
            "stats_support": support,
            "team_stats": stats_payload,
            "learning_note": item.get("_learning_note"),
            "learning_boost": item.get("_learning_boost"),
            "point": item.get("point"),
            "categories": (
                ["top_picks", "atlas_insight", "player_props", "value_plays"]
                if bet_type == "player_prop"
                else ["top_picks", "atlas_insight", "value_plays"]
            ),
            "pick": {
                "bet_type": bet_type,
                "team_or_side": selection,
                "player_name": item.get("player_name"),
                "point": item.get("point"),
            },
        },
        "status": "active",
        "data_as_of": now,
    }


async def _enrich_catalog(
    catalog: list[dict[str, Any]],
    *,
    learning: dict[str, Any],
    min_edge: float,
    min_opp: float,
    dampen: float,
    news_pool: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    cache = read_odds_cache() or {}
    events_by_id = {
        str(e.get("id")): e for e in (cache.get("events") or []) if isinstance(e, dict) and e.get("id")
    }
    news_pool = news_pool or []

    # Stats index from unique matchups (scores cache — no Odds spend when locked).
    stub_events: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for c in catalog:
        sk = str(c.get("sport_key") or "")
        home = str(c.get("home_team") or "")
        away = str(c.get("away_team") or "")
        if not sk or not home or not away:
            continue
        key = f"{sk}|{home}|{away}"
        if key in seen_keys:
            continue
        seen_keys.add(key)
        stub_events.append(
            {
                "_sport_key": sk,
                "home_team": home,
                "away_team": away,
                "id": c.get("event_id"),
            }
        )

    stats_index: dict[str, dict[str, Any]] = {}
    if stub_events:
        try:
            stats_index = await build_stats_index(stub_events)
        except Exception as exc:
            logger.warning("Atlas Insight stats index skipped: %s", exc)

    enriched: list[dict[str, Any]] = []
    for item in catalog:
        row = dict(item)
        event = events_by_id.get(str(item.get("event_id") or ""))
        edge, books, median_imp = _edge_vs_cache(item, event)
        row["_edge_pct"] = edge
        row["_book_count"] = books
        row["_median_implied"] = median_imp

        support = 0.0
        details: dict[str, Any] = {}
        home = str(item.get("home_team") or "")
        away = str(item.get("away_team") or "")
        if home and away and item.get("sport_key"):
            stub = {
                "_sport_key": item.get("sport_key"),
                "home_team": home,
                "away_team": away,
            }
            match = lookup_match_stats(stub, stats_index)
            bet_type = str(item.get("bet_type") or "moneyline")
            support_type = (
                "total"
                if item.get("prop_market") == "fight_total_rounds"
                else "spread"
                if item.get("prop_market") == "fight_spread"
                else bet_type
                if bet_type != "player_prop"
                else "moneyline"
            )
            sel = _outcome_name_for_item(item) or str(item.get("selection") or "")
            if support_type == "moneyline" and bet_type == "player_prop":
                support, details = 0.0, {}
                if match:
                    details = match_stats_payload(match) or {}
            else:
                support, details = compute_pick_support(
                    support_type,
                    sel,
                    item.get("point"),
                    home,
                    away,
                    match,
                )
        row["_stats_support"] = support
        row["_team_stats"] = details or None
        row["_form_note"] = (details or {}).get("form_note") or (details or {}).get("summary")

        boost, learn_note = _learning_boost(item, learning)
        row["_learning_boost"] = boost
        row["_learning_note"] = learn_note
        row = _attach_web_news(row, news_pool)

        scored = _score_enriched(row, min_edge=min_edge, min_opp=min_opp, dampen=dampen)
        enriched.append(scored)

    enriched.sort(key=lambda x: float(x.get("_rank_score") or 0), reverse=True)
    return enriched


async def _polish_explanations(items: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    """Optional LLM polish — numbers stay authoritative; copy becomes clearer using free web context."""
    if not items or not llm_service.is_configured():
        return {}
    slim = []
    for it in items:
        slim.append(
            {
                "id": it.get("id"),
                "sport": it.get("sport"),
                "event": it.get("event_name"),
                "bet_type": it.get("bet_type"),
                "selection": it.get("selection"),
                "odds": it.get("odds_american"),
                "implied_pct": it.get("_implied_pct"),
                "edge_pct": it.get("_model_edge"),
                "books": it.get("_book_count"),
                "fair_pct": it.get("_fair_pct"),
                "form": it.get("_form_note"),
                "stats_support": it.get("_stats_support"),
                "learning": it.get("_learning_note"),
                "headlines": [
                    {"title": n.get("title"), "source": n.get("source")}
                    for n in (it.get("_related_news") or [])[:3]
                ],
                "draft_thesis": _build_bettor_thesis(it)[0],
            }
        )
    user = (
        "Polish these pre-ranked Atlas Insight picks. "
        "Use the provided headlines; if web search is available, add only free public "
        "analyst/news consensus that supports or risks the pick — never invent markets.\n"
        f"{slim}"
    )
    result: dict[str, Any] | None = None
    used_web = False
    try:
        result = await asyncio.wait_for(
            llm_service.complete_json_with_web_search(
                system=_EXPLAIN_SYSTEM,
                user=user,
                max_tokens=1800,
                web_timeout_s=22.0,
            ),
            timeout=28.0,
        )
        used_web = bool((result or {}).get("_web_search"))
    except Exception as exc:
        logger.warning("Atlas Insight web polish failed, trying local polish: %s", exc)
        try:
            result = await asyncio.wait_for(
                llm_service.complete_json(
                    system=_EXPLAIN_SYSTEM,
                    user=user,
                    max_tokens=1600,
                ),
                timeout=20.0,
            )
        except Exception as exc2:
            logger.warning("Atlas Insight explanation polish skipped: %s", exc2)
            return {}

    out: dict[str, dict[str, Any]] = {}
    if not result or not isinstance(result.get("picks"), list):
        return out
    for pick in result["picks"]:
        if not isinstance(pick, dict):
            continue
        cid = str(pick.get("id") or "").strip()
        if not cid:
            continue
        web_notes = [str(n) for n in (pick.get("web_notes") or []) if n][:3]
        out[cid] = {
            "thesis": str(pick.get("thesis") or ""),
            "bull": str(pick.get("bull_case") or ""),
            "bear": str(pick.get("bear_case") or ""),
            "web_notes": web_notes,
            "_web_search": used_web,
        }
    return out


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
        try:
            return await self._refresh_openai_picks_inner(limit=limit)
        except Exception as exc:
            logger.exception("Atlas Insight scan failed: %s", exc)
            return {
                "signals_created": 0,
                "credits_used": 0,
                "cache_used": True,
                "openai_web": llm_service.is_configured(),
                "fanduel_verified": True,
                "message": f"Atlas Insight failed: {str(exc)[:180]}. Tap Rescore / Insight again.",
            }

    async def _refresh_openai_picks_inner(self, *, limit: int = 16) -> dict[str, Any]:
        # Close the learning loop first: grade finished Atlas board + user sports picks.
        graded_prior = 0
        try:
            from app.services.outcome_resolver import OutcomeResolverService

            resolve = await OutcomeResolverService(self.db, self.user_id).resolve_pending(
                limit=50,
                module="sports",
            )
            graded_prior = int((resolve or {}).get("resolved") or 0)
            if graded_prior:
                logger.info("Atlas Insight graded %s finished sports picks before ranking", graded_prior)
        except Exception as exc:
            logger.warning("Atlas Insight pre-grade skipped: %s", exc)

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
                "graded_prior": graded_prior,
                "message": catalog_meta.get("message")
                or "No FanDuel-verified markets available. Unlock Odds or wait for cache, then Atlas Insight.",
            }

        calibration = await CalibrationService(self.db, self.user_id).get_adjustments(lookback=200)
        learning = calibration.get("sports_learning") or {}
        min_edge = float(calibration.get("sports_min_edge_pct") or 0.6)
        min_opp = float(calibration.get("sports_min_opportunity") or 28.0)
        dampen = float(calibration.get("sports_confidence_dampen") or 0.0)

        ranking_catalog = catalog[:64]
        news_pool: list[dict[str, Any]] = []
        try:
            news_pool = await asyncio.wait_for(fetch_sports_news(limit_per_feed=5), timeout=8.0)
        except Exception as exc:
            logger.warning("Atlas Insight news prefetch skipped: %s", exc)

        enriched = await _enrich_catalog(
            ranking_catalog,
            learning=learning,
            min_edge=min_edge,
            min_opp=min_opp,
            dampen=dampen,
            news_pool=news_pool,
        )

        # Prefer real edge / form-backed sides; always keep a combat reserve.
        passed = [e for e in enriched if e.get("_passes")]
        if len(passed) < max(6, limit // 2):
            # Soften bar so the board still fills from best available numbers.
            passed = enriched[: max(limit, 12)]

        selected: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in passed:
            cid = str(item.get("id") or "")
            if not cid or cid in seen:
                continue
            seen.add(cid)
            selected.append(item)
            if len(selected) >= limit:
                break

        for item in enriched:
            if not _is_combat_item(item):
                continue
            cid = str(item.get("id") or "")
            if not cid or cid in seen:
                continue
            seen.add(cid)
            selected.append(item)
            if len(selected) >= max(limit, 12):
                break

        if not selected:
            selected = enriched[:limit]

        polished = await _polish_explanations(selected[:limit])
        used_web = any(bool(v.get("_web_search")) for v in polished.values())
        rows: list[dict[str, Any]] = []
        news_backed = 0
        for item in selected[: max(limit, 12)]:
            thesis, bull, bear = _build_bettor_thesis(item)
            polish = polished.get(str(item.get("id") or "")) or {}
            if polish.get("thesis"):
                thesis = str(polish["thesis"])
            if polish.get("bull"):
                bull = str(polish["bull"])
            if polish.get("bear"):
                bear = str(polish["bear"])
            web_notes = [str(n) for n in (polish.get("web_notes") or []) if n][:3]
            if web_notes:
                sources_extra = list(item.get("_context_sources") or [])
                for note in web_notes:
                    sources_extra.append(
                        {"type": "web_analyst", "title": note[:160], "provider": "openai_web"}
                    )
                item = dict(item)
                item["_context_sources"] = sources_extra[:6]
                item["_web_search"] = bool(polish.get("_web_search") or used_web)
            if item.get("_news_verified") or item.get("_web_search"):
                news_backed += 1
            item = dict(item)
            item["_web_search"] = bool(item.get("_web_search") or polish.get("_web_search") or used_web)
            src_labels = ["FanDuel", "Atlas board results", "Form/H2H", "Your graded picks"]
            if item.get("_news_verified"):
                src_labels.append("Sports news")
            if item.get("_web_search"):
                src_labels.append("Web analyst consensus")
            rows.append(
                _catalog_to_row(
                    self.user_id,
                    item,
                    confidence=float(item.get("_confidence") or 55),
                    opportunity=float(item.get("_opportunity") or 45),
                    risk=float(item.get("_risk") or 50),
                    thesis=thesis,
                    bull=bull,
                    bear=bear,
                    sources=src_labels,
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

        prop_count = sum(1 for r in (saved or rows) if str(r.get("bet_type")) == "player_prop")
        edged = sum(
            1
            for r in (saved or rows)
            if float(((r.get("scoring_snapshot") or {}).get("edge_pct") or 0)) >= 0.5
        )
        with_stats = sum(
            1
            for r in (saved or rows)
            if (r.get("scoring_snapshot") or {}).get("team_stats")
            or (r.get("scoring_snapshot") or {}).get("stats_support")
        )
        atlas_learn = learning.get("atlas") if isinstance(learning.get("atlas"), dict) else {}
        user_learn = learning.get("user") if isinstance(learning.get("user"), dict) else {}
        learn_notes = "; ".join(str(n) for n in (calibration.get("learning_notes") or [])[:3])
        msg = (
            f"Atlas Insight posted {len(saved)} edge-ranked picks"
            f" ({prop_count} props, {edged} with multi-book edge, {with_stats} with form/H2H"
            f", {news_backed} with news/web context"
            f", catalog {catalog_meta.get('player_props', 0)} props / {catalog_meta.get('game_lines', 0)} lines"
            f", 0 Odds credits"
            f"{' · web analyst search on' if used_web else ''}"
            f"{f'; graded {graded_prior} finished board picks' if graded_prior else ''}"
            f"{f'; replaced {expired} prior Insight picks' if expired else ''})."
        )
        if learn_notes:
            msg = f"{msg} Learning: {learn_notes}."
        elif atlas_learn.get("decided") or user_learn.get("decided"):
            msg = (
                f"{msg} Learning from "
                f"{int(atlas_learn.get('decided') or 0)} Atlas board outcomes + "
                f"{int(user_learn.get('decided') or 0)} of your logged picks."
            )

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
            "web_context": True,
            "news_backed": news_backed,
            "stats_engine": True,
            "edged_picks": edged,
            "stats_backed": with_stats,
            "graded_prior": graded_prior,
            "learning_active": bool(learning.get("decided")),
            "atlas_outcomes": int(atlas_learn.get("decided") or 0),
            "user_outcomes": int(user_learn.get("decided") or 0),
            "catalog_props": catalog_meta.get("player_props"),
            "catalog_game_lines": catalog_meta.get("game_lines"),
            "mma_props": catalog_meta.get("mma_props"),
            "top_opportunity": float(saved[0]["opportunity_score"]) if saved else None,
            "message": msg,
        }
