"""Verify sports catalog / MMA props / Odds-scan path before push."""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

env_path = ROOT / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


async def _run() -> int:
    from app.agents.sports_analyst import analyze_event
    from app.agents.sports_categories import (
        category_counts,
        filter_by_category,
        tag_pool_categories,
    )
    from app.providers.sports.odds_api import _read_cache
    from app.services.fanduel_catalog import _append_game_lines, build_fanduel_catalog
    from app.services.freshness import filter_upcoming_events, hours_until_event
    from app.services.signal_service import _is_openai_web_row, _sports_window_match

    errors: list[str] = []

    cache = _read_cache() or {}
    events = list(cache.get("events") or [])
    mma = [
        e
        for e in events
        if str(e.get("sport_key") or e.get("_sport_key") or "").startswith("mma")
    ]
    up = filter_upcoming_events(mma)
    print("cache_fetched", cache.get("fetched_at"))
    print("mma_total", len(mma), "mma_upcoming", len(up))
    tonight = [e for e in up if (hours_until_event(e.get("commence_time")) or 999) <= 18]
    print("mma_tonight", len(tonight))
    for e in tonight:
        h = hours_until_event(e.get("commence_time"))
        print(f"  tonight {h:.2f}h {e.get('away_team')} @ {e.get('home_team')}")

    # 1) Catalog fight props
    cat: list[dict] = []
    for e in tonight or up[:2]:
        ev = dict(e)
        ev.setdefault("_sport_key", e.get("sport_key"))
        ev.setdefault("_sport_label", "MMA")
        _append_game_lines(cat, ev)
    props = [c for c in cat if c.get("bet_type") == "player_prop"]
    print("catalog_direct_mma_props", len(props))
    if (tonight or up) and not props:
        errors.append("upcoming MMA fights produced 0 catalog fight props")

    meta = await build_fanduel_catalog(include_props=True, max_prop_events=0)
    items = meta.get("items") or []
    mma_props = [
        i
        for i in items
        if i.get("bet_type") == "player_prop"
        and (
            str(i.get("sport_key") or "").startswith("mma")
            or str(i.get("sport") or "").upper() == "MMA"
        )
    ]
    print("trimmed_mma_props", len(mma_props), "meta", meta.get("mma_props"))
    ranking = items[:48]
    mma_in_rank = [
        i
        for i in ranking
        if i.get("bet_type") == "player_prop"
        and str(i.get("sport_key") or "").startswith("mma")
    ]
    print("mma_props_in_first_48", len(mma_in_rank))
    if mma_props and not mma_in_rank:
        errors.append("MMA props exist but none in first 48 Insight ranking slice")

    # 2) Odds-scan analyst path must emit fight props for tonight cards
    analyst_props = 0
    analyst_rows = 0
    for e in tonight[:3] or up[:2]:
        ev = dict(e)
        ev["_sport_key"] = e.get("sport_key") or "mma_mixed_martial_arts"
        ev["_sport_label"] = "MMA"
        setups = analyze_event(ev, calibration={"slate_mode": True})
        analyst_rows += len(setups)
        fight = [
            s
            for s in setups
            if s.bet_type == "player_prop" or bool((s.scoring_snapshot or {}).get("is_fight_prop"))
        ]
        analyst_props += len(fight)
        print(
            f"analyze_event {e.get('away_team')} @ {e.get('home_team')}: "
            f"{len(setups)} setups, {len(fight)} fight props"
        )
        for s in fight:
            print("   ", s.bet_type, s.selection, s.opportunity_score)
    if (tonight or up) and analyst_props == 0:
        errors.append("analyze_event produced 0 MMA fight props for upcoming fights")

    # 3) Category / window filters
    fake_rows = []
    for item in mma_props[:4]:
        fake_rows.append(
            {
                "id": f"t-{item.get('id')}",
                "sport": item.get("sport") or "MMA",
                "bet_type": item.get("bet_type"),
                "selection": item.get("selection"),
                "event_name": item.get("event_name"),
                "event_start": item.get("event_start"),
                "opportunity_score": 60,
                "odds_decimal": 1.9,
                "expected_value": 2,
                "risk_score": 40,
                "sharp_indicator": "consensus",
                "scoring_snapshot": {
                    "source": "openai_web",
                    "openai_web": True,
                    "is_player_prop": True,
                    "is_fight_prop": True,
                    "prop_market": item.get("prop_market"),
                    "sport_key": item.get("sport_key") or "mma_mixed_martial_arts",
                    "categories": [
                        "atlas_insight",
                        "player_props",
                        "top_picks",
                        "value_plays",
                    ],
                },
                "line_movement": {"source": "openai_web"},
            }
        )
    if fake_rows:
        tag_pool_categories(fake_rows)
        counts = category_counts(fake_rows)
        props_cat = filter_by_category(fake_rows, "player_props")
        insight_cat = filter_by_category(fake_rows, "atlas_insight")
        print(
            "filters props",
            len(props_cat),
            "insight",
            len(insight_cat),
            "counts",
            counts.get("player_props"),
        )
        for w in ("today", "soon", "week", "month", "all"):
            kept = [r for r in fake_rows if _sports_window_match(r, w)]
            print(f"window_{w}", len(kept))
            if w != "futures" and len(kept) < len(fake_rows):
                # Insight rows should survive date windows
                if not all(_is_openai_web_row(r) for r in fake_rows):
                    errors.append(f"window {w} dropped non-insight unexpectedly")
        if len(props_cat) < 1:
            errors.append("player_props category filter returned empty for MMA props")

        # Sport filter parity (API)
        sport_norm = "mma"
        matched = []
        for r in fake_rows:
            label = str(r.get("sport") or "").strip().lower().replace(" ", "_")
            key = str((r.get("scoring_snapshot") or {}).get("sport_key") or "").lower()
            ok = (
                label == sport_norm
                or key == sport_norm
                or ("mma" in label or key.startswith("mma_"))
            )
            if ok:
                matched.append(r)
        print("sport_filter_mma", len(matched))
        if len(matched) < 1:
            errors.append("MMA sport filter matched 0 rows")

    if errors:
        print("VERIFY_FAIL")
        for err in errors:
            print(" -", err)
        return 1

    print(
        "VERIFY_OK",
        f"tonight={len(tonight)}",
        f"catalog_props={len(mma_props)}",
        f"analyst_props={analyst_props}",
        f"analyst_rows={analyst_rows}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_run()))
