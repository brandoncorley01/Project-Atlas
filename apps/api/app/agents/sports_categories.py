"""Sports bet category definitions, tagging, and sorting."""

from __future__ import annotations

from typing import Any, Callable

from app.services.sports_ranking import composite_score, is_near_term

CATEGORY_CATALOG: dict[str, dict[str, str]] = {
    "top_picks": {
        "title": "Top Picks",
        "short_label": "Top Picks",
        "description": "Best overall plays — highest opportunity score blending edge, confidence, and risk.",
        "guide": (
            "Top Picks rank every active signal by opportunity score (0–100). Atlas weights estimated "
            "market edge, book consensus, timing to game start, and risk profile. Use this view when you "
            "want the single best starting point — plays that balance payout potential with a defensible "
            "probability of winning. Compare the FanDuel play line against other books in the odds strip "
            "before placing a bet."
        ),
    },
    "best_edge": {
        "title": "Best Edge",
        "short_label": "Best Edge",
        "description": "Lines that beat the market median by the widest implied-probability gap.",
        "guide": (
            "Best Edge bets show the largest gap between FanDuel (or best available) pricing and the "
            "median price across all tracked sportsbooks. Edge is expressed as implied probability "
            "advantage — e.g. a 3% edge means the line is 3 percentage points cheaper than the market "
            "consensus. These are core +EV spots for sharp bettors. Edge can shrink quickly as books "
            "adjust, so act before line moves. Pair with the news panel to confirm no injury or lineup "
            "news is already priced in."
        ),
    },
    "highest_ev": {
        "title": "Highest EV",
        "short_label": "Highest EV",
        "description": "Plays with the strongest expected-value proxy from edge and market context.",
        "guide": (
            "Expected Value (EV) here is a conservative proxy derived from market edge and book depth. "
            "Higher EV plays offer more theoretical long-run profit per dollar risked, assuming your "
            "edge estimate holds. EV alone does not guarantee a win on any single bet — it identifies "
            "where the odds appear mispriced relative to the market. Best used alongside confidence "
            "and risk scores; avoid oversized stakes on high-EV longshots."
        ),
    },
    "most_likely": {
        "title": "Most Likely",
        "short_label": "Most Likely",
        "description": "Favorites and high implied-probability sides — highest win probability.",
        "guide": (
            "Most Likely picks have the highest implied win probability based on current American odds "
            "(typically favorites at −110 to −300 or stronger). These are lower-payout, higher-hit-rate "
            "plays suited for building confidence, parlay anchors, or conservative bankroll strategies. "
            "Lower risk scores often correlate here, but juice on heavy favorites can still erode ROI — "
            "check that edge remains positive vs the market median."
        ),
    },
    "greatest_odds": {
        "title": "Greatest Odds",
        "short_label": "Longshots",
        "description": "Biggest payouts — underdogs and plus-money lines with the highest decimal odds.",
        "guide": (
            "Greatest Odds surfaces the highest-payout plays — underdogs, plus-money sides, and long "
            "prices. These carry lower win rates but larger returns when they hit. Ideal for small-stake "
            "lottery-style bets or multi-leg parlay spice, not core bankroll allocation. Always verify "
            "news: a +400 underdog with a key injury reported may be correctly priced, not a value spot."
        ),
    },
    "steam_moves": {
        "title": "Steam Moves",
        "short_label": "Steam",
        "description": "Sharp steam indicators — edge ≥ 3.5% vs market median.",
        "guide": (
            "Steam Moves flag lines where Atlas detects sharp-style value: edge of 3.5% or more against "
            "the market median across multiple books. In betting markets, 'steam' often signals "
            "professional money moving a number before the public catches up. These can move fast — "
            "if FanDuel still shows the edge while other books have adjusted, there may be a short "
            "window to act. Cross-check recent news for late-breaking injury or weather updates."
        ),
    },
    "value_plays": {
        "title": "Value Plays",
        "short_label": "Value",
        "description": "Solid +EV spots with edge ≥ 2% — reliable value without extreme steam.",
        "guide": (
            "Value Plays sit in the sweet spot between recreational betting and sharp steam: at least "
            "2% edge vs market median with multi-book confirmation. These are workhorse +EV bets for "
            "daily volume — not as flashy as longshots, not as chalky as favorites. Review the "
            "multi-book odds strip to see if FanDuel is still best, or if another book offers an "
            "even better number."
        ),
    },
    "safest_plays": {
        "title": "Safest Plays",
        "short_label": "Safest",
        "description": "Lowest risk scores among qualified +EV plays — steadier profiles.",
        "guide": (
            "Safest Plays filter for the lowest risk scores among signals that still meet the minimum "
            "opportunity threshold. Risk incorporates implied probability, edge stability, and bet type. "
            "Use this category when preserving bankroll matters more than maximizing upside — e.g. "
            "building a conservative parlay or avoiding volatile longshot exposure. Safer does not "
            "mean guaranteed; always respect the invalidation triggers on each card."
        ),
    },
    "starting_soon": {
        "title": "Starting Soon",
        "short_label": "Live Soon",
        "description": "Games kicking off within 48 hours — act before lines move.",
        "guide": (
            "Starting Soon surfaces plays for games in the next 48 hours. Atlas prioritizes this window "
            "because edges shrink as kickoff approaches and books adjust. Use this as your default slate — "
            "rescan later in the week for mid-week and weekend games. Pair with verified news when shown; "
            "odds-only plays still require checking injury reports before you bet."
        ),
    },
    "atlas_insight": {
        "title": "Atlas Insight",
        "short_label": "Insight",
        "description": "OpenAI-ranked FanDuel/DraftKings markets — props and game lines Atlas verified.",
        "guide": (
            "Atlas Insight picks are ranked from real FanDuel/DraftKings open markets using web consensus. "
            "They include player props and game lines. Confirm the number is still posted before betting."
        ),
    },
    "player_props": {
        "title": "Player Props",
        "short_label": "Props",
        "description": "Player prop markets — points, hits, yards, and more from verified books.",
        "guide": (
            "Player Props focus on individual athlete markets. Most props on the board come from Atlas Insight "
            "pulling FanDuel/DraftKings event odds. Filter by league above to narrow to WNBA, MLB, and others."
        ),
    },
}

CATEGORY_ORDER = (
    "starting_soon",
    "top_picks",
    "atlas_insight",
    "player_props",
    "best_edge",
    "highest_ev",
    "most_likely",
    "greatest_odds",
    "steam_moves",
    "value_plays",
    "safest_plays",
)


def _is_openai_web(row: dict[str, Any]) -> bool:
    snap = row.get("scoring_snapshot") or {}
    lm = row.get("line_movement") or {}
    return (
        bool(snap.get("openai_web"))
        or bool(lm.get("openai_web"))
        or str(snap.get("source") or "") == "openai_web"
        or str(lm.get("source") or "") == "openai_web"
        or str(row.get("pick_source") or "") == "openai_web"
    )


def _is_player_prop(row: dict[str, Any]) -> bool:
    snap = row.get("scoring_snapshot") or {}
    bet = str(row.get("bet_type") or "").lower()
    prop_market = str(snap.get("prop_market") or "").lower()
    return (
        bet == "player_prop"
        or bool(snap.get("is_player_prop"))
        or bool(snap.get("is_fight_prop"))
        or prop_market.startswith("fight_")
        or bet.startswith("player_")
        or bet.startswith("batter_")
        or bet.startswith("pitcher_")
    )


def _edge(row: dict[str, Any]) -> float:
    snap = row.get("scoring_snapshot") or {}
    lm = row.get("line_movement") or {}
    return float(snap.get("edge_pct") or lm.get("edge_pct") or 0)


def _implied_prob(row: dict[str, Any]) -> float:
    snap = row.get("scoring_snapshot") or {}
    if snap.get("implied_prob") is not None:
        return float(snap["implied_prob"])
    odds = int(row.get("odds_american") or -110)
    if odds > 0:
        return 100 / (odds + 100) * 100
    return abs(odds) / (abs(odds) + 100) * 100


def _sort_key_for_category(slug: str) -> Callable[[dict[str, Any]], float]:
    if slug == "best_edge":
        return _edge
    if slug == "highest_ev":
        return lambda r: float(r.get("expected_value") or 0)
    if slug == "most_likely":
        return _implied_prob
    if slug == "greatest_odds":
        return lambda r: float(r.get("odds_decimal") or 0)
    if slug == "safest_plays":
        return lambda r: -float(r.get("risk_score") or 100)
    if slug in {"atlas_insight", "player_props"}:
        return lambda r: float(r.get("opportunity_score") or 0)
    return lambda r: float(r.get("opportunity_score") or 0)


def categories_for_row(row: dict[str, Any]) -> list[str]:
    snap = row.get("scoring_snapshot") or {}
    stored = snap.get("categories")
    cats: list[str] = []
    if isinstance(stored, list) and stored:
        cats = [str(c) for c in stored]
    else:
        cats = ["top_picks"]
    # Always derive Insight / props membership even for older rows missing tags.
    if _is_openai_web(row) and "atlas_insight" not in cats:
        cats.append("atlas_insight")
    if _is_player_prop(row) and "player_props" not in cats:
        cats.append("player_props")
    if _is_openai_web(row) and "value_plays" not in cats:
        cats.append("value_plays")
    if "top_picks" not in cats:
        cats.append("top_picks")
    return cats


def tag_pool_categories(pool: list[dict[str, Any]], *, top_n: int = 8) -> None:
    """Assign category tags relative to the current signal pool."""
    if not pool:
        return

    def _tag_top(key_fn: Callable[[dict[str, Any]], float], slug: str, n: int = top_n) -> None:
        ranked = sorted(pool, key=key_fn, reverse=True)
        for row in ranked[:n]:
            snap = row.setdefault("scoring_snapshot", {})
            cats: list[str] = list(snap.get("categories") or [])
            if slug not in cats:
                cats.append(slug)
            snap["categories"] = cats

    _tag_top(lambda r: float(r.get("opportunity_score") or 0), "top_picks", min(10, len(pool)))
    _tag_top(_edge, "best_edge")
    _tag_top(lambda r: float(r.get("expected_value") or 0), "highest_ev")
    _tag_top(_implied_prob, "most_likely")
    _tag_top(lambda r: float(r.get("odds_decimal") or 0), "greatest_odds")
    _tag_top(lambda r: -float(r.get("risk_score") or 100), "safest_plays")

    for row in pool:
        snap = row.setdefault("scoring_snapshot", {})
        cats: list[str] = list(snap.get("categories") or [])
        if is_near_term(row) and "starting_soon" not in cats:
            cats.insert(0, "starting_soon")
        sharp = row.get("sharp_indicator")
        edge = _edge(row)
        if sharp == "steam" and "steam_moves" not in cats:
            cats.append("steam_moves")
        if (sharp == "value" or edge >= 2.0 or _is_openai_web(row)) and "value_plays" not in cats:
            cats.append("value_plays")
        if _is_openai_web(row) and "atlas_insight" not in cats:
            cats.append("atlas_insight")
        if _is_player_prop(row) and "player_props" not in cats:
            cats.append("player_props")
        if not cats:
            cats.append("top_picks")
        snap["categories"] = cats


def filter_by_category(pool: list[dict[str, Any]], slug: str) -> list[dict[str, Any]]:
    if slug not in CATEGORY_CATALOG:
        return []
    if slug == "starting_soon":
        filtered = [
            r
            for r in pool
            if is_near_term(r) or "starting_soon" in categories_for_row(r) or _is_openai_web(r)
        ]
    elif slug == "steam_moves":
        filtered = [r for r in pool if r.get("sharp_indicator") == "steam" or "steam_moves" in categories_for_row(r)]
    elif slug == "value_plays":
        filtered = [
            r
            for r in pool
            if "value_plays" in categories_for_row(r)
            or r.get("sharp_indicator") == "value"
            or _edge(r) >= 2.0
            or _is_openai_web(r)
        ]
    elif slug == "atlas_insight":
        filtered = [r for r in pool if _is_openai_web(r) or "atlas_insight" in categories_for_row(r)]
    elif slug == "player_props":
        filtered = [r for r in pool if _is_player_prop(r) or "player_props" in categories_for_row(r)]
    elif slug == "top_picks":
        filtered = [r for r in pool if "top_picks" in categories_for_row(r) or _is_openai_web(r)]
        if not filtered:
            filtered = list(pool)
    else:
        # best_edge / highest_ev / etc. — include Insight so props don't vanish from edge boards
        filtered = [r for r in pool if slug in categories_for_row(r)]
        if slug in {"best_edge", "highest_ev", "most_likely", "greatest_odds", "safest_plays"}:
            filtered_ids = {str(r.get("id") or id(r)) for r in filtered}
            insight = [
                r
                for r in pool
                if _is_openai_web(r) and str(r.get("id") or id(r)) not in filtered_ids
            ]
            filtered = filtered + insight

    if not filtered and slug == "top_picks":
        filtered = list(pool)

    key_fn = _sort_key_for_category(slug)
    if slug == "starting_soon":
        filtered.sort(key=lambda r: (composite_score(r), key_fn(r)), reverse=True)
    else:
        filtered.sort(key=key_fn, reverse=True)
    return filtered


def category_counts(pool: list[dict[str, Any]]) -> dict[str, int]:
    counts = {slug: 0 for slug in CATEGORY_ORDER}
    for row in pool:
        for slug in categories_for_row(row):
            if slug in counts:
                counts[slug] += 1
    if pool and counts["top_picks"] == 0:
        counts["top_picks"] = len(pool)
    # Derived counts always reflect live membership.
    counts["atlas_insight"] = sum(1 for r in pool if _is_openai_web(r))
    counts["player_props"] = sum(1 for r in pool if _is_player_prop(r))
    return counts


def category_payload(slug: str, *, count: int = 0) -> dict[str, Any]:
    meta = CATEGORY_CATALOG.get(slug, {})
    return {
        "slug": slug,
        "title": meta.get("title", slug),
        "short_label": meta.get("short_label", slug),
        "description": meta.get("description", ""),
        "guide": meta.get("guide", ""),
        "count": count,
    }
