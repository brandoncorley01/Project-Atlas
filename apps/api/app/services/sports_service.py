"""Sports odds scan, scoring, and persistence."""

from __future__ import annotations

import asyncio
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
    is_calendar_today,
    is_near_term,
    is_user_entry_row,
    is_within_horizon,
    market_family_key,
    sort_for_display,
    timing_tier,
)

logger = logging.getLogger(__name__)

MAX_SIGNALS = 160
# ~4 scroll pages of cards on the Sports board (desktop ~10–12/viewport).
TARGET_BOARD_PICKS = 120
MIN_OPPORTUNITY = 24.0
MIN_BOARD_PICKS = 8
MIN_PER_SPORT = 1
MAX_PER_SPORT = 18
# Keep both American and international markets on every board — never flip to one side.
MIN_US_BOARD_SHARE = 0.35
MIN_GLOBAL_BOARD_SHARE = 0.35


def _setup_sport_key(row: dict[str, Any]) -> str:
    snap = row.get("scoring_snapshot") or {}
    lm = row.get("line_movement") or {}
    return str(snap.get("sport_key") or lm.get("sport_key") or "")


def _select_diverse_setups(setups: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    """Fill a large US+global board from cache-scored edges — no extra Odds credits."""
    if not setups:
        return []

    from app.providers.sports.odds_api import is_us_market_sport_key

    # Always keep the full horizon pool. Near-term-only often yields <25 plays and
    # makes the board look empty / single-market after a Rescore.
    pool = [r for r in setups if is_near_term(r) or is_within_horizon(r)]
    if not pool:
        pool = list(setups)

    us_pool = sorted(
        (r for r in pool if is_us_market_sport_key(_setup_sport_key(r))),
        key=composite_score,
        reverse=True,
    )
    global_pool = sorted(
        (r for r in pool if not is_us_market_sport_key(_setup_sport_key(r))),
        key=composite_score,
        reverse=True,
    )

    selected: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _take(row: dict[str, Any]) -> bool:
        k = market_family_key(row)
        if k in seen:
            return False
        selected.append(row)
        seen.add(k)
        return True

    # Round 1: lock Eastern calendar-today first so Repair / Today isn't starved by
    # higher-scoring tomorrow (Next 48h) edges — the board used to look like a 48h slate.
    today_pool = sorted(
        (r for r in pool if is_calendar_today(r)),
        key=composite_score,
        reverse=True,
    )
    if today_pool and limit >= 8:
        today_floor = min(len(today_pool), max(8, int(round(limit * 0.35))))
        today_have = sum(1 for r in selected if is_calendar_today(r))
        for row in today_pool:
            if today_have >= today_floor or len(selected) >= limit:
                break
            if _take(row):
                today_have += 1

    # Round 1b: lock a real combination so the board never flips US-only or global-only.
    if us_pool and global_pool and limit >= 8:
        us_floor = min(len(us_pool), max(1, int(round(limit * MIN_US_BOARD_SHARE))))
        global_floor = min(len(global_pool), max(1, int(round(limit * MIN_GLOBAL_BOARD_SHARE))))
        for row in us_pool:
            if sum(1 for r in selected if is_us_market_sport_key(_setup_sport_key(r))) >= us_floor:
                break
            _take(row)
        for row in global_pool:
            if sum(1 for r in selected if not is_us_market_sport_key(_setup_sport_key(r))) >= global_floor:
                break
            _take(row)

    near_pool = sorted(
        (r for r in pool if is_near_term(r)),
        key=composite_score,
        reverse=True,
    )
    if near_pool and limit >= 8:
        near_floor = min(len(near_pool), max(3, int(round(limit * 0.35))))
        near_have = sum(1 for r in selected if is_near_term(r))
        for row in near_pool:
            if near_have >= near_floor or len(selected) >= limit:
                break
            if _take(row):
                near_have += 1

    by_sport: dict[str, list[dict[str, Any]]] = {}
    for row in pool:
        by_sport.setdefault(str(row.get("sport") or "Sports"), []).append(row)
    for rows in by_sport.values():
        rows.sort(key=composite_score, reverse=True)

    sport_order = sorted(
        by_sport.keys(),
        key=lambda s: composite_score(by_sport[s][0]) if by_sport[s] else 0,
        reverse=True,
    )
    per_sport = min(
        MAX_PER_SPORT,
        max(MIN_PER_SPORT, limit // max(1, min(len(by_sport), 20))),
    )

    # Round 2: diversify remaining slots across leagues.
    for sport in sport_order:
        if len(selected) >= limit:
            break
        for row in by_sport[sport][:per_sport]:
            if len(selected) >= limit:
                break
            _take(row)

    # Round 3: fill by pure Atlas composite score.
    if len(selected) < limit:
        for row in sorted(pool, key=composite_score, reverse=True):
            if len(selected) >= limit:
                break
            _take(row)

    return sort_for_display(dedupe_one_side_per_market(selected))[:limit]


def _openai_quota_skipped(stats: dict[str, Any]) -> bool:
    reason = str(stats.get("reason") or "").lower()
    return any(token in reason for token in ("insufficient_quota", "quota", "429"))


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
        # Never expire user Search bets as "contradicting sides" — they are intentional logs.
        losers = [
            r
            for r in rows
            if str(r.get("id")) not in keep_ids and not is_user_entry_row(r)
        ]
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

    @staticmethod
    def _live_odds_pulled(*, cache_only: bool, fetch_stats: dict[str, Any]) -> bool:
        """True when this refresh actually wrote fresh live odds (not aspirational credits)."""
        if cache_only or fetch_stats.get("cached") or fetch_stats.get("cache_only"):
            return False
        if fetch_stats.get("error") or fetch_stats.get("credits_blocked"):
            return False
        events = int(fetch_stats.get("events") or 0)
        return bool(fetch_stats.get("configured")) and events > 0 and int(
            fetch_stats.get("credits_used") or 0
        ) > 0

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
                "ok": False,
                "message": _odds_error_message(exc),
            }
        except OSError as exc:
            logger.warning("Sports scan network error: %s", exc)
            return {
                "signals_created": 0,
                "events_scanned": 0,
                "stats": {"configured": True, "error": str(exc)},
                "top_opportunity": None,
                "ok": False,
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
                "ok": False,
                "message": fetch_stats.get("error") or "ODDS_API_KEY is not configured",
            }

        # Provider returned a hard error with nothing to score (cold cache, spend lock, etc.)
        if fetch_stats.get("error") and not events:
            return {
                "signals_created": 0,
                "events_scanned": 0,
                "stats": fetch_stats,
                "credits_used": int(fetch_stats.get("credits_used") or 0),
                "cache_used": bool(fetch_stats.get("cached")),
                "top_opportunity": None,
                "ok": False,
                "message": fetch_stats.get("error"),
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
                "ok": False,
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
                "ok": False,
                "message": fetch_stats.get("error")
                or fetch_stats.get("message")
                or "Odds credits too low for a live scan — use Rescore on cached lines.",
            }

        live_odds_pulled = self._live_odds_pulled(cache_only=cache_only, fetch_stats=fetch_stats)
        # Trust provider stats over the request flag — a warm cache serve sets cached=True.
        used_cache = bool(fetch_stats.get("cached") or fetch_stats.get("stale")) or (
            cache_only and not live_odds_pulled
        )

        # Live pull attempted but returned nothing usable — fail closed (do not pretend success).
        if (
            not used_cache
            and not events
            and (force_refresh or fetch_stats.get("error") or int(fetch_stats.get("credits_used") or 0) > 0)
        ):
            return {
                "signals_created": 0,
                "events_scanned": 0,
                "stats": fetch_stats,
                "credits_used": int(fetch_stats.get("credits_used") or 0),
                "cache_used": False,
                "top_opportunity": None,
                "ok": False,
                "message": fetch_stats.get("error")
                or fetch_stats.get("message")
                or (
                    "Live odds pull returned no upcoming games. "
                    "Tap Fetch live odds once, or add another ODDS_API_KEY."
                ),
            }

        setups: list[dict[str, Any]] = []
        # Scores pulls cost Odds credits and can take minutes across 40+ leagues —
        # never do that on cache Scan/Rescore, or under ODDS_SPEND_MODE=cache_only
        # after an intentional cold seed (would burn more credits + risk timeouts).
        stats_index: dict[str, Any] = {}
        spend_locked = not config.settings.odds_live_spending_allowed()
        if not used_cache and not spend_locked:
            try:
                stats_index = await build_stats_index(events)
            except Exception as exc:
                logger.warning("Team stats skipped (non-fatal): %s", exc)
                stats_index = {}
        elif not used_cache and spend_locked:
            fetch_stats["scores_skipped"] = "spend_locked"

        from app.services.calibration_service import CalibrationService

        calibration = await CalibrationService(self.db, self.user_id).get_adjustments()
        min_opp = float(calibration.get("sports_min_opportunity", MIN_OPPORTUNITY))

        def _score_events(cal: dict[str, Any], floor: float) -> list[dict[str, Any]]:
            scored: list[dict[str, Any]] = []
            for event in events:
                try:
                    match_stats = lookup_match_stats(event, stats_index) if stats_index else None
                    for setup in analyze_event(event, match_stats=match_stats, calibration=cal):
                        if setup.opportunity_score >= floor:
                            scored.append(setup_to_row(self.user_id, setup))
                except Exception as exc:
                    logger.info("Sports analyze skip event: %s", exc)
            return scored

        setups = _score_events(calibration, min_opp)

        # Always soft-fill from the full odds cache toward a multi-page board.
        # Uses 0 Odds credits — scoring only — so Rescore/Scan stay dense.
        target = min(limit, TARGET_BOARD_PICKS)
        openai_meta: dict[str, Any] = {"openai_slate": False}
        if len(setups) < target and events:
            slate_cal = dict(calibration)
            slate_cal["slate_mode"] = True
            slate_cal["sports_min_edge_pct"] = min(
                0.25, float(slate_cal.get("sports_min_edge_pct") or 0.6)
            )
            slate_cal["sports_min_opportunity"] = min(
                18.0, float(slate_cal.get("sports_min_opportunity") or 24.0)
            )
            soft = _score_events(slate_cal, float(slate_cal["sports_min_opportunity"]))
            if soft:
                by_key: dict[str, dict[str, Any]] = {}
                for row in setups + soft:
                    key = market_family_key(row)
                    prev = by_key.get(key)
                    if prev is None or composite_score(row) > composite_score(prev):
                        by_key[key] = row
                setups = list(by_key.values())
                fetch_stats["slate_mode"] = True
                fetch_stats["board_fill_target"] = target

        # Guarantee Today's Eastern slate fills when odds cache has tonight's games.
        # Dense weekend/tomorrow edges used to crowd out zero-edge FD/DK market lines.
        from app.providers.sports.odds_api import calendar_today_events

        today_odds = calendar_today_events(events)
        today_setups = [r for r in setups if is_calendar_today(r)]
        today_floor = min(len(today_odds), max(6, int(round(limit * 0.25)))) if today_odds else 0
        if today_odds and len(today_setups) < today_floor:
            today_cal = dict(calibration)
            today_cal["slate_mode"] = True
            today_cal["sports_min_edge_pct"] = 0.0
            today_cal["sports_min_opportunity"] = 18.0
            today_scored: list[dict[str, Any]] = []
            for event in today_odds:
                try:
                    match_stats = lookup_match_stats(event, stats_index) if stats_index else None
                    for setup in analyze_event(event, match_stats=match_stats, calibration=today_cal):
                        if setup.opportunity_score >= 18.0:
                            today_scored.append(setup_to_row(self.user_id, setup))
                except Exception as exc:
                    logger.info("Sports today-slate analyze skip: %s", exc)
            if today_scored:
                by_key = {}
                for row in setups + today_scored:
                    key = market_family_key(row)
                    prev = by_key.get(key)
                    if prev is None or composite_score(row) > composite_score(prev):
                        by_key[key] = row
                setups = list(by_key.values())
                fetch_stats["today_slate_fill"] = True
                fetch_stats["today_events"] = len(today_odds)
                fetch_stats["today_setups"] = sum(1 for r in setups if is_calendar_today(r))

        setups.sort(key=composite_score, reverse=True)

        # OpenAI slate ranking is optional polish — never block a dense cache scan.
        # Quota/timeouts previously burned 60–120s and the BFF dropped the response,
        # so the UI showed "no changes" even after a successful board fill.
        # Under spend lock, skip after cold seed too — keep Scan fast enough for Vercel/BFF.
        if setups and config.settings.openai_api_key and not used_cache and not spend_locked:
            try:
                from app.services.sports_slate_ai import rank_slate_with_openai

                setups, openai_meta = await asyncio.wait_for(
                    rank_slate_with_openai(setups, limit=min(limit, 24)),
                    timeout=12.0,
                )
                fetch_stats.update(openai_meta)
            except TimeoutError:
                logger.warning("OpenAI slate ranking timed out — keeping deterministic ranks")
                fetch_stats["openai_slate"] = False
                fetch_stats["reason"] = "timeout"
            except Exception as exc:
                logger.warning("OpenAI slate ranking skipped: %s", exc)

        setups = _select_diverse_setups(setups, limit=limit)

        tag_pool_categories(setups)

        news_pool: list[dict[str, Any]] = []
        # News is polish — never block Scan/Repair past the BFF budget.
        # Sequential RSS used to burn 60–160s and make Repair look broken (60s BFF abort).
        if setups:
            try:
                news_pool = await asyncio.wait_for(
                    fetch_sports_news(limit_per_feed=4 if used_cache or cache_only else 8),
                    timeout=8.0 if (used_cache or cache_only) else 12.0,
                )
            except TimeoutError:
                logger.warning("Sports news fetch timed out — continuing without headlines")
                fetch_stats["news_skipped"] = "timeout"
            except Exception as exc:
                logger.warning("Sports news fetch skipped: %s", exc)
                fetch_stats["news_skipped"] = str(exc)[:80]

        for row in setups:
            snap = row.setdefault("scoring_snapshot", {})
            snap["timing_tier"] = timing_tier(row)
            if not news_pool:
                continue
            matched = match_news_to_signal(row, news_pool)
            # Keep prior verified news if this pass finds nothing (avoid wiping good context).
            if not matched and snap.get("news_verified") and snap.get("related_news"):
                continue
            analysis = build_news_analysis(row, matched)
            row["explanation"] = analysis["explanation"]
            row["bull_case"] = analysis["bull_case"]
            row["bear_case"] = analysis["bear_case"]
            snap["related_news"] = [
                {
                    "title": n.get("title"),
                    "url": n.get("url"),
                    "source": n.get("source"),
                    "summary": n.get("summary"),
                    "published_at": n.get("published_at"),
                    "relevance_score": n.get("relevance_score"),
                    "matched_tokens": n.get("matched_tokens"),
                    "context_tier": n.get("context_tier"),
                }
                for n in matched
            ]
            snap["analysis_summary"] = analysis["analysis_summary"]
            snap["news_count"] = len(matched)
            snap["news_verified"] = bool(analysis.get("news_verified"))

        setups = sort_for_display([row for row in setups if is_sports_actionable(row)])

        try:
            from app.services.kalshi_public_pulse import enrich_setup_snapshots_with_kalshi

            setups = await asyncio.wait_for(
                enrich_setup_snapshots_with_kalshi(setups),
                timeout=6.0,
            )
        except TimeoutError:
            logger.info("Kalshi public pulse on scan timed out — continuing")
        except Exception as exc:
            logger.info("Kalshi public pulse on scan skipped: %s", exc)

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
            has_existing = bool(existing)
            msg = kept_msg if has_existing or purged else self._result_message(
                setups, fetch_stats, parlays_invalidated=False, calibration=calibration
            )
            if live_odds_pulled:
                msg = f"{msg} · Atlas Insight will rank the fresh board next."
            # Empty board + nothing kept = hard failure (UI must not treat as success).
            ok = bool(has_existing or purged)
            if not ok:
                err = str(fetch_stats.get("error") or fetch_stats.get("message") or "").strip()
                msg = err or msg or (
                    "Sports scan found no plays. Tap Repair sports board or Fetch live odds once "
                    "to seed the odds cache, then Scan again."
                )
            return {
                "signals_created": 0,
                "signals_kept": has_existing,
                "contradictions_purged": purged,
                "events_scanned": len(events),
                "stats": fetch_stats,
                "top_opportunity": None,
                "parlays_invalidated": False,
                "calibration": calibration,
                "live_odds_pulled": live_odds_pulled,
                "insight_pending": live_odds_pulled,
                "ok": ok,
                "message": msg,
                **({"error": msg} if not ok else {}),
            }

        # Insert new Odds-derived rows BEFORE deleting old ones so a failed save
        # cannot wipe the board (previous delete-then-insert left an empty slate).
        saved: list[dict[str, Any]] = []
        insert_errors: list[str] = []
        if setups:
            chunk_size = 40
            for start in range(0, len(setups), chunk_size):
                chunk = setups[start : start + chunk_size]
                try:
                    inserted = await self.db.insert("sports_signals", chunk)
                    if inserted:
                        saved.extend(inserted)
                except Exception as exc:
                    detail = getattr(exc, "detail", None) or str(exc)
                    insert_errors.append(str(detail)[:180])
                    logger.warning("Sports insert chunk failed (%s rows): %s", len(chunk), exc)

        if setups and not saved:
            msg = (
                "Sports scan scored picks but failed to save them — your board was left unchanged. "
                f"{insert_errors[0] if insert_errors else 'Database write failed.'}"
            )
            return {
                "signals_created": 0,
                "signals_kept": True,
                "events_scanned": len(events),
                "stats": fetch_stats,
                "top_opportunity": float(setups[0]["opportunity_score"]) if setups else None,
                "credits_used": int(fetch_stats.get("credits_used") or 0),
                "cache_used": bool(fetch_stats.get("cached")),
                "live_odds_pulled": live_odds_pulled,
                "insight_pending": False,
                "ok": False,
                "message": msg,
            }

        if replace and saved:
            # Grade finished picks from durable snapshots before wiping Odds-derived rows.
            try:
                from app.services.outcome_resolver import OutcomeResolverService

                await asyncio.wait_for(
                    OutcomeResolverService(self.db, self.user_id).resolve_pending(
                        limit=60,
                        module="sports",
                    ),
                    timeout=12.0,
                )
            except TimeoutError:
                logger.warning("Pre-replace sports auto-grade timed out")
            except Exception as exc:
                logger.warning("Pre-replace sports auto-grade skipped: %s", exc)

            saved_ids = {str(r.get("id")) for r in saved if r.get("id")}
            # Keep OpenAI web-desk picks + user Search bets — Odds scans only replace Odds rows.
            active = await self.db.select(
                "sports_signals",
                filters={"user_id": f"eq.{self.user_id}", "status": "eq.active"},
                select="id,scoring_snapshot,line_movement",
                limit=400,
            )
            delete_ids: list[str] = []
            for row in active:
                sid = str(row.get("id") or "")
                if not sid or sid in saved_ids:
                    continue
                snap = row.get("scoring_snapshot") or {}
                lm = row.get("line_movement") or {}
                source = str(snap.get("source") or lm.get("source") or "")
                if (
                    source in {"openai_web", "user_entry"}
                    or bool(snap.get("openai_web"))
                    or bool(lm.get("openai_web"))
                    or bool(snap.get("user_entry"))
                    or str(snap.get("pick_origin") or "") == "user"
                ):
                    continue
                delete_ids.append(sid)
            # Batch deletes — one-by-one was taking minutes and timing out the UI.
            for start in range(0, len(delete_ids), 40):
                chunk = delete_ids[start : start + 40]
                try:
                    await self.db.delete(
                        "sports_signals",
                        {"id": f"in.({','.join(chunk)})", "user_id": f"eq.{self.user_id}"},
                    )
                except Exception as exc:
                    logger.warning("Failed to clear odds sports chunk: %s", exc)
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

        if saved:
            if not used_cache:
                from app.services.signal_registry_service import SignalRegistryService

                try:
                    await asyncio.wait_for(
                        SignalRegistryService(self.db, self.user_id).register_batch("sports", saved),
                        timeout=10.0,
                    )
                except TimeoutError:
                    logger.warning("Signal registry timed out after sports save")
                except Exception as exc:
                    logger.warning("Signal registry skipped: %s", exc)

                try:
                    from app.services.alert_service import AlertService

                    await asyncio.wait_for(
                        AlertService(self.db, self.user_id).notify_high_score_signals(
                            "sports",
                            saved,
                            title_fn=lambda s: f"Sports play · {s.get('sport')} ({float(s.get('opportunity_score') or 0):.0f}/100)",
                            message_fn=lambda s: str(s.get("recommendation") or s.get("selection") or "New sports signal"),
                        ),
                        timeout=8.0,
                    )
                except TimeoutError:
                    logger.warning("Sports alerts timed out")
                except Exception as exc:
                    logger.warning("Sports alerts skipped: %s", exc)

            if config.settings.is_intelligence_enabled() and not used_cache:
                try:
                    from app.sports_intelligence.service import SportsIntelligenceService

                    await SportsIntelligenceService(self.db, self.user_id).refresh_active_signals(
                        saved,
                        limit=min(16, len(saved)),
                    )
                except Exception as exc:
                    logger.warning("Post-scan intelligence refresh skipped: %s", exc)

        # Remove concluded games from the board and grade finished Atlas + user picks promptly.
        graded_resolved = 0
        try:
            from app.services.stale_signal_service import StaleSignalService

            await StaleSignalService(self.db, self.user_id).expire_concluded_sports()
            if not used_cache:
                from app.services.outcome_resolver import OutcomeResolverService

                grade_result = await asyncio.wait_for(
                    OutcomeResolverService(self.db, self.user_id).resolve_pending(
                        limit=60,
                        module="sports",
                    ),
                    timeout=15.0,
                )
                graded_resolved = int((grade_result or {}).get("resolved") or 0)
        except TimeoutError:
            logger.info("Post-scan sports grade timed out — board already saved")
        except Exception as exc:
            logger.warning("Post-scan sports grade/expire skipped: %s", exc)

        result = {
            "signals_created": len(saved),
            "events_scanned": len(events),
            "stats": fetch_stats,
            "sports_in_results": sports_in_results,
            "leagues_with_near_term_games": fetch_stats.get("leagues_with_near_term_games") or [],
            "top_opportunity": float(setups[0]["opportunity_score"]) if setups else None,
            "credits_used": int(fetch_stats.get("credits_used") or 0),
            "cache_used": bool(fetch_stats.get("cached")),
            "live_odds_pulled": live_odds_pulled,
            "insight_pending": live_odds_pulled,
            "parlays_invalidated": bool(replace and saved),
            "graded_resolved": graded_resolved,
            "calibration": calibration,
            "ok": True,
            "today_picks_saved": sum(1 for r in setups if is_calendar_today(r)) if setups else 0,
            "message": self._result_message(
                setups,
                fetch_stats,
                parlays_invalidated=bool(replace and saved),
                calibration=calibration,
                saved_count=len(saved),
            ),
        }
        if live_odds_pulled:
            base = str(result.get("message") or "").strip()
            result["message"] = (
                f"{base} · Atlas Insight will rank the fresh board next." if base else "Atlas Insight will rank the fresh board next."
            )
        return result

    async def repair_sports_board(
        self,
        *,
        replace: bool = True,
        limit: int = MAX_SIGNALS,
    ) -> dict[str, Any]:
        """Recover an empty sports board / Today slate from Atlas.

        Live-seeds when cache is cold, essentials are incomplete, or there are
        no Eastern-calendar-today games (the common failure after a partial Fetch).
        Otherwise free cache-only rescan. Never treats an empty board as success.
        """
        from app.providers.sports.odds_api import odds_cache_status

        status = odds_cache_status()
        today_events = int(status.get("today_event_count") or 0)
        # Live-seed only when there is nothing usable OR Tonight is missing.
        # Do NOT live-seed for "incomplete essentials" alone — that burned credits on
        # every Repair and left Scan broken when the quota was drained.
        need_live = not bool(status.get("has_data")) or today_events == 0 or bool(
            status.get("missing_today_slate")
        )
        if need_live:
            result = await self.refresh_sports(
                replace=replace,
                limit=limit,
                force_refresh=True,
                cache_only=False,
            )
            result["repair_mode"] = "live_seed"
            result["cache_was_cold"] = not bool(status.get("has_data"))
            result["missing_today_before"] = today_events == 0
        else:
            result = await self.refresh_sports(
                replace=replace,
                limit=limit,
                force_refresh=False,
                cache_only=True,
            )
            result["repair_mode"] = "cache_rescan"
            result["cache_was_cold"] = False
            result["missing_today_before"] = False

        created = int(result.get("signals_created") or 0)
        kept = bool(result.get("signals_kept"))
        today_saved = 0
        if created > 0 or kept:
            post = odds_cache_status()
            today_saved = int(post.get("today_event_count") or 0)
        today_picks = int(result.get("today_picks_saved") or 0)
        result["today_event_count"] = today_saved
        result["today_picks_expected"] = today_saved > 0 or today_picks > 0
        # Board Today is what the UI shows — cache can have tonight's games and still save 0 today picks.
        result["today_still_empty"] = today_picks == 0 if "today_picks_saved" in result else today_saved == 0

        if created == 0 and not kept:
            result["ok"] = False
            err = str(result.get("message") or result.get("error") or "").strip()
            if need_live:
                result["error"] = err or (
                    "Repair could not seed the odds cache. Check ODDS_API_KEY credits, "
                    "then tap Repair sports board again."
                )
            else:
                result["error"] = err or (
                    "Odds cache is warm but no plays ranked. Stay on Today and tap Repair again, "
                    "or Fetch live odds once."
                )
            if not result.get("message"):
                result["message"] = result["error"]
        elif created > 0:
            # Never mark ok=False when picks were saved — the Sports UI aborts reload on ok=false
            # and the board looks permanently empty (Scan/Repair "not working at all").
            result["ok"] = True
            base = str(result.get("message") or "").strip()
            if today_picks > 0:
                today_note = f" · {today_picks} Today's plays on the board"
            elif today_saved > 0:
                today_note = f" · {today_saved} games on Today's odds slate"
            else:
                today_note = (
                    " · Today's Eastern slate still empty — stayed on Today. "
                    "Tap Repair again or Fetch live odds once."
                )
            durable = (
                " · Durable odds cache seeded — Scan/Rescore stay free after redeploys."
                if need_live
                else ""
            )
            result["message"] = (
                f"{base}{today_note}{durable}" if base else f"Repaired{today_note}{durable}"
            )
            result.pop("error", None)
        return result

    @staticmethod
    def _result_message(
        setups: list[dict[str, Any]],
        stats: dict[str, Any],
        *,
        parlays_invalidated: bool = False,
        calibration: dict[str, Any] | None = None,
        saved_count: int | None = None,
    ) -> str | None:
        source = _source_note(stats)
        credits = int(stats.get("credits_used") or 0)
        credit_note = (
            " · 0 API credits (cached odds)"
            if stats.get("cached")
            else f" · ~{credits} API credits used"
        )
        near_leagues = stats.get("leagues_with_near_term_games") or []
        near_label = ", ".join(near_leagues[:6]) if near_leagues else "none in the next 7 days"
        dropped = int(stats.get("events_dropped_far_out") or 0)
        skipped = stats.get("skipped_off_season") or []
        persisted = len(setups) if saved_count is None else saved_count

        scan_note = ""
        if stats.get("fetch_cooldown"):
            scan_note = str(stats.get("message") or (
                "Fetch cooldown — served cache (0 Odds credits). Use Rescore / Scan."
            ))
        elif stats.get("credit_guard") or stats.get("credits_blocked"):
            scan_note = (
                stats.get("message")
                or "Odds credits low — rescored from cache (0 Odds credits). Atlas Insight still ranks FanDuel/DraftKings picks."
            )
        elif stats.get("cached"):
            scan_note = f"Rescored from cache · {len(near_leagues)} leagues with games this week ({near_label})"
            if stats.get("cache_needs_live_refresh"):
                scan_note += (
                    " · coverage looks narrow — Fetch live odds ONCE if needed "
                    "(~8 credits, then 20m cooldown). Prefer Rescore."
                )
            if stats.get("openai_slate"):
                scan_note += f" · OpenAI ranked {stats.get('openai_ranked', '?')} picks"
            elif _openai_quota_skipped(stats):
                scan_note += " · OpenAI ranking skipped (quota) — FanDuel/DK edges still saved"
        else:
            scanned = int(stats.get("sports_scanned") or 0)
            scan_note = (
                f"Live US-book scan: {scanned} leagues{credit_note} · "
                f"{len(near_leagues)} had games in the next 7 days ({near_label})"
            )
            if stats.get("cache_merged"):
                scan_note += " · merged into existing cache"
            if stats.get("openai_slate"):
                scan_note += f" · OpenAI ranked {stats.get('openai_ranked', '?')} picks"
            elif _openai_quota_skipped(stats):
                scan_note += " · OpenAI ranking skipped (quota) — FanDuel/DK edges still saved"
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
        base = f"{scan_note} · saved {persisted} plays"
        if calibration and calibration.get("active") and calibration.get("learning_notes"):
            base += f" · Atlas learning: {calibration['learning_notes'][0]}"
        if parlays_invalidated and setups:
            parlay_note = " · Rebuild parlays to refresh tickets"
            return f"{base}{parlay_note}" if base else "Rebuild parlays to refresh tickets"
        return base