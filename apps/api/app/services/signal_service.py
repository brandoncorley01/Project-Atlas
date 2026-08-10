from app.db.supabase_client import SupabaseClient, explained_to_options_row
from app.engine.models import ExplainedSignal
from app.engine.pipeline import run_options_pipeline
from app.agents.news_ai import sanitize_catalyst_context
from app.services.options_service import contract_identity_key
from app.agents.sports_categories import (
    CATEGORY_ORDER,
    category_counts,
    category_payload,
    filter_by_category,
    categories_for_row,
)
from app.services.freshness import (
    age_hours,
    format_data_as_of_label,
    hours_until_event,
    is_options_fresh,
    is_sports_listable,
    is_stock_fresh,
    sports_staleness_reason,
    stock_staleness_reason,
)
from app.services.sports_ranking import (
    MONTH_HOURS,
    NEAR_TERM_HOURS,
    WEEK_HOURS,
    dedupe_one_side_per_market,
    filter_near_term,
    is_calendar_today,
    is_futures_row,
    sort_for_display,
)
import asyncio
import logging
import re

logger = logging.getLogger(__name__)

def _is_openai_web_row(row: dict) -> bool:
    snap = row.get("scoring_snapshot") or {}
    lm = row.get("line_movement") or {}
    return (
        bool(snap.get("openai_web"))
        or bool(lm.get("openai_web"))
        or str(snap.get("source") or "") == "openai_web"
        or str(lm.get("source") or "") == "openai_web"
        or str(row.get("pick_source") or "") == "openai_web"
    )


def _is_user_entry_row(row: dict) -> bool:
    from app.services.sports_ranking import is_user_entry_row

    return is_user_entry_row(row)


def _sports_window_match(row: dict, window: str) -> bool:
    """Match board windows — concluded / started games are already excluded by is_sports_listable."""
    hours = hours_until_event(row.get("event_start"))
    insight_or_user = _is_openai_web_row(row) or _is_user_entry_row(row)
    if hours is None:
        # OpenAI / user-logged picks often lack a precise kickoff — still list them.
        if insight_or_user:
            return window != "futures" or is_futures_row(row)
        # Futures without a commence time still listable
        return is_futures_row(row) and window in {"all", "futures", "month"}
    if hours <= 0:
        return False
    if window == "today":
        return is_calendar_today(row)
    if window == "soon":
        return hours <= NEAR_TERM_HOURS and not is_futures_row(row)
    if window == "week":
        return hours <= WEEK_HOURS and not is_futures_row(row)
    if window == "month":
        return hours <= MONTH_HOURS or is_futures_row(row)
    if window == "futures":
        return is_futures_row(row) or hours > WEEK_HOURS
    # window == "all" — every upcoming listable row stays on the board
    return True


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _format_strike(value: object) -> str:
    """Match web formatStrike — half strikes must not round into twin titles."""
    n = _safe_float(value)
    if abs(n - round(n)) < 1e-6:
        return str(int(round(n)))
    return f"{n:.1f}".rstrip("0").rstrip(".")


def _options_row_identity(row: dict) -> str:
    """Read-path contract identity (mirrors options_service.contract_identity_key)."""
    from types import SimpleNamespace
    from datetime import date, datetime

    exp = row.get("expiration")
    if isinstance(exp, str):
        try:
            exp = date.fromisoformat(exp[:10])
        except ValueError:
            pass
    elif isinstance(exp, datetime):
        exp = exp.date()
    candidate = SimpleNamespace(
        symbol=row.get("underlying"),
        option_type=row.get("option_type"),
        strike=row.get("strike"),
        expiration=exp,
    )
    return contract_identity_key(candidate)


def _dedupe_options_rows(rows: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for row in rows:
        key = _options_row_identity(row)
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _legacy_context_from_explanation(explanation: str | None) -> dict:
    """Backfill market context for signals saved before structured context existed."""
    if not explanation:
        return {}

    ctx: dict = {}
    if match := re.search(r"RSI (\d+)", explanation):
        ctx["rsi"] = float(match.group(1))
    if match := re.search(r"relative volume ([\d.]+)x", explanation):
        ctx["relative_volume"] = float(match.group(1))
    if match := re.search(r"News catalyst: (.+?)(?: Confidence|$)", explanation):
        ctx["has_catalyst"] = True
        ctx["top_headline"] = match.group(1).strip()
    return ctx


class SignalService:
    def __init__(self, db: SupabaseClient, user_id: str) -> None:
        self.db = db
        self.user_id = user_id

    async def clear_active_options(self) -> None:
        await self.db.delete(
            "options_signals",
            {"user_id": f"eq.{self.user_id}", "status": "eq.active"},
        )

    async def run_mock_options_pipeline(self, *, replace: bool = True) -> list[dict]:
        explained = run_options_pipeline()
        if replace:
            await self.clear_active_options()

        rows = [explained_to_options_row(self.user_id, s) for s in explained]
        if not rows:
            return []

        saved = await self.db.insert("options_signals", rows)
        if saved:
            from app.services.signal_registry_service import SignalRegistryService

            await SignalRegistryService(self.db, self.user_id).register_batch("options", saved)
        return saved

    async def list_options(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        status: str = "active",
        budget_only: bool = False,
    ) -> list[dict]:
        fetch_limit = max(limit * 4, 40) if budget_only else max(limit * 3, 60)
        rows = await self.db.select(
            "options_signals",
            filters={
                "user_id": f"eq.{self.user_id}",
                "status": f"eq.{status}",
            },
            order="opportunity_score.desc",
            limit=fetch_limit,
            offset=offset,
        )
        if not budget_only:
            rows = [r for r in rows if is_options_fresh(r)]
            # Prefer under-$100 contracts first so the board protects capital by default.
            rows.sort(
                key=lambda r: (
                    1 if self._is_budget_row(r) else 0,
                    float((r.get("scoring_snapshot") or {}).get("profit_probability") or 0),
                    float(r.get("opportunity_score") or 0),
                ),
                reverse=True,
            )
            return _dedupe_options_rows(rows)[:limit]

        budget_rows = [row for row in rows if self._is_budget_row(row) and is_options_fresh(row)]
        budget_rows.sort(
            key=lambda r: float((r.get("scoring_snapshot") or {}).get("profit_probability") or 0),
            reverse=True,
        )
        return _dedupe_options_rows(budget_rows)[:limit]

    async def get_options(self, signal_id: str) -> dict | None:
        """Return an options signal for detail views, including stale/expired rows."""
        rows = await self.db.select(
            "options_signals",
            filters={"id": f"eq.{signal_id}", "user_id": f"eq.{self.user_id}"},
            limit=1,
        )
        return rows[0] if rows else None

    @staticmethod
    def _is_budget_row(row: dict) -> bool:
        snap = row.get("scoring_snapshot") or {}
        if snap.get("is_budget"):
            return True
        premium = float(row.get("premium") or 0)
        return premium * 100 <= 100

    async def list_stocks(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        status: str = "active",
        skip_expire: bool = False,
    ) -> list[dict]:
        if status == "active" and not skip_expire:
            from app.services.stale_signal_service import StaleSignalService

            await StaleSignalService(self.db, self.user_id).expire_all()

        fetch_limit = max(limit * 4, 80)
        rows = await self.db.select(
            "stock_signals",
            filters={
                "user_id": f"eq.{self.user_id}",
                "status": f"eq.{status}",
            },
            order="opportunity_score.desc",
            limit=fetch_limit,
            offset=offset,
        )
        rows = [r for r in rows if is_stock_fresh(r)]
        return rows[:limit]

    async def get_stock(self, signal_id: str) -> dict | None:
        rows = await self.db.select(
            "stock_signals",
            filters={"id": f"eq.{signal_id}", "user_id": f"eq.{self.user_id}"},
            limit=1,
        )
        return rows[0] if rows else None

    async def list_sports(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        status: str = "active",
        sport: str | None = None,
        category: str | None = None,
        window: str = "soon",
        skip_expire: bool = False,
    ) -> list[dict]:
        # Drop concluded/in-progress games from the live board, then grade finished picks.
        if not skip_expire and status == "active":
            try:
                from app.services.stale_signal_service import StaleSignalService

                await StaleSignalService(self.db, self.user_id).expire_concluded_sports()
            except Exception as exc:
                logger.warning("Expire concluded sports on list: %s", exc)
            try:
                from app.services.outcome_resolver import OutcomeResolverService

                await asyncio.wait_for(
                    OutcomeResolverService(self.db, self.user_id).resolve_pending(
                        limit=50,
                        module="sports",
                    ),
                    timeout=8.0,
                )
            except TimeoutError:
                logger.info("Sports list auto-grade timed out — board still filtered")
            except Exception as exc:
                logger.warning("Sports list auto-grade skipped: %s", exc)

        fetch_limit = 300 if category or window in {"all", "month", "futures", "today", "week"} else max(limit * 3, 80)
        rows = await self.db.select(
            "sports_signals",
            filters={
                "user_id": f"eq.{self.user_id}",
                "status": f"eq.{status}",
            },
            order="opportunity_score.desc",
            limit=fetch_limit,
            offset=offset if not category else 0,
        )
        # Always union Search / My bets — low opportunity scores can fall outside the top-N
        # opportunity-ordered fetch and disappear from the board after refresh.
        if status == "active" and offset == 0:
            try:
                recent = await self.db.select(
                    "sports_signals",
                    filters={
                        "user_id": f"eq.{self.user_id}",
                        "status": "eq.active",
                    },
                    order="data_as_of.desc",
                    limit=200,
                )
                by_id = {str(r.get("id")): r for r in rows if r.get("id")}
                for r in recent:
                    if not _is_user_entry_row(r):
                        continue
                    rid = str(r.get("id") or "")
                    if rid and rid not in by_id:
                        by_id[rid] = r
                        rows.append(r)
            except Exception as exc:
                logger.warning("Sports list user-bet union skipped: %s", exc)
        if sport:
            sport_norm = str(sport).strip().lower().replace(" ", "_")
            def _sport_match(row: dict) -> bool:
                label = str(row.get("sport") or "").strip().lower().replace(" ", "_")
                key = str((row.get("scoring_snapshot") or {}).get("sport_key") or "").lower()
                if not sport_norm:
                    return True
                if label == sport_norm or key == sport_norm:
                    return True
                if sport_norm in {"mma", "ufc"} and (
                    "mma" in label or "ufc" in label or key.startswith("mma_")
                ):
                    return True
                if sport_norm == "boxing" and ("boxing" in label or key.startswith("boxing_")):
                    return True
                return sport_norm in label or label in sport_norm or sport_norm in key

            rows = [r for r in rows if _sport_match(r)]
        rows = [r for r in rows if is_sports_listable(r)]
        rows = [r for r in rows if _sports_window_match(r, window)]
        if category:
            rows = filter_by_category(rows, category)
        rows = dedupe_one_side_per_market(rows)
        rows = sort_for_display(rows)
        # Never truncate away Atlas Insight / player props when applying the board limit.
        if offset == 0 and limit > 0 and len(rows) > limit:
            insight = [r for r in rows if _is_openai_web_row(r) or _is_user_entry_row(r)]
            props = [
                r
                for r in rows
                if (
                    str(r.get("bet_type") or "").lower() == "player_prop"
                    or bool((r.get("scoring_snapshot") or {}).get("is_player_prop"))
                )
                and not _is_openai_web_row(r)
                and not _is_user_entry_row(r)
            ]
            reserved: list[dict] = []
            seen_ids: set[str] = set()
            for r in insight + props:
                rid = str(r.get("id") or "")
                if rid and rid in seen_ids:
                    continue
                if rid:
                    seen_ids.add(rid)
                reserved.append(r)
                if len(reserved) >= max(40, limit // 2):
                    break
            rest = [r for r in rows if str(r.get("id") or "") not in seen_ids]
            rows = (reserved + rest)[:limit]
            return rows
        return rows[offset : offset + limit]

    async def get_sports(self, signal_id: str) -> dict | None:
        """Return a sports signal for detail views, including started/expired rows."""
        rows = await self.db.select(
            "sports_signals",
            filters={"id": f"eq.{signal_id}", "user_id": f"eq.{self.user_id}"},
            limit=1,
        )
        return rows[0] if rows else None

    async def list_all_sports(self, *, status: str = "active", limit: int = 200) -> list[dict]:
        rows = await self.db.select(
            "sports_signals",
            filters={
                "user_id": f"eq.{self.user_id}",
                "status": f"eq.{status}",
            },
            order="opportunity_score.desc",
            limit=limit,
        )
        rows = [r for r in rows if is_sports_listable(r)]
        return dedupe_one_side_per_market(rows)

    async def sports_category_catalog(self) -> list[dict]:
        pool = await self.list_all_sports()
        counts = category_counts(pool)
        return [category_payload(slug, count=counts.get(slug, 0)) for slug in CATEGORY_ORDER]

    async def sports_category_detail(self, slug: str, *, limit: int = 30) -> dict | None:
        from app.agents.sports_categories import CATEGORY_CATALOG

        if slug not in CATEGORY_CATALOG:
            return None
        pool = await self.list_all_sports()
        filtered = filter_by_category(pool, slug)[:limit]
        counts = category_counts(pool)
        return {
            **category_payload(slug, count=counts.get(slug, 0)),
            "items": [self.format_sports_item(row) for row in filtered],
        }

    async def sports_opportunities(
        self,
        limit: int = 8,
        *,
        skip_expire: bool = False,
        window: str = "soon",
    ) -> list[dict]:
        sports = await self.list_sports(limit=limit, skip_expire=skip_expire, window=window)
        return [self._format_summary(row, "sports") for row in sports]

    async def top_opportunities(self, limit: int = 10) -> list[dict]:
        options = await self.list_options(limit=limit)
        return [self._format_summary(row, "options") for row in options]

    async def stock_opportunities(self, limit: int = 8, *, skip_expire: bool = False) -> list[dict]:
        stocks = await self.list_stocks(limit=limit, skip_expire=skip_expire)
        return [self._format_summary(row, "stock") for row in stocks]

    async def budget_opportunities(self, limit: int = 8) -> list[dict]:
        options = await self.list_options(limit=limit, budget_only=True)
        return [self._format_summary(row, "options") for row in options]

    def format_sports_item(self, row: dict) -> dict:
        summary = self._format_summary(row, "sports")
        snapshot = row.get("scoring_snapshot") or {}
        line_movement = row.get("line_movement") or {}
        book_odds = snapshot.get("book_odds") or line_movement.get("book_odds") or []
        preferred_book = snapshot.get("preferred_book") or line_movement.get("preferred_book") or "fanduel"
        preferred_book_title = (
            snapshot.get("preferred_book_title")
            or line_movement.get("preferred_book_title")
            or "FanDuel"
        )
        categories = categories_for_row(row)
        related_news = snapshot.get("related_news") or []
        news_verified = bool(snapshot.get("news_verified"))
        stale_reason = sports_staleness_reason(row)
        return {
            **summary,
            "sport": row.get("sport") or "Sports",
            "event_name": row.get("event_name") or "",
            "event_start": row.get("event_start"),
            "hours_until_start": round(hours_until_event(row.get("event_start")), 1)
            if hours_until_event(row.get("event_start")) is not None
            else None,
            "timing_tier": snapshot.get("timing_tier"),
            "is_stale": stale_reason is not None,
            "staleness_reason": stale_reason,
            "data_as_of_label": format_data_as_of_label(row.get("data_as_of")),
            "bet_type": row.get("bet_type") or "moneyline",
            "selection": row.get("selection") or "",
            "odds_american": int(_safe_float(row.get("odds_american"))),
            "odds_decimal": _safe_float(row.get("odds_decimal")),
            "expected_value": _safe_float(row.get("expected_value")),
            "line_movement": line_movement,
            "book_odds": book_odds,
            "preferred_book": preferred_book,
            "preferred_book_title": preferred_book_title,
            "categories": categories,
            "related_news": related_news if news_verified else [],
            "analysis_summary": snapshot.get("analysis_summary"),
            "news_count": int(snapshot.get("news_count") or len(related_news)),
            "news_verified": news_verified,
            "implied_prob": _safe_float(snapshot.get("implied_prob")),
            "sharp_indicator": row.get("sharp_indicator"),
            "stats_support": _safe_float(snapshot.get("stats_support")),
            "team_stats": snapshot.get("team_stats"),
            "public_market": (
                row.get("public_market")
                if isinstance(row.get("public_market"), dict)
                else snapshot.get("public_market")
                if isinstance(snapshot.get("public_market"), dict)
                else None
            ),
            "pick_source": str(snapshot.get("source") or line_movement.get("source") or "odds_api"),
            "openai_web": bool(
                snapshot.get("openai_web")
                or snapshot.get("source") == "openai_web"
                or line_movement.get("source") == "openai_web"
            ),
            "user_entry": bool(
                snapshot.get("user_entry")
                or snapshot.get("source") == "user_entry"
                or line_movement.get("source") == "user_entry"
                or snapshot.get("pick_origin") == "user"
            ),
            "confidence_score": _safe_float(row.get("confidence_score")),
            "risk_score": _safe_float(row.get("risk_score")),
            "opportunity_score": _safe_float(row.get("opportunity_score")),
            "bull_case": row.get("bull_case"),
            "bear_case": row.get("bear_case"),
            "invalidation": row.get("invalidation"),
            "suggested_action": row.get("suggested_action"),
            "risk_warning": row.get("risk_warning", ""),
            "scoring_snapshot": snapshot,
        }

    def format_stock_item(self, row: dict) -> dict:
        summary = self._format_summary(row, "stock")
        snapshot = row.get("scoring_snapshot") or {}
        technicals = row.get("technicals") or {}
        entry = row.get("entry_range") or {}
        stale_reason = stock_staleness_reason(row)
        return {
            **summary,
            "ticker": row.get("ticker") or "UNKNOWN",
            "is_stale": stale_reason is not None,
            "staleness_reason": stale_reason,
            "data_as_of_label": format_data_as_of_label(row.get("data_as_of")),
            "scan_age_hours": round(age_hours(row.get("data_as_of")), 1)
            if age_hours(row.get("data_as_of")) is not None
            else None,
            "current_price": _safe_float(row.get("current_price")),
            "entry_range": entry,
            "stop_loss": _safe_float(row.get("stop_loss")),
            "profit_targets": row.get("profit_targets") or [],
            "expected_hold_time": row.get("expected_hold_time"),
            "timeframe": row.get("timeframe"),
            "technicals": technicals,
            "confidence_score": _safe_float(row.get("confidence_score")),
            "risk_score": _safe_float(row.get("risk_score")),
            "opportunity_score": _safe_float(row.get("opportunity_score")),
            "bull_case": row.get("bull_case"),
            "bear_case": row.get("bear_case"),
            "invalidation": row.get("invalidation"),
            "suggested_action": row.get("suggested_action"),
            "risk_warning": row.get("risk_warning", ""),
            "scoring_snapshot": snapshot,
            "chart_bars": snapshot.get("chart_bars") or [],
        }

    def format_options_item(self, row: dict) -> dict:
        """Full options row for the Retail Options page."""
        summary = self._format_summary(row, "options")
        snapshot = row.get("scoring_snapshot") or {}
        return {
            **summary,
            "underlying": row.get("underlying") or "?",
            "option_type": row.get("option_type") or "call",
            "strike": _safe_float(row.get("strike")),
            "confidence_score": _safe_float(row.get("confidence_score")),
            "risk_score": _safe_float(row.get("risk_score")),
            "opportunity_score": _safe_float(row.get("opportunity_score")),
            "premium": _safe_float(row.get("premium")),
            "days_to_expiration": int(_safe_float(row.get("days_to_expiration"))),
            "risk_warning": row.get("risk_warning", ""),
            "bull_case": row.get("bull_case"),
            "scoring_snapshot": snapshot,
        }

    @staticmethod
    def _format_summary(row: dict, module: str) -> dict:
        if module == "options":
            underlying = row.get("underlying") or "?"
            option_type = str(row.get("option_type") or "call").upper()
            title = f"{underlying} {option_type} ${_format_strike(row.get('strike'))}"
        elif module == "stock":
            price = _safe_float(row.get("current_price"))
            title = f"{row.get('ticker') or '?'} ${price:.2f}"
        elif module == "sports":
            sport = row.get("sport") or "Sports"
            selection = row.get("selection") or "Pick"
            odds = int(_safe_float(row.get("odds_american")))
            title = f"{sport} · {selection} ({odds:+d})"
        else:
            title = row.get("ticker") or row.get("event_name") or "Signal"

        snapshot = row.get("scoring_snapshot") or {}
        context = dict(snapshot.get("market_context") or {})

        catalyst_val = snapshot.get("catalyst")
        catalyst_score = 0.0
        if isinstance(catalyst_val, (int, float)):
            catalyst_score = float(catalyst_val)
        elif isinstance(catalyst_val, dict):
            catalyst_score = float(catalyst_val.get("catalyst_impact") or 0)
            if catalyst_val.get("top_headline") and not context.get("top_headline"):
                context["top_headline"] = catalyst_val.get("top_headline")
            if catalyst_val.get("has_catalyst"):
                context["has_catalyst"] = True

        if not context.get("has_catalyst") and catalyst_score > 0:
            context["has_catalyst"] = True

        legacy = _legacy_context_from_explanation(row.get("explanation"))
        for key, value in legacy.items():
            context.setdefault(key, value)

        if not context.get("top_headline") and row.get("bull_case"):
            match = re.search(r"News catalyst: (.+?) Trend", str(row["bull_case"]))
            if match:
                context["top_headline"] = match.group(1).strip()
                context["has_catalyst"] = True

        if context.get("profit_probability") is None and snapshot.get("profit_probability") is not None:
            context["profit_probability"] = snapshot.get("profit_probability")

        market_ctx = snapshot.get("market_context") or {}
        if module == "sports":
            for key in ("expected_value", "sharp_indicator", "bet_type", "edge_pct"):
                if snapshot.get(key) is not None and context.get(key) is None:
                    context[key] = snapshot.get(key)
                if market_ctx.get(key) is not None and context.get(key) is None:
                    context[key] = market_ctx.get(key)
            if row.get("expected_value") is not None:
                context.setdefault("expected_value", _safe_float(row.get("expected_value")))
            line_movement = row.get("line_movement") or {}
            book_odds = snapshot.get("book_odds") or line_movement.get("book_odds")
            if book_odds:
                context["book_odds"] = book_odds
                context["preferred_book"] = (
                    snapshot.get("preferred_book") or line_movement.get("preferred_book") or "fanduel"
                )
            if snapshot.get("implied_prob") is not None:
                context["implied_prob"] = snapshot.get("implied_prob")
            if snapshot.get("categories"):
                context["categories"] = snapshot.get("categories")
            if snapshot.get("news_count"):
                context["news_count"] = snapshot.get("news_count")

        contract_cost = snapshot.get("contract_cost")
        if contract_cost is None and module == "options":
            contract_cost = round(float(row.get("premium") or 0) * 100, 2)

        is_budget = False
        if module == "options":
            is_budget = bool(snapshot.get("is_budget") or (contract_cost or 0) <= 100)

        symbol = (
            SignalService._summary_symbol(row.get("underlying"))
            if module == "options"
            else SignalService._summary_symbol(row.get("ticker"))
        )
        context = sanitize_catalyst_context(context, symbol or "")

        return {
            "id": row.get("id"),
            "module": module,
            "title": title,
            "recommendation": row.get("recommendation") or "hold",
            "explanation": row.get("explanation"),
            "context": context,
            "trade_plan": snapshot.get("trade_plan"),
            "expiration": row.get("expiration"),
            "contract_cost": contract_cost,
            "is_budget": is_budget,
            "premium": _safe_float(row.get("premium")) if module == "options" else None,
            "scores": {
                "confidence": _safe_float(row.get("confidence_score")),
                "risk": _safe_float(row.get("risk_score")),
                "opportunity": _safe_float(row.get("opportunity_score")),
            },
            "data_as_of": row.get("data_as_of"),
        }

    @staticmethod
    def _summary_symbol(symbol: str | None) -> str | None:
        sym = str(symbol or "").upper().strip()
        return sym if sym and sym != "?" else None

    @staticmethod
    def apply_live_catalysts(
        summaries: list[dict],
        catalyst_map: dict[str, dict],
    ) -> list[dict]:
        """Refresh opportunity catalysts from validated news matches."""
        enriched: list[dict] = []
        for summary in summaries:
            item = dict(summary)
            sym = SignalService._summary_symbol_from_title(item.get("title"))
            ctx = dict(item.get("context") or {})

            if sym and sym in catalyst_map:
                live = catalyst_map[sym]
                if live.get("has_catalyst"):
                    ctx.update(
                        {
                            "has_catalyst": True,
                            "top_headline": live.get("top_headline"),
                            "catalyst_impact": live.get("catalyst_impact"),
                            "catalyst_sentiment": live.get("catalyst_sentiment"),
                        }
                    )
                else:
                    ctx = sanitize_catalyst_context(ctx, sym)
            elif sym:
                ctx = sanitize_catalyst_context(ctx, sym)

            item["context"] = ctx
            enriched.append(item)
        return enriched

    @staticmethod
    def _summary_symbol_from_title(title: str | None) -> str | None:
        parts = str(title or "").split()
        return SignalService._summary_symbol(parts[0] if parts else None)
