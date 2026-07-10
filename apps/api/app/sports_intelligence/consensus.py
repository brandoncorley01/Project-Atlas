"""Expert consensus calculations."""

from __future__ import annotations

from collections import Counter
from typing import Any

from app.sports_intelligence.adjustment import confidence_label
from app.sports_intelligence.types import IntelligenceConsensus


def build_consensus(
    signal_id: str,
    event_id: str | None,
    items: list[dict[str, Any]],
    *,
    model_selection: str,
    home_team: str,
    away_team: str,
) -> IntelligenceConsensus:
    active = [i for i in items if i.get("status") == "active"]
    picks = [
        i
        for i in active
        if i.get("source_type") in ("analyst_pick", "expert_prediction")
        and i.get("predicted_selection")
    ]
    news_items = [i for i in active if i.get("source_type") in ("news_article", "injury_update")]

    home_w, away_w, total_w = _weighted_support(picks, home_team, away_team)
    home_pct = round(home_w / total_w * 100, 1) if total_w else None
    away_pct = round(away_w / total_w * 100, 1) if total_w else None

    majority_pick = _majority_pick(picks, home_team, away_team)
    minority_pick = _minority_pick(picks, majority_pick, home_team, away_team)
    majority_reasons = _top_reasons(picks, limit=4)
    minority_reasons = _minority_reasons(picks, majority_pick, limit=3)

    expert_count = len({i.get("author_name") or i.get("id") for i in picks})
    source_count = len({i.get("source_name") or i.get("provider_id") for i in active})

    weighted_score = _consensus_strength(home_pct, away_pct, expert_count, source_count)
    agreement = _model_agreement(model_selection, majority_pick, weighted_score)
    verdict = _build_verdict(model_selection, majority_pick, agreement, weighted_score)
    news_summary = _summarize_news(news_items)
    injury_summary = _summarize_injuries(active)
    contrarian = _contrarian_summary(picks, majority_pick, minority_pick)

    adj_placeholder = 0.0
    label = confidence_label(50.0)

    return IntelligenceConsensus(
        signal_id=signal_id,
        event_id=event_id,
        expert_count=expert_count,
        source_count=source_count,
        home_support_pct=home_pct,
        away_support_pct=away_pct,
        top_consensus_pick=majority_pick,
        weighted_consensus_score=weighted_score,
        contrarian_summary=contrarian,
        majority_reasoning=majority_reasons,
        minority_reasoning=minority_reasons,
        key_news_summary=news_summary,
        injury_impact_summary=injury_summary,
        model_agreement_status=agreement,
        confidence_adjustment=adj_placeholder,
        confidence_label=label,
        verdict=verdict,
        items=active[:12],
    )


def _weight_item(item: dict[str, Any]) -> float:
    rel = float(item.get("relevance_score") or 0.5)
    fresh = float(item.get("freshness_score") or 0.5)
    rel_src = float(item.get("source_reliability_score") or 0.5)
    conf = float(item.get("confidence_score") or 55.0) / 100.0
    w = rel_src * rel * fresh * (0.5 + conf * 0.5)
    return max(0.15, min(1.0, w))


def _weighted_support(
    picks: list[dict[str, Any]],
    home_team: str,
    away_team: str,
) -> tuple[float, float, float]:
    home_w = away_w = 0.0
    for item in picks:
        w = _weight_item(item)
        side = str(item.get("predicted_side") or "")
        sel = str(item.get("predicted_selection") or "").lower()
        if side == "home" or home_team.lower() in sel:
            home_w += w
        elif side == "away" or away_team.lower() in sel:
            away_w += w
    total = home_w + away_w
    return home_w, away_w, total or 1.0


def _majority_pick(picks: list[dict[str, Any]], home_team: str, away_team: str) -> str | None:
    if not picks:
        return None
    counter: Counter[str] = Counter()
    for item in picks:
        sel = item.get("predicted_selection")
        if sel:
            counter[str(sel)] += 1
        elif item.get("predicted_side") == "home":
            counter[home_team] += 1
        elif item.get("predicted_side") == "away":
            counter[away_team] += 1
    if not counter:
        return None
    return counter.most_common(1)[0][0]


def _minority_pick(
    picks: list[dict[str, Any]],
    majority: str | None,
    home_team: str,
    away_team: str,
) -> str | None:
    if not picks or not majority:
        return None
    for item in picks:
        sel = str(item.get("predicted_selection") or "")
        if sel and sel != majority:
            return sel
    alt = away_team if majority.lower() in home_team.lower() else home_team
    return alt if alt != majority else None


def _top_reasons(picks: list[dict[str, Any]], *, limit: int) -> list[str]:
    reasons: list[str] = []
    for item in picks:
        for r in item.get("key_arguments") or []:
            if r and r not in reasons:
                reasons.append(str(r))
            if len(reasons) >= limit:
                return reasons
    return reasons


def _minority_reasons(
    picks: list[dict[str, Any]],
    majority: str | None,
    *,
    limit: int,
) -> list[str]:
    reasons: list[str] = []
    for item in picks:
        sel = str(item.get("predicted_selection") or "")
        if majority and sel and sel == majority:
            continue
        for r in item.get("risk_factors") or item.get("key_arguments") or []:
            if r and r not in reasons:
                reasons.append(str(r))
            if len(reasons) >= limit:
                return reasons
    return reasons


def _consensus_strength(
    home_pct: float | None,
    away_pct: float | None,
    expert_count: int,
    source_count: int,
) -> float:
    if home_pct is None or away_pct is None:
        return 0.0
    lead = abs(home_pct - away_pct)
    diversity = min(1.0, source_count / 4.0)
    sample = min(1.0, expert_count / 5.0)
    return round(lead * diversity * sample, 1)


def _model_agreement(model_selection: str, consensus_pick: str | None, strength: float) -> str:
    if not consensus_pick:
        return "no_expert_data"
    model = model_selection.lower()
    pick = consensus_pick.lower()
    if pick in model or model in pick:
        return "agrees" if strength >= 30 else "lean_agrees"
    return "disagrees" if strength >= 35 else "mixed"


def _build_verdict(
    model_selection: str,
    consensus_pick: str | None,
    agreement: str,
    strength: float,
) -> str:
    if not consensus_pick:
        return (
            "Limited analyst coverage for this event. Atlas leans on market model, "
            "form, and verified headlines only."
        )
    if agreement == "agrees":
        return (
            f"Atlas agrees with the weighted expert lean toward {consensus_pick}. "
            f"Consensus strength is {strength:.0f}/100 — confirm line value before entry."
        )
    if agreement == "disagrees":
        return (
            f"Most tracked experts favor {consensus_pick}, but Atlas disagrees based on "
            f"market edge and model factors. Review both cases before betting."
        )
    return (
        f"Expert signals are mixed. Atlas keeps its model selection on {model_selection} "
        f"with reduced intelligence weight."
    )


def _summarize_news(items: list[dict[str, Any]]) -> str | None:
    if not items:
        return None
    titles = [str(i.get("title") or "") for i in items[:3] if i.get("title")]
    if not titles:
        return None
    return "Recent headlines: " + "; ".join(titles)


def _summarize_injuries(items: list[dict[str, Any]]) -> str | None:
    injury_items = [i for i in items if i.get("source_type") == "injury_update"]
    if not injury_items:
        return None
    notes = []
    for item in injury_items[:3]:
        for inj in item.get("injury_mentions") or []:
            note = inj.get("note") or inj.get("player") or item.get("title")
            if note:
                notes.append(str(note))
    return "; ".join(notes[:3]) if notes else injury_items[0].get("title")


def _contrarian_summary(
    picks: list[dict[str, Any]],
    majority: str | None,
    minority: str | None,
) -> str | None:
    if not majority or not minority or len(picks) < 2:
        return None
    return f"Contrarian view: some analysts prefer {minority} vs majority on {majority}."
