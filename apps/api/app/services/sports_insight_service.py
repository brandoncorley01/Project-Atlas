"""On-demand sports insight: market data, form stats, news context, and pick thesis."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from app.agents.sports_stats import compute_pick_support
from app.providers.sports.sports_news import fetch_sports_news, match_news_for_insight
from app.providers.sports.team_stats import (
    build_stats_index,
    lookup_match_stats,
    match_stats_payload,
)
from app.services.llm_service import llm_service

logger = logging.getLogger(__name__)

_SPORTS_INSIGHT_SYSTEM = """You are Atlas, explaining why you ranked a sports pick.
Write a clear pick thesis using whatever facts are in the payload — market edge, EV, odds,
line movement, confidence/risk/opportunity scores, team form, H2H, and headlines.
Never invent injuries, lineups, scores, or odds that are not in the payload.
If event-specific news is thin, lean on market + form data and say so honestly.
Tone: direct, formative, decision-oriented. Explain WHY this pick over the other side."""


def _participants_from_signal(signal: dict[str, Any]) -> tuple[str, str, str | None]:
    snap = signal.get("scoring_snapshot") or {}
    home = str(snap.get("home_team") or "").strip()
    away = str(snap.get("away_team") or "").strip()
    sport_key = snap.get("sport_key")

    if home and away:
        return home, away, sport_key

    event = str(signal.get("event_name") or "")
    if " @ " in event:
        away_part, home_part = event.split(" @ ", 1)
        return home_part.strip(), away_part.strip(), sport_key
    if re.search(r"\s+vs\.?\s+", event, flags=re.I):
        parts = re.split(r"\s+vs\.?\s+", event, maxsplit=1, flags=re.I)
        if len(parts) == 2:
            return parts[0].strip(), parts[1].strip(), sport_key
    return "", "", sport_key


def _event_dict_from_signal(signal: dict[str, Any]) -> dict[str, Any]:
    home, away, sport_key = _participants_from_signal(signal)
    snap = signal.get("scoring_snapshot") or {}
    return {
        "_sport_key": sport_key or snap.get("sport_key"),
        "home_team": home,
        "away_team": away,
        "id": snap.get("event_id"),
    }


def _format_team_side(label: str, team: dict[str, Any] | None) -> dict[str, Any]:
    if not team:
        return {"label": label}
    return {
        "label": label,
        "name": team.get("name"),
        "record": team.get("record_label") or team.get("record"),
        "win_pct": team.get("win_pct"),
        "avg_scored": team.get("avg_scored"),
        "avg_allowed": team.get("avg_allowed"),
        "form": team.get("form") or team.get("form_label"),
        "recent_results": team.get("recent_results"),
        "games_sampled": team.get("games_sampled"),
        "home_record": team.get("home_record"),
        "away_record": team.get("away_record"),
    }


def _market_context(signal: dict[str, Any], formatted: dict[str, Any]) -> dict[str, Any]:
    snap = signal.get("scoring_snapshot") or {}
    line = signal.get("line_movement") or formatted.get("line_movement") or {}
    scores = formatted.get("scores") or {}
    pick = snap.get("pick") or {}

    odds = signal.get("odds_american")
    if odds is None:
        odds = formatted.get("odds_american")
    ev = signal.get("expected_value")
    if ev is None:
        ev = formatted.get("expected_value")

    return {
        "selection": signal.get("selection") or formatted.get("selection"),
        "bet_type": signal.get("bet_type") or formatted.get("bet_type"),
        "sport": signal.get("sport") or formatted.get("sport"),
        "event": signal.get("event_name") or formatted.get("event_name"),
        "odds_american": odds,
        "expected_value": ev,
        "edge_pct": snap.get("edge_pct") or line.get("edge_pct"),
        "implied_prob": snap.get("implied_prob") or formatted.get("implied_prob"),
        "sharp_indicator": signal.get("sharp_indicator") or formatted.get("sharp_indicator"),
        "opening_odds": line.get("opening_odds"),
        "book_count": snap.get("book_count") or line.get("consensus_books"),
        "point": pick.get("point"),
        "confidence": scores.get("confidence") or signal.get("confidence_score"),
        "risk": scores.get("risk") or signal.get("risk_score"),
        "opportunity": scores.get("opportunity") or signal.get("opportunity_score"),
        "recommendation": formatted.get("recommendation") or signal.get("recommendation"),
        "bull_case": signal.get("bull_case") or formatted.get("bull_case"),
        "bear_case": signal.get("bear_case") or formatted.get("bear_case"),
        "invalidation": signal.get("invalidation") or formatted.get("invalidation"),
        "suggested_action": signal.get("suggested_action") or formatted.get("suggested_action"),
        "stats_support": snap.get("stats_support") or formatted.get("stats_support"),
        "rejected_side": snap.get("rejected_side"),
        "decision_margin": snap.get("decision_margin"),
        "atlas_decision": snap.get("atlas_decision"),
    }


def _template_stats_comparison(
    signal: dict[str, Any],
    stats_payload: dict[str, Any] | None,
    support: float,
) -> dict[str, Any]:
    home, away, _ = _participants_from_signal(signal)
    selection = str(signal.get("selection") or "")
    bet_type = str(signal.get("bet_type") or "moneyline")

    if not stats_payload:
        return {
            "summary": (
                f"Historical form sample is limited for {home or 'home'} vs {away or 'away'}. "
                "Atlas leans on market edge, expected value, and scan scores for this pick."
            ),
            "home": _format_team_side("home", None),
            "away": _format_team_side("away", None),
            "h2h": None,
            "pick_support": support,
            "selection": selection,
            "bet_type": bet_type,
            "available": False,
        }

    home_team = stats_payload.get("home") or {}
    away_team = stats_payload.get("away") or {}
    h2h = stats_payload.get("h2h") or {}
    summary = str(stats_payload.get("summary") or stats_payload.get("form_note") or "")

    if support >= 12:
        lean = f"Recent form supports {selection}."
    elif support <= -12:
        lean = f"Recent form leans against {selection} — market edge must carry more weight."
    else:
        lean = "Recent form is mixed; market pricing and edge drive the ranking."

    h2h_note = ""
    if h2h.get("games"):
        h2h_note = (
            f" Head-to-head: {h2h.get('home_wins', 0)}-{h2h.get('away_wins', 0)}"
            + (f"-{h2h['draws']}" if h2h.get("draws") else "")
            + f" over {h2h['games']} meetings."
        )

    return {
        "summary": f"{summary}. {lean}{h2h_note}".strip(),
        "home": _format_team_side(home_team.get("name") or home, home_team),
        "away": _format_team_side(away_team.get("name") or away, away_team),
        "h2h": h2h if h2h.get("games") else None,
        "pick_support": support,
        "selection": selection,
        "bet_type": bet_type,
        "available": True,
    }


def _build_pick_thesis(
    market: dict[str, Any],
    stats: dict[str, Any],
    news_articles: list[dict[str, Any]],
) -> str:
    """Full template thesis when OpenAI is unavailable — still explains the pick."""
    selection = market.get("selection") or "this side"
    bet_type = str(market.get("bet_type") or "moneyline")
    event = market.get("event") or "this matchup"
    sport = market.get("sport") or "sports"

    parts: list[str] = []
    rejected = market.get("rejected_side")
    if rejected:
        parts.append(
            f"Atlas ranks {selection} ({bet_type}) on {event} ({sport}) over {rejected} "
            "after comparing market edge, form/H2H, and opportunity — one best decision for this market."
        )
    else:
        parts.append(
            f"Atlas ranks {selection} ({bet_type}) on {event} ({sport}) as the best available "
            "side for this market using price, form, and news context."
        )

    odds = market.get("odds_american")
    ev = market.get("expected_value")
    edge = market.get("edge_pct")
    market_bits: list[str] = []
    if odds is not None:
        try:
            market_bits.append(f"FanDuel {int(odds):+d}")
        except (TypeError, ValueError):
            market_bits.append(f"odds {odds}")
    if ev is not None:
        try:
            market_bits.append(f"EV {float(ev):+.1f}%")
        except (TypeError, ValueError):
            pass
    if edge is not None:
        try:
            market_bits.append(f"edge {float(edge):+.1f}%")
        except (TypeError, ValueError):
            pass
    if market_bits:
        parts.append("Market: " + ", ".join(market_bits) + ".")

    opp = market.get("opportunity")
    conf = market.get("confidence")
    risk = market.get("risk")
    score_bits: list[str] = []
    if opp is not None:
        score_bits.append(f"opportunity {float(opp):.0f}")
    if conf is not None:
        score_bits.append(f"confidence {float(conf):.0f}")
    if risk is not None:
        score_bits.append(f"risk {float(risk):.0f}")
    if score_bits:
        parts.append("Atlas scores — " + ", ".join(score_bits) + ".")

    if market.get("sharp_indicator"):
        parts.append(f"Sharp read: {market['sharp_indicator']}.")

    if stats.get("available") and stats.get("summary"):
        parts.append(f"Form/H2H: {stats['summary']}")
    elif stats.get("summary"):
        parts.append(str(stats["summary"]))

    if market.get("bull_case"):
        parts.append(f"Bull case: {str(market['bull_case'])[:220]}")

    team_news = [n for n in news_articles if n.get("context_tier") != "sport"]
    sport_news = [n for n in news_articles if n.get("context_tier") == "sport"]
    if team_news:
        titles = "; ".join(str(n.get("title")) for n in team_news[:2] if n.get("title"))
        if titles:
            parts.append(f"Related headlines: {titles}.")
    elif sport_news:
        titles = "; ".join(str(n.get("title")) for n in sport_news[:2] if n.get("title"))
        if titles:
            parts.append(
                f"No team-specific headlines matched closely; sport context includes: {titles}."
            )
    else:
        parts.append(
            "No strong matching headlines right now — this ranking is driven by price, edge, and form."
        )

    if market.get("suggested_action"):
        parts.append(str(market["suggested_action"]))

    return " ".join(parts)


class SportsInsightService:
    async def _fetch_news(self) -> list[dict[str, Any]]:
        try:
            return await fetch_sports_news(limit_per_feed=14)
        except Exception as exc:
            logger.warning("Sports insight news fetch failed: %s", exc)
            return []

    async def _fetch_stats(
        self, signal: dict[str, Any], event: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, float]:
        stats_payload: dict[str, Any] | None = None
        support = 0.0

        # Prefer fresh scores when we have teams + sport key
        if event.get("home_team") and event.get("away_team") and event.get("_sport_key"):
            try:
                stats_index = await build_stats_index([event])
                match_stats = lookup_match_stats(event, stats_index)
                stats_payload = match_stats_payload(match_stats)
                snap = signal.get("scoring_snapshot") or {}
                pick = snap.get("pick") or {}
                support, enriched = compute_pick_support(
                    str(signal.get("bet_type") or pick.get("bet_type") or "moneyline"),
                    str(signal.get("selection") or pick.get("team_or_side") or ""),
                    pick.get("point"),
                    event["home_team"],
                    event["away_team"],
                    match_stats,
                )
                if enriched:
                    stats_payload = {**(stats_payload or {}), **enriched}
            except Exception as exc:
                logger.warning("Sports insight stats fetch failed: %s", exc)

        # Always fall back to scan-cached team stats so every pick has something
        if stats_payload is None:
            cached = (signal.get("scoring_snapshot") or {}).get("team_stats")
            if isinstance(cached, dict) and cached:
                stats_payload = cached
                support = float(
                    (signal.get("scoring_snapshot") or {}).get("stats_support")
                    or cached.get("support_score")
                    or 0
                )

        return stats_payload, support

    async def gather_context(
        self,
        signal: dict[str, Any],
        formatted: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        formatted = formatted or {}
        event = _event_dict_from_signal(signal)
        news_pool, (stats_payload, support) = await asyncio.gather(
            self._fetch_news(),
            self._fetch_stats(signal, event),
        )

        matched = match_news_for_insight(signal, news_pool, limit=8)

        # Merge any scan-attached related news the matcher may have missed
        snap = signal.get("scoring_snapshot") or {}
        cached_news = snap.get("related_news") or formatted.get("related_news") or []
        seen = {str(n.get("url") or n.get("title") or "") for n in matched}
        for item in cached_news:
            key = str(item.get("url") or item.get("title") or "")
            if key and key not in seen:
                matched.append({**item, "context_tier": item.get("context_tier") or "team"})
                seen.add(key)

        news_articles = [
            {
                "title": n.get("title"),
                "url": n.get("url"),
                "source": n.get("source"),
                "summary": (str(n.get("summary") or ""))[:280] or None,
                "published_at": n.get("published_at"),
                "relevance_score": n.get("relevance_score"),
                "context_tier": n.get("context_tier") or "team",
            }
            for n in matched[:8]
        ]

        stats_comparison = _template_stats_comparison(signal, stats_payload, support)
        market = _market_context(signal, formatted)
        thesis = _build_pick_thesis(market, stats_comparison, news_articles)

        return {
            "news_articles": news_articles,
            "stats_comparison": stats_comparison,
            "market": market,
            "pick_thesis": thesis,
            "participants": {
                "home": event.get("home_team"),
                "away": event.get("away_team"),
            },
        }

    async def explain_pick(
        self,
        *,
        signal: dict[str, Any],
        formatted: dict[str, Any],
    ) -> dict[str, Any]:
        context = await self.gather_context(signal, formatted)
        thesis = context["pick_thesis"]

        template = {
            "explanation": thesis,
            "pick_thesis": thesis,
            "why_atlas": thesis,
            "bullets": self._template_bullets(formatted, signal, context),
            "risks": self._template_risks(formatted, signal, context),
            "news_articles": context["news_articles"],
            "stats_comparison": context["stats_comparison"],
            "market": context["market"],
            "source": "template",
            "model": None,
        }

        if not llm_service.is_configured():
            return template

        facts = {
            "market": context["market"],
            "stats_comparison": context["stats_comparison"],
            "news_articles": context["news_articles"],
            "participants": context["participants"],
            "template_thesis": thesis,
            "scan_explanation": formatted.get("explanation") or signal.get("explanation"),
        }

        llm_result = await llm_service.complete_json(
            system=_SPORTS_INSIGHT_SYSTEM,
            user=(
                "Return JSON with keys:\n"
                "why_atlas (4-7 sentences: full formative insight on WHY Atlas chooses this pick — "
                "weave market edge, scores, form/H2H if present, and headlines; be specific),\n"
                "bullets (4-6 short strings citing concrete numbers or headlines from the payload),\n"
                "risks (2-3 strings: what could invalidate the pick),\n"
                "stats_comparison_summary (1-2 sentences comparing participants using available stats).\n\n"
                f"PICK RESEARCH PAYLOAD:\n{facts}"
            ),
            max_tokens=1200,
        )

        if not llm_result:
            return template

        stats_comparison = dict(context["stats_comparison"])
        if llm_result.get("stats_comparison_summary"):
            stats_comparison["summary"] = str(llm_result["stats_comparison_summary"])[:500]

        why = str(llm_result.get("why_atlas") or llm_result.get("explanation") or thesis)[:1600]

        return {
            "explanation": why,
            "pick_thesis": why,
            "why_atlas": why,
            "bullets": [
                str(b)[:240]
                for b in (llm_result.get("bullets") or template["bullets"])[:6]
            ],
            "risks": [
                str(r)[:240]
                for r in (llm_result.get("risks") or template["risks"])[:3]
            ],
            "news_articles": context["news_articles"],
            "stats_comparison": stats_comparison,
            "market": context["market"],
            "source": "openai",
            "model": llm_service.model,
        }

    @staticmethod
    def _template_bullets(
        formatted: dict[str, Any],
        signal: dict[str, Any],
        context: dict[str, Any],
    ) -> list[str]:
        bullets: list[str] = []
        market = context.get("market") or {}
        stats = context.get("stats_comparison") or {}

        if market.get("rejected_side"):
            margin = market.get("decision_margin")
            margin_txt = f" (margin {float(margin):.1f})" if margin is not None else ""
            bullets.insert(
                0,
                f"Chose {market.get('selection')} over {market['rejected_side']}{margin_txt}.",
            )
        if market.get("expected_value") is not None:
            try:
                bullets.append(f"Expected value {float(market['expected_value']):+.1f}%.")
            except (TypeError, ValueError):
                pass
        if market.get("edge_pct") is not None:
            try:
                bullets.append(f"Model edge {float(market['edge_pct']):+.1f}% vs the market.")
            except (TypeError, ValueError):
                pass
        if market.get("odds_american") is not None:
            try:
                bullets.append(f"Price: FanDuel {int(market['odds_american']):+d}.")
            except (TypeError, ValueError):
                pass
        if market.get("opportunity") is not None:
            bullets.append(f"Opportunity score {float(market['opportunity']):.0f}/100.")
        if market.get("confidence") is not None:
            bullets.append(f"Confidence {float(market['confidence']):.0f}/100.")
        if stats.get("available") and stats.get("summary"):
            bullets.append(str(stats["summary"])[:200])
        if market.get("sharp_indicator"):
            bullets.append(f"Sharp indicator: {market['sharp_indicator']}.")
        if market.get("bull_case"):
            bullets.append(str(market["bull_case"])[:180])

        for article in (context.get("news_articles") or [])[:2]:
            title = article.get("title")
            if title:
                tier = "Context" if article.get("context_tier") == "sport" else "News"
                bullets.append(f"{tier}: {title}")

        return bullets[:6] or ["Scan edge and line value drive this ranking."]

    @staticmethod
    def _template_risks(
        formatted: dict[str, Any],
        signal: dict[str, Any],
        context: dict[str, Any],
    ) -> list[str]:
        risks: list[str] = []
        market = context.get("market") or {}
        support = float((context.get("stats_comparison") or {}).get("pick_support") or 0)

        if support <= -12:
            risks.append("Recent form leans against this side — size down if you need form confirmation.")
        if market.get("bear_case"):
            risks.append(str(market["bear_case"])[:200])
        if market.get("invalidation"):
            risks.append(f"Invalidation: {market['invalidation']}")
        warning = signal.get("risk_warning") or formatted.get("risk_warning")
        if warning and len(risks) < 3:
            risks.append(str(warning)[:200])
        if not risks:
            risks.append("All sports picks carry loss risk — size stakes responsibly.")
        return risks[:3]


sports_insight_service = SportsInsightService()
