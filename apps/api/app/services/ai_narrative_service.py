"""Atlas AI narratives — briefing, coach insight, and signal explanations."""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from typing import Any

from app.services.llm_service import llm_service

logger = logging.getLogger(__name__)

_BRIEFING_CACHE: dict[str, tuple[str, dict[str, Any]]] = {}
_COACH_CACHE: dict[str, tuple[str, dict[str, Any]]] = {}

_BRIEFING_SYSTEM = """You are Atlas, a personal decision-intelligence coach for retail traders and bettors.
Write concise, actionable briefings. Never invent prices, odds, Greeks, or scores — only use facts from the user payload.
Tone: direct, encouraging, risk-aware. No financial advice disclaimers every sentence — one short reminder is enough."""

_EXPLAIN_SYSTEM = """You are Atlas explaining a single ranked pick to a retail user.
Use only numbers and facts from the payload. Do not invent market data.
Be practical: what matters, what could go wrong, what to watch. Plain English."""

_COACH_SYSTEM = """You are Atlas coaching a user on their logged pick performance.
Interpret calibration data honestly. Suggest one concrete habit to improve logging or discipline.
Never invent win rates — use only provided stats."""


def _today_key() -> str:
    return date.today().isoformat()


def _pick_titles(items: list[dict[str, Any]], *, limit: int = 3) -> list[str]:
    titles: list[str] = []
    for item in items[:limit]:
        title = str(item.get("title") or "").strip()
        if title:
            titles.append(title)
    return titles


def _template_briefing(ctx: dict[str, Any]) -> dict[str, Any]:
    top = ctx.get("top_opportunities") or []
    sports = ctx.get("sports_opportunities") or []
    stocks = ctx.get("stock_opportunities") or []
    news = ctx.get("breaking_news") or []
    perf = ctx.get("performance_summary") or {}
    needs = (ctx.get("needs_refresh") or {}) if isinstance(ctx.get("needs_refresh"), dict) else {}

    highlights: list[str] = []
    if top:
        highlights.append(f"Top options pick: {top[0].get('title', '—')}")
    if sports:
        highlights.append(f"Best sports edge: {sports[0].get('title', '—')}")
    if stocks:
        highlights.append(f"Leading stock setup: {stocks[0].get('title', '—')}")
    if news:
        headline = news[0].get("headline") or news[0].get("title")
        if headline:
            highlights.append(f"Breaking: {headline}")

    watch: list[str] = []
    if needs.get("sports"):
        watch.append("Run a sports scan — no live odds in cache yet.")
    if needs.get("stocks"):
        watch.append("Scan stock swings to refresh technical setups.")
    if needs.get("options"):
        watch.append("Run a deep options scan for new ranked contracts.")

    learning = ""
    if perf.get("learning_active"):
        notes = perf.get("learning_notes") or []
        learning = notes[0] if notes else "Atlas is adjusting thresholds from your logged results."
    elif (perf.get("total_logged") or 0) > 0:
        learning = "Keep logging Win/Loss on settled picks — Atlas learns after 8+ outcomes."

    total_signals = len(top) + len(ctx.get("budget_opportunities") or []) + len(stocks) + len(sports)
    headline = "Your Atlas snapshot" if total_signals else "Ready when you scan"

    summary_parts: list[str] = []
    if total_signals:
        summary_parts.append(f"{total_signals} active signals across your modules.")
    else:
        summary_parts.append("No live signals yet — use the scanner bar to populate the dashboard.")
    if perf.get("win_rate_30d") is not None:
        summary_parts.append(f"30-day win rate: {perf['win_rate_30d']}% on {perf.get('total_logged', 0)} logged picks.")

    return {
        "headline": headline,
        "summary": " ".join(summary_parts),
        "highlights": highlights[:4],
        "watch_items": watch[:3],
        "learning_insight": learning or None,
        "generated_at": datetime.now(UTC).isoformat(),
        "source": "template",
        "model": None,
    }


class AiNarrativeService:
    async def daily_briefing(
        self,
        *,
        user_id: str,
        ctx: dict[str, Any],
        refresh: bool = False,
        use_llm: bool = True,
    ) -> dict[str, Any]:
        cache_key = f"{user_id}:{_today_key()}"
        if not refresh and cache_key in _BRIEFING_CACHE:
            return dict(_BRIEFING_CACHE[cache_key][1])

        base = _template_briefing(ctx)
        if not use_llm or not llm_service.is_configured():
            _BRIEFING_CACHE[cache_key] = (_today_key(), base)
            return dict(base)

        payload = {
            "top_options": _pick_titles(ctx.get("top_opportunities") or []),
            "budget_options": _pick_titles(ctx.get("budget_opportunities") or [], limit=2),
            "stocks": _pick_titles(ctx.get("stock_opportunities") or []),
            "sports": _pick_titles(ctx.get("sports_opportunities") or []),
            "news_headlines": [
                str(n.get("headline") or n.get("title") or "")[:120]
                for n in (ctx.get("breaking_news") or [])[:3]
                if n.get("headline") or n.get("title")
            ],
            "performance": ctx.get("performance_summary") or {},
            "needs_refresh": ctx.get("needs_refresh") or {},
            "parlay": (ctx.get("best_parlay") or {}).get("title") if ctx.get("best_parlay") else None,
            "market_intelligence": ctx.get("market_intelligence") or {},
        }

        llm_result = await llm_service.complete_json(
            system=_BRIEFING_SYSTEM,
            user=(
                "Create a daily Atlas briefing JSON with keys: "
                "headline (string), summary (2-3 sentences), highlights (array of 2-4 short strings), "
                "watch_items (array of 0-3 actionable strings), learning_insight (string or null).\n\n"
                f"DATA:\n{payload}"
            ),
            max_tokens=700,
        )

        if llm_result:
            briefing = {
                "headline": str(llm_result.get("headline") or base["headline"])[:120],
                "summary": str(llm_result.get("summary") or base["summary"])[:600],
                "highlights": [
                    str(h)[:160] for h in (llm_result.get("highlights") or base["highlights"])[:4]
                ],
                "watch_items": [
                    str(w)[:160] for w in (llm_result.get("watch_items") or base["watch_items"])[:3]
                ],
                "learning_insight": llm_result.get("learning_insight") or base.get("learning_insight"),
                "generated_at": datetime.now(UTC).isoformat(),
                "source": "openai",
                "model": llm_service.model,
            }
        else:
            briefing = base

        _BRIEFING_CACHE[cache_key] = (_today_key(), briefing)
        return dict(briefing)

    async def coach_insight(self, *, user_id: str, summary: dict[str, Any], refresh: bool = False) -> dict[str, Any]:
        cache_key = f"{user_id}:{_today_key()}"
        if not refresh and cache_key in _COACH_CACHE:
            return dict(_COACH_CACHE[cache_key][1])

        calibration = summary.get("calibration") or {}
        template = {
            "narrative": self._template_coach(summary),
            "focus_areas": self._coach_focus_areas(summary),
            "generated_at": datetime.now(UTC).isoformat(),
            "source": "template",
            "model": None,
        }

        if not llm_service.is_configured():
            _COACH_CACHE[cache_key] = (_today_key(), template)
            return dict(template)

        stats = {
            "win_rate": summary.get("win_rate"),
            "avg_return_pct": summary.get("avg_return_pct"),
            "total_signals": summary.get("total_signals"),
            "wins": summary.get("wins"),
            "losses": summary.get("losses"),
            "by_module": summary.get("by_module"),
            "confidence_accuracy": summary.get("confidence_accuracy"),
            "learning_notes": summary.get("learning_notes") or calibration.get("learning_notes"),
            "calibration_active": calibration.get("active"),
            "sample_count": calibration.get("sample_count"),
        }

        llm_result = await llm_service.complete_json(
            system=_COACH_SYSTEM,
            user=(
                "Return JSON with keys: narrative (2-4 sentences), focus_areas (array of 2-3 short strings).\n\n"
                f"STATS:\n{stats}"
            ),
            max_tokens=650,
        )

        if llm_result:
            result = {
                "narrative": str(llm_result.get("narrative") or template["narrative"])[:800],
                "focus_areas": [str(f)[:120] for f in (llm_result.get("focus_areas") or [])[:3]],
                "generated_at": datetime.now(UTC).isoformat(),
                "source": "openai",
                "model": llm_service.model,
            }
        else:
            result = template

        _COACH_CACHE[cache_key] = (_today_key(), result)
        return dict(result)

    async def explain_signal(self, *, module: str, signal: dict[str, Any], formatted: dict[str, Any]) -> dict[str, Any]:
        base_explanation = str(formatted.get("explanation") or signal.get("explanation") or "").strip()
        template = {
            "explanation": base_explanation or "No template explanation available for this pick.",
            "bullets": self._explain_bullets(formatted, signal),
            "risks": self._explain_risks(formatted, signal),
            "source": "template",
            "model": None,
        }

        if not llm_service.is_configured():
            return template

        facts = {
            "module": module,
            "title": formatted.get("title"),
            "recommendation": formatted.get("recommendation"),
            "scores": formatted.get("scores"),
            "context": formatted.get("context"),
            "bull_case": signal.get("bull_case") or formatted.get("bull_case"),
            "bear_case": signal.get("bear_case") or formatted.get("bear_case"),
            "invalidation": signal.get("invalidation") or formatted.get("invalidation"),
            "suggested_action": signal.get("suggested_action") or formatted.get("suggested_action"),
            "risk_warning": signal.get("risk_warning") or formatted.get("risk_warning"),
            "template_explanation": base_explanation,
        }

        llm_result = await llm_service.complete_json(
            system=_EXPLAIN_SYSTEM,
            user=(
                "Return JSON: explanation (2-3 sentences), bullets (3-5 strings), risks (1-3 strings).\n\n"
                f"PICK:\n{facts}"
            ),
            max_tokens=750,
        )

        if not llm_result:
            return template

        return {
            "explanation": str(llm_result.get("explanation") or template["explanation"])[:900],
            "bullets": [str(b)[:200] for b in (llm_result.get("bullets") or template["bullets"])[:5]],
            "risks": [str(r)[:200] for r in (llm_result.get("risks") or template["risks"])[:3]],
            "source": "openai",
            "model": llm_service.model,
        }

    @staticmethod
    def _template_coach(summary: dict[str, Any]) -> str:
        total = summary.get("total_signals") or 0
        if total < 3:
            return (
                "Log a few more settled picks with Win or Loss so Atlas can spot where confidence "
                "matches reality. Sports picks can auto-grade when games finish."
            )
        win_rate = summary.get("win_rate")
        parts = [f"You've logged {total} outcomes in the last 30 days."]
        if win_rate is not None:
            parts.append(f"Win rate is {win_rate}%.")
        notes = summary.get("learning_notes") or []
        if notes:
            parts.append(notes[0])
        else:
            parts.append("Keep grading picks consistently — calibration kicks in after 8 closed results.")
        return " ".join(parts)

    @staticmethod
    def _coach_focus_areas(summary: dict[str, Any]) -> list[str]:
        areas: list[str] = []
        by_mod = summary.get("by_module") or {}
        for mod, data in by_mod.items():
            if isinstance(data, dict) and (data.get("losses") or 0) > (data.get("wins") or 0):
                areas.append(f"Review {mod} picks — losses outnumber wins recently.")
        conf = summary.get("confidence_accuracy") or {}
        for label, bucket in conf.items():
            if isinstance(bucket, dict) and bucket.get("count", 0) >= 3:
                wr = bucket.get("win_rate", 100)
                if wr < 45:
                    areas.append(f"Confidence {label} bucket underperforming — Atlas will dampen similar scores.")
        if not areas:
            areas.append("Log outcomes within 24h of settlement for sharper learning.")
        return areas[:3]

    @staticmethod
    def _explain_bullets(formatted: dict[str, Any], signal: dict[str, Any]) -> list[str]:
        bullets: list[str] = []
        scores = formatted.get("scores") or {}
        if scores.get("opportunity") is not None:
            bullets.append(f"Opportunity score {float(scores['opportunity']):.0f}/100.")
        if scores.get("confidence") is not None:
            bullets.append(f"Confidence {float(scores['confidence']):.0f}/100.")
        if signal.get("bull_case"):
            bullets.append(str(signal["bull_case"])[:180])
        elif formatted.get("bull_case"):
            bullets.append(str(formatted["bull_case"])[:180])
        if not bullets and formatted.get("recommendation"):
            bullets.append(f"Recommendation: {formatted['recommendation']}.")
        return bullets[:5]

    @staticmethod
    def _explain_risks(formatted: dict[str, Any], signal: dict[str, Any]) -> list[str]:
        risks: list[str] = []
        warning = signal.get("risk_warning") or formatted.get("risk_warning")
        if warning:
            risks.append(str(warning)[:200])
        if signal.get("bear_case"):
            risks.append(str(signal["bear_case"])[:200])
        if signal.get("invalidation"):
            risks.append(f"Invalidation: {signal['invalidation']}")
        if not risks:
            risks.append("All ranked picks carry loss risk — size positions accordingly.")
        return risks[:3]


ai_narrative_service = AiNarrativeService()
