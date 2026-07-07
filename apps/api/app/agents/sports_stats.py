"""Apply historical form and H2H stats to sports pick scoring."""

from __future__ import annotations

from typing import Any

from app.agents.sports_analyst import SportsBetSetup
from app.providers.sports.team_stats import MatchStats, match_stats_payload, normalize_team


def compute_pick_support(
    bet_type: str,
    selection: str,
    point: float | None,
    home: str,
    away: str,
    stats: MatchStats | None,
) -> tuple[float, dict[str, Any]]:
    """
    How much recent results support this pick (-100 to +100).
    Positive = historical trend aligns with the bet.
    """
    if stats is None or stats.sample_games < 2:
        return 0.0, {}

    home_key = normalize_team(home)
    away_key = normalize_team(away)
    sel_key = normalize_team(selection)

    home_pct = stats.home.win_pct
    away_pct = stats.away.win_pct
    home_margin = (stats.home.avg_scored or 0) - (stats.home.avg_allowed or 0)
    away_margin = (stats.away.avg_scored or 0) - (stats.away.avg_allowed or 0)

    support = 0.0
    notes: list[str] = []

    if bet_type == "moneyline":
        if sel_key == home_key:
            support += (home_pct - away_pct) * 80
            support += 8  # home court/field bump when records are close
            if stats.home.home_wins > stats.home.home_losses:
                support += 6
            notes.append(f"{stats.home.name} {stats.home.record_label()} last {stats.home.games_sampled}")
        elif sel_key == away_key:
            support += (away_pct - home_pct) * 80
            if stats.away.away_wins > stats.away.away_losses:
                support += 6
            notes.append(f"{stats.away.name} {stats.away.record_label()} last {stats.away.games_sampled}")

    elif bet_type == "spread" and point is not None:
        if sel_key == home_key:
            margin_edge = home_margin - away_margin
            cover_proxy = margin_edge + float(point)
            support += max(-40, min(40, cover_proxy * 4))
            notes.append(f"Home avg margin {home_margin:+.1f}")
        elif sel_key == away_key:
            margin_edge = away_margin - home_margin
            cover_proxy = margin_edge + float(point)
            support += max(-40, min(40, cover_proxy * 4))
            notes.append(f"Away avg margin {away_margin:+.1f}")

    elif bet_type == "total" and point is not None:
        combined = (stats.home.avg_scored or 0) + (stats.away.avg_scored or 0)
        if combined > 0:
            diff = combined - float(point)
            if selection.lower().startswith("over"):
                support += max(-35, min(35, diff * 3))
            else:
                support += max(-35, min(35, -diff * 3))
            notes.append(f"Recent combined avg {combined:.1f} vs line {point:g}")

    # Recent form streak (last 5)
    for team_form, key in ((stats.home, home_key), (stats.away, away_key)):
        recent = team_form.recent_results[:5]
        if not recent:
            continue
        wins = recent.count("W")
        if bet_type in ("moneyline", "spread") and sel_key == key:
            support += (wins - len(recent) / 2) * 6

    # Head-to-head when sample exists
    if stats.h2h_games >= 1 and bet_type == "moneyline":
        if sel_key == home_key and stats.h2h_home_wins > stats.h2h_away_wins:
            support += 10
            notes.append(f"H2H favors {home}")
        elif sel_key == away_key and stats.h2h_away_wins > stats.h2h_home_wins:
            support += 10
            notes.append(f"H2H favors {away}")

    support = max(-100.0, min(100.0, round(support, 1)))
    payload = match_stats_payload(stats) or {}
    if payload:
        payload["support_score"] = support
        payload["form_note"] = " · ".join(notes) if notes else stats.summary()
        payload["selection_team"] = selection
    return support, payload


def apply_stats_to_setup(setup: SportsBetSetup, support: float, details: dict[str, Any]) -> None:
    """Adjust scores and copy using historical context."""
    if not details or abs(support) < 1:
        return

    boost = max(-12.0, min(12.0, support * 0.12))
    setup.confidence_score = round(min(90.0, max(20.0, setup.confidence_score + boost * 0.7)), 1)
    setup.opportunity_score = round(min(95.0, max(0.0, setup.opportunity_score + boost * 0.5)), 1)

    if boost <= -8 and setup.opportunity_score < 42:
        return

    setup.scoring_snapshot["stats_support"] = round(support, 1)
    setup.scoring_snapshot["team_stats"] = details

    form_note = details.get("form_note") or details.get("summary")
    if not form_note:
        return

    direction = "supports" if support >= 12 else ("counters" if support <= -12 else "is mixed on")
    if direction != "is mixed on":
        setup.explanation += f" Recent form/H2H {direction} this play ({form_note})."
        if support >= 25:
            setup.bull_case += f" Historical trend: {form_note}."
        elif support <= -25:
            setup.bear_case += (
                f" Recent results lean the other way ({form_note}) despite the line edge."
            )
