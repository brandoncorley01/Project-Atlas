"""Sport-specific key metrics for Atlas insight team comparison."""

from __future__ import annotations

from typing import Any


def sport_family(sport_key: str | None, sport_label: str | None = None) -> str:
    key = str(sport_key or "").lower()
    label = str(sport_label or "").lower()
    blob = f"{key} {label}"
    if "basketball" in blob or "nba" in blob or "wnba" in blob or "ncaab" in blob:
        return "basketball"
    if "baseball" in blob or "mlb" in blob:
        return "baseball"
    if "americanfootball" in blob or "nfl" in blob or "ncaaf" in blob or "cfl" in blob:
        return "football"
    if "icehockey" in blob or "nhl" in blob:
        return "hockey"
    if "soccer" in blob or "epl" in blob or "mls" in blob or "liga" in blob:
        return "soccer"
    if "mma" in blob or "ufc" in blob or "boxing" in blob:
        return "combat"
    if "tennis" in blob or "atp" in blob or "wta" in blob:
        return "tennis"
    return "general"


def metric_labels(family: str) -> dict[str, str]:
    """Human labels for the scoring/allowed averages we derive from recent results."""
    profiles = {
        "basketball": {
            "scored": "PPG",
            "allowed": "Opp PPG",
            "diff": "Net PPG",
            "title": "Basketball keys",
            "unit": "pts",
        },
        "baseball": {
            "scored": "R/G",
            "allowed": "RA/G",
            "diff": "Run diff/G",
            "title": "Baseball keys",
            "unit": "runs",
        },
        "football": {
            "scored": "PPG",
            "allowed": "Opp PPG",
            "diff": "Point diff/G",
            "title": "Football keys",
            "unit": "pts",
        },
        "hockey": {
            "scored": "GF/G",
            "allowed": "GA/G",
            "diff": "Goal diff/G",
            "title": "Hockey keys",
            "unit": "goals",
        },
        "soccer": {
            "scored": "GF/G",
            "allowed": "GA/G",
            "diff": "Goal diff/G",
            "title": "Soccer keys",
            "unit": "goals",
        },
        "combat": {
            "scored": "Score rate",
            "allowed": "Opp score rate",
            "diff": "Margin",
            "title": "Combat form keys",
            "unit": "",
        },
        "tennis": {
            "scored": "Sets/games won rate",
            "allowed": "Sets/games allowed",
            "diff": "Margin",
            "title": "Tennis form keys",
            "unit": "",
        },
        "general": {
            "scored": "Avg scored",
            "allowed": "Avg allowed",
            "diff": "Avg margin",
            "title": "Matchup keys",
            "unit": "",
        },
    }
    return profiles.get(family, profiles["general"])


def _num(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _edge_side(home_val: float | None, away_val: float | None, *, higher_is_better: bool = True) -> str | None:
    if home_val is None or away_val is None:
        return None
    if abs(home_val - away_val) < 0.05:
        return "even"
    if higher_is_better:
        return "home" if home_val > away_val else "away"
    return "home" if home_val < away_val else "away"


def build_key_metrics_comparison(
    *,
    sport_key: str | None,
    sport_label: str | None,
    home: dict[str, Any] | None,
    away: dict[str, Any] | None,
    selection: str,
    bet_type: str,
    h2h: dict[str, Any] | None = None,
    pick_support: float = 0.0,
) -> dict[str, Any]:
    """
    Compare the major prediction keys we can derive from recent results:
    record/win%, offense, defense, margin, form, venue splits, H2H.
    """
    family = sport_family(sport_key, sport_label)
    labels = metric_labels(family)
    home = home or {}
    away = away or {}
    home_name = str(home.get("name") or "Home")
    away_name = str(away.get("name") or "Away")

    home_scored = _num(home.get("avg_scored"))
    away_scored = _num(away.get("avg_scored"))
    home_allowed = _num(home.get("avg_allowed"))
    away_allowed = _num(away.get("avg_allowed"))
    home_diff = (
        round(home_scored - home_allowed, 1)
        if home_scored is not None and home_allowed is not None
        else None
    )
    away_diff = (
        round(away_scored - away_allowed, 1)
        if away_scored is not None and away_allowed is not None
        else None
    )
    home_win = _num(home.get("win_pct"))
    away_win = _num(away.get("win_pct"))

    rows: list[dict[str, Any]] = [
        {
            "key": "record",
            "label": "Record (recent)",
            "home": home.get("record"),
            "away": away.get("record"),
            "edge": _edge_side(home_win, away_win),
            "home_sort": home_win,
            "away_sort": away_win,
        },
        {
            "key": "win_pct",
            "label": "Win %",
            "home": f"{home_win:.0f}%" if home_win is not None else None,
            "away": f"{away_win:.0f}%" if away_win is not None else None,
            "edge": _edge_side(home_win, away_win),
            "delta": round(home_win - away_win, 1) if home_win is not None and away_win is not None else None,
        },
        {
            "key": "scored",
            "label": labels["scored"],
            "home": home_scored,
            "away": away_scored,
            "edge": _edge_side(home_scored, away_scored, higher_is_better=True),
            "delta": round(home_scored - away_scored, 1)
            if home_scored is not None and away_scored is not None
            else None,
        },
        {
            "key": "allowed",
            "label": labels["allowed"],
            "home": home_allowed,
            "away": away_allowed,
            "edge": _edge_side(home_allowed, away_allowed, higher_is_better=False),
            "delta": round(home_allowed - away_allowed, 1)
            if home_allowed is not None and away_allowed is not None
            else None,
        },
        {
            "key": "diff",
            "label": labels["diff"],
            "home": home_diff,
            "away": away_diff,
            "edge": _edge_side(home_diff, away_diff, higher_is_better=True),
            "delta": round(home_diff - away_diff, 1)
            if home_diff is not None and away_diff is not None
            else None,
        },
        {
            "key": "form",
            "label": "Recent form",
            "home": home.get("form"),
            "away": away.get("form"),
            "edge": None,
        },
        {
            "key": "venue",
            "label": "Home / away split",
            "home": home.get("home_record") or None,
            "away": away.get("away_record") or None,
            "edge": None,
        },
    ]

    # Drop empty rows
    rows = [r for r in rows if r.get("home") not in (None, "", "0-0") or r.get("away") not in (None, "", "0-0")]

    if h2h and h2h.get("games"):
        rows.append(
            {
                "key": "h2h",
                "label": "Head-to-head",
                "home": f"{h2h.get('home_wins', 0)}W",
                "away": f"{h2h.get('away_wins', 0)}W",
                "edge": _edge_side(
                    float(h2h.get("home_wins") or 0),
                    float(h2h.get("away_wins") or 0),
                ),
                "note": f"{h2h.get('games')} meetings"
                + (f", {h2h.get('draws')} draws" if h2h.get("draws") else ""),
            }
        )

    home_edges = sum(1 for r in rows if r.get("edge") == "home")
    away_edges = sum(1 for r in rows if r.get("edge") == "away")

    analysis_bits: list[str] = []
    analysis_bits.append(
        f"{labels['title']}: comparing {home_name} vs {away_name} on the stats that usually drive "
        f"{family} outcomes — {labels['scored']}, {labels['allowed']}, {labels['diff']}, win rate, and form."
    )

    leaders: list[str] = []
    for row in rows:
        if row.get("edge") in {"home", "away"} and row.get("key") in {"scored", "allowed", "diff", "win_pct"}:
            leader = home_name if row["edge"] == "home" else away_name
            delta = row.get("delta")
            if delta is not None and row["key"] != "allowed":
                leaders.append(f"{leader} leads {row['label']} ({abs(float(delta)):.1f})")
            elif delta is not None and row["key"] == "allowed":
                leaders.append(f"{leader} allows fewer ({abs(float(delta)):.1f})")
            else:
                leaders.append(f"{leader} leads {row['label']}")
    if leaders:
        analysis_bits.append("Keys: " + "; ".join(leaders[:4]) + ".")

    if home_edges or away_edges:
        if home_edges > away_edges:
            analysis_bits.append(
                f"Stat board leans {home_name} ({home_edges}-{away_edges} key edges)."
            )
        elif away_edges > home_edges:
            analysis_bits.append(
                f"Stat board leans {away_name} ({away_edges}-{home_edges} key edges)."
            )
        else:
            analysis_bits.append("Key metrics are split — market price and matchup context matter more.")

    sel = selection.lower()
    if pick_support >= 12:
        analysis_bits.append(f"These keys support Atlas on {selection} for this {bet_type}.")
    elif pick_support <= -12:
        analysis_bits.append(
            f"These keys lean against {selection} — Atlas needs the market edge to carry more of the case."
        )
    elif "over" in sel or "under" in sel:
        combined = None
        if home_scored is not None and away_scored is not None:
            combined = round(home_scored + away_scored, 1)
        if combined is not None:
            analysis_bits.append(
                f"Combined recent {labels['scored']} ≈ {combined} — use that vs the total line for {selection}."
            )
    else:
        analysis_bits.append(
            f"Form sample is still building; Atlas weights available {family} keys plus market edge for {selection}."
        )

    available = bool(
        home.get("games_sampled") or away.get("games_sampled") or home_scored is not None or home.get("record")
    )

    return {
        "sport_family": family,
        "title": labels["title"],
        "metric_labels": labels,
        "home_name": home_name,
        "away_name": away_name,
        "rows": [
            {k: v for k, v in row.items() if k not in {"home_sort", "away_sort"}}
            for row in rows
        ],
        "home_edges": home_edges,
        "away_edges": away_edges,
        "analysis": " ".join(analysis_bits),
        "available": available,
    }
