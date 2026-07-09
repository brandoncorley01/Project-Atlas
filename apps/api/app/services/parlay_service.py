"""Cross-sport parlay builder and persistence."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from app.agents.parlay_builder import build_all_parlays, build_custom_parlay
from app.agents.parlay_categories import (
    PARLAY_CATEGORY_ORDER,
    category_counts,
    category_payload,
    compute_parlay_time_meta,
    filter_parlays_by_category,
    is_parlay_actionable,
)
from app.agents.sports_analyst import PREFERRED_BOOK_KEY, PREFERRED_BOOK_TITLE
from app.db.supabase_client import SupabaseClient
from app.services.freshness import format_data_as_of_label, hours_until_event, is_parlay_fresh, is_sports_actionable
from app.services.sports_ranking import sort_for_parlay_pool

logger = logging.getLogger(__name__)

SPORTS_POOL_SIZE = 100


class ParlayService:
    def __init__(self, db: SupabaseClient, user_id: str) -> None:
        self.db = db
        self.user_id = user_id

    @staticmethod
    def _signal_id(value: Any) -> str:
        return str(value or "").strip().lower()

    async def _load_sports_pool(self) -> list[dict[str, Any]]:
        rows = await self.db.select(
            "sports_signals",
            filters={
                "user_id": f"eq.{self.user_id}",
                "status": "eq.active",
            },
            order="opportunity_score.desc",
            limit=SPORTS_POOL_SIZE,
        )
        return sort_for_parlay_pool([r for r in rows if is_sports_actionable(r)])

    async def build_parlays(self, *, replace: bool = True) -> dict[str, Any]:
        await self._expire_obsolete_parlays()

        signals = await self._load_sports_pool()
        if len(signals) < 2:
            return {
                "parlays_created": 0,
                "legs_created": 0,
                "items": [],
                "message": "Need at least 2 upcoming plays in the next 48h. Scan sports odds first.",
                "styles_built": [],
                "sports_pool": len(signals),
            }

        proposals = build_all_parlays(signals)
        if not proposals:
            sports_seen = sorted({str(s.get("sport")) for s in signals})
            return {
                "parlays_created": 0,
                "legs_created": 0,
                "items": [],
                "message": (
                    f"Could not combine {len(signals)} signals across "
                    f"{', '.join(sports_seen) or 'available sports'}. "
                    "Try Fetch live odds for more plays."
                ),
                "styles_built": [],
                "sports_pool": len(signals),
            }

        if replace:
            await self.db.delete(
                "parlays",
                {"user_id": f"eq.{self.user_id}", "status": "eq.active"},
            )

        now = datetime.now(UTC).isoformat()
        signal_map = {self._signal_id(s["id"]): s for s in signals}
        parlay_rows = [
            {
                "user_id": self.user_id,
                "name": p["name"],
                "style": p["style"],
                "combined_odds_american": p["combined_odds_american"],
                "combined_odds_decimal": p["combined_odds_decimal"],
                "expected_value": p["expected_value"],
                "correlation_warning": p.get("correlation_warning"),
                "confidence_score": p["confidence_score"],
                "risk_score": p["risk_score"],
                "opportunity_score": p["opportunity_score"],
                "recommendation": p["recommendation"],
                "explanation": p["explanation"],
                "risk_warning": p["risk_warning"],
                "status": "active",
                "data_as_of": now,
            }
            for p in proposals
        ]

        saved_parlays = await self.db.insert("parlays", parlay_rows)
        leg_rows: list[dict[str, Any]] = []
        for parlay_row, proposal in zip(saved_parlays, proposals):
            for leg in proposal["legs"]:
                leg_rows.append(
                    {
                        "parlay_id": parlay_row["id"],
                        "user_id": self.user_id,
                        "leg_order": leg["leg_order"],
                        "sport": leg["sport"],
                        "event_name": leg["event_name"],
                        "bet_type": leg["bet_type"],
                        "selection": leg["selection"],
                        "odds_american": leg["odds_american"],
                        "leg_reason": leg["leg_reason"],
                        "sports_signal_id": leg.get("sports_signal_id"),
                    }
                )
                # event_start stored via linked sports_signal_id at format time

        if leg_rows:
            await self.db.insert("parlay_legs", leg_rows)

        formatted_items: list[dict[str, Any]] = []
        for parlay_row, proposal in zip(saved_parlays, proposals):
            formatted_items.append(
                self.format_parlay(
                    parlay_row,
                    proposal["legs"],
                    signal_map=signal_map,
                )
            )

        if saved_parlays:
            from app.services.alert_service import AlertService

            await AlertService(self.db, self.user_id).notify_high_score_signals(
                "parlay",
                saved_parlays,
                title_fn=lambda p: f"Parlay · {p.get('style', 'built').title()} ({float(p.get('opportunity_score') or 0):.0f}/100)",
            )

        return {
            "parlays_created": len(saved_parlays),
            "legs_created": len(leg_rows),
            "styles_built": [p["style"] for p in proposals],
            "sports_pool": len(signals),
            "items": formatted_items,
            "message": None,
        }

    async def _expire_obsolete_parlays(self) -> int:
        """Expire parlays with stale data_as_of or past/unlinked legs."""
        try:
            rows = await self.db.select(
                "parlays",
                filters={
                    "user_id": f"eq.{self.user_id}",
                    "status": "eq.active",
                },
                limit=100,
            )
        except Exception as exc:
            logger.warning("Expire obsolete parlays: %s", exc)
            return 0

        expired = 0
        for row in rows:
            stale = not is_parlay_fresh(row)
            if not stale:
                legs = await self.get_legs(str(row["id"]))
                signal_map = await self._load_signals_for_legs(legs)
                stale = not is_parlay_actionable(legs, signal_map)
            if not stale:
                continue
            try:
                await self.db.update(
                    "parlays",
                    {
                        "id": f"eq.{row['id']}",
                        "user_id": f"eq.{self.user_id}",
                    },
                    {"status": "expired"},
                )
                expired += 1
            except Exception as exc:
                logger.info("Could not expire parlay %s: %s", row.get("id"), exc)
        return expired

    async def _list_actionable_formatted(
        self,
        *,
        style: str | None = None,
        category: str | None = None,
        limit: int = 10,
        status: str = "active",
        refresh_stale: bool = True,
    ) -> list[dict[str, Any]]:
        if refresh_stale:
            await self._expire_obsolete_parlays()

        rows = await self.db.select(
            "parlays",
            filters={
                "user_id": f"eq.{self.user_id}",
                "status": f"eq.{status}",
            },
            order="opportunity_score.desc",
            limit=max(limit * 4, 40),
        )
        rows = [r for r in rows if is_parlay_fresh(r)]
        if style:
            rows = [r for r in rows if str(r.get("style")) == style]

        formatted: list[dict[str, Any]] = []
        for row in rows:
            legs = await self.get_legs(str(row["id"]))
            signal_map = await self._load_signals_for_legs(legs)
            if not is_parlay_actionable(legs, signal_map):
                continue
            item = self.format_parlay(row, legs, signal_map=signal_map)
            if category and category not in (item.get("categories") or []):
                continue
            formatted.append(item)
            if len(formatted) >= limit:
                break
        return formatted

    async def _load_signals_for_legs(self, legs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        signal_ids = sorted(
            {
                self._signal_id(leg.get("sports_signal_id"))
                for leg in legs
                if leg.get("sports_signal_id")
            }
        )
        if not signal_ids:
            return {}

        try:
            rows = await self.db.select(
                "sports_signals",
                filters={
                    "user_id": f"eq.{self.user_id}",
                    "id": f"in.({','.join(signal_ids)})",
                },
                limit=len(signal_ids),
            )
        except Exception as exc:
            logger.warning("Batch load sports signals for parlay legs: %s", exc)
            rows = []

        signal_map = {self._signal_id(row["id"]): row for row in rows}
        if len(signal_map) < len(signal_ids):
            for signal_id in signal_ids:
                if signal_id in signal_map:
                    continue
                single = await self.db.select(
                    "sports_signals",
                    filters={"id": f"eq.{signal_id}", "user_id": f"eq.{self.user_id}"},
                    limit=1,
                )
                if single:
                    signal_map[self._signal_id(single[0]["id"])] = single[0]
        return signal_map

    async def parlay_category_catalog(self) -> list[dict[str, Any]]:
        items = await self._list_actionable_formatted(limit=100)
        return self._category_catalog_from_items(items)

    @staticmethod
    def _category_catalog_from_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        counts = category_counts(items)
        return [
            category_payload(slug, count=counts.get(slug, 0))
            for slug in PARLAY_CATEGORY_ORDER
        ]

    async def parlay_category_detail(self, slug: str, *, limit: int = 20) -> dict[str, Any] | None:
        from app.agents.parlay_categories import PARLAY_CATEGORY_CATALOG

        if slug not in PARLAY_CATEGORY_CATALOG:
            return None
        all_items = await self._list_actionable_formatted(limit=100)
        counts = category_counts(all_items)
        filtered = filter_parlays_by_category(all_items, slug)[:limit]
        return {
            **category_payload(slug, count=counts.get(slug, 0)),
            "items": filtered,
        }

    async def list_parlays(
        self,
        *,
        style: str | None = None,
        category: str | None = None,
        limit: int = 10,
        status: str = "active",
    ) -> list[dict[str, Any]]:
        return await self._list_actionable_formatted(
            style=style,
            category=category,
            limit=limit,
            status=status,
        )

    async def get_parlay_row(self, parlay_id: str) -> dict[str, Any] | None:
        rows = await self.db.select(
            "parlays",
            filters={"id": f"eq.{parlay_id}", "user_id": f"eq.{self.user_id}"},
            limit=1,
        )
        return rows[0] if rows else None

    async def get_parlay(self, parlay_id: str, *, for_edit: bool = False) -> dict[str, Any] | None:
        row = await self.get_parlay_row(parlay_id)
        if not row:
            return None
        if for_edit:
            return row
        if str(row.get("status")) != "active" or not is_parlay_fresh(row):
            return None
        legs = await self.get_legs(parlay_id)
        signal_map = await self._load_signals_for_legs(legs)
        if not is_parlay_actionable(legs, signal_map):
            return None
        return row

    async def create_custom_parlay(self, signal_ids: list[str]) -> dict[str, Any]:
        signals = await self._load_signals_by_ids(signal_ids)
        proposal = build_custom_parlay(signals)
        return await self._persist_parlay_proposal(proposal)

    async def update_parlay_legs(self, parlay_id: str, signal_ids: list[str]) -> dict[str, Any]:
        row = await self.get_parlay_row(parlay_id)
        if not row:
            raise ValueError("Parlay not found")
        if str(row.get("status")) not in ("active", "expired"):
            raise ValueError("Parlay cannot be edited")

        signals = await self._load_signals_by_ids(signal_ids)
        proposal = build_custom_parlay(signals)

        await self.db.delete(
            "parlay_legs",
            {"parlay_id": f"eq.{parlay_id}", "user_id": f"eq.{self.user_id}"},
        )

        now = datetime.now(UTC).isoformat()
        leg_rows = [
            {
                "parlay_id": parlay_id,
                "user_id": self.user_id,
                "leg_order": leg["leg_order"],
                "sport": leg["sport"],
                "event_name": leg["event_name"],
                "bet_type": leg["bet_type"],
                "selection": leg["selection"],
                "odds_american": leg["odds_american"],
                "leg_reason": leg["leg_reason"],
                "sports_signal_id": leg.get("sports_signal_id"),
            }
            for leg in proposal["legs"]
        ]
        if leg_rows:
            await self.db.insert("parlay_legs", leg_rows)

        updated = await self.db.update(
            "parlays",
            {"id": f"eq.{parlay_id}", "user_id": f"eq.{self.user_id}"},
            {
                "name": proposal["name"],
                "style": proposal["style"],
                "combined_odds_american": proposal["combined_odds_american"],
                "combined_odds_decimal": proposal["combined_odds_decimal"],
                "expected_value": proposal["expected_value"],
                "correlation_warning": proposal.get("correlation_warning"),
                "confidence_score": proposal["confidence_score"],
                "risk_score": proposal["risk_score"],
                "opportunity_score": proposal["opportunity_score"],
                "recommendation": proposal["recommendation"],
                "explanation": proposal["explanation"],
                "risk_warning": proposal["risk_warning"],
                "status": "active",
                "data_as_of": now,
                "updated_at": now,
            },
        )
        signal_map = {self._signal_id(s["id"]): s for s in signals}
        return self.format_parlay(updated[0], proposal["legs"], signal_map=signal_map)

    async def _load_signals_by_ids(self, signal_ids: list[str]) -> list[dict[str, Any]]:
        if len(signal_ids) < 2:
            raise ValueError("Parlay must have at least 2 legs")
        if len(signal_ids) > 6:
            raise ValueError("Parlay cannot exceed 6 legs")

        unique_ids = [self._signal_id(sid) for sid in signal_ids]
        if len(unique_ids) != len(set(unique_ids)):
            raise ValueError("Duplicate legs are not allowed")

        signal_map = await self._load_signals_for_ids(unique_ids)
        signals: list[dict[str, Any]] = []
        for sid in unique_ids:
            row = signal_map.get(sid)
            if not row:
                raise ValueError(f"Sports signal not found: {sid}")
            signals.append(row)
        return signals

    async def _load_signals_for_ids(self, signal_ids: list[str]) -> dict[str, dict[str, Any]]:
        if not signal_ids:
            return {}
        try:
            rows = await self.db.select(
                "sports_signals",
                filters={
                    "user_id": f"eq.{self.user_id}",
                    "id": f"in.({','.join(signal_ids)})",
                },
                limit=len(signal_ids),
            )
        except Exception as exc:
            logger.warning("Batch load sports signals: %s", exc)
            rows = []
        return {self._signal_id(row["id"]): row for row in rows}

    async def _persist_parlay_proposal(self, proposal: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(UTC).isoformat()
        saved = await self.db.insert(
            "parlays",
            [
                {
                    "user_id": self.user_id,
                    "name": proposal["name"],
                    "style": proposal["style"],
                    "combined_odds_american": proposal["combined_odds_american"],
                    "combined_odds_decimal": proposal["combined_odds_decimal"],
                    "expected_value": proposal["expected_value"],
                    "correlation_warning": proposal.get("correlation_warning"),
                    "confidence_score": proposal["confidence_score"],
                    "risk_score": proposal["risk_score"],
                    "opportunity_score": proposal["opportunity_score"],
                    "recommendation": proposal["recommendation"],
                    "explanation": proposal["explanation"],
                    "risk_warning": proposal["risk_warning"],
                    "status": "active",
                    "data_as_of": now,
                }
            ],
        )
        parlay_row = saved[0]
        parlay_id = str(parlay_row["id"])
        leg_rows = [
            {
                "parlay_id": parlay_id,
                "user_id": self.user_id,
                "leg_order": leg["leg_order"],
                "sport": leg["sport"],
                "event_name": leg["event_name"],
                "bet_type": leg["bet_type"],
                "selection": leg["selection"],
                "odds_american": leg["odds_american"],
                "leg_reason": leg["leg_reason"],
                "sports_signal_id": leg.get("sports_signal_id"),
            }
            for leg in proposal["legs"]
        ]
        if leg_rows:
            await self.db.insert("parlay_legs", leg_rows)

        signal_ids = [
            self._signal_id(leg.get("sports_signal_id"))
            for leg in proposal["legs"]
            if leg.get("sports_signal_id")
        ]
        signal_map = await self._load_signals_for_ids(signal_ids)
        return self.format_parlay(parlay_row, proposal["legs"], signal_map=signal_map)

    async def get_legs(self, parlay_id: str) -> list[dict[str, Any]]:
        rows = await self.db.select(
            "parlay_legs",
            filters={"parlay_id": f"eq.{parlay_id}", "user_id": f"eq.{self.user_id}"},
            order="leg_order.asc",
        )
        return rows

    @staticmethod
    def _book_odds_from_signal(signal: dict[str, Any]) -> list[dict[str, Any]]:
        snapshot = signal.get("scoring_snapshot") or {}
        line_movement = signal.get("line_movement") or {}
        return snapshot.get("book_odds") or line_movement.get("book_odds") or []

    @staticmethod
    def format_parlay(
        row: dict[str, Any],
        legs: list[dict[str, Any]],
        *,
        signal_map: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        signal_map = signal_map or {}
        formatted_legs = []
        for leg in legs:
            signal_id = ParlayService._signal_id(leg.get("sports_signal_id"))
            linked = signal_map.get(signal_id) if signal_id else None
            book_odds = leg.get("book_odds") or (
                ParlayService._book_odds_from_signal(linked) if linked else []
            )
            event_start = leg.get("event_start") or (
                linked.get("event_start") if linked else None
            )
            formatted_legs.append(
                {
                    "id": leg.get("id"),
                    "leg_order": leg.get("leg_order"),
                    "sport": leg.get("sport"),
                    "event_name": leg.get("event_name"),
                    "event_start": event_start,
                    "hours_until_start": hours_until_event(event_start),
                    "bet_type": leg.get("bet_type"),
                    "selection": leg.get("selection"),
                    "odds_american": leg.get("odds_american"),
                    "book_odds": book_odds,
                    "leg_reason": leg.get("leg_reason"),
                    "sports_signal_id": leg.get("sports_signal_id"),
                }
            )
        time_meta = compute_parlay_time_meta(legs, signal_map)
        return {
            "id": row["id"],
            "name": row.get("name"),
            "style": row.get("style"),
            "combined_odds_american": row.get("combined_odds_american"),
            "combined_odds_decimal": float(row.get("combined_odds_decimal") or 0),
            "expected_value": float(row.get("expected_value") or 0),
            "correlation_warning": row.get("correlation_warning"),
            "confidence_score": float(row.get("confidence_score") or 0),
            "risk_score": float(row.get("risk_score") or 0),
            "opportunity_score": float(row.get("opportunity_score") or 0),
            "recommendation": row.get("recommendation"),
            "explanation": row.get("explanation"),
            "risk_warning": row.get("risk_warning"),
            "legs": formatted_legs,
            "leg_count": len(formatted_legs),
            "sports": sorted({str(leg.get("sport")) for leg in formatted_legs if leg.get("sport")}),
            "preferred_book": PREFERRED_BOOK_KEY,
            "preferred_book_title": PREFERRED_BOOK_TITLE,
            "data_as_of": row.get("data_as_of"),
            "data_as_of_label": format_data_as_of_label(row.get("data_as_of")),
            **time_meta,
        }

    async def format_parlay_with_legs(self, row: dict[str, Any]) -> dict[str, Any]:
        legs = await self.get_legs(str(row["id"]))
        signal_map = await self._load_signals_for_legs(legs)
        return self.format_parlay(row, legs, signal_map=signal_map)
