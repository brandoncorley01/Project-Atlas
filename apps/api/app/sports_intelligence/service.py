"""Sports intelligence orchestration service."""

from __future__ import annotations

import logging
import re
from typing import Any

from app.config import settings
from app.db.supabase_client import SupabaseClient
from app.services.sports_intelligence_db import SportsIntelligenceDb
from app.sports_intelligence.adjustment import compute_adjustment, confidence_label
from app.sports_intelligence.consensus import build_consensus
from app.sports_intelligence.dedup import deduplicate_items, mark_syndicate_duplicates
from app.sports_intelligence.normalization import normalize_item
from app.sports_intelligence.providers.registry import get_manual_provider, get_providers
from app.sports_intelligence.types import SportsIntelligenceItem

logger = logging.getLogger(__name__)


class SportsIntelligenceService:
    def __init__(self, db: SupabaseClient, user_id: str) -> None:
        self.db_layer = SportsIntelligenceDb(db, user_id)
        self.user_id = user_id

    @staticmethod
    def is_enabled() -> bool:
        return settings.is_intelligence_enabled()

    async def get_intelligence_payload(self, signal: dict[str, Any]) -> dict[str, Any] | None:
        if not self.is_enabled():
            return None

        signal_id = str(signal.get("id") or "")
        consensus_row = await self.db_layer.get_consensus(signal_id)
        items = await self.db_layer.list_items_for_signal(signal_id)

        if not consensus_row and not items:
            return {
                "enabled": True,
                "signal_id": signal_id,
                "status": "empty",
                "message": "No intelligence cached yet. Refresh to ingest sources.",
            }

        consensus = self._consensus_from_db(consensus_row, items, signal)
        adjustment = compute_adjustment(signal, consensus, active_items=items)
        consensus.confidence_label = confidence_label(adjustment.adjusted_confidence)

        return self._format_payload(signal, consensus, adjustment, items, consensus_row)

    async def refresh_signal_intelligence(self, signal: dict[str, Any]) -> dict[str, Any]:
        if not self.is_enabled():
            return {"enabled": False, "message": "Intelligence layer disabled"}

        signal_id = str(signal.get("id") or "")
        home, away, event_id = _participants(signal)
        params = {
            "signal_id": signal_id,
            "event_id": event_id,
            "league": signal.get("sport"),
            "home_team": home,
            "away_team": away,
            "event_start_time": signal.get("event_start"),
            "selection": signal.get("selection"),
            "signal": signal,
        }

        manual_rows = await self.db_layer.list_manual_items(signal_id)
        get_manual_provider().set_rows(manual_rows)

        normalized: list[SportsIntelligenceItem] = []
        provider_stats: list[dict[str, Any]] = []

        for provider in get_providers():
            if not provider.is_enabled():
                continue
            try:
                raw_items = await provider.fetch_event_content(params)
                provider_stats.append(
                    {"id": provider.id, "fetched": len(raw_items), "status": "ok"}
                )
                for raw in raw_items:
                    normalized.append(
                        normalize_item(
                            raw,
                            provider_id=provider.id,
                            source_name=provider.name,
                            signal_id=signal_id,
                            event_id=event_id,
                            reliability=provider.reliability_score,
                            home_team=home,
                            away_team=away,
                        )
                    )
            except Exception as exc:
                logger.warning("Provider %s failed: %s", provider.id, exc)
                provider_stats.append(
                    {"id": provider.id, "fetched": 0, "status": "error", "error": str(exc)[:120]}
                )

        existing_hashes = await self.db_layer.existing_hashes(signal_id)
        unique = deduplicate_items(normalized, existing_hashes)
        unique = mark_syndicate_duplicates(unique)
        to_store = [i for i in unique if i.status == "active"]
        saved = await self.db_layer.insert_items(to_store)
        items = await self.db_layer.list_items_for_signal(signal_id)

        consensus = build_consensus(
            signal_id,
            event_id,
            items,
            model_selection=str(signal.get("selection") or ""),
            home_team=home,
            away_team=away,
        )
        adjustment = compute_adjustment(signal, consensus, active_items=items)
        consensus.confidence_adjustment = adjustment.final_suggested_adjustment
        consensus.confidence_label = confidence_label(adjustment.adjusted_confidence)

        consensus_row = await self.db_layer.upsert_consensus(
            {
                "signal_id": signal_id,
                "event_id": event_id,
                "expert_count": consensus.expert_count,
                "source_count": consensus.source_count,
                "home_support_pct": consensus.home_support_pct,
                "away_support_pct": consensus.away_support_pct,
                "top_consensus_pick": consensus.top_consensus_pick,
                "weighted_consensus_score": consensus.weighted_consensus_score,
                "contrarian_summary": consensus.contrarian_summary,
                "majority_reasoning": consensus.majority_reasoning,
                "minority_reasoning": consensus.minority_reasoning,
                "key_news_summary": consensus.key_news_summary,
                "injury_impact_summary": consensus.injury_impact_summary,
                "confidence_adjustment": adjustment.final_suggested_adjustment,
                "model_agreement_status": consensus.model_agreement_status,
                "verdict": consensus.verdict,
                "confidence_label": consensus.confidence_label,
                "adjustment_payload": {
                    "adjustment": adjustment.__dict__,
                    "learning_mode": settings.atlas_intelligence_learning_mode,
                    "provider_stats": provider_stats,
                },
            }
        )

        if settings.atlas_intelligence_learning_mode == "observe":
            await self._record_observation(signal, consensus, adjustment)

        payload = self._format_payload(signal, consensus, adjustment, items, consensus_row)
        payload["refresh"] = {
            "items_added": len(saved),
            "providers": provider_stats,
        }
        return payload

    async def refresh_active_signals(self, signals: list[dict[str, Any]], *, limit: int = 12) -> dict:
        if not self.is_enabled():
            return {"enabled": False, "refreshed": 0}
        count = 0
        errors: list[str] = []
        for signal in signals[:limit]:
            try:
                await self.refresh_signal_intelligence(signal)
                count += 1
            except Exception as exc:
                errors.append(str(exc)[:80])
        return {"enabled": True, "refreshed": count, "errors": errors}

    async def add_manual_entry(self, entry: dict[str, Any]) -> dict[str, Any] | None:
        if not self.is_enabled():
            return None
        from app.sports_intelligence.normalization import content_hash

        entry["content_hash"] = content_hash(
            str(entry.get("title") or entry.get("selection") or ""),
            str(entry.get("summary") or ""),
            entry.get("source_url"),
        )
        return await self.db_layer.insert_manual_entry(entry)

    async def delete_manual_entry(self, item_id: str) -> bool:
        return await self.db_layer.delete_manual_entry(item_id)

    async def diagnostics(self) -> dict[str, Any]:
        if not self.is_enabled():
            return {"enabled": False}
        stats = await self.db_layer.provider_diagnostics()
        return {
            "enabled": True,
            "providers": [
                {"id": p.id, "name": p.name, "enabled": p.is_enabled()}
                for p in get_providers()
            ],
            **stats,
        }

    async def _record_observation(
        self,
        signal: dict[str, Any],
        consensus: Any,
        adjustment: Any,
    ) -> None:
        """Observation-mode learning — stored in consensus adjustment_payload only."""
        _ = signal, consensus, adjustment

    def _consensus_from_db(
        self,
        row: dict[str, Any] | None,
        items: list[dict[str, Any]],
        signal: dict[str, Any],
    ) -> Any:
        signal_id = str(signal.get("id") or "")
        home, away, event_id = _participants(signal)
        if row:
            from app.sports_intelligence.types import IntelligenceConsensus

            return IntelligenceConsensus(
                signal_id=signal_id,
                event_id=row.get("event_id") or event_id,
                expert_count=int(row.get("expert_count") or 0),
                source_count=int(row.get("source_count") or 0),
                home_support_pct=_float(row.get("home_support_pct")),
                away_support_pct=_float(row.get("away_support_pct")),
                top_consensus_pick=row.get("top_consensus_pick"),
                weighted_consensus_score=float(row.get("weighted_consensus_score") or 0),
                contrarian_summary=row.get("contrarian_summary"),
                majority_reasoning=list(row.get("majority_reasoning") or []),
                minority_reasoning=list(row.get("minority_reasoning") or []),
                key_news_summary=row.get("key_news_summary"),
                injury_impact_summary=row.get("injury_impact_summary"),
                model_agreement_status=str(row.get("model_agreement_status") or "unknown"),
                confidence_adjustment=float(row.get("confidence_adjustment") or 0),
                confidence_label=str(row.get("confidence_label") or "Lean"),
                verdict=str(row.get("verdict") or ""),
                items=items,
            )
        return build_consensus(
            signal_id,
            event_id,
            items,
            model_selection=str(signal.get("selection") or ""),
            home_team=home,
            away_team=away,
        )

    def _format_payload(
        self,
        signal: dict[str, Any],
        consensus: Any,
        adjustment: Any,
        items: list[dict[str, Any]],
        consensus_row: dict[str, Any] | None,
    ) -> dict[str, Any]:
        model_sel = str(signal.get("selection") or "")
        analysts = [
            {
                "source": (i.get("raw_metadata") or {}).get("source_name")
                or i.get("author_name")
                or "Source",
                "analyst": i.get("author_name"),
                "pick": i.get("predicted_selection"),
                "market": i.get("predicted_market"),
                "reasoning": (i.get("key_arguments") or [i.get("summary") or i.get("title")])[:2],
                "confidence": i.get("confidence_score"),
                "published_at": i.get("published_at"),
                "url": i.get("source_url"),
                "source_type": i.get("source_type"),
                "title": i.get("title"),
                "supports_atlas": _item_supports_atlas(i, model_sel),
            }
            for i in items
            if i.get("status") == "active"
        ][:12]

        supporting_analysts = [a for a in analysts if a.get("supports_atlas")][:6]

        news_updates = [
            {
                "title": i.get("title"),
                "summary": i.get("summary"),
                "url": i.get("source_url"),
                "published_at": i.get("published_at"),
                "type": i.get("source_type"),
            }
            for i in items
            if i.get("source_type")
            in ("news_article", "injury_update", "official_team_update", "analyst_pick")
            and i.get("status") == "active"
        ][:8]

        agrees = sum(1 for a in analysts if a.get("supports_atlas"))
        disagrees = sum(
            1
            for i in items
            if i.get("predicted_selection") and not _item_supports_atlas(i, model_sel)
        )

        generated_at = (consensus_row or {}).get("generated_at") or (consensus_row or {}).get(
            "updated_at"
        )

        return {
            "enabled": True,
            "signal_id": signal.get("id"),
            "last_updated": generated_at,
            "source_transparency": {
                "sources_analyzed": consensus.source_count,
                "unique_analysts": consensus.expert_count,
                "items_active": len([i for i in items if i.get("status") == "active"]),
                "video_transcripts_available": False,
                "injury_confirmed": bool(consensus.injury_impact_summary),
                "atlas_summarized": True,
            },
            "atlas_recommendation": {
                "selection": signal.get("selection"),
                "odds_american": signal.get("odds_american"),
                "raw_confidence": adjustment.original_model_confidence,
                "adjusted_confidence": adjustment.adjusted_confidence,
                "confidence_label": consensus.confidence_label,
                "expected_value": signal.get("expected_value"),
                "risk_score": signal.get("risk_score"),
                "primary_reasons": _atlas_primary_reasons(signal, consensus),
                "invalidation": signal.get("invalidation"),
            },
            "expert_consensus": {
                "expert_count": consensus.expert_count,
                "source_count": consensus.source_count,
                "weighted_consensus_score": consensus.weighted_consensus_score,
                "majority_selection": consensus.top_consensus_pick,
                "minority_selection": _minority_from_items(items, consensus.top_consensus_pick),
                "home_support_pct": consensus.home_support_pct,
                "away_support_pct": consensus.away_support_pct,
                "experts_agreeing_with_atlas": agrees,
                "experts_disagreeing_with_atlas": disagrees,
                "model_agreement": consensus.model_agreement_status,
            },
            "analyst_cards": analysts,
            "supporting_analysts": supporting_analysts,
            "news_updates": news_updates,
            "bull_case": signal.get("bull_case")
            or (
                consensus.majority_reasoning[0]
                if consensus.majority_reasoning
                and consensus.model_agreement_status in {"agrees", "lean_agrees"}
                else (consensus.minority_reasoning[0] if consensus.minority_reasoning else None)
            ),
            "bear_case": signal.get("bear_case")
            or (
                consensus.majority_reasoning[0]
                if consensus.majority_reasoning and consensus.model_agreement_status == "disagrees"
                else (consensus.minority_reasoning[0] if consensus.minority_reasoning else None)
            ),
            "verdict": consensus.verdict,
            "adjustment": {
                "expert": adjustment.expert_consensus_adjustment,
                "news": adjustment.news_adjustment,
                "injury": adjustment.injury_adjustment,
                "disagreement_penalty": adjustment.disagreement_penalty,
                "total": adjustment.final_suggested_adjustment,
                "explanation": adjustment.explanation,
            },
            "disclaimer": (
                "Atlas provides analysis and decision support, not guaranteed outcomes. "
                "Verify lines, injuries, and rules before wagering."
            ),
        }


def _item_supports_atlas(item: dict[str, Any], model_selection: str) -> bool:
    """True when the source's predicted side matches Atlas's pick."""
    if not model_selection:
        return False
    if (item.get("raw_metadata") or {}).get("supports_atlas") is True:
        return True
    predicted = str(item.get("predicted_selection") or "").strip()
    if not predicted:
        return False
    model = model_selection.lower()
    pred = predicted.lower()
    if pred in model or model in pred:
        return True
    model_tokens = {t for t in re.split(r"[\s/+-]+", model) if len(t) > 2}
    pred_tokens = {t for t in re.split(r"[\s/+-]+", pred) if len(t) > 2}
    return bool(model_tokens & pred_tokens)


def _participants(signal: dict[str, Any]) -> tuple[str, str, str | None]:
    snap = signal.get("scoring_snapshot") or {}
    home = str(snap.get("home_team") or "").strip()
    away = str(snap.get("away_team") or "").strip()
    event_id = snap.get("event_id")

    if home and away:
        return home, away, str(event_id) if event_id else None

    event = str(signal.get("event_name") or "")
    if " @ " in event:
        away_part, home_part = event.split(" @ ", 1)
        return home_part.strip(), away_part.strip(), str(event_id) if event_id else None
    if re.search(r"\s+vs\.?\s+", event, flags=re.I):
        parts = re.split(r"\s+vs\.?\s+", event, maxsplit=1, flags=re.I)
        if len(parts) == 2:
            return parts[0].strip(), parts[1].strip(), str(event_id) if event_id else None
    return home or "Home", away or "Away", str(event_id) if event_id else None


def _float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _atlas_primary_reasons(signal: dict[str, Any], consensus: Any) -> list[str]:
    """Reasons that support Atlas's pick — never opposing expert majority when they disagree."""
    reasons: list[str] = []
    agreement = str(getattr(consensus, "model_agreement_status", "") or "")
    if agreement in {"agrees", "lean_agrees"}:
        reasons.extend(list(getattr(consensus, "majority_reasoning", None) or [])[:3])
    elif agreement == "disagrees":
        # Experts favor the other side — lead with Atlas model case, then note the dissent.
        if signal.get("bull_case"):
            reasons.append(str(signal["bull_case"])[:240])
        if signal.get("explanation"):
            reasons.append(str(signal["explanation"])[:240])
        minority = list(getattr(consensus, "minority_reasoning", None) or [])[:2]
        reasons.extend(minority)
        top = getattr(consensus, "top_consensus_pick", None)
        if top:
            reasons.append(
                f"Tracked experts lean {top}; Atlas still prefers "
                f"{signal.get('selection')} on market edge + model factors."
            )
    else:
        if signal.get("bull_case"):
            reasons.append(str(signal["bull_case"])[:240])
        reasons.extend(list(getattr(consensus, "minority_reasoning", None) or [])[:2])
        reasons.extend(list(getattr(consensus, "majority_reasoning", None) or [])[:1])

    if signal.get("recommendation") and not reasons:
        reasons.append(str(signal["recommendation"]))
    # Deduplicate while preserving order
    seen: set[str] = set()
    out: list[str] = []
    for r in reasons:
        text = str(r or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
        if len(out) >= 4:
            break
    return out or [str(signal.get("recommendation") or "Atlas model selection")]


def _minority_from_items(items: list[dict[str, Any]], majority: str | None) -> str | None:
    if not majority:
        return None
    for item in items:
        sel = str(item.get("predicted_selection") or "")
        if sel and sel != majority:
            return sel
    return None
