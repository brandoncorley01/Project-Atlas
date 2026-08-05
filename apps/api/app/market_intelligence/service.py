"""Orchestrates Options Intelligence + Market Intelligence + Exit guidance."""

from __future__ import annotations

import logging
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from app.config import settings
from app.db.supabase_client import SupabaseClient
from app.market_intelligence.alerts import default_alert_settings, should_send_alert
from app.market_intelligence.freshness import build_freshness, utcnow
from app.market_intelligence.equity_heatmap import build_equity_market_heatmap
from app.market_intelligence.heatmap import (
    SECTOR_MAP,
    build_market_heatmap,
    build_options_bias_heatmap,
    build_sector_rotation,
    build_smart_money_heatmap,
)
from app.market_intelligence.low_premium import LowPremiumFilters, scan_low_premium
from app.market_intelligence.outcomes import compute_outcome_metrics
from app.market_intelligence.providers import get_options_flow_provider, list_provider_statuses
from app.market_intelligence.scoring import (
    classify_market_weather,
    list_score_versions,
    score_exit_urgency,
    score_options_activity,
)
from app.market_intelligence.smart_money import build_smart_money_watchlist
from app.market_intelligence.types import DataStatus, NormalizedOptionsActivity

logger = logging.getLogger(__name__)


class MarketIntelligenceService:
    def __init__(self, db: SupabaseClient | None, user_id: str):
        self.db = db
        self.user_id = user_id

    def enabled(self) -> bool:
        return bool(getattr(settings, "atlas_market_intelligence_enabled", True))

    async def provider_status(self) -> dict[str, Any]:
        active = get_options_flow_provider()
        return {
            "enabled": self.enabled(),
            "active_provider": active.status_payload(),
            "providers": list_provider_statuses(),
            "score_versions": list_score_versions(),
        }

    async def _load_events(self, params: dict[str, Any] | None = None) -> list[NormalizedOptionsActivity]:
        provider = get_options_flow_provider()
        events = await provider.fetch_activity(params)
        # Best-effort persistence when DB available
        if self.db and events:
            await self._persist_events(events)
        return events

    async def _persist_events(self, events: list[NormalizedOptionsActivity]) -> None:
        assert self.db is not None
        rows = []
        for e in events:
            rows.append(
                {
                    "user_id": self.user_id,
                    "underlying": e.underlying,
                    "option_type": e.option_type,
                    "strike": float(e.strike),
                    "expiration": e.expiration.isoformat(),
                    "trade_timestamp": e.trade_timestamp.isoformat(),
                    "contract_price": float(e.contract_price) if e.contract_price is not None else None,
                    "bid": float(e.bid) if e.bid is not None else None,
                    "ask": float(e.ask) if e.ask is not None else None,
                    "midpoint": float(e.midpoint) if e.midpoint is not None else None,
                    "contracts": e.contracts,
                    "estimated_premium": float(e.estimated_premium) if e.estimated_premium is not None else None,
                    "contract_volume": e.contract_volume,
                    "open_interest": e.open_interest,
                    "volume_oi_ratio": float(e.volume_oi_ratio) if e.volume_oi_ratio is not None else None,
                    "implied_volatility": float(e.implied_volatility) if e.implied_volatility is not None else None,
                    "delta": float(e.delta) if e.delta is not None else None,
                    "execution_class": e.execution_class,
                    "flow_class": e.flow_class,
                    "open_close": e.open_close,
                    "data_source": e.data_source,
                    "source_event_id": e.source_event_id,
                    "idempotency_key": e.idempotency_key,
                    "data_status": e.data_status.value,
                    "data_timestamp": e.data_timestamp.isoformat() if e.data_timestamp else None,
                    "raw_metadata": e.raw_metadata,
                }
            )
        try:
            await self.db.upsert(
                "options_activity_events",
                rows,
                on_conflict="user_id,idempotency_key",
            )
        except Exception as exc:
            logger.debug("options_activity_events persist skipped: %s", exc)

    def _meta_for_events(self, events: list[NormalizedOptionsActivity]) -> dict[str, Any]:
        if not events:
            provider = get_options_flow_provider()
            return build_freshness(
                provider_name=provider.name,
                data_timestamp=None,
                data_status=provider.default_status,
                missing_fields=["events"],
            ).to_dict()
        e0 = events[0]
        return build_freshness(
            provider_name=e0.data_source,
            data_timestamp=e0.data_timestamp,
            data_status=e0.data_status,
        ).to_dict()

    async def flow_scanner(self, *, limit: int = 50, underlying: str | None = None) -> dict[str, Any]:
        events = await self._load_events({"underlying": underlying} if underlying else None)
        counts: Counter[str] = Counter(f"{e.underlying}:{e.option_type}" for e in events)
        cards = []
        for e in events[:limit]:
            breakdown, direction = score_options_activity(
                e,
                repeat_count=counts[f"{e.underlying}:{e.option_type}"],
            )
            cards.append(self._trade_card(e, breakdown, direction.value))
        cards.sort(key=lambda c: c["unusual_score"], reverse=True)
        return {
            "items": cards[:limit],
            "count": len(cards),
            "freshness": self._meta_for_events(events),
            "disclaimer": (
                "Options activity does not prove intent. Large trades may be hedges or spread legs. "
                "Simulated/delayed badges must be respected."
            ),
        }

    def _trade_card(self, e: NormalizedOptionsActivity, breakdown, direction: str) -> dict[str, Any]:
        spread = None
        if e.bid is not None and e.ask is not None and e.midpoint and e.midpoint > 0:
            spread = float((e.ask - e.bid) / e.midpoint * 100)
        risk = "elevated" if breakdown.final_score >= 75 and breakdown.confidence < 50 else (
            "moderate" if breakdown.final_score >= 55 else "contained"
        )
        liq = "A"
        if spread is not None and spread > 10:
            liq = "C"
        elif spread is not None and spread > 5:
            liq = "B"
        if (e.open_interest or 0) < 200:
            liq = "D"
        return {
            "ticker": e.underlying,
            "contract": f"{e.underlying} {e.expiration.isoformat()} {e.strike} {e.option_type.upper()}",
            "direction": direction,
            "strike": str(e.strike),
            "expiration": e.expiration.isoformat(),
            "current_premium": str(e.contract_price or e.midpoint),
            "estimated_total_premium": str(e.estimated_premium) if e.estimated_premium is not None else None,
            "bid_ask_spread_pct": spread,
            "volume": e.contract_volume,
            "open_interest": e.open_interest,
            "volume_oi_ratio": str(e.volume_oi_ratio) if e.volume_oi_ratio is not None else None,
            "implied_volatility": str(e.implied_volatility) if e.implied_volatility is not None else None,
            "delta": str(e.delta) if e.delta is not None else None,
            "unusual_score": breakdown.final_score,
            "atlas_confidence": breakdown.confidence,
            "risk_level": risk,
            "liquidity_grade": liq,
            "catalyst_summary": "Catalyst unknown — not required for listing",
            "technical_confirmation": "partial" if "underlying_momentum" in breakdown.missing_inputs else "available",
            "sector_confirmation": e.sector or SECTOR_MAP.get(e.underlying, "Unknown"),
            "market_regime_confirmation": "partial",
            "suggested_review_zone": {
                "premium_ref": str(e.midpoint or e.contract_price),
                "note": "Review zone only — not a guaranteed entry",
            },
            "invalidation_conditions": [
                "Thesis breaks if underlying loses key support/resistance against direction",
                "Liquidity collapses (spread widens sharply)",
            ],
            "warnings": breakdown.penalties + breakdown.negative_contributors[:3],
            "explanation": (
                f"{direction.replace('_', ' ').title()} lean with unusual score "
                f"{breakdown.final_score:.0f}/100 (confidence {breakdown.confidence:.0f}). "
                f"Positives: {', '.join(breakdown.positive_contributors[:2]) or 'n/a'}. "
                f"Data quality: {breakdown.data_quality}."
            ),
            "score": breakdown.to_dict(),
            "data_status": e.data_status.value,
            "provider": e.data_source,
            "idempotency_key": e.idempotency_key,
        }

    async def low_premium(self, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        events = await self._load_events()
        counts = Counter(f"{e.underlying}:{e.option_type}" for e in events)
        lp_filters = LowPremiumFilters(**(filters or {})) if filters else LowPremiumFilters()
        items = scan_low_premium(events, filters=lp_filters, repeat_counts=dict(counts))
        return {
            "items": items,
            "count": len(items),
            "filters": lp_filters.__dict__,
            "freshness": self._meta_for_events(events),
            "disclaimer": "Cheap contracts are not ranked highly merely because they are cheap.",
        }

    async def smart_money(self) -> dict[str, Any]:
        events = await self._load_events()
        items = build_smart_money_watchlist(events)
        return {
            "items": items,
            "count": len(items),
            "freshness": self._meta_for_events(events),
            "disclaimer": "Atlas never labels prints as named institutions.",
        }

    async def options_heatmap(self) -> dict[str, Any]:
        events = await self._load_events()
        return {
            **build_options_bias_heatmap(events),
            "freshness": self._meta_for_events(events),
        }

    async def signal_history(self, *, limit: int = 50) -> dict[str, Any]:
        """Persist-qualified signals from current scan into history payload."""
        flow = await self.flow_scanner(limit=limit)
        items = [c for c in flow["items"] if c["unusual_score"] >= 55 and c["atlas_confidence"] >= 40]
        # Optional DB persist
        if self.db:
            for card in items[:20]:
                try:
                    await self.db.upsert(
                        "options_intel_signals",
                        [
                            {
                                "user_id": self.user_id,
                                "underlying": card["ticker"],
                                "option_type": "call" if " CALL" in card["contract"] else "put",
                                "strike": float(card["strike"]),
                                "expiration": card["expiration"],
                                "direction": card["direction"],
                                "unusual_score": card["unusual_score"],
                                "confidence": card["atlas_confidence"],
                                "risk_level": card["risk_level"],
                                "liquidity_grade": card["liquidity_grade"],
                                "premium_at_signal": float(card["current_premium"]) if card["current_premium"] else None,
                                "score_version": card["score"]["score_version"],
                                "explanation": card["explanation"],
                                "warnings": card["warnings"],
                                "evidence": {"score": card["score"]},
                                "data_status": card["data_status"],
                                "detected_at": utcnow().isoformat(),
                                "status": "active",
                            }
                        ],
                        on_conflict="user_id,underlying,option_type,strike,expiration,detected_at",
                    )
                except Exception as exc:
                    logger.debug("signal history persist skipped: %s", exc)
        return {"items": items, "count": len(items), "freshness": flow["freshness"]}

    async def performance_analytics(self) -> dict[str, Any]:
        # Compute illustrative outcome metrics from fixture-safe synthetic paths (labelled)
        sample = compute_outcome_metrics(
            entry_underlying=100,
            entry_contract=2.0,
            underlying_path=[100, 101, 103, 102, 105],
            contract_path=[2.0, 2.2, 2.8, 2.5, 3.1],
        )
        return {
            "summary": {
                "signals_tracked": 0,
                "note": "Populate via live signal persistence + outcome job over time.",
            },
            "example_outcome_math": sample,
            "disclaimer": "Example path is methodological — not a live performance claim.",
            "score_versions": list_score_versions(),
        }

    async def alert_settings(self) -> dict[str, Any]:
        return {"items": default_alert_settings(), "allow_simulated_alerts": settings.environment == "development"}

    async def evaluate_alert(
        self,
        *,
        alert_type: str,
        dedup_key: str,
        data_status: str,
        last_sent_at: datetime | None = None,
        cooldown_minutes: int = 60,
    ) -> dict[str, Any]:
        allow_sim = settings.environment == "development"
        ok, reason = should_send_alert(
            alert_type=alert_type,
            dedup_key=dedup_key,
            last_sent_at=last_sent_at,
            cooldown_minutes=cooldown_minutes,
            data_status=data_status,
            allow_simulated=allow_sim,
        )
        return {"should_send": ok, "reason": reason}

    # ----- Market Intelligence -----

    async def market_heatmap(self, *, size_by: str = "market_cap", color_by: str = "daily_return") -> dict[str, Any]:
        """Real equity market heatmap (cap × daily return), not options-flow tiles."""
        try:
            return await build_equity_market_heatmap(size_by=size_by, color_by=color_by)
        except Exception as exc:
            logger.warning("Equity heatmap failed, falling back: %s", exc)
            # Keep prior options-derived fallback only if equity build fails hard
            events = await self._load_events()
            by_sym: dict[str, NormalizedOptionsActivity] = {}
            for e in events:
                by_sym[e.underlying] = e
            universe = []
            for sym, e in by_sym.items():
                universe.append(
                    {
                        "symbol": sym,
                        "sector": e.sector or SECTOR_MAP.get(sym, "Other"),
                        "industry": "General",
                        "market_cap": float(e.estimated_premium or 1_000_000),
                        "volume": e.underlying_volume or e.contract_volume or 1,
                        "dollar_volume": float(e.estimated_premium or 1),
                        "daily_return": float(e.raw_metadata.get("daily_return") or 0),
                        "momentum_score": 0.0,
                        "options_bias": 0.0,
                    }
                )
            if not universe:
                from app.providers.market.universe import CORE_LIQUID

                universe = [
                    {
                        "symbol": s,
                        "sector": SECTOR_MAP.get(s, "Other"),
                        "market_cap": 1e11,
                        "daily_return": 0.0,
                    }
                    for s in CORE_LIQUID[:12]
                ]
            payload = build_market_heatmap(universe, size_by=size_by, color_by=color_by)
            payload["freshness"] = build_freshness(
                provider_name="equity_heatmap_fallback",
                data_timestamp=utcnow(),
                data_status=DataStatus.PARTIAL,
                missing_fields=["equity_quotes"],
            ).to_dict()
            payload["disclaimer"] = (
                "Equity quote heatmap unavailable — showing partial fallback. Not live tape."
            )
            payload["heatmap_kind"] = "fallback"
            return payload

    async def dark_pool(self, *, limit: int = 40) -> dict[str, Any]:
        from app.market_intelligence.providers.finra_ats import fetch_dark_pool_summary

        return await fetch_dark_pool_summary(limit=limit)

    async def congress_trades(self, *, limit: int = 40) -> dict[str, Any]:
        from app.market_intelligence.providers.congress_trades import fetch_congress_trades

        return await fetch_congress_trades(limit=limit)

    async def sector_rotation(self) -> dict[str, Any]:
        events = await self._load_events()
        rows = build_sector_rotation(events)
        return {
            "items": rows,
            "count": len(rows),
            "freshness": self._meta_for_events(events),
            "disclaimer": "Classifications are evidence-based heuristics, not forecasts.",
        }

    async def smart_money_heatmap(self) -> dict[str, Any]:
        events = await self._load_events()
        return {
            **build_smart_money_heatmap(events),
            "freshness": self._meta_for_events(events),
        }

    async def market_weather(self) -> dict[str, Any]:
        events = await self._load_events()
        bias = 0.0
        if events:
            bull = sum(1 for e in events if e.option_type == "call" and (e.execution_class or "") == "ask")
            bear = sum(1 for e in events if e.option_type == "put" and (e.execution_class or "") == "ask")
            total = max(bull + bear, 1)
            bias = (bull - bear) / total

        sectors = build_sector_rotation(events)
        strongest = [s["sector"] for s in sectors[:2]]
        weakest = [s["sector"] for s in sectors[-2:]] if sectors else []

        label, breakdown, payload = classify_market_weather(
            {
                "index_momentum": bias * 0.5,
                "breadth": bias * 0.3,
                "sector_leadership": 0.2 if strongest else 0.0,
                "options_bias": bias,
                "volatility_regime": 0.4,
                "news_sentiment": None,
                "strongest_sectors": strongest,
                "weakest_sectors": weakest,
                "favorable_environments": ["Directional swings aligned with sector leaders"] if strongest else [],
                "areas_to_avoid": weakest,
            }
        )
        return {
            "label": label,
            "confidence": breakdown.confidence,
            "risk_level": payload["risk_level"],
            "score": breakdown.to_dict(),
            "details": payload,
            "freshness": self._meta_for_events(events),
            "last_update": utcnow().isoformat(),
        }

    async def historical_replay(self) -> dict[str, Any]:
        return {
            "available": False,
            "message": (
                "Historical replay will use persisted market_snapshots / weather snapshots. "
                "MVP stores schemas and outcome math; full tape replay arrives after data retention fills."
            ),
            "outcome_engine_ready": True,
        }

    # ----- Exit intelligence -----

    async def evaluate_position(self, position: dict[str, Any]) -> dict[str, Any]:
        breakdown, action, explanation = score_exit_urgency(position)
        return {
            "position_key": position.get("position_key") or position.get("symbol"),
            "symbol": position.get("symbol"),
            "module": position.get("module", "stock"),
            "exit_urgency": breakdown.final_score,
            "urgency_label": None,
            "action": action.value,
            "thesis_status": (
                "invalidated"
                if action.value == "Thesis Invalidated"
                else ("intact" if position.get("thesis_valid", True) else "uncertain")
            ),
            "confidence": breakdown.confidence,
            "explanation": explanation,
            "score": breakdown.to_dict(),
            "data_status": position.get("data_status", "partial"),
            "disclaimer": "Exit guidance is decision support. Atlas does not place trades automatically.",
        }

    async def portfolio_exit_heatmap(self, positions: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        positions = positions or await self._default_positions_from_watchlist()
        tiles = []
        for pos in positions:
            evaluation = await self.evaluate_position(pos)
            tiles.append(
                {
                    "symbol": evaluation["symbol"],
                    "sector": pos.get("sector") or SECTOR_MAP.get(str(pos.get("symbol", "")).upper(), "Other"),
                    "market_cap": float(pos.get("position_value") or pos.get("capital_at_risk") or 1),
                    "daily_return": float(pos.get("return_pct") or 0),
                    "exit_urgency": evaluation["exit_urgency"],
                    "options_bias": float(pos.get("options_support") or 0),
                    "action": evaluation["action"],
                    "thesis_status": evaluation["thesis_status"],
                    "confidence": evaluation["confidence"],
                    "primary_reason": evaluation["explanation"],
                    "main_risk": (evaluation["score"].get("negative_contributors") or ["n/a"])[0],
                    "evaluated_at": evaluation["score"]["evaluation_timestamp"],
                }
            )
        payload = build_market_heatmap(tiles, size_by="market_cap", color_by="exit_urgency")
        payload["tiles_detail"] = tiles
        payload["freshness"] = build_freshness(
            provider_name="position_monitor",
            data_timestamp=utcnow(),
            data_status=DataStatus.PARTIAL,
        ).to_dict()
        payload["disclaimer"] = "Portfolio Exit Heatmap uses watchlist/open-signal proxies until a ledger exists."
        return payload

    async def _default_positions_from_watchlist(self) -> list[dict[str, Any]]:
        if not self.db:
            return [
                {
                    "position_key": "demo-AAPL",
                    "symbol": "AAPL",
                    "module": "options",
                    "return_pct": 18,
                    "momentum_score": 0.1,
                    "trend_ok": True,
                    "relative_volume": 1.2,
                    "options_support": -0.3,
                    "sector_support": 0.2,
                    "market_support": 0.1,
                    "thesis_valid": True,
                    "reward_risk": 1.1,
                    "days_to_event": 10,
                    "at_first_target": True,
                    "position_value": 2500,
                    "data_status": "simulated",
                }
            ]
        try:
            rows = await self.db.select(
                "watchlist_items",
                filters={"user_id": f"eq.{self.user_id}"},
                limit=30,
            )
        except Exception:
            rows = []
        positions = []
        for row in rows or []:
            meta = row.get("metadata") or {}
            symbol = str(meta.get("underlying") or meta.get("ticker") or row.get("symbol") or "").upper()
            if not symbol or len(symbol) > 8:
                # skip UUID-like option symbols without underlying
                if meta.get("underlying"):
                    symbol = str(meta["underlying"]).upper()
                else:
                    continue
            positions.append(
                {
                    "position_key": str(row.get("id")),
                    "symbol": symbol,
                    "module": "options" if meta.get("option_type") or meta.get("watchlist_kind") == "option_signal" else "stock",
                    "return_pct": meta.get("return_pct"),
                    "momentum_score": meta.get("momentum_score"),
                    "trend_ok": meta.get("trend_ok"),
                    "thesis_valid": meta.get("thesis_valid", True),
                    "reward_risk": meta.get("reward_risk"),
                    "position_value": meta.get("position_value") or 1000,
                    "sector": meta.get("sector") or SECTOR_MAP.get(symbol),
                    "data_status": "partial",
                }
            )
        if positions:
            return positions
        return [
            {
                "position_key": "demo-AAPL",
                "symbol": "AAPL",
                "module": "options",
                "return_pct": 18,
                "momentum_score": 0.1,
                "trend_ok": True,
                "relative_volume": 1.2,
                "options_support": -0.3,
                "sector_support": 0.2,
                "market_support": 0.1,
                "thesis_valid": True,
                "reward_risk": 1.1,
                "days_to_event": 10,
                "at_first_target": True,
                "position_value": 2500,
                "data_status": "simulated",
            }
        ]

    # ----- Earnings Intelligence (live Yahoo data) -----

    async def earnings_desk(self) -> dict[str, Any]:
        from app.market_intelligence.earnings.service_api import build_earnings_desk

        desk = await build_earnings_desk(
            normal_risk_usd=float(
                getattr(settings, "atlas_earnings_normal_risk_usd", None)
                or getattr(settings, "atlas_earnings_paper_risk_usd", 100.0)
            ),
            micro_fraction=float(getattr(settings, "atlas_earnings_micro_coattail_fraction", 0.18)),
            allow_fixture_fallback=bool(
                getattr(settings, "atlas_earnings_allow_fixture_fallback", False)
                or getattr(settings, "atlas_earnings_allow_simulated", False)
            ),
        )
        if self.db and desk.get("recently_reviewed"):
            try:
                await self._persist_earnings_reviews(desk["recently_reviewed"])
            except Exception as exc:
                logger.debug("earnings persist skipped: %s", exc)
        return desk

    async def record_earnings_outcome(self, body: dict[str, Any]) -> dict[str, Any]:
        from app.market_intelligence.earnings.service_api import record_earnings_outcome_payload

        entry = body.get("entry", body.get("paper_entry"))
        exit_px = body.get("exit", body.get("paper_exit"))
        payload = record_earnings_outcome_payload(
            recommendation=body.get("recommendation") or {},
            actual_direction=body.get("actual_direction"),
            actual_move_pct=body.get("actual_move_pct"),
            actual_iv_crush_pct=body.get("actual_iv_crush_pct"),
            entry=entry,
            exit=exit_px,
            mfe_pct=body.get("mfe_pct"),
            mae_pct=body.get("mae_pct"),
            net_result_after_costs=body.get("net_result_after_costs"),
        )
        payload["user_id"] = self.user_id
        payload["policy_auto_update"] = False
        # Map to existing DB column names
        db_row = {
            **{k: v for k, v in payload.items() if k not in ("entry", "exit")},
            "paper_entry": entry,
            "paper_exit": exit_px,
            "paper_only": False,
            "live_trading_enabled": False,
        }
        if self.db:
            try:
                await self.db.insert("earnings_setup_outcomes", db_row)
            except Exception as exc:
                logger.debug("earnings outcome insert skipped: %s", exc)
                payload["persisted"] = False
            else:
                payload["persisted"] = True
        else:
            payload["persisted"] = False
        return payload

    async def _persist_earnings_reviews(self, reviews: list[dict[str, Any]]) -> None:
        assert self.db is not None
        for rec in reviews[:20]:
            size = rec.get("position_size_usd", rec.get("paper_position_size_usd"))
            row = {
                "user_id": self.user_id,
                "symbol": rec.get("symbol"),
                "recommendation": rec.get("recommendation"),
                "direction": rec.get("direction"),
                "phase": rec.get("phase"),
                "strategy": rec.get("strategy"),
                "confidence": rec.get("confidence"),
                "expected_move_pct": rec.get("expected_move_pct"),
                "expected_value": rec.get("expected_value"),
                "paper_position_size_usd": size,
                "paper_only": False,
                "evidence": rec,
                "data_status": rec.get("data_status") or "delayed",
                "score_version": "earnings_setup_v1",
            }
            try:
                await self.db.upsert(
                    "earnings_setup_signals",
                    row,
                    on_conflict="user_id,symbol,evaluated_day",
                )
            except Exception:
                # Table may not be migrated yet — non-fatal
                return
