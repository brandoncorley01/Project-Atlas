"""Sports betting signal scoring — deterministic V1."""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.providers.sports.team_stats import MatchStats
from app.services.freshness import hours_until_event
from app.services.sports_ranking import NEAR_TERM_HOURS, timing_boost

# Primary sportsbook for displayed/playable lines (FanDuel).
PREFERRED_BOOK_KEY = "fanduel"
PREFERRED_BOOK_TITLE = "FanDuel"

# Order for multi-book display in the UI.
DISPLAY_BOOK_ORDER = (
    "fanduel",
    "draftkings",
    "betmgm",
    "williamhill_us",
    "betrivers",
    "bovada",
    "betus",
    "mybookieag",
    "fanatics",
    "pointsbetus",
)


@dataclass
class SportsBetSetup:
    sport: str
    event_name: str
    event_start: str | None
    bet_type: str
    selection: str
    odds_american: int
    odds_decimal: float
    expected_value: float
    line_movement: dict[str, Any]
    sharp_indicator: str | None
    confidence_score: float
    risk_score: float
    opportunity_score: float
    recommendation: str
    explanation: str
    bull_case: str
    bear_case: str
    invalidation: str
    suggested_action: str
    scoring_snapshot: dict[str, Any]


def american_to_implied_prob(odds: int) -> float:
    if odds > 0:
        return 100 / (odds + 100)
    return abs(odds) / (abs(odds) + 100)


def american_to_decimal(odds: int) -> float:
    if odds > 0:
        return round(1 + odds / 100, 4)
    return round(1 + 100 / abs(odds), 4)


def _format_selection(bet_type: str, name: str, point: float | None) -> str:
    if bet_type == "moneyline":
        return name
    if bet_type == "spread" and point is not None:
        sign = "+" if point > 0 else ""
        return f"{name} {sign}{point:g}"
    if bet_type == "total" and point is not None:
        return f"{name} {point:g}"
    return name


def _bet_type_label(bet_type: str) -> str:
    return {"moneyline": "Moneyline", "spread": "Spread", "total": "Total"}.get(
        bet_type, bet_type.capitalize()
    )


def _compute_edge(best_american: int, all_americans: list[int]) -> float:
    if not all_americans:
        return 0.0
    best_imp = american_to_implied_prob(best_american)
    median_imp = statistics.median(american_to_implied_prob(o) for o in all_americans)
    return round((median_imp - best_imp) * 100, 2)


def _hours_until(commence_time: str | None) -> float | None:
    return hours_until_event(commence_time)


def _format_kickoff(event_start: str | None) -> str:
    if not event_start:
        return "time TBD"
    try:
        text = str(event_start).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        dt = dt.astimezone(UTC)
        day = dt.day
        hour = dt.strftime("%I").lstrip("0") or "12"
        minute = dt.strftime("%M")
        ampm = dt.strftime("%p")
        return f"{dt.strftime('%a %b')} {day} · {hour}:{minute} {ampm} UTC"
    except (TypeError, ValueError):
        return "soon"


def _market_key_for_bet_type(bet_type: str) -> str:
    return {"moneyline": "h2h", "spread": "spreads", "total": "totals"}.get(bet_type, "h2h")


def _collect_outcome_odds(
    event: dict[str, Any],
    market_key: str,
    outcome_name: str,
    point: float | None = None,
) -> list[int]:
    prices: list[int] = []
    for book in event.get("bookmakers") or []:
        for market in book.get("markets") or []:
            if market.get("key") != market_key:
                continue
            for outcome in market.get("outcomes") or []:
                if outcome.get("name") != outcome_name:
                    continue
                if point is not None:
                    outcome_point = outcome.get("point")
                    if outcome_point is None or abs(float(outcome_point) - point) > 0.01:
                        continue
                try:
                    prices.append(int(outcome.get("price")))
                except (TypeError, ValueError):
                    continue
    return prices


def _collect_book_odds(
    event: dict[str, Any],
    market_key: str,
    outcome_name: str,
    point: float | None = None,
) -> list[dict[str, Any]]:
    """Per-book American odds for one outcome."""
    rows: list[dict[str, Any]] = []
    for book in event.get("bookmakers") or []:
        book_key = str(book.get("key") or "")
        if not book_key:
            continue
        for market in book.get("markets") or []:
            if market.get("key") != market_key:
                continue
            for outcome in market.get("outcomes") or []:
                if outcome.get("name") != outcome_name:
                    continue
                if point is not None:
                    outcome_point = outcome.get("point")
                    if outcome_point is None or abs(float(outcome_point) - point) > 0.01:
                        continue
                try:
                    american = int(outcome.get("price"))
                except (TypeError, ValueError):
                    continue
                rows.append(
                    {
                        "key": book_key,
                        "title": str(book.get("title") or book_key.replace("_", " ").title()),
                        "american": american,
                        "decimal": american_to_decimal(american),
                        "is_primary": book_key == PREFERRED_BOOK_KEY,
                    }
                )
                break
    order = {k: i for i, k in enumerate(DISPLAY_BOOK_ORDER)}
    rows.sort(key=lambda r: (order.get(r["key"], 999), r["title"]))
    return rows


def _select_primary_odds(book_odds: list[dict[str, Any]], all_prices: list[int]) -> int | None:
    """FanDuel line when posted; otherwise best price across the market."""
    for row in book_odds:
        if row.get("key") == PREFERRED_BOOK_KEY:
            return int(row["american"])
    return _best_price(all_prices)


def primary_odds_from_signal(signal: dict[str, Any]) -> tuple[int, float]:
    """Resolve FanDuel-first odds from a persisted sports signal."""
    snapshot = signal.get("scoring_snapshot") or {}
    book_odds = snapshot.get("book_odds") or signal.get("book_odds") or []
    for row in book_odds:
        if row.get("key") == PREFERRED_BOOK_KEY and row.get("american") is not None:
            american = int(row["american"])
            return american, float(row.get("decimal") or american_to_decimal(american))
    american = int(signal.get("odds_american") or -110)
    return american, float(signal.get("odds_decimal") or american_to_decimal(american))


def _best_price(prices: list[int]) -> int | None:
    if not prices:
        return None
    # Better payout = higher decimal odds
    return max(prices, key=lambda p: american_to_decimal(p))


def analyze_event(
    event: dict[str, Any],
    *,
    match_stats: MatchStats | None = None,
    calibration: dict[str, Any] | None = None,
) -> list[SportsBetSetup]:
    """Extract ranked bet opportunities from a single Odds API event."""
    from app.agents.sports_stats import apply_stats_to_setup, compute_pick_support

    cal = calibration or {}
    min_edge = float(cal.get("sports_min_edge_pct", 1.0))
    min_opportunity = float(cal.get("sports_min_opportunity", 38.0))
    confidence_dampen = float(cal.get("sports_confidence_dampen", 0.0))
    sport_key = str(event.get("_sport_key") or "")
    home = str(event.get("home_team") or "")
    away = str(event.get("away_team") or "")
    if not home or not away:
        return []

    sport = str(event.get("_sport_label") or event.get("sport_title") or "Sports")
    event_name = f"{away} @ {home}"
    event_start = event.get("commence_time")
    hours = _hours_until(event_start)
    if hours is not None and hours <= 0:
        return []

    book_count = len(event.get("bookmakers") or [])

    candidates: list[dict[str, Any]] = []

    # Moneyline
    for team in (home, away):
        prices = _collect_outcome_odds(event, "h2h", team)
        book_odds = _collect_book_odds(event, "h2h", team)
        primary = _select_primary_odds(book_odds, prices)
        if primary is None:
            continue
        edge = _compute_edge(primary, prices)
        candidates.append(
            {
                "bet_type": "moneyline",
                "selection": team,
                "point": None,
                "odds_american": primary,
                "edge": edge,
                "book_count": len(prices),
                "book_odds": book_odds,
            }
        )

    # Spreads — use home line as anchor
    home_spread_prices = _collect_outcome_odds(event, "spreads", home)
    away_spread_prices = _collect_outcome_odds(event, "spreads", away)
    home_point = None
    away_point = None
    for book in event.get("bookmakers") or []:
        for market in book.get("markets") or []:
            if market.get("key") != "spreads":
                continue
            for outcome in market.get("outcomes") or []:
                if outcome.get("name") == home and home_point is None:
                    home_point = outcome.get("point")
                if outcome.get("name") == away and away_point is None:
                    away_point = outcome.get("point")

    if home_point is not None:
        prices = _collect_outcome_odds(event, "spreads", home, float(home_point))
        book_odds = _collect_book_odds(event, "spreads", home, float(home_point))
        primary = _select_primary_odds(book_odds, prices)
        if primary is not None:
            candidates.append(
                {
                    "bet_type": "spread",
                    "selection": home,
                    "point": float(home_point),
                    "odds_american": primary,
                    "edge": _compute_edge(primary, prices),
                    "book_count": len(prices),
                    "book_odds": book_odds,
                }
            )
    if away_point is not None:
        prices = _collect_outcome_odds(event, "spreads", away, float(away_point))
        book_odds = _collect_book_odds(event, "spreads", away, float(away_point))
        primary = _select_primary_odds(book_odds, prices)
        if primary is not None:
            candidates.append(
                {
                    "bet_type": "spread",
                    "selection": away,
                    "point": float(away_point),
                    "odds_american": primary,
                    "edge": _compute_edge(primary, prices),
                    "book_count": len(prices),
                    "book_odds": book_odds,
                }
            )

    # Totals
    for side in ("Over", "Under"):
        point = None
        for book in event.get("bookmakers") or []:
            for market in book.get("markets") or []:
                if market.get("key") != "totals":
                    continue
                for outcome in market.get("outcomes") or []:
                    if outcome.get("name") == side and point is None:
                        point = outcome.get("point")
        if point is None:
            continue
        prices = _collect_outcome_odds(event, "totals", side, float(point))
        book_odds = _collect_book_odds(event, "totals", side, float(point))
        primary = _select_primary_odds(book_odds, prices)
        if primary is None:
            continue
        candidates.append(
            {
                "bet_type": "total",
                "selection": side,
                "point": float(point),
                "odds_american": primary,
                "edge": _compute_edge(primary, prices),
                "book_count": len(prices),
                "book_odds": book_odds,
            }
        )

    setups: list[SportsBetSetup] = []
    for cand in candidates:
        edge = float(cand["edge"])
        if edge < min_edge or cand["book_count"] < 2:
            continue

        bet_type = cand["bet_type"]
        odds = int(cand["odds_american"])
        selection_label = _format_selection(bet_type, cand["selection"], cand["point"])
        implied = american_to_implied_prob(odds)
        ev = round(edge * 0.85, 2)

        liquidity_boost = min(12, book_count * 1.5)
        timing_boost_val = timing_boost(hours)

        setup_strength = min(55, edge * 8 + liquidity_boost + timing_boost_val)
        if setup_strength < 18:
            continue

        risk = round(min(88, max(20, 38 + implied * 40 - edge * 3)), 1)
        confidence = round(min(90, setup_strength + min(10, book_count) - confidence_dampen), 1)
        opportunity = round(min(95, confidence * 0.5 + (100 - risk) * 0.3 + edge * 4 + timing_boost_val * 0.35), 1)

        # Far-out games need a stronger edge to surface — rescan later for those slates.
        if hours is not None and hours > NEAR_TERM_HOURS:
            opportunity -= min(15.0, (hours - NEAR_TERM_HOURS) * 0.12)
        if opportunity < min_opportunity:
            continue

        sharp = "steam" if edge >= 3.5 else ("value" if edge >= 2.0 else None)
        type_label = _bet_type_label(bet_type)

        kickoff = _format_kickoff(event_start)
        has_fanduel = any(b.get("key") == PREFERRED_BOOK_KEY for b in cand.get("book_odds") or [])
        book_label = PREFERRED_BOOK_TITLE if has_fanduel else "market best"
        recommendation = f"{type_label} — {selection_label} · {kickoff} ({sport})"
        explanation = (
            f"Bet {selection_label} ({type_label.lower()}) on {event_name}, starting {kickoff}. "
            f"{book_label} line {odds:+d} across {cand['book_count']} books — "
            f"{edge:.1f}% edge vs market median (EV proxy {ev:+.1f}%)."
        )
        bull_case = (
            f"{book_label} {odds:+d} on {selection_label} is {edge:.1f}% better than the median "
            f"price at {cand['book_count']} books before {kickoff}."
        )
        bear_case = (
            f"Line moves against {selection_label} before kickoff, or late injury/news "
            f"not yet in the odds, would weaken this {edge:.1f}% edge."
        )
        invalidation = "Closing line moves 1+ point against this side or odds shorten materially."
        suggested_action = f"Play {odds:+d} on FanDuel for {selection_label}" if has_fanduel else (
            f"Target {odds:+d} or better on {selection_label}"
        )

        market_key = _market_key_for_bet_type(bet_type)
        line_movement = {
            "opening_odds": odds,
            "consensus_books": cand["book_count"],
            "edge_pct": edge,
            "preferred_book": PREFERRED_BOOK_KEY,
            "preferred_book_title": PREFERRED_BOOK_TITLE,
            "book_odds": cand.get("book_odds") or [],
            "market_median_implied": round(
                statistics.median(
                    american_to_implied_prob(p)
                    for p in _collect_outcome_odds(
                        event,
                        market_key,
                        cand["selection"],
                        cand["point"],
                    )
                )
                * 100,
                2,
            ),
            "event_id": event.get("id"),
        }

        setups.append(
            SportsBetSetup(
                sport=sport,
                event_name=event_name,
                event_start=event_start,
                bet_type=bet_type,
                selection=selection_label,
                odds_american=odds,
                odds_decimal=american_to_decimal(odds),
                expected_value=ev,
                line_movement=line_movement,
                sharp_indicator=sharp,
                confidence_score=confidence,
                risk_score=risk,
                opportunity_score=opportunity,
                recommendation=recommendation,
                explanation=explanation,
                bull_case=bull_case,
                bear_case=bear_case,
                invalidation=invalidation,
                suggested_action=suggested_action,
                scoring_snapshot={
                    "edge_pct": edge,
                    "implied_prob": round(implied * 100, 2),
                    "book_count": book_count,
                    "book_odds": cand.get("book_odds") or [],
                    "preferred_book": PREFERRED_BOOK_KEY,
                    "preferred_book_title": PREFERRED_BOOK_TITLE,
                    "hours_to_start": round(hours, 1) if hours is not None else None,
                    "sport_key": sport_key,
                    "event_id": event.get("id"),
                    "home_team": home,
                    "away_team": away,
                    "pick": {
                        "bet_type": bet_type,
                        "team_or_side": cand["selection"],
                        "point": cand.get("point"),
                    },
                    "market_context": {
                        "expected_value": ev,
                        "sharp_indicator": sharp,
                        "bet_type": bet_type,
                    },
                },
            )
        )
        support, stats_detail = compute_pick_support(
            bet_type,
            cand["selection"],
            cand.get("point"),
            home,
            away,
            match_stats,
        )
        apply_stats_to_setup(setups[-1], support, stats_detail)

    return setups


def setup_to_row(user_id: str, setup: SportsBetSetup) -> dict[str, Any]:
    now = datetime.now(UTC).isoformat()
    return {
        "user_id": user_id,
        "sport": setup.sport,
        "event_name": setup.event_name,
        "event_start": setup.event_start,
        "bet_type": setup.bet_type,
        "selection": setup.selection,
        "odds_american": setup.odds_american,
        "odds_decimal": setup.odds_decimal,
        "expected_value": setup.expected_value,
        "line_movement": setup.line_movement,
        "injury_impact": None,
        "weather_impact": None,
        "travel_rest_impact": None,
        "public_betting_pct": None,
        "sharp_indicator": setup.sharp_indicator,
        "confidence_score": setup.confidence_score,
        "risk_score": setup.risk_score,
        "opportunity_score": setup.opportunity_score,
        "recommendation": setup.recommendation,
        "explanation": setup.explanation,
        "bull_case": setup.bull_case,
        "bear_case": setup.bear_case,
        "invalidation": setup.invalidation,
        "suggested_action": setup.suggested_action,
        "risk_warning": "Sports betting involves risk. Lines move quickly. This is not financial advice.",
        "scoring_snapshot": setup.scoring_snapshot,
        "status": "active",
        "data_as_of": now,
    }
