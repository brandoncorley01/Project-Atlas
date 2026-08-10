"""One Atlas decision per event+market — never both sides."""

from app.services.sports_ranking import dedupe_one_side_per_market, market_family_key


def _row(
    *,
    sid: str,
    event: str,
    bet_type: str,
    selection: str,
    opportunity: float,
    event_id: str = "evt-1",
    source: str | None = None,
) -> dict:
    snap: dict = {"event_id": event_id, "edge_pct": opportunity / 10}
    lm: dict = {"edge_pct": opportunity / 10}
    if source:
        snap["source"] = source
        lm["source"] = source
        if source == "user_entry":
            snap["user_entry"] = True
            snap["pick_origin"] = "user"
    return {
        "id": sid,
        "event_name": event,
        "bet_type": bet_type,
        "selection": selection,
        "opportunity_score": opportunity,
        "scoring_snapshot": snap,
        "line_movement": lm,
        "event_start": "2099-07-11T00:00:00Z",
    }


def test_market_family_key_uses_event_and_bet_type():
    row = _row(sid="a", event="A @ B", bet_type="moneyline", selection="A", opportunity=50)
    assert market_family_key(row) == "evt-1|moneyline"


def test_dedupe_keeps_stronger_moneyline_side():
    rows = [
        _row(sid="1", event="Away @ Home", bet_type="moneyline", selection="Away", opportunity=40),
        _row(sid="2", event="Away @ Home", bet_type="moneyline", selection="Home", opportunity=55),
        _row(sid="3", event="Away @ Home", bet_type="spread", selection="Away -1.5", opportunity=48),
    ]
    kept = dedupe_one_side_per_market(rows)
    assert len(kept) == 2
    ml = next(r for r in kept if r["bet_type"] == "moneyline")
    assert ml["id"] == "2"
    assert ml["selection"] == "Home"


def test_dedupe_drops_over_under_pair():
    rows = [
        _row(sid="o", event="A @ B", bet_type="total", selection="Over 8.5", opportunity=44),
        _row(sid="u", event="A @ B", bet_type="total", selection="Under 8.5", opportunity=51),
    ]
    kept = dedupe_one_side_per_market(rows)
    assert len(kept) == 1
    assert kept[0]["selection"] == "Under 8.5"


def test_user_entry_keeps_both_moneyline_sides():
    rows = [
        _row(
            sid="u1",
            event="Away @ Home",
            bet_type="moneyline",
            selection="Away",
            opportunity=82,
            source="user_entry",
        ),
        _row(
            sid="u2",
            event="Away @ Home",
            bet_type="moneyline",
            selection="Home",
            opportunity=82,
            source="user_entry",
        ),
    ]
    kept = dedupe_one_side_per_market(rows)
    assert len(kept) == 2
    assert {r["selection"] for r in kept} == {"Away", "Home"}
    assert market_family_key(rows[0]) == "evt-1|moneyline|Away|user_entry"


def test_user_entry_does_not_collapse_with_odds_pick():
    rows = [
        _row(sid="o1", event="Away @ Home", bet_type="moneyline", selection="Home", opportunity=70),
        _row(
            sid="u1",
            event="Away @ Home",
            bet_type="moneyline",
            selection="Away",
            opportunity=82,
            source="user_entry",
        ),
    ]
    kept = dedupe_one_side_per_market(rows)
    assert len(kept) == 2
    assert {r["id"] for r in kept} == {"o1", "u1"}
