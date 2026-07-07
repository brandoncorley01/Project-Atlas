"""Multi-parlay combinator — many tickets per style × time window from the sports pool."""

from __future__ import annotations

import itertools
from typing import Any, Callable

from app.agents.parlay_categories import compute_parlay_time_meta
from app.agents.sports_analyst import PREFERRED_BOOK_KEY, PREFERRED_BOOK_TITLE, primary_odds_from_signal
from app.services.freshness import hours_until_event
from app.services.sports_ranking import is_near_term, sort_for_parlay_pool

STYLE_ORDER = ("conservative", "balanced", "aggressive")

STYLE_CONFIG: dict[str, dict[str, Any]] = {
    "conservative": {
        "legs": 2,
        "min_opp": 36.0,
        "max_avg_risk": 60.0,
        "label": "Conservative",
        "subtitle": "2-leg · higher hit rate",
    },
    "balanced": {
        "legs": 3,
        "min_opp": 34.0,
        "max_avg_risk": 70.0,
        "label": "Balanced",
        "subtitle": "3-leg · risk/reward blend",
    },
    "aggressive": {
        "legs": 4,
        "min_opp": 32.0,
        "max_avg_risk": 80.0,
        "label": "Aggressive",
        "subtitle": "4-leg · max payout",
    },
}

TIME_LABELS = {
    "next_48h": "24–48h",
    "multi_day": "Multi-day",
}

TOP_SIGNALS_FOR_COMBOS = 16
MAX_COMBOS_TO_SCORE = 500
MAX_PARLAYS_PER_STYLE_CATEGORY = 6


def decimal_to_american(decimal_odds: float) -> int:
    if decimal_odds <= 1.0:
        return -110
    if decimal_odds >= 2.0:
        return round((decimal_odds - 1) * 100)
    return round(-100 / (decimal_odds - 1))


def detect_correlation(legs: list[dict[str, Any]]) -> str | None:
    events = [str(leg.get("event_name") or "") for leg in legs]
    if len(events) != len(set(events)):
        return "Multiple legs reference the same event — outcomes are highly correlated."

    sports = [str(leg.get("sport") or "") for leg in legs]
    if len(sports) != len(set(sports)):
        dupes = {s for s in sports if sports.count(s) > 1}
        names = ", ".join(sorted(dupes))
        return (
            f"Multiple legs in the same sport ({names}) — diversify across sports when possible; "
            "correlated results can wipe the ticket."
        )
    return None


def _leg_decimal(signal: dict[str, Any]) -> float:
    _, decimal = primary_odds_from_signal(signal)
    return decimal


def _book_odds_for_signal(signal: dict[str, Any]) -> list[dict[str, Any]]:
    snapshot = signal.get("scoring_snapshot") or {}
    line_movement = signal.get("line_movement") or {}
    return snapshot.get("book_odds") or line_movement.get("book_odds") or []


def _eligible_for_style(style: str, signal: dict[str, Any]) -> bool:
    cfg = STYLE_CONFIG[style]
    return (
        float(signal.get("opportunity_score") or 0) >= float(cfg["min_opp"])
        and float(signal.get("risk_score") or 100) <= float(cfg["max_avg_risk"]) + 18
    )


def _combo_is_valid(picks: tuple[dict[str, Any], ...]) -> bool:
    ids = [str(p.get("id")) for p in picks]
    if len(ids) != len(set(ids)):
        return False
    events = [str(p.get("event_name") or "") for p in picks]
    if len(events) != len(set(events)):
        return False
    return True


def _time_categories_for_picks(picks: tuple[dict[str, Any], ...]) -> list[str]:
    signal_map = {str(s["id"]): s for s in picks}
    legs = [
        {"sports_signal_id": s["id"], "event_start": s.get("event_start")}
        for s in picks
    ]
    return compute_parlay_time_meta(legs, signal_map).get("categories") or []


def _score_picks(picks: tuple[dict[str, Any], ...], style: str) -> dict[str, float] | None:
    cfg = STYLE_CONFIG[style]
    leg_count = int(cfg["legs"])
    if len(picks) != leg_count:
        return None

    avg_risk = sum(float(p.get("risk_score") or 0) for p in picks) / leg_count
    if avg_risk > float(cfg["max_avg_risk"]):
        return None

    combined_decimal = 1.0
    for leg in picks:
        combined_decimal *= _leg_decimal(leg)

    confidences = [float(p.get("confidence_score") or 0) for p in picks]
    risks = [float(p.get("risk_score") or 0) for p in picks]
    evs = [float(p.get("expected_value") or 0) for p in picks]

    confidence = min(confidences) * 0.85 + sum(confidences) / leg_count * 0.15
    risk = min(92.0, sum(risks) / leg_count + (leg_count - 2) * 6)
    combined_ev = sum(evs) / leg_count
    opportunity = min(
        95.0,
        confidence * 0.45 + (100 - risk) * 0.3 + combined_ev * 2.5 + leg_count * 2,
    )
    sports_count = len({str(p.get("sport")) for p in picks})

    return {
        "combined_decimal": combined_decimal,
        "combined_american": decimal_to_american(combined_decimal),
        "confidence": confidence,
        "risk": risk,
        "combined_ev": combined_ev,
        "opportunity": opportunity,
        "sports_count": float(sports_count),
        "payout_score": combined_decimal * (opportunity / 100.0),
    }


def _assemble_parlay(
    style: str,
    picks: tuple[dict[str, Any], ...],
    *,
    time_category: str,
    variant: int,
) -> dict[str, Any]:
    cfg = STYLE_CONFIG[style]
    metrics = _score_picks(picks, style)
    if not metrics:
        raise ValueError("invalid picks for style")

    combined_decimal = round(metrics["combined_decimal"], 4)
    combined_american = int(metrics["combined_american"])
    confidence = round(metrics["confidence"], 1)
    risk = round(metrics["risk"], 1)
    combined_ev = round(metrics["combined_ev"], 2)
    opportunity = round(metrics["opportunity"], 1)

    sports_list = sorted({str(p.get("sport")) for p in picks})
    sport_tag = "+".join(s[:4] for s in sports_list[:3])
    if len(sports_list) > 3:
        sport_tag += f"+{len(sports_list) - 3}"
    time_label = TIME_LABELS.get(time_category, time_category)
    name = f"{cfg['label']} · {time_label} #{variant} · {sport_tag}"

    leg_details = []
    for idx, signal in enumerate(picks, start=1):
        american, _ = primary_odds_from_signal(signal)
        reason = str(signal.get("bull_case") or signal.get("explanation") or "")[:220]
        leg_details.append(
            {
                "leg_order": idx,
                "sport": signal.get("sport"),
                "event_name": signal.get("event_name"),
                "event_start": signal.get("event_start"),
                "bet_type": signal.get("bet_type"),
                "selection": signal.get("selection"),
                "odds_american": american,
                "book_odds": _book_odds_for_signal(signal),
                "leg_reason": reason,
                "sports_signal_id": signal.get("id"),
            }
        )

    correlation_warning = detect_correlation(leg_details)
    slate_hint = "all legs start within 48h" if all(is_near_term(p) for p in picks) else "near-term slate"
    explanation = (
        f"{cfg['label']} {len(picks)}-leg parlay ({slate_hint}) across {', '.join(sports_list)}. "
        f"FanDuel combined {combined_american:+d} ({combined_decimal:.2f}x) — "
        f"avg leg EV {combined_ev:+.1f}%."
    )
    if correlation_warning:
        explanation += f" Note: {correlation_warning}"

    return {
        "name": name,
        "style": style,
        "time_category": time_category,
        "variant": variant,
        "combined_odds_american": combined_american,
        "combined_odds_decimal": combined_decimal,
        "expected_value": combined_ev,
        "correlation_warning": correlation_warning,
        "confidence_score": confidence,
        "risk_score": risk,
        "opportunity_score": opportunity,
        "recommendation": (
            f"{name} — FanDuel {combined_american:+d} ({combined_decimal:.2f}x)"
        ),
        "explanation": explanation,
        "risk_warning": (
            "Parlays require every leg to win. Higher odds mean lower hit rate. "
            "Not financial advice — bet responsibly."
        ),
        "legs": leg_details,
        "sports": sports_list,
        "preferred_book": PREFERRED_BOOK_KEY,
        "preferred_book_title": PREFERRED_BOOK_TITLE,
        "_payout_score": metrics["payout_score"],
        "_sports_count": metrics["sports_count"],
    }


def _leg_set_key(picks: tuple[dict[str, Any], ...]) -> frozenset[str]:
    return frozenset(str(p.get("id")) for p in picks)


def _generate_combos(
    eligible: list[dict[str, Any]],
    leg_count: int,
) -> list[tuple[dict[str, Any], ...]]:
    pool = sort_for_parlay_pool(eligible)[:TOP_SIGNALS_FOR_COMBOS]
    if len(pool) < leg_count:
        return []

    combos: list[tuple[dict[str, Any], ...]] = []
    for combo in itertools.combinations(pool, leg_count):
        if not _combo_is_valid(combo):
            continue
        combos.append(combo)
        if len(combos) >= MAX_COMBOS_TO_SCORE:
            break
    return combos


def _rank_for_bucket(
    scored: list[tuple[tuple[dict[str, Any], ...], dict[str, float]]],
    *,
    sort_key: Callable[[dict[str, float]], float],
) -> list[tuple[dict[str, Any], ...]]:
    return [
        picks
        for picks, _ in sorted(
            scored,
            key=lambda item: sort_key(item[1]),
            reverse=True,
        )
    ]


def build_all_parlays(signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build near-term parlays (next 48h legs only)."""
    if len(signals) < 2:
        return []

    signals = [s for s in sort_for_parlay_pool(signals) if is_near_term(s)]
    if len(signals) < 2:
        return []

    built: list[dict[str, Any]] = []
    used_leg_sets: set[frozenset[str]] = set()

    for style in STYLE_ORDER:
        cfg = STYLE_CONFIG[style]
        leg_count = int(cfg["legs"])
        eligible = [s for s in signals if _eligible_for_style(style, s)]
        if len(eligible) < leg_count:
            continue

        combos = _generate_combos(eligible, leg_count)
        buckets: dict[str, list[tuple[tuple[dict[str, Any], ...], dict[str, float]]]] = {
            "next_48h": [],
        }

        for combo in combos:
            if not all(is_near_term(p) for p in combo):
                continue
            metrics = _score_picks(combo, style)
            if not metrics:
                continue
            buckets["next_48h"].append((combo, metrics))

        for time_category in ("next_48h",):
            bucket = buckets[time_category]
            if not bucket:
                continue

            # Mix ranking strategies for variety within each bucket.
            ranking_passes: list[list[tuple[dict[str, Any], ...]]] = [
                _rank_for_bucket(bucket, sort_key=lambda m: m["opportunity"]),
                _rank_for_bucket(bucket, sort_key=lambda m: m["payout_score"]),
                _rank_for_bucket(bucket, sort_key=lambda m: m["combined_ev"]),
                _rank_for_bucket(bucket, sort_key=lambda m: m["sports_count"]),
                _rank_for_bucket(bucket, sort_key=lambda m: -m["risk"]),
            ]

            variant = 0
            for ranked in ranking_passes:
                for picks in ranked:
                    leg_key = _leg_set_key(picks)
                    if leg_key in used_leg_sets:
                        continue
                    used_leg_sets.add(leg_key)
                    variant += 1
                    parlay = _assemble_parlay(
                        style,
                        picks,
                        time_category=time_category,
                        variant=variant,
                    )
                    parlay.pop("_payout_score", None)
                    parlay.pop("_sports_count", None)
                    built.append(parlay)
                    if variant >= MAX_PARLAYS_PER_STYLE_CATEGORY:
                        break
                if variant >= MAX_PARLAYS_PER_STYLE_CATEGORY:
                    break

    built.sort(
        key=lambda p: (
            STYLE_ORDER.index(p["style"]) if p["style"] in STYLE_ORDER else 99,
            p.get("time_category") or "",
            -float(p.get("opportunity_score") or 0),
        ),
    )
    return built


# Backward-compatible single-parlay helper (tests / legacy callers).
def build_parlay(style: str, signals: list[dict[str, Any]]) -> dict[str, Any] | None:
    all_built = build_all_parlays(signals)
    for parlay in all_built:
        if parlay.get("style") == style:
            return parlay
    return None


def build_custom_parlay(signals: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a user-selected parlay from 2–6 sports signals (manual builder)."""
    leg_count = len(signals)
    if leg_count < 2:
        raise ValueError("Parlay must have at least 2 legs")
    if leg_count > 6:
        raise ValueError("Parlay cannot exceed 6 legs")

    picks = tuple(signals)
    if not _combo_is_valid(picks):
        raise ValueError("Each leg must be a unique event — no same-game parlays")

    combined_decimal = 1.0
    for leg in picks:
        combined_decimal *= _leg_decimal(leg)

    confidences = [float(p.get("confidence_score") or 0) for p in picks]
    risks = [float(p.get("risk_score") or 0) for p in picks]
    evs = [float(p.get("expected_value") or 0) for p in picks]

    confidence = min(confidences) * 0.85 + sum(confidences) / leg_count * 0.15
    risk = min(92.0, sum(risks) / leg_count + (leg_count - 2) * 6)
    combined_ev = sum(evs) / leg_count
    opportunity = min(
        95.0,
        confidence * 0.45 + (100 - risk) * 0.3 + combined_ev * 2.5 + leg_count * 2,
    )

    combined_decimal = round(combined_decimal, 4)
    combined_american = int(decimal_to_american(combined_decimal))
    confidence = round(confidence, 1)
    risk = round(risk, 1)
    combined_ev = round(combined_ev, 2)
    opportunity = round(opportunity, 1)

    sports_list = sorted({str(p.get("sport")) for p in picks})
    sport_tag = "+".join(s[:4] for s in sports_list[:3])
    if len(sports_list) > 3:
        sport_tag += f"+{len(sports_list) - 3}"
    name = f"Custom · {leg_count}-leg · {sport_tag}"

    leg_details = []
    for idx, signal in enumerate(picks, start=1):
        american, _ = primary_odds_from_signal(signal)
        reason = str(signal.get("bull_case") or signal.get("explanation") or "")[:220]
        leg_details.append(
            {
                "leg_order": idx,
                "sport": signal.get("sport"),
                "event_name": signal.get("event_name"),
                "event_start": signal.get("event_start"),
                "bet_type": signal.get("bet_type"),
                "selection": signal.get("selection"),
                "odds_american": american,
                "book_odds": _book_odds_for_signal(signal),
                "leg_reason": reason,
                "sports_signal_id": signal.get("id"),
            }
        )

    correlation_warning = detect_correlation(leg_details)
    explanation = (
        f"Custom {leg_count}-leg parlay across {', '.join(sports_list)}. "
        f"FanDuel combined {combined_american:+d} ({combined_decimal:.2f}x) — "
        f"avg leg EV {combined_ev:+.1f}%."
    )
    if correlation_warning:
        explanation += f" Note: {correlation_warning}"

    style = {2: "conservative", 3: "balanced", 4: "aggressive"}.get(leg_count, "custom")

    return {
        "name": name,
        "style": style,
        "combined_odds_american": combined_american,
        "combined_odds_decimal": combined_decimal,
        "expected_value": combined_ev,
        "correlation_warning": correlation_warning,
        "confidence_score": confidence,
        "risk_score": risk,
        "opportunity_score": opportunity,
        "recommendation": f"{name} — FanDuel {combined_american:+d} ({combined_decimal:.2f}x)",
        "explanation": explanation,
        "risk_warning": (
            "Parlays require every leg to win. Higher odds mean lower hit rate. "
            "Not financial advice — bet responsibly."
        ),
        "legs": leg_details,
        "sports": sports_list,
        "preferred_book": PREFERRED_BOOK_KEY,
        "preferred_book_title": PREFERRED_BOOK_TITLE,
        "leg_count": leg_count,
    }
