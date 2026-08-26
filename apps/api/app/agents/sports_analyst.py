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
# American retail books guaranteed for MLB / WNBA / NFL / NBA boards.
US_PREFERRED_BOOK_KEYS = frozenset({"fanduel", "draftkings"})

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
    if bet_type in {"futures", "outright"}:
        return name
    if bet_type == "spread" and point is not None:
        sign = "+" if point > 0 else ""
        return f"{name} {sign}{point:g}"
    if bet_type == "total" and point is not None:
        return f"{name} {point:g}"
    return name


def _is_combat_sport_key(sport_key: str | None) -> bool:
    key = (sport_key or "").lower()
    return key.startswith("mma_") or key.startswith("boxing_") or key in {"mma", "boxing", "ufc"}


def _bet_type_label(bet_type: str) -> str:
    return {
        "moneyline": "Moneyline",
        "spread": "Spread",
        "total": "Total",
        "player_prop": "Player prop",
        "futures": "Futures",
        "outright": "Futures",
    }.get(bet_type, bet_type.capitalize())


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
    return {
        "moneyline": "h2h",
        "spread": "spreads",
        "total": "totals",
        "player_prop": "totals",
        "futures": "outrights",
        "outright": "outrights",
    }.get(bet_type, "h2h")


def _promote_combat_candidates(candidates: list[dict[str, Any]], *, sport_key: str) -> None:
    """Tag MMA/Boxing round totals + fight handicaps as player props."""
    if not _is_combat_sport_key(sport_key):
        return
    for cand in candidates:
        if cand.get("bet_type") == "total":
            cand["bet_type"] = "player_prop"
            cand["prop_market"] = "fight_total_rounds"
            cand["is_fight_prop"] = True
            cand["is_player_prop"] = True
        elif cand.get("bet_type") == "spread":
            cand["bet_type"] = "player_prop"
            cand["prop_market"] = "fight_spread"
            cand["is_fight_prop"] = True
            cand["is_player_prop"] = True
            cand["player_name"] = cand.get("selection")


def _combat_selection_label(cand: dict[str, Any]) -> str:
    bet_type = str(cand.get("bet_type") or "")
    point = cand.get("point")
    name = str(cand.get("selection") or "")
    if cand.get("prop_market") == "fight_total_rounds":
        if point is not None:
            return f"Fight {name} {float(point):g} Rounds"
        return f"Fight {name} Rounds"
    if cand.get("prop_market") == "fight_spread":
        return _format_selection("spread", name, float(point) if point is not None else None)
    return _format_selection(bet_type if bet_type != "player_prop" else "moneyline", name, point)


def _is_outright_event(event: dict[str, Any]) -> bool:
    if event.get("_is_outright"):
        return True
    key = str(event.get("_sport_key") or event.get("sport_key") or "").lower()
    if "_winner" in key or key.endswith("_winner"):
        return True
    for book in event.get("bookmakers") or []:
        for market in book.get("markets") or []:
            if market.get("key") in {"outrights", "outrights_lay"}:
                return True
    return False


def analyze_outright(
    event: dict[str, Any],
    *,
    calibration: dict[str, Any] | None = None,
) -> list[SportsBetSetup]:
    """Rank championship/season futures by +EV vs multi-book median."""
    max_per_market = 8

    cal = calibration or {}
    min_edge = float(cal.get("sports_min_edge_pct", 1.0))
    min_opportunity = float(cal.get("sports_min_opportunity", 28.0))
    confidence_dampen = float(cal.get("sports_confidence_dampen", 0.0))

    sport = str(event.get("_sport_label") or event.get("sport_title") or "Futures")
    event_name = str(event.get("sport_title") or sport)
    if "winner" not in event_name.lower() and "championship" not in event_name.lower():
        event_name = f"{event_name} Futures"
    event_start = event.get("commence_time")
    hours = _hours_until(event_start)
    if hours is not None and hours <= 0:
        return []

    # Collect every named outcome across books.
    names: set[str] = set()
    for book in event.get("bookmakers") or []:
        for market in book.get("markets") or []:
            if market.get("key") not in {"outrights", "outrights_lay"}:
                continue
            for outcome in market.get("outcomes") or []:
                name = str(outcome.get("name") or "").strip()
                if name:
                    names.add(name)

    candidates: list[dict[str, Any]] = []
    for name in names:
        prices = _collect_outcome_odds(event, "outrights", name)
        if len(prices) < 1:
            continue
        book_odds = _collect_book_odds(event, "outrights", name)
        primary = _select_primary_odds(book_odds, prices)
        if primary is None:
            continue
        edge = _compute_edge(primary, prices)
        if edge < min_edge and len(prices) >= 2:
            continue
        candidates.append(
            {
                "bet_type": "futures",
                "selection": name,
                "point": None,
                "odds_american": primary,
                "edge": edge,
                "book_count": len(prices),
                "book_odds": book_odds,
            }
        )

    candidates.sort(key=lambda c: (c["edge"], c["book_count"]), reverse=True)
    candidates = candidates[:max_per_market]

    setups: list[SportsBetSetup] = []
    book_count = len(event.get("bookmakers") or [])
    for cand in candidates:
        odds = int(cand["odds_american"])
        edge = float(cand["edge"])
        selection_label = cand["selection"]
        implied = american_to_implied_prob(odds)
        ev = round(edge * 0.7, 2)
        liquidity_boost = min(10, cand["book_count"] * 1.2)
        setup_strength = min(50, edge * 7 + liquidity_boost + 4)
        if setup_strength < 14:
            continue
        risk = round(min(92, max(25, 45 + implied * 35 - edge * 2)), 1)
        confidence = round(min(85, setup_strength + min(8, cand["book_count"]) - confidence_dampen), 1)
        opportunity = round(
            min(90, confidence * 0.45 + (100 - risk) * 0.25 + edge * 3.5 + 4),
            1,
        )
        if opportunity < min_opportunity:
            continue

        sharp = "value" if edge >= 2.0 else None
        kickoff = _format_kickoff(event_start)
        has_fanduel = any(
            (b.get("key") == PREFERRED_BOOK_KEY) for b in (event.get("bookmakers") or [])
        )
        book_label = PREFERRED_BOOK_TITLE if has_fanduel else "market best"
        recommendation = f"Futures — {selection_label} · {event_name}"
        explanation = (
            f"Futures bet on {selection_label} to win {event_name} "
            f"(settles around {kickoff}). {book_label} {odds:+d} across "
            f"{cand['book_count']} books — {edge:.1f}% edge vs market median."
        )
        bull_case = (
            f"{selection_label} at {odds:+d} is {edge:.1f}% better than the "
            f"multi-book median — early futures often offer the best number."
        )
        bear_case = (
            f"Long-dated futures can drift for months; injuries, trades, or "
            f"form swings can erase a {edge:.1f}% opening edge."
        )

        line_movement = {
            "opening_odds": odds,
            "consensus_books": cand["book_count"],
            "edge_pct": edge,
            "preferred_book": PREFERRED_BOOK_KEY,
            "preferred_book_title": PREFERRED_BOOK_TITLE,
            "book_odds": cand.get("book_odds") or [],
            "event_id": event.get("id"),
            "is_futures": True,
        }

        setups.append(
            SportsBetSetup(
                sport=sport,
                event_name=event_name,
                event_start=event_start,
                bet_type="futures",
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
                invalidation="Odds shorten materially or the contender's outlook collapses.",
                suggested_action=(
                    f"Play {odds:+d} on FanDuel for {selection_label}"
                    if has_fanduel
                    else f"Target {odds:+d} or better on {selection_label}"
                ),
                scoring_snapshot={
                    "edge_pct": edge,
                    "book_count": cand["book_count"],
                    "books_available": book_count,
                    "bet_type": "futures",
                    "is_futures": True,
                    "sport_key": event.get("_sport_key"),
                    "hours_until_start": hours,
                    "pick_origin": "atlas",
                    "atlas_presented": True,
                    "atlas_tracked": True,
                    "source": "odds_scan",
                    "pick": {"bet_type": "futures", "team_or_side": selection_label},
                },
            )
        )
    return setups


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
    """Best FanDuel/DraftKings price when posted; otherwise best market price.

    Using the better of the two US retail books (not FanDuel-only) so MLB/WNBA
    edges aren't wiped when DraftKings is the playable number.
    """
    us_rows = [r for r in book_odds if r.get("key") in US_PREFERRED_BOOK_KEYS]
    if us_rows:
        best = max(us_rows, key=lambda r: american_to_decimal(int(r["american"])))
        return int(best["american"])
    for row in book_odds:
        if row.get("key") == PREFERRED_BOOK_KEY:
            return int(row["american"])
    return _best_price(all_prices)


def _primary_book_label(book_odds: list[dict[str, Any]], primary_american: int) -> tuple[str, str]:
    """Book key/title that matches the playable American price (FD preferred on ties)."""
    us_rows = [r for r in book_odds if r.get("key") in US_PREFERRED_BOOK_KEYS]
    matches = [r for r in us_rows if int(r["american"]) == primary_american]
    if matches:
        matches.sort(key=lambda r: 0 if r.get("key") == PREFERRED_BOOK_KEY else 1)
        row = matches[0]
        return str(row["key"]), str(row.get("title") or row["key"])
    if any(r.get("key") == PREFERRED_BOOK_KEY for r in book_odds):
        return PREFERRED_BOOK_KEY, PREFERRED_BOOK_TITLE
    return "market", "market best"


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

    if _is_outright_event(event):
        return analyze_outright(event, calibration=calibration)

    cal = calibration or {}
    slate_mode = bool(cal.get("slate_mode"))
    min_edge = float(cal.get("sports_min_edge_pct", 0.4 if slate_mode else 0.6))
    min_opportunity = float(cal.get("sports_min_opportunity", 22.0 if slate_mode else 28.0))
    confidence_dampen = float(cal.get("sports_confidence_dampen", 0.0))
    strength_floor = 8.0 if slate_mode else 12.0
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

    _promote_combat_candidates(candidates, sport_key=sport_key)

    setups: list[SportsBetSetup] = []
    for cand in candidates:
        edge = float(cand["edge"])
        book_odds = cand.get("book_odds") or []
        has_us_book = any(b.get("key") in US_PREFERRED_BOOK_KEYS for b in book_odds)
        # Prefer multi-book confirmation; FanDuel/DK alone is enough for US boards.
        min_books = 1 if has_us_book else 2
        # Single-book MMA totals/spreads have edge=0 vs themselves — still list as props.
        is_fight_prop = bool(cand.get("is_fight_prop"))
        # Live scans only pull FanDuel+DraftKings. When those two agree, edge≈0 vs the
        # median — that used to drop entire MLB/WNBA nights from the board. Keep US
        # book market lines so Today's slate can still fill.
        us_market_line = has_us_book and edge < min_edge
        effective_min_edge = (
            0.0
            if (has_us_book and (is_fight_prop or us_market_line or slate_mode or cand["book_count"] <= 2))
            else min_edge
        )
        if edge < effective_min_edge or cand["book_count"] < min_books:
            continue

        bet_type = str(cand["bet_type"])
        odds = int(cand["odds_american"])
        book_key, book_label = _primary_book_label(book_odds, odds)
        selection_label = (
            _combat_selection_label(cand)
            if is_fight_prop
            else _format_selection(bet_type, cand["selection"], cand["point"])
        )
        implied = american_to_implied_prob(odds)
        ev = round(edge * 0.85, 2)

        liquidity_boost = min(12, book_count * 1.5)
        timing_boost_val = timing_boost(hours)

        setup_strength = min(55, edge * 8 + liquidity_boost + timing_boost_val)
        if has_us_book:
            setup_strength += 4.0
        if is_fight_prop and has_us_book:
            setup_strength += 6.0
        # Tonight's US majors (MLB/WNBA/NFL…) clear the strength floor even at edge≈0.
        if us_market_line and hours is not None and hours <= 24:
            setup_strength = max(setup_strength, strength_floor + 2.0)
        if setup_strength < strength_floor and not (is_fight_prop and has_us_book):
            continue

        risk = round(min(88, max(20, 38 + implied * 40 - edge * 3)), 1)
        confidence = round(min(90, setup_strength + min(10, book_count) - confidence_dampen), 1)
        opportunity = round(
            min(95, confidence * 0.5 + (100 - risk) * 0.3 + edge * 4 + timing_boost_val * 0.35),
            1,
        )

        # Longer-dated games need a bit more edge, but stay visible for early value.
        if hours is not None and hours > NEAR_TERM_HOURS:
            opportunity -= min(8.0, (hours - NEAR_TERM_HOURS) * 0.03)
        # Single-book US lines get a small haircut — not a free pass to the board.
        if has_us_book and cand["book_count"] < 2 and not is_fight_prop:
            opportunity -= 2.0
        # Tonight's MMA/Boxing props should clear the board even without multi-book edge.
        if is_fight_prop and has_us_book:
            opportunity = max(
                opportunity,
                34.0 if (hours is not None and hours <= 12) else 28.0,
            )
        # Same for FanDuel/DK market lines on today's US slate (edge often 0 with 2 books).
        if us_market_line:
            if hours is not None and hours <= 12:
                opportunity = max(opportunity, 30.0)
            elif hours is not None and hours <= 24:
                opportunity = max(opportunity, 26.0)
            elif slate_mode:
                opportunity = max(opportunity, min(min_opportunity, 20.0))
        effective_min_opportunity = (
            min(min_opportunity, 18.0)
            if (is_fight_prop and has_us_book) or (us_market_line and slate_mode)
            else min_opportunity
        )
        if us_market_line and hours is not None and hours <= 24:
            effective_min_opportunity = min(effective_min_opportunity, 24.0)
        if opportunity < effective_min_opportunity:
            continue

        sharp = (
            "steam"
            if edge >= 3.5
            else ("value" if edge >= 2.0 or is_fight_prop else ("market" if us_market_line else None))
        )
        type_label = "Fight prop" if is_fight_prop else _bet_type_label(bet_type)

        kickoff = _format_kickoff(event_start)
        recommendation = f"{type_label} — {selection_label} · {kickoff} ({sport})"
        if us_market_line and edge < 0.5:
            explanation = (
                f"Track {selection_label} ({type_label.lower()}) on {event_name}, starting {kickoff}. "
                f"{book_label} line {odds:+d} on FanDuel/DraftKings — market line on tonight's slate "
                f"(books agree; no measurable cross-book edge yet)."
            )
            bull_case = (
                f"{book_label} {odds:+d} is the current US retail number for {selection_label} "
                f"before {kickoff}."
            )
            bear_case = (
                f"Without a cross-book edge, late line moves or injury news can flip this "
                f"{type_label.lower()} quickly."
            )
        else:
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
        suggested_action = (
            f"Play {odds:+d} on {book_label} for {selection_label}"
            if has_us_book
            else f"Target {odds:+d} or better on {selection_label}"
        )

        market_key = (
            "totals"
            if cand.get("prop_market") == "fight_total_rounds"
            else "spreads"
            if cand.get("prop_market") == "fight_spread"
            else _market_key_for_bet_type(bet_type)
        )
        outcome_prices = _collect_outcome_odds(
            event,
            market_key,
            cand["selection"],
            cand["point"],
        )
        line_movement = {
            "opening_odds": odds,
            "consensus_books": cand["book_count"],
            "edge_pct": edge,
            "preferred_book": book_key,
            "preferred_book_title": book_label,
            "book_odds": book_odds,
            "prop_market": cand.get("prop_market"),
            "player_name": cand.get("player_name"),
            "market_median_implied": round(
                statistics.median(american_to_implied_prob(p) for p in outcome_prices) * 100,
                2,
            )
            if outcome_prices
            else None,
            "event_id": event.get("id"),
        }

        snap_categories = None
        if is_fight_prop:
            snap_categories = ["top_picks", "player_props", "value_plays"]
            if hours is not None and hours <= 48:
                snap_categories.insert(0, "starting_soon")

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
                    "book_odds": book_odds,
                    "preferred_book": book_key,
                    "preferred_book_title": book_label,
                    "hours_to_start": round(hours, 1) if hours is not None else None,
                    "sport_key": sport_key,
                    "sport": sport,
                    "bet_type": bet_type,
                    "pick_origin": "atlas",
                    "atlas_presented": True,
                    "atlas_tracked": True,
                    "source": "odds_scan",
                    "event_id": event.get("id"),
                    "home_team": home,
                    "away_team": away,
                    "slate_mode": slate_mode,
                    "us_market_line": us_market_line,
                    "is_player_prop": bet_type == "player_prop" or is_fight_prop,
                    "is_fight_prop": is_fight_prop,
                    "prop_market": cand.get("prop_market"),
                    "player_name": cand.get("player_name"),
                    **({"categories": snap_categories} if snap_categories else {}),
                    "pick": {
                        "bet_type": bet_type,
                        "team_or_side": cand["selection"],
                        "point": cand.get("point"),
                        "player_name": cand.get("player_name"),
                    },
                    "market_context": {
                        "expected_value": ev,
                        "sharp_indicator": sharp,
                        "bet_type": bet_type,
                    },
                },
            )
        )
        support_bet = (
            "total"
            if cand.get("prop_market") == "fight_total_rounds"
            else "spread"
            if cand.get("prop_market") == "fight_spread"
            else bet_type
        )
        support, stats_detail = compute_pick_support(
            support_bet,
            cand["selection"],
            cand.get("point"),
            home,
            away,
            match_stats,
        )
        apply_stats_to_setup(setups[-1], support, stats_detail)

    # Drop plays that form demotion pushed below the opportunity floor.
    setups = [
        s
        for s in setups
        if s.opportunity_score
        >= (
            min(min_opportunity, 18.0)
            if bool((s.scoring_snapshot or {}).get("is_fight_prop"))
            or bool((s.scoring_snapshot or {}).get("us_market_line"))
            else min_opportunity
        )
    ]
    return _select_best_per_market(setups)


def _setup_decision_score(setup: SportsBetSetup) -> float:
    """Combined score for choosing one side of a market — edge + form + confidence."""
    snap = setup.scoring_snapshot or {}
    edge = float(snap.get("edge_pct") or 0)
    support = float(snap.get("stats_support") or 0)
    return (
        float(setup.opportunity_score)
        + edge * 0.5
        + support * 0.15
        + float(setup.confidence_score) * 0.1
        - float(setup.risk_score) * 0.05
    )


def _select_best_per_market(setups: list[SportsBetSetup]) -> list[SportsBetSetup]:
    """Keep one Atlas decision per event + bet type — never both sides of the same market."""
    if len(setups) <= 1:
        return setups

    by_family: dict[str, list[SportsBetSetup]] = {}
    for setup in setups:
        snap = setup.scoring_snapshot or {}
        event_id = str(snap.get("event_id") or setup.event_name or "")
        family = str(setup.bet_type or "moneyline")
        # Player/fight props must not collapse every market on a card into one pick.
        if family == "player_prop" or bool(snap.get("is_fight_prop")):
            prop_market = str(snap.get("prop_market") or "player_prop")
            key = f"{event_id}|{family}|{prop_market}"
        else:
            key = f"{event_id}|{family}"
        by_family.setdefault(key, []).append(setup)

    winners: list[SportsBetSetup] = []
    for group in by_family.values():
        group.sort(key=_setup_decision_score, reverse=True)
        best = group[0]
        if len(group) > 1:
            runner = group[1]
            best_score = _setup_decision_score(best)
            runner_score = _setup_decision_score(runner)
            margin = round(best_score - runner_score, 1)
            # Require a clear winner — if nearly tied, keep only if best has real edge/support.
            snap = best.scoring_snapshot
            edge = float(snap.get("edge_pct") or 0)
            support = float(snap.get("stats_support") or 0)
            if margin < 1.0 and edge < 1.25 and support < 8:
                # FanDuel/DK-only scans often produce edge≈0 with near-tied sides.
                # Still pick one side for US market lines / slate fills so Tonight's
                # MLB/WNBA board isn't wiped empty.
                if not (
                    bool(snap.get("us_market_line"))
                    or bool(snap.get("slate_mode"))
                    or bool(snap.get("is_fight_prop"))
                ):
                    continue
                snap["decision_note"] = (
                    "Sides nearly tied on FanDuel/DraftKings — kept the stronger side for the slate."
                )
            rejected = runner.selection
            snap["rejected_side"] = rejected
            snap["decision_margin"] = margin
            snap["atlas_decision"] = "best_of_market"
            best.explanation = (
                f"{best.explanation} Atlas chose {best.selection} over {rejected} "
                f"(decision margin {margin:.1f}) after comparing edge, form, and opportunity."
            )
            best.bull_case = (
                f"{best.bull_case} Beats the alternate {rejected} on combined market + form score."
            )
            if runner.opportunity_score >= best.opportunity_score - 5:
                best.bear_case = (
                    f"{best.bear_case} Close call vs {rejected} — recheck if the line moves."
                )
        else:
            best.scoring_snapshot["atlas_decision"] = "sole_qualifier"
        winners.append(best)

    winners.sort(key=_setup_decision_score, reverse=True)
    return winners


def fallback_slate_setup_from_event(
    event: dict[str, Any],
    *,
    calibration: dict[str, Any] | None = None,
) -> SportsBetSetup | None:
    """Minimal Today card when cache lists a game but FanDuel/DK bookmakers are missing.

    Remote odds cache sometimes hydrates commence_time + teams without market payloads.
    Without this fallback, Scan scores 0 calendar-Today picks while Next 24h still fills.
    """
    if _is_outright_event(event):
        return None
    home = str(event.get("home_team") or "").strip()
    away = str(event.get("away_team") or "").strip()
    if not home or not away:
        return None
    event_start = event.get("commence_time")
    hours = _hours_until(event_start)
    if hours is not None and hours <= 0:
        return None

    cal = calibration or {}
    slate_mode = bool(cal.get("slate_mode"))
    sport_key = str(event.get("_sport_key") or "")
    sport = str(event.get("_sport_label") or event.get("sport_title") or "Sports")
    event_name = f"{away} @ {home}"
    kickoff = _format_kickoff(event_start)
    selection = home
    odds = -110
    implied = american_to_implied_prob(odds)
    opportunity = 28.0 if hours is not None and hours <= 24 else 24.0
    if slate_mode:
        opportunity = max(opportunity, float(cal.get("sports_min_opportunity") or 18.0))

    explanation = (
        f"Track {home} (moneyline) on {event_name}, starting {kickoff}. "
        "Tonight's game is on the odds slate — FanDuel/DraftKings lines were not in cache. "
        "Tap Repair sports board once for live numbers."
    )
    line_movement = {
        "opening_odds": odds,
        "consensus_books": 0,
        "edge_pct": 0.0,
        "preferred_book": PREFERRED_BOOK_KEY,
        "preferred_book_title": PREFERRED_BOOK_TITLE,
        "book_odds": [],
        "event_id": event.get("id"),
        "slate_fallback": True,
    }

    return SportsBetSetup(
        sport=sport,
        event_name=event_name,
        event_start=event_start,
        bet_type="moneyline",
        selection=selection,
        odds_american=odds,
        odds_decimal=american_to_decimal(odds),
        expected_value=0.0,
        line_movement=line_movement,
        sharp_indicator="market",
        confidence_score=42.0,
        risk_score=48.0,
        opportunity_score=opportunity,
        recommendation=f"Moneyline — {selection} · {kickoff} ({sport})",
        explanation=explanation,
        bull_case=f"{home} is on tonight's {sport} slate — Repair once for live FanDuel/DraftKings lines.",
        bear_case="Placeholder line only until live odds are fetched — do not bet from -110 stub pricing.",
        invalidation="Fetch live odds or wait for bookmakers to appear in cache before staking.",
        suggested_action=f"Repair sports board for live {selection} ML pricing",
        scoring_snapshot={
            "edge_pct": 0.0,
            "implied_prob": round(implied * 100, 2),
            "book_count": 0,
            "book_odds": [],
            "preferred_book": PREFERRED_BOOK_KEY,
            "preferred_book_title": PREFERRED_BOOK_TITLE,
            "hours_to_start": round(hours, 1) if hours is not None else None,
            "sport_key": sport_key,
            "sport": sport,
            "bet_type": "moneyline",
            "pick_origin": "atlas",
            "atlas_presented": True,
            "atlas_tracked": True,
            "source": "odds_slate_fallback",
            "event_id": event.get("id"),
            "home_team": home,
            "away_team": away,
            "slate_mode": True,
            "us_market_line": True,
            "slate_fallback": True,
            "pick": {
                "bet_type": "moneyline",
                "team_or_side": home,
                "point": None,
            },
            "market_context": {
                "expected_value": 0.0,
                "sharp_indicator": "market",
                "bet_type": "moneyline",
            },
        },
    )


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
