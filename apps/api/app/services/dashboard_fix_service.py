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

logger = logging.getLogger(__name__)


async def _step(name: str, coro) -> dict[str, Any]:
    try:
        result = await coro
        payload = result if isinstance(result, dict) else {"result": result}
        return {"step": name, "ok": True, **payload}
    except Exception as exc:
        msg = str(exc).strip() or exc.__class__.__name__
        logger.warning("fix-all step %s failed: %s", name, msg)
        return {"step": name, "ok": False, "error": msg}


async def run_fix_all(
    user_id: str,
    token: str,
    *,
    scan_empty: bool = True,
    modules: list[str] | None = None,
) -> dict[str, Any]:
    """Repair dashboard health and optionally scan empty boards.

    Order:
      1. expire stale
      2. backfill tracking
      3. resolve outcomes
      4. refresh news
      5. scan empty modules (options / stocks / sports)
      6. build parlays if sports was scanned
    """
    db = SupabaseClient(token)
    write_db = get_write_db(token)
    steps: list[dict[str, Any]] = []

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

    # Detect empty boards after maintenance.
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
        # Honor explicit module list even if boards aren't empty.
        pass
    else:
        requested = set()

    sports_scanned = False

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

    if "sports" in requested:
        from app.services.sports_service import SportsRefreshService

        sports_step = await _step(
            "refresh_sports",
            SportsRefreshService(write_db, user_id).refresh_sports(
                replace=True,
                limit=80,
                force_refresh=False,
                cache_only=False,
            ),
        )
        steps.append(sports_step)
        sports_scanned = bool(sports_step.get("ok"))

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
