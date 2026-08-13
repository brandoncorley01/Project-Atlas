"""Proactive Home repair — maintenance + scan empty modules."""

from __future__ import annotations

import logging
from typing import Any

from app.db.service_client import get_write_db
from app.db.supabase_client import SupabaseClient
from app.jobs.refresh_news import run_refresh_news_job
from app.jobs.resolve_outcomes import run_resolve_outcomes_job
from app.services.parlay_service import ParlayService
from app.services.signal_registry_service import SignalRegistryService
from app.services.signal_service import SignalService
from app.services.stale_signal_service import StaleSignalService
from app.services.sports_user_bets_service import SportsUserBetsService

logger = logging.getLogger(__name__)


async def _step(name: str, coro) -> dict[str, Any]:
    try:
        result = await coro
        payload = result if isinstance(result, dict) else {"result": result}
        # Prefer the coro’s own ok flag when present (e.g. sports scan ok=False).
        ok = True if "ok" not in payload else bool(payload.get("ok"))
        out = {"step": name, **payload, "ok": ok}
        if not ok and not out.get("error"):
            out["error"] = str(
                payload.get("message")
                or payload.get("error")
                or f"{name} failed"
            )
        return out
    except Exception as exc:
        msg = str(exc).strip() or exc.__class__.__name__
        detail = getattr(exc, "detail", None)
        if isinstance(detail, str) and detail.strip():
            msg = detail.strip()
        logger.warning("fix-all step %s failed: %s", name, msg)
        return {"step": name, "ok": False, "error": msg}


def _failed_step_summary(steps: list[dict[str, Any]]) -> str | None:
    failed = [s for s in steps if not s.get("ok")]
    if not failed:
        return None
    parts: list[str] = []
    for s in failed[:3]:
        name = str(s.get("step") or "step")
        err = str(s.get("error") or s.get("message") or "failed").strip()
        parts.append(f"{name}: {err[:140]}")
    extra = len(failed) - len(parts)
    summary = " · ".join(parts)
    if extra > 0:
        summary += f" · +{extra} more"
    return summary


async def run_fix_all(
    user_id: str,
    token: str,
    *,
    scan_empty: bool = True,
    modules: list[str] | None = None,
) -> dict[str, Any]:
    """Repair dashboard health and optionally scan empty boards.

    Order:
      1. Detect empty boards first (so we know what to scan)
      2. Scan empty modules early (sports/options/stocks) — before slow maintenance
         that can push Fix all past the BFF timeout
      3. expire stale / backfill / resolve / news / recover user bets
      4. build parlays if sports was scanned
    """
    db = SupabaseClient(token)
    write_db = get_write_db(token)
    steps: list[dict[str, Any]] = []

    # Detect empty boards up front so scans start before slow grading/news work.
    signal_service = SignalService(db, user_id)
    top = await signal_service.top_opportunities(limit=3)
    budget = await signal_service.budget_opportunities(limit=3)
    stocks = await signal_service.stock_opportunities(limit=3, skip_expire=True)
    sports = await signal_service.sports_opportunities(limit=3, skip_expire=True, window="week")

    needs = {
        "options": len(top) == 0 and len(budget) == 0,
        "stocks": len(stocks) == 0,
        "sports": len(sports) == 0,
    }

    requested = {m.strip().lower() for m in (modules or []) if m}
    if not requested and scan_empty:
        requested = {k for k, empty in needs.items() if empty}
    elif requested:
        pass
    else:
        requested = set()

    sports_scanned = False
    sports_created = 0

    # Empty-board scans first — Home "Fix all" is usually about filling Sports/Options.
    if "sports" in requested:
        from app.providers.sports.odds_api import odds_cache_status
        from app.services.sports_service import SportsRefreshService

        sports_svc = SportsRefreshService(write_db, user_id)
        # Prefer free cache-only first (disk or durable Supabase hydrate).
        sports_step = await _step(
            "refresh_sports",
            sports_svc.refresh_sports(
                replace=True,
                limit=80,
                force_refresh=False,
                cache_only=True,
            ),
        )
        steps.append(sports_step)
        sports_scanned = bool(sports_step.get("ok"))
        sports_created = int(sports_step.get("signals_created") or 0)

        # Cold / missing-Today cache: one live seed via Repair.
        if needs["sports"] and sports_created == 0:
            cache_status = odds_cache_status()
            need_live = (
                not bool(cache_status.get("has_data"))
                or bool(cache_status.get("missing_today_slate"))
                or int(cache_status.get("today_event_count") or 0) == 0
            )
            if need_live:
                repair_step = await _step(
                    "repair_sports",
                    sports_svc.repair_sports_board(replace=True, limit=80),
                )
                steps.append(repair_step)
                sports_created = int(repair_step.get("signals_created") or 0)
                sports_scanned = bool(repair_step.get("ok")) and sports_created > 0
                if sports_scanned:
                    # Cache-only miss is expected when cold — don't fail Fix all after a good repair.
                    sports_step["ok"] = True
                    sports_step["error"] = None
                    sports_step["message"] = sports_step.get("message") or (
                        "Cache missing Today's slate — repaired with live seed"
                    )
                else:
                    err = str(
                        repair_step.get("error")
                        or repair_step.get("message")
                        or sports_step.get("error")
                        or sports_step.get("message")
                        or ""
                    ).strip()
                    sports_step["ok"] = False
                    sports_step["error"] = err or (
                        "Sports cache empty — open Sports → Repair sports board "
                        "(or Fetch live odds ONCE)"
                    )
                    sports_scanned = False
            else:
                err = str(sports_step.get("error") or sports_step.get("message") or "").strip()
                sports_step["ok"] = False
                sports_step["error"] = err or (
                    "Sports board empty after cache scan — open Sports → Repair sports board"
                )
                sports_scanned = False
        elif needs["sports"] and sports_created > 0:
            # Board filled from cache — only live-repair when Tonight is completely missing.
            cache_status = odds_cache_status()
            if int(cache_status.get("today_event_count") or 0) == 0 or bool(
                cache_status.get("missing_today_slate")
            ):
                repair_step = await _step(
                    "repair_sports",
                    sports_svc.repair_sports_board(replace=True, limit=80),
                )
                steps.append(repair_step)
                if int(repair_step.get("signals_created") or 0) > 0:
                    sports_created = int(repair_step.get("signals_created") or 0)
                    sports_scanned = True

    if "options" in requested:
        from app.services.options_service import OptionsRefreshService

        steps.append(
            await _step(
                "refresh_options",
                OptionsRefreshService(db, user_id).refresh_live_options(replace=True, limit=12),
            )
        )

    if "stocks" in requested:
        from app.services.stock_service import StockRefreshService

        steps.append(
            await _step(
                "refresh_stocks",
                StockRefreshService(db, user_id).refresh_stocks(replace=True, limit=12),
            )
        )

    # Maintenance after scans so a long grade/news pass cannot starve empty boards.
    steps.append(
        await _step(
            "expire_stale",
            StaleSignalService(db, user_id).expire_all(),
        )
    )
    steps.append(
        await _step(
            "signal_backfill",
            SignalRegistryService(db, user_id).backfill_all(limit_per_module=80),
        )
    )
    steps.append(
        await _step(
            "resolve_outcomes",
            run_resolve_outcomes_job(user_id, token, limit=200, passes=5),
        )
    )
    steps.append(
        await _step(
            "refresh_news",
            run_refresh_news_job(user_id, token),
        )
    )
    steps.append(
        await _step(
            "recover_sports_user_bets",
            SportsUserBetsService(db, user_id).recover_user_bets(),
        )
    )

    if sports_scanned or "parlays" in requested:
        steps.append(
            await _step(
                "build_parlays",
                ParlayService(db, user_id).build_parlays(replace=True),
            )
        )

    ok_count = sum(1 for s in steps if s.get("ok"))
    fail_count = len(steps) - ok_count

    # Re-check emptiness for the response.
    top2 = await signal_service.top_opportunities(limit=3)
    budget2 = await signal_service.budget_opportunities(limit=3)
    stocks2 = await signal_service.stock_opportunities(limit=3, skip_expire=True)
    sports2 = await signal_service.sports_opportunities(limit=3, skip_expire=True, window="week")
    needs_after = {
        "options": len(top2) == 0 and len(budget2) == 0,
        "stocks": len(stocks2) == 0,
        "sports": len(sports2) == 0,
    }

    message_parts = [
        f"Fixed {ok_count}/{len(steps)} steps",
    ]
    if fail_count:
        message_parts.append(f"{fail_count} still need attention")
    scanned = sorted(requested)
    if scanned:
        message_parts.append("scanned: " + ", ".join(scanned))
    failed_summary = _failed_step_summary(steps)
    if failed_summary:
        message_parts.append(failed_summary)
    elif needs_after.get("sports") and "sports" in requested:
        message_parts.append(
            "Sports board still empty — open Sports → Repair sports board "
            "(or Fetch live odds once)"
        )

    return {
        "status": "ok" if fail_count == 0 else "partial",
        "message": " · ".join(message_parts),
        "steps": steps,
        "modules_scanned": scanned,
        "needs_refresh_before": needs,
        "needs_refresh_after": needs_after,
        "ok_count": ok_count,
        "fail_count": fail_count,
    }
