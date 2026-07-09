"""On-demand sports insight: fresh news, historical stats, and AI synthesis."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from app.agents.sports_stats import compute_pick_support
from app.providers.sports.sports_news import fetch_sports_news, match_news_to_signal
from app.providers.sports.team_stats import (
    build_stats_index,
    lookup_match_stats,
    match_stats_payload,
)
from app.services.llm_service import llm_service

logger = logging.getLogger(__name__)

_SPORTS_INSIGHT_SYSTEM = """You are Atlas analyzing a sports bet with fresh headlines and historical team stats.
Use ONLY facts from the payload — news titles/summaries, win-loss records, averages, H2H. Never invent injuries, lineups, or scores.
Compare both participants honestly. Note when news or form supports vs contradicts the pick.
Plain English, practical tone. No repetitive disclaimers."""


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
        "recent_results": team.get("recent_results"),
        "games_sampled": team.get("games_sampled"),
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
                f"Limited recent game data for {home or 'home'} vs {away or 'away'}. "
                "Rely on the scan edge and line movement until more results are available."
            ),
            "home": _format_team_side("home", None),
            "away": _format_team_side("away", None),
            "h2h": None,
            "pick_support": support,
            "selection": selection,
            "bet_type": bet_type,
        }

    home_team = stats_payload.get("home") or {}
    away_team = stats_payload.get("away") or {}
    h2h = stats_payload.get("h2h") or {}
    summary = str(stats_payload.get("summary") or stats_payload.get("form_note") or "")

    if support >= 12:
        lean = f"Recent form leans toward {selection}."
    elif support <= -12:
        lean = f"Recent form leans against {selection}."
    else:
        lean = "Recent form is mixed relative to this pick."

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
    }


class SportsInsightService:
    async def _fetch_news(self) -> list[dict[str, Any]]:
        try:
            return await fetch_sports_news(limit_per_feed=10)
        except Exception as exc:
            logger.warning("Sports insight news fetch failed: %s", exc)
            return []

    async def _fetch_stats(
        self, signal: dict[str, Any], event: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, float]:
        stats_payload: dict[str, Any] | None = None
        support = 0.0
        if not (event.get("home_team") and event.get("away_team") and event.get("_sport_key")):
            return stats_payload, support
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
        return stats_payload, support

    async def gather_context(self, signal: dict[str, Any]) -> dict[str, Any]:
        event = _event_dict_from_signal(signal)
        news_pool, (stats_payload, support) = await asyncio.gather(
            self._fetch_news(),
            self._fetch_stats(signal, event),
        )

        matched = match_news_to_signal(signal, news_pool, limit=6)
        news_articles = [
            {
                "title": n.get("title"),
                "url": n.get("url"),
                "source": n.get("source"),
                "summary": (str(n.get("summary") or ""))[:280] or None,
                "published_at": n.get("published_at"),
                "relevance_score": n.get("relevance_score"),
            }
            for n in matched
        ]

        if stats_payload is None:
            cached = (signal.get("scoring_snapshot") or {}).get("team_stats")
            if isinstance(cached, dict) and cached:
                stats_payload = cached
                support = float((signal.get("scoring_snapshot") or {}).get("stats_support") or 0)

        stats_comparison = _template_stats_comparison(signal, stats_payload, support)
        return {
            "news_articles": news_articles,
            "stats_comparison": stats_comparison,
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
        context = await self.gather_context(signal)
        base_explanation = str(formatted.get("explanation") or signal.get("explanation") or "").strip()

        template = {
            "explanation": base_explanation or "No template explanation available for this pick.",
            "bullets": self._template_bullets(formatted, signal, context),
            "risks": self._template_risks(formatted, signal, context),
            "news_articles": context["news_articles"],
            "stats_comparison": context["stats_comparison"],
            "source": "template",
            "model": None,
        }

        if not llm_service.is_configured():
            return template

        snap = signal.get("scoring_snapshot") or {}
        pick = snap.get("pick") or {}
        facts = {
            "sport": signal.get("sport"),
            "event": signal.get("event_name"),
            "selection": signal.get("selection"),
            "bet_type": signal.get("bet_type"),
            "recommendation": formatted.get("recommendation"),
            "scores": formatted.get("scores"),
            "bull_case": signal.get("bull_case"),
            "bear_case": signal.get("bear_case"),
            "invalidation": signal.get("invalidation"),
            "template_explanation": base_explanation,
            "news_articles": context["news_articles"],
            "stats_comparison": context["stats_comparison"],
            "odds_american": signal.get("odds_american"),
            "expected_value": signal.get("expected_value"),
            "point": pick.get("point"),
        }

        llm_result = await llm_service.complete_json(
            system=_SPORTS_INSIGHT_SYSTEM,
            user=(
                "Return JSON with keys: "
                "explanation (2-4 sentences synthesizing news + stats for this pick), "
                "bullets (3-5 short strings citing specific stats or headlines), "
                "risks (1-3 strings), "
                "stats_comparison_summary (1-2 sentences comparing participants).\n\n"
                f"PICK AND RESEARCH:\n{facts}"
            ),
            max_tokens=950,
        )

        if not llm_result:
            return template

        stats_comparison = dict(context["stats_comparison"])
        if llm_result.get("stats_comparison_summary"):
            stats_comparison["summary"] = str(llm_result["stats_comparison_summary"])[:500]

        return {
            "explanation": str(llm_result.get("explanation") or template["explanation"])[:1000],
            "bullets": [str(b)[:220] for b in (llm_result.get("bullets") or template["bullets"])[:5]],
            "risks": [str(r)[:220] for r in (llm_result.get("risks") or template["risks"])[:3]],
            "news_articles": context["news_articles"],
            "stats_comparison": stats_comparison,
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
        stats = context.get("stats_comparison") or {}
        if stats.get("summary"):
            bullets.append(str(stats["summary"])[:200])

        for article in (context.get("news_articles") or [])[:2]:
            title = article.get("title")
            if title:
                bullets.append(f"News: {title}")

        scores = formatted.get("scores") or {}
        if scores.get("opportunity") is not None:
            bullets.append(f"Opportunity score {float(scores['opportunity']):.0f}/100.")
        if signal.get("bull_case"):
            bullets.append(str(signal["bull_case"])[:180])
        return bullets[:5] or ["Scan edge and line value drive this ranking."]

    @staticmethod
    def _template_risks(
        formatted: dict[str, Any],
        signal: dict[str, Any],
        context: dict[str, Any],
    ) -> list[str]:
        risks: list[str] = []
        support = float((context.get("stats_comparison") or {}).get("pick_support") or 0)
        if support <= -12:
            risks.append("Recent results lean against this side — form may override the line edge.")
        if not context.get("news_articles"):
            risks.append("No closely matched headlines found — verify injury and lineup news before betting.")

        warning = signal.get("risk_warning") or formatted.get("risk_warning")
        if warning:
            risks.append(str(warning)[:200])
        if signal.get("bear_case"):
            risks.append(str(signal["bear_case"])[:200])
        if not risks:
            risks.append("All sports picks carry loss risk — size stakes responsibly.")
        return risks[:3]


sports_insight_service = SportsInsightService()
