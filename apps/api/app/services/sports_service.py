"""Sports odds scan, scoring, and persistence."""

from __future__ import annotations

import logging
from typing import Any

from app import config
from app.agents.sports_analyst import analyze_event, setup_to_row
from app.agents.sports_categories import tag_pool_categories
from app.db.supabase_client import SupabaseClient
from app.providers.sports.odds_api import OddsApiError, fetch_all_sports_odds
from app.providers.sports.sports_news import build_news_analysis, fetch_sports_news, match_news_to_signal
from app.providers.sports.team_stats import build_stats_index, lookup_match_stats
from app.services.freshness import filter_upcoming_events, hours_until_event, is_sports_actionable
from app.services.sports_ranking import (
    composite_score,
    dedupe_one_side_per_market,
    is_near_term,
    is_within_horizon,
    market_family_key,
    sort_for_display,
    timing_tier,
)

logger = logging.getLogger(__name__)

MAX_SIGNALS = 120
MIN_OPPORTUNITY = 28.0
MIN_BOARD_PICKS = 8
MIN_PER_SPORT = 1
MAX_PER_SPORT = 10


def _source_note(stats: dict[str, Any]) -> str:
    """Human-readable suffix describing whether odds are live, cached, or stale."""
    if stats.get("stale"):
        age = stats.get("cache_age_minutes")
        age_txt = f" ({int(age)}m old)" if isinstance(age, (int, float)) else ""
        return f" · using last-known odds{age_txt} — all API keys out of credits"
    if stats.get("cached"):
        age = stats.get("cache_age_minutes")
        age_txt = f" ({int(age)}m old)" if isinstance(age, (int, float)) else ""
        return f" · cached odds{age_txt} — no credits spent"
    remaining = stats.get("total_remaining")
    if remaining is None:
        remaining = stats.get("requests_remaining")
    if remaining is not None:
        return f" · live odds · {remaining} API credits left"
    return " · live odds"


def _odds_error_message(exc: OddsApiError | str) -> str:
    msg = str(exc)
    if "INVALID_KEY" in msg:
        return (
            "Odds API key rejected. Copy your key from the-odds-api.com into "
            "ODDS_API_KEY in apps/api/.env, then restart the API."
        )
    if "OUT_OF_USAGE_CREDITS" in msg or "quota" in msg.lower() or "usage" in msg.lower():
        return (
            "Odds API monthly quota exhausted. No live odds until credits reset "
            "or you upgrade at the-odds-api.com."
        )
    return msg


def _select_diverse_setups(setups: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    """Prefer near-term plays; one Atlas decision per event+market; diversify sports."""
    if not setups:
        return []

    near = [r for r in setups if is_near_term(r)]
    later = [r for r in setups if not is_near_term(r) and is_within_horizon(r)]
    pool = near if len(near) >= max(3, limit // 3) else near + later

    by_sport: dict[str, list[dict[str, Any]]] = {}
    for row in pool:
        by_sport.setdefault(str(row.get("sport") or "Sports"), []).append(row)
    for rows in by_sport.values():
        rows.sort(key=composite_score, reverse=True)

    per_sport = min(
        MAX_PER_SPORT,
        max(MIN_PER_SPORT, limit // max(1, len(by_sport))),
    )
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()

    for sport in sorted(by_sport.keys()):
        for row in by_sport[sport][:per_sport]:
            k = market_family_key(row)
            if k not in seen:
                selected.append(row)
                seen.add(k)

    if len(selected) < limit:
        for row in sorted(pool, key=composite_score, reverse=True):
            k = market_family_key(row)
            if k in seen:
                continue
            selected.append(row)
            seen.add(k)
            if len(selected) >= limit:
                break

    return sort_for_display(dedupe_one_side_per_market(selected))[:limit]


class SportsRefreshService:
    def __init__(self, db: SupabaseClient, user_id: str) -> None:
        self.db = db
        self.user_id = user_id

    async def _purge_contradicting_sides(self) -> int:
        """Expire alternate sides still sitting in active picks from older scans."""
        rows = await self.db.select(
            "sports_signals",
            filters={"user_id": f"eq.{self.user_id}", "status": "eq.active"},
            order="opportunity_score.desc",
            limit=300,
        )
        if len(rows) <= 1:
            return 0
        keep_ids = {str(r.get("id")) for r in dedupe_one_side_per_market(rows) if r.get("id")}
        losers = [r for r in rows if str(r.get("id")) not in keep_ids]
        purged = 0
        for row in losers:
            sid = row.get("id")
            if not sid:
                continue
            try:
                await self.db.update(
                    "sports_signals",
                    {"id": f"eq.{sid}", "user_id": f"eq.{self.user_id}"},
                    {"status": "expired"},
                )
                purged += 1
            except Exception as exc:
                logger.warning("Failed to expire contradicting sports pick %s: %s", sid, exc)
        return purged

    async def refresh_sports(
        self,
        *,
        replace: bool = True,
        limit: int = MAX_SIGNALS,
        force_refresh: bool = False,
        cache_only: bool = False,
    ) -> dict[str, Any]:
        from app.config import reload_settings

        reload_settings()
        try:
            events, fetch_stats = await fetch_all_sports_odds(
                force_refresh=force_refresh,
                cache_only=cache_only,
            )
            raw_count = len(events)
            events = filter_upcoming_events(events)
            events = [
                e
                for e in events
                if is_within_horizon(
                    {
                        "event_start": e.get("commence_time"),
                        "bet_type": "futures" if e.get("_is_outright") else "moneyline",
                        "scoring_snapshot": {"is_futures": bool(e.get("_is_outright"))},
                    }
                )
            ]
            events.sort(key=lambda e: hours_until_event(e.get("commence_time")) or 9999)
            fetch_stats["events_before_filter"] = raw_count
            fetch_stats["events_upcoming"] = len(events)
            fetch_stats["events_dropped_past"] = raw_count - len(events)
        except OddsApiError as exc:
            return {
                "signals_created": 0,
                "events_scanned": 0,
                "stats": {"configured": False, "error": str(exc)},
                "top_opportunity": None,
                "message": _odds_error_message(exc),
            }
        except OSError as exc:
            logger.warning("Sports scan network error: %s", exc)
            return {
                "signals_created": 0,
                "events_scanned": 0,
                "stats": {"configured": True, "error": str(exc)},
                "top_opportunity": None,
                "message": (
                    "Network/DNS error reaching external services. "
                    "Check the PC running the API has internet, then tap Restart and try again."
                ),
            }

        if not fetch_stats.get("configured"):
            return {
                "signals_created": 0,
                "events_scanned": 0,
                "stats": fetch_stats,
                "top_opportunity": None,
                "message": fetch_stats.get("error") or "ODDS_API_KEY is not configured",
            }

        if cache_only and fetch_stats.get("error") and not events:
            return {
                "signals_created": 0,
                "events_scanned": 0,
                "stats": fetch_stats,
                "credits_used": 0,
                "cache_used": False,
                "top_opportunity": None,
                "message": fetch_stats.get("error")
                or "No cached odds — tap Fetch live odds first (Rescore uses 0 credits after that).",
            }

        # All keys exhausted AND no cached odds to fall back on.
        if fetch_stats.get("quota_exhausted") and not events:
            key_count = fetch_stats.get("key_count") or len(config.settings.odds_api_keys)
            plural = "keys are" if key_count and key_count > 1 else "key is"
            return {
                "signals_created": 0,
                "events_scanned": 0,
                "stats": fetch_stats,
                "top_opportunity": None,
                "message": (
                    f"All {key_count} Odds API {plural} out of monthly credits, and no cached "
                    "odds are available yet. Add another free key at the-odds-api.com to "
                    "ODDS_API_KEY (comma-separated) for automatic failover, or wait for the reset."
                ),
            }

        if fetch_stats.get("credits_blocked") and not events:
            return {
                "signals_created": 0,
                "events_scanned": 0,
                "stats": fetch_stats,
                "top_opportunity": None,
                "message": fetch_stats.get("error")
                or fetch_stats.get("message")
                or "Odds credits too low for a live scan — use Rescore on cached lines.",
            }

        setups: list[dict[str, Any]] = []
        try:
            stats_index = await build_stats_index(events)
        except Exception as exc:
            logger.warning("Team stats skipped (non-fatal): %s", exc)
            stats_index = {}

        from app.services.calibration_service import CalibrationService

        calibration = await CalibrationService(self.db, self.user_id).get_adjustments()
        min_opp = float(calibration.get("sports_min_opportunity", MIN_OPPORTUNITY))

        def _score_events(cal: dict[str, Any], floor: float) -> list[dict[str, Any]]:
            scored: list[dict[str, Any]] = []
            for event in events:
                try:
                    match_stats = lookup_match_stats(event, stats_index)
                    for setup in analyze_event(event, match_stats=match_stats, calibration=cal):
                        if setup.opportunity_score >= floor:
                            scored.append(setup_to_row(self.user_id, setup))
                except Exception as exc:
                    logger.info("Sports analyze skip event: %s", exc)
            return scored

        setups = _score_events(calibration, min_opp)

        # If strict filters wipe today's MLB/WNBA slate, reopen with slate mode
        # so OpenAI can rank real FanDuel/DraftKings lines instead of returning empty.
        openai_meta: dict[str, Any] = {"openai_slate": False}
        if len(setups) < MIN_BOARD_PICKS and events:
            slate_cal = dict(calibration)
            slate_cal["slate_mode"] = True
            slate_cal["sports_min_edge_pct"] = min(0.35, float(slate_cal.get("sports_min_edge_pct") or 0.6))
            slate_cal["sports_min_opportunity"] = min(20.0, float(slate_cal.get("sports_min_opportunity") or 28.0))
            soft = _score_events(slate_cal, float(slate_cal["sports_min_opportunity"]))
            if len(soft) > len(setups):
                setups = soft
                fetch_stats["slate_mode"] = True

        setups.sort(key=composite_score, reverse=True)

        if setups and config.settings.openai_api_key:
            try:
                from app.services.sports_slate_ai import rank_slate_with_openai

                setups, openai_meta = await rank_slate_with_openai(setups, limit=min(limit, 24))
                fetch_stats.update(openai_meta)
            except Exception as exc:
                logger.warning("OpenAI slate ranking skipped: %s", exc)

        setups = _select_diverse_setups(setups, limit=limit)

        tag_pool_categories(setups)

        news_pool: list[dict[str, Any]] = []
        try:
            news_pool = await fetch_sports_news(limit_per_feed=10)
        except Exception as exc:
            logger.warning("Sports news fetch skipped: %s", exc)

        for row in setups:
            matched = match_news_to_signal(row, news_pool)
            analysis = build_news_analysis(row, matched)
            row["explanation"] = analysis["explanation"]
            row["bull_case"] = analysis["bull_case"]
            row["bear_case"] = analysis["bear_case"]
            snap = row.setdefault("scoring_snapshot", {})
            snap["related_news"] = [
                {
                    "title": n.get("title"),
                    "url": n.get("url"),
                    "source": n.get("source"),
                    "summary": n.get("summary"),
                    "published_at": n.get("published_at"),
                    "relevance_score": n.get("relevance_score"),
                    "matched_tokens": n.get("matched_tokens"),
                }
                for n in matched
            ]
            snap["analysis_summary"] = analysis["analysis_summary"]
            snap["news_count"] = len(matched)
            snap["news_verified"] = bool(analysis.get("news_verified"))
            snap["timing_tier"] = timing_tier(row)

        setups = sort_for_display([row for row in setups if is_sports_actionable(row)])

        sports_in_results = sorted({str(r.get("sport")) for r in setups})

        if replace and not setups:
            purged = await self._purge_contradicting_sides()
            existing = await self.db.select(
                "sports_signals",
                filters={"user_id": f"eq.{self.user_id}", "status": "eq.active"},
                limit=1,
            )
            if purged:
                kept_msg = (
                    f"No new +EV edges this scan — removed {purged} contradicting alternate-side "
                    "pick(s) so Atlas keeps one decision per market. "
                    "Use Fetch live odds when you want a fresh slate."
                )
            else:
                kept_msg = (
                    "No new +EV edges in this scan — your current picks are unchanged. "
                    "Use Fetch live odds only when you want fresh lines from the API."
                )
            return {
                "signals_created": 0,
                "signals_kept": len(existing) > 0,
                "contradictions_purged": purged,
                "events_scanned": len(events),
                "stats": fetch_stats,
                "top_opportunity": None,
                "parlays_invalidated": False,
                "calibration": calibration,
                "message": kept_msg if existing or purged else self._result_message(
                    setups, fetch_stats, parlays_invalidated=False, calibration=calibration
                ),
            }

        if replace and setups:
            # Keep OpenAI web-desk picks — Odds scans only replace Odds-derived rows.
            active = await self.db.select(
                "sports_signals",
                filters={"user_id": f"eq.{self.user_id}", "status": "eq.active"},
                limit=300,
            )
            for row in active:
                snap = row.get("scoring_snapshot") or {}
                lm = row.get("line_movement") or {}
                source = str(snap.get("source") or lm.get("source") or "")
                if (
                    source in {"openai_web", "user_entry"}
                    or bool(snap.get("openai_web"))
                    or bool(lm.get("openai_web"))
                    or bool(snap.get("user_entry"))
                    or str(row.get("pick_source") or "") in {"openai_web", "user_entry"}
                    or str(snap.get("pick_origin") or "") == "user"
                ):
                    continue
                sid = row.get("id")
                if not sid:
                    continue
                try:
                    await self.db.delete("sports_signals", {"id": f"eq.{sid}"})
                except Exception as exc:
                    logger.warning("Failed to clear odds sports pick %s: %s", sid, exc)
            # Sports IDs change on rescan — invalidate parlays that reference old legs.
            try:
                await self.db.update(
                    "parlays",
                    {
                        "user_id": f"eq.{self.user_id}",
                        "status": "eq.active",
                    },
                    {"status": "expired"},
                )
            except Exception as exc:
                logger.warning("Expire parlays after sports rescan: %s", exc)

        saved = await self.db.insert("sports_signals", setups) if setups else []

        if saved:
            from app.services.alert_service import AlertService
            from app.services.signal_registry_service import SignalRegistryService

            await SignalRegistryService(self.db, self.user_id).register_batch("sports", saved)
            await AlertService(self.db, self.user_id).notify_high_score_signals(
                "sports",
                saved,
                title_fn=lambda s: f"Sports play · {s.get('sport')} ({float(s.get('opportunity_score') or 0):.0f}/100)",
                message_fn=lambda s: str(s.get("recommendation") or s.get("selection") or "New sports signal"),
            )

            if config.settings.is_intelligence_enabled():
                try:
                    from app.sports_intelligence.service import SportsIntelligenceService

                    await SportsIntelligenceService(self.db, self.user_id).refresh_active_signals(
                        saved,
                        limit=min(8, len(saved)),
                    )
                except Exception as exc:
                    logger.warning("Post-scan intelligence refresh skipped: %s", exc)

        return {
            "signals_created": len(saved),
            "events_scanned": len(events),
            "stats": fetch_stats,
            "sports_in_results": sports_in_results,
            "leagues_with_near_term_games": fetch_stats.get("leagues_with_near_term_games") or [],
            "top_opportunity": float(setups[0]["opportunity_score"]) if setups else None,
            "credits_used": int(fetch_stats.get("credits_used") or 0),
            "cache_used": bool(fetch_stats.get("cached")),
            "parlays_invalidated": replace,
            "calibration": calibration,
            "message": self._result_message(setups, fetch_stats, parlays_invalidated=replace, calibration=calibration),
        }

    @staticmethod
    def _result_message(
        setups: list[dict[str, Any]],
        stats: dict[str, Any],
        *,
        parlays_invalidated: bool = False,
        calibration: dict[str, Any] | None = None,
    ) -> str | None:
        source = _source_note(stats)
        credits = int(stats.get("credits_used") or 0)
        credit_note = (
            " · 0 API credits (cached odds)"
            if stats.get("cached")
            else f" · ~{credits} API credits used"
        )
        scanned = int(stats.get("sports_scanned") or 0)
        near_leagues = stats.get("leagues_with_near_term_games") or []
        near_label = ", ".join(near_leagues[:6]) if near_leagues else "none in the next 7 days"
        dropped = int(stats.get("events_dropped_far_out") or 0)
        skipped = stats.get("skipped_off_season") or []

        scan_note = ""
        if stats.get("credit_guard") or stats.get("credits_blocked"):
            scan_note = (
                stats.get("message")
                or "Odds credits low — rescored from cache (0 Odds credits). Atlas Insight still ranks FanDuel/DraftKings picks."
            )
        elif stats.get("cached"):
            scan_note = f"Rescored from cache · {len(near_leagues)} leagues with games this week ({near_label})"
            if stats.get("cache_needs_live_refresh"):
                scan_note += (
                    " · cache is missing in-season leagues (e.g. MLB/WNBA) — "
                    "use Fetch live odds (~4 credits), not Rescore"
                )
            if stats.get("openai_slate"):
                scan_note += f" · Atlas Insight ranked {stats.get('openai_ranked', '?')} picks"
        else:
            scanned = int(stats.get("sports_scanned") or 0)
            scan_note = (
                f"Live US-book scan: {scanned} leagues{credit_note} · "
                f"{len(near_leagues)} had games in the next 7 days ({near_label})"
            )
            if stats.get("cache_merged"):
                scan_note += " · merged into existing cache"
            if stats.get("openai_slate"):
                scan_note += f" · Atlas Insight ranked {stats.get('openai_ranked', '?')} picks"
            if stats.get("slate_mode"):
                scan_note += " · slate mode (board fill)"
            if dropped > 0:
                scan_note += f" · ignored {dropped} far-future lines"
            if skipped:
                scan_note += f" · skipped off-season: {', '.join(skipped[:3])}"

        if not setups:
            base = (
                "No +EV plays in the next 48 hours. "
                f"{scan_note}. Try Fetch live odds for a fresh slate. "
            )
            if int(stats.get("events_upcoming") or 0) == 0 and not near_leagues:
                base += "No upcoming games in the odds feed for scanned leagues. "
            else:
                base += "Edges may be below threshold — widen filters or rescan later. "
            return f"{base}{source}"
        if stats.get("cached"):
            base = f"{scan_note} · saved {len(setups)} plays"
        else:
            base = f"{scan_note} · saved {len(setups)} plays"
        if calibration and calibration.get("active") and calibration.get("learning_notes"):
            base += f" · Atlas learning: {calibration['learning_notes'][0]}"
        if parlays_invalidated and setups:
            parlay_note = " · Rebuild parlays to refresh tickets"
            return f"{base}{parlay_note}" if base else "Rebuild parlays to refresh tickets"
        return base
