"""Learn from logged pick outcomes — tighten thresholds when edge underperforms."""

from __future__ import annotations

from typing import Any

from app.db.supabase_client import SupabaseClient

MIN_SAMPLES = 8
CONFIDENCE_BUCKETS = (
    (0, 60, "50-60"),
    (60, 70, "60-70"),
    (70, 80, "70-80"),
    (80, 90, "80-90"),
    (90, 101, "90+"),
)

# Keep options capital-light until Atlas has enough graded wins to trust larger contracts.
OPTIONS_PROVEN_MIN_DECIDED = 15
OPTIONS_PROVEN_MIN_WIN_RATE = 55.0

SIGNAL_TABLES: dict[str, str] = {
    "options": "options_signals",
    "stock": "stock_signals",
    "sports": "sports_signals",
    "parlay": "parlays",
}


class CalibrationService:
    def __init__(self, db: SupabaseClient, user_id: str) -> None:
        self.db = db
        self.user_id = user_id

    async def get_adjustments(self, *, lookback: int = 120) -> dict[str, Any]:
        """User-specific scoring tweaks derived from closed picks."""
        rows = await self.db.select(
            "signal_performance",
            filters={
                "user_id": f"eq.{self.user_id}",
                "outcome": "in.(win,loss,scratch)",
            },
            order="logged_at.desc",
            limit=max(lookback, MIN_SAMPLES * 2),
        )
        by_module: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            mod = str(row.get("module") or "")
            by_module.setdefault(mod, []).append(row)

        sports_learning = self._sports_learning_slices(by_module.get("sports") or [])
        sports = self._sports_adjustments(by_module.get("sports") or [])
        options = self._options_adjustments(by_module.get("options") or [])
        stock = self._stock_adjustments(by_module.get("stock") or [])
        parlay_note = self._parlay_learning_note(by_module.get("parlay") or [])

        market_learning = self._market_learning_pulse(
            by_module,
            sports_adj=sports,
            options_adj=options,
            stock_adj=stock,
            sports_learning=sports_learning,
            parlay_note=parlay_note,
        )

        if len(rows) < MIN_SAMPLES:
            defaults = self._defaults(sample_count=len(rows))
            defaults["sports_learning"] = sports_learning
            defaults["market_learning"] = market_learning
            defaults["options_min_profit_probability"] = options["min_profit_probability"]
            defaults["options_min_opportunity"] = options["min_opportunity"]
            defaults["options_budget_first"] = options["budget_first"]
            defaults["options_proven"] = options["proven"]
            defaults["options_decided"] = options["decided"]
            defaults["options_win_rate"] = options["win_rate"]
            defaults["learning_notes"] = list(sports_learning.get("notes") or []) + [
                n for n in (sports.get("note"), options.get("note"), stock.get("note"), parlay_note) if n
            ]
            return defaults

        confidence_accuracy = self._confidence_accuracy(rows)

        notes: list[str] = []
        if sports.get("note"):
            notes.append(sports["note"])
        if options.get("note"):
            notes.append(options["note"])
        if stock.get("note"):
            notes.append(stock["note"])
        if parlay_note:
            notes.append(parlay_note)

        return {
            "sample_count": len(rows),
            "sports_min_edge_pct": sports["min_edge_pct"],
            "sports_min_opportunity": sports["min_opportunity"],
            "sports_confidence_dampen": sports["confidence_dampen"],
            "options_min_profit_probability": options["min_profit_probability"],
            "options_min_opportunity": options["min_opportunity"],
            "options_budget_first": options["budget_first"],
            "options_proven": options["proven"],
            "options_decided": options["decided"],
            "options_win_rate": options["win_rate"],
            "stock_min_opportunity": stock["min_opportunity"],
            "confidence_accuracy": confidence_accuracy,
            "sports_learning": sports_learning,
            "market_learning": market_learning,
            "learning_notes": notes + list(sports_learning.get("notes") or []),
            "active": len(rows) >= MIN_SAMPLES,
        }

    @staticmethod
    def _defaults(*, sample_count: int = 0) -> dict[str, Any]:
        return {
            "sample_count": sample_count,
            "sports_min_edge_pct": 0.6,
            "sports_min_opportunity": 28.0,
            "sports_confidence_dampen": 0.0,
            "options_min_profit_probability": 52.0,
            "options_min_opportunity": 45.0,
            "options_budget_first": True,
            "options_proven": False,
            "options_decided": 0,
            "options_win_rate": None,
            "stock_min_opportunity": 35.0,
            "confidence_accuracy": {},
            "sports_learning": {
                "overall_win_rate": None,
                "decided": 0,
                "by_sport": {},
                "by_bet_type": {},
                "atlas": {"overall_win_rate": None, "decided": 0, "by_sport": {}, "by_bet_type": {}},
                "user": {"overall_win_rate": None, "decided": 0, "by_sport": {}, "by_bet_type": {}},
                "web_context": {
                    "decided": 0,
                    "win_rate": None,
                    "plain_decided": 0,
                    "plain_win_rate": None,
                    "note": None,
                    "examples": [],
                },
                "notes": [],
            },
            "market_learning": {
                "markets": [],
                "headline": "Grade a few settled picks — Atlas starts adapting thresholds per market.",
                "web_sources": {
                    "decided": 0,
                    "win_rate": None,
                    "note": None,
                    "examples": [],
                    "summary": (
                        "Atlas pulls free ESPN/CBS/BBC sports headlines and OpenAI web analyst consensus "
                        "into Insight rankings — then learns which news-backed picks actually hit."
                    ),
                },
            },
            "learning_notes": [],
            "active": False,
        }

    def _parlay_learning_note(self, rows: list[dict[str, Any]]) -> str | None:
        decided = [r for r in rows if r.get("outcome") in ("win", "loss")]
        if len(decided) < 4:
            return None
        wr = self._win_rate(decided)
        if wr is None:
            return None
        if wr < 35.0:
            return f"Parlays: hitting {wr:.0f}% over {len(decided)} — Atlas will favor fewer, stronger legs"
        if wr >= 50.0:
            return f"Parlays: hitting {wr:.0f}% over {len(decided)} — multi-leg builds stay eligible"
        return f"Parlays: {wr:.0f}% over {len(decided)} graded"

    def _market_learning_pulse(
        self,
        by_module: dict[str, list[dict[str, Any]]],
        *,
        sports_adj: dict[str, Any],
        options_adj: dict[str, Any],
        stock_adj: dict[str, Any],
        sports_learning: dict[str, Any],
        parlay_note: str | None,
    ) -> dict[str, Any]:
        """Per-market learning indicators for Performance UI + future scan bias."""
        markets: list[dict[str, Any]] = []

        def _maturity(n: int) -> str:
            if n >= MIN_SAMPLES:
                return "active"
            if n >= 4:
                return "warming"
            if n >= 1:
                return "seeding"
            return "cold"

        def _maturity_label(level: str) -> str:
            return {
                "active": "Learning active",
                "warming": "Warming up",
                "seeding": "Collecting grades",
                "cold": "Needs first grades",
            }.get(level, level)

        # Sports
        sports_rows = [r for r in (by_module.get("sports") or []) if r.get("outcome") in ("win", "loss")]
        sports_wr = self._win_rate(sports_rows)
        atlas = sports_learning.get("atlas") if isinstance(sports_learning.get("atlas"), dict) else {}
        user = sports_learning.get("user") if isinstance(sports_learning.get("user"), dict) else {}
        sports_detail: list[str] = []
        if atlas.get("decided"):
            sports_detail.append(
                f"Board {atlas.get('overall_win_rate')}% ({atlas.get('decided')} outcomes)"
            )
        if user.get("decided"):
            sports_detail.append(
                f"Your picks {user.get('overall_win_rate')}% ({user.get('decided')})"
            )
        top_bets = sorted(
            (sports_learning.get("by_bet_type") or {}).items(),
            key=lambda kv: kv[1].get("count", 0),
            reverse=True,
        )[:3]
        for bet, meta in top_bets:
            if meta.get("count", 0) >= 3:
                sports_detail.append(
                    f"{str(bet).replace('_', ' ')} {meta.get('win_rate')}% ({meta.get('count')})"
                )
        sports_level = _maturity(len(sports_rows))
        markets.append(
            {
                "id": "sports",
                "label": "Sports",
                "decided": len(sports_rows),
                "win_rate": sports_wr,
                "maturity": sports_level,
                "maturity_label": _maturity_label(sports_level),
                "adjustment": sports_adj.get("note")
                or (
                    f"Edge bar {sports_adj.get('min_edge_pct')}% · opp ≥ {sports_adj.get('min_opportunity')}"
                    if sports_level == "active"
                    else "Thresholds still at defaults until more grades land"
                ),
                "feeds_next_picks": True,
                "details": sports_detail[:4],
            }
        )

        # Stocks
        stock_rows = [r for r in (by_module.get("stock") or []) if r.get("outcome") in ("win", "loss")]
        stock_wr = self._win_rate(stock_rows)
        stock_level = _maturity(len(stock_rows))
        markets.append(
            {
                "id": "stock",
                "label": "Stocks",
                "decided": len(stock_rows),
                "win_rate": stock_wr,
                "maturity": stock_level,
                "maturity_label": _maturity_label(stock_level),
                "adjustment": stock_adj.get("note")
                or (
                    f"Min opportunity {stock_adj.get('min_opportunity')}"
                    if stock_level == "active"
                    else "Stock scans use default opportunity floor until grades accumulate"
                ),
                "feeds_next_picks": True,
                "details": [],
            }
        )

        # Options
        opt_rows = [r for r in (by_module.get("options") or []) if r.get("outcome") in ("win", "loss")]
        opt_wr = self._win_rate(opt_rows)
        opt_level = _maturity(len(opt_rows))
        markets.append(
            {
                "id": "options",
                "label": "Options",
                "decided": len(opt_rows),
                "win_rate": opt_wr,
                "maturity": opt_level,
                "maturity_label": _maturity_label(opt_level),
                "adjustment": options_adj.get("note")
                or (
                    f"Min profit prob {options_adj.get('min_profit_probability')}% · opp ≥ {options_adj.get('min_opportunity')}"
                    if opt_level == "active"
                    else "Options scans use default probability floor until grades accumulate"
                ),
                "feeds_next_picks": True,
                "details": (
                    ["Under-$100 contracts prioritized until Atlas proves options win rate"]
                    if options_adj.get("budget_first")
                    else []
                ),
            }
        )

        # Parlays
        parlay_rows = [r for r in (by_module.get("parlay") or []) if r.get("outcome") in ("win", "loss")]
        parlay_wr = self._win_rate(parlay_rows)
        parlay_level = _maturity(len(parlay_rows))
        markets.append(
            {
                "id": "parlay",
                "label": "Parlays",
                "decided": len(parlay_rows),
                "win_rate": parlay_wr,
                "maturity": parlay_level,
                "maturity_label": _maturity_label(parlay_level),
                "adjustment": parlay_note
                or (
                    "Parlay builders learn from settled multi-leg results"
                    if parlay_level != "cold"
                    else "Build and grade parlays so Atlas can tighten leg selection"
                ),
                "feeds_next_picks": True,
                "details": [],
            }
        )

        active_n = sum(1 for m in markets if m["maturity"] == "active")
        warming_n = sum(1 for m in markets if m["maturity"] in {"warming", "seeding"})
        if active_n >= 2:
            headline = (
                f"Atlas is actively adapting {active_n} markets from real outcomes — "
                "future scans raise or lower bars from what actually hit, plus free news/web context."
            )
        elif active_n == 1:
            headline = (
                "One market is fully calibrating; keep grading sports, stocks, and options "
                "so the loop spreads across the whole app. News and analyst coverage feed Insight too."
            )
        elif warming_n:
            headline = (
                "Learning loop is seeding — each graded win/loss plus free public news/analyst "
                "context teaches Atlas how to pick the next sports, stock, options, and parlay setups."
            )
        else:
            headline = (
                "Grade settled picks (or open Sports so Atlas auto-grades finished games) — "
                "Atlas also pulls free sports news and web analyst context into Insight."
            )

        web_ctx = sports_learning.get("web_context") if isinstance(sports_learning, dict) else {}
        if not isinstance(web_ctx, dict):
            web_ctx = {}

        return {
            "markets": markets,
            "headline": headline,
            "active_markets": active_n,
            "web_sources": {
                "decided": int(web_ctx.get("decided") or 0),
                "win_rate": web_ctx.get("win_rate"),
                "note": web_ctx.get("note"),
                "examples": web_ctx.get("examples") or [],
                "summary": (
                    "Atlas pulls free ESPN/CBS/BBC sports headlines and OpenAI web analyst consensus "
                    "into Insight rankings — then learns which news-backed picks actually hit."
                ),
            },
        }

    def _sports_learning_slices(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        """Win-rate slices from graded sports picks — Atlas board + user picks."""
        decided = [r for r in rows if r.get("outcome") in ("win", "loss")]
        atlas_rows = [r for r in decided if self._sports_origin(r) in ("atlas", "both")]
        user_rows = [r for r in decided if self._sports_origin(r) in ("user", "both")]

        def _bucket(bucket_rows: list[dict[str, Any]]) -> dict[str, Any]:
            overall = self._win_rate(bucket_rows)
            by_sport: dict[str, list[dict[str, Any]]] = {}
            by_bet: dict[str, list[dict[str, Any]]] = {}
            for row in bucket_rows:
                snap = row.get("scoring_snapshot") if isinstance(row.get("scoring_snapshot"), dict) else {}
                pick = snap.get("pick") if isinstance(snap.get("pick"), dict) else {}
                sport = str(
                    snap.get("sport") or row.get("signal_label") or row.get("label") or "Sports"
                ).split("·")[0].strip()[:40]
                if not sport:
                    sport = "Sports"
                bet_type = str(
                    pick.get("bet_type") or snap.get("bet_type") or row.get("bet_type") or "moneyline"
                )
                by_sport.setdefault(sport, []).append(row)
                by_bet.setdefault(bet_type, []).append(row)
            return {
                "overall_win_rate": overall,
                "decided": len(bucket_rows),
                "by_sport": self._slice_wr(by_sport),
                "by_bet_type": self._slice_wr(by_bet),
            }

        combined = _bucket(decided)
        atlas = _bucket(atlas_rows)
        user = _bucket(user_rows)

        # Ranking prior: prefer Atlas-presented outcomes, blend in user grades.
        ranking_by_sport = self._blend_slices(
            atlas.get("by_sport") or {},
            user.get("by_sport") or {},
            combined.get("by_sport") or {},
        )
        ranking_by_bet = self._blend_slices(
            atlas.get("by_bet_type") or {},
            user.get("by_bet_type") or {},
            combined.get("by_bet_type") or {},
        )

        notes: list[str] = []
        if atlas.get("overall_win_rate") is not None and atlas.get("decided", 0) >= 3:
            notes.append(
                f"Atlas board picks hit {atlas['overall_win_rate']:.0f}% "
                f"({atlas['decided']} graded real outcomes)"
            )
        if user.get("overall_win_rate") is not None and user.get("decided", 0) >= 3:
            notes.append(
                f"Your logged picks hit {user['overall_win_rate']:.0f}% "
                f"({user['decided']} graded)"
            )
        if not notes and combined.get("overall_win_rate") is not None and combined.get("decided", 0) >= 3:
            notes.append(
                f"Sports picks hit {combined['overall_win_rate']:.0f}% "
                f"({combined['decided']} graded)"
            )
        for bet_type, meta in sorted(
            ranking_by_bet.items(), key=lambda kv: kv[1]["count"], reverse=True
        )[:3]:
            if meta["count"] >= 5:
                notes.append(
                    f"{bet_type.replace('_', ' ')} hits {meta['win_rate']:.0f}% over {meta['count']}"
                )

        web_ctx = self._web_context_slice(decided)
        if web_ctx.get("note"):
            notes.append(str(web_ctx["note"]))

        return {
            "overall_win_rate": combined.get("overall_win_rate"),
            "decided": combined.get("decided") or 0,
            "by_sport": ranking_by_sport,
            "by_bet_type": ranking_by_bet,
            "atlas": atlas,
            "user": user,
            "web_context": web_ctx,
            "notes": notes,
        }

    def _web_context_slice(self, decided: list[dict[str, Any]]) -> dict[str, Any]:
        """How news/web-backed sports picks are performing vs market-only."""
        web_rows: list[dict[str, Any]] = []
        plain_rows: list[dict[str, Any]] = []
        examples: list[dict[str, Any]] = []
        for row in decided:
            snap = row.get("scoring_snapshot") if isinstance(row.get("scoring_snapshot"), dict) else {}
            is_web = bool(
                snap.get("news_verified")
                or snap.get("web_search")
                or snap.get("web_context")
                or snap.get("related_news")
                or snap.get("context_sources")
            )
            if is_web:
                web_rows.append(row)
                for src in (snap.get("context_sources") or [])[:2]:
                    if isinstance(src, dict) and src.get("title"):
                        examples.append(
                            {
                                "title": str(src.get("title"))[:120],
                                "url": src.get("url"),
                                "provider": src.get("provider") or src.get("type"),
                            }
                        )
            else:
                plain_rows.append(row)

        web_wr = self._win_rate(web_rows)
        plain_wr = self._win_rate(plain_rows)
        note = None
        if web_wr is not None and len(web_rows) >= 4:
            note = (
                f"News/web-backed sports picks hit {web_wr:.0f}% "
                f"({len(web_rows)} graded)"
            )
            if plain_wr is not None and len(plain_rows) >= 4:
                note += f" vs {plain_wr:.0f}% market-only ({len(plain_rows)})"
        seen: set[str] = set()
        uniq_examples: list[dict[str, Any]] = []
        for ex in examples:
            key = str(ex.get("title") or "")
            if not key or key in seen:
                continue
            seen.add(key)
            uniq_examples.append(ex)
            if len(uniq_examples) >= 5:
                break
        return {
            "decided": len(web_rows),
            "win_rate": web_wr,
            "plain_decided": len(plain_rows),
            "plain_win_rate": plain_wr,
            "note": note,
            "examples": uniq_examples,
        }

    def _slice_wr(self, bucket: dict[str, list[dict[str, Any]]]) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for key, bucket_rows in bucket.items():
            wr = self._win_rate(bucket_rows)
            if wr is None:
                continue
            out[key] = {
                "count": len(bucket_rows),
                "win_rate": wr,
                "boost": round(max(-8.0, min(8.0, (wr - 50.0) * 0.35)), 2)
                if len(bucket_rows) >= 4
                else 0.0,
            }
        return out

    @staticmethod
    def _blend_slices(
        atlas: dict[str, dict[str, Any]],
        user: dict[str, dict[str, Any]],
        combined: dict[str, dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        """70% Atlas board outcomes + 30% user grades when both have signal."""
        keys = set(atlas) | set(user) | set(combined)
        out: dict[str, dict[str, Any]] = {}
        for key in keys:
            a = atlas.get(key)
            u = user.get(key)
            c = combined.get(key) or {"count": 0, "win_rate": 50.0, "boost": 0.0}
            if a and u and a["count"] >= 3 and u["count"] >= 3:
                wr = round(0.7 * float(a["win_rate"]) + 0.3 * float(u["win_rate"]), 1)
                count = int(a["count"]) + int(u["count"])
                boost = round(0.7 * float(a.get("boost") or 0) + 0.3 * float(u.get("boost") or 0), 2)
            elif a and a["count"] >= 3:
                wr, count, boost = float(a["win_rate"]), int(a["count"]), float(a.get("boost") or 0)
            elif u and u["count"] >= 3:
                wr, count, boost = float(u["win_rate"]), int(u["count"]), float(u.get("boost") or 0)
            else:
                wr, count, boost = float(c["win_rate"]), int(c["count"]), float(c.get("boost") or 0)
            out[key] = {
                "count": count,
                "win_rate": wr,
                "boost": round(max(-8.0, min(8.0, boost if boost else (wr - 50.0) * 0.35)), 2)
                if count >= 4
                else 0.0,
            }
        return out

    @staticmethod
    def _sports_origin(row: dict[str, Any]) -> str:
        snap = row.get("scoring_snapshot") if isinstance(row.get("scoring_snapshot"), dict) else {}
        origin = snap.get("pick_origin")
        if origin in ("atlas", "user", "both"):
            return str(origin)
        if snap.get("atlas_presented") or snap.get("source") in {
            "openai_web",
            "odds_scan",
            "sports_scan",
        }:
            return "atlas"
        if snap.get("user_entry") or snap.get("source") == "user_entry":
            return "user"
        src = str(row.get("resolution_source") or "")
        if src in ("watchlist", "manual", "manual_edit"):
            return "user"
        if src.startswith("auto_") or src == "auto_scan":
            return "atlas"
        return "atlas"

    def _sports_adjustments(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        min_edge = 0.6
        min_opp = 28.0
        dampen = 0.0
        note: str | None = None

        low_edge = []
        for row in rows:
            snap = row.get("scoring_snapshot") or {}
            edge = snap.get("edge_pct")
            if edge is None:
                edge = (row.get("line_movement") or {}).get("edge_pct") if isinstance(row.get("line_movement"), dict) else None
            if edge is not None and float(edge) < 2.0:
                low_edge.append(row)

        if len(low_edge) >= 5:
            wr = self._win_rate(low_edge)
            if wr is not None and wr < 48.0:
                min_edge = 1.0
                min_opp = 32.0
                note = f"Sports: low-edge picks won {wr:.0f}% — raised edge bar to {min_edge}%"

        mid_conf = [r for r in rows if self._confidence(r) is not None and 70 <= self._confidence(r) < 85]
        if len(mid_conf) >= 5:
            wr = self._win_rate(mid_conf)
            if wr is not None and wr < 50.0:
                dampen = 5.0
                if not note:
                    note = f"Sports: 70–85 confidence bucket won {wr:.0f}% — scores adjusted"

        return {
            "min_edge_pct": min_edge,
            "min_opportunity": min_opp,
            "confidence_dampen": dampen,
            "note": note,
        }

    def _options_adjustments(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        min_prob = 52.0
        min_opp = 45.0
        notes: list[str] = []

        mid_prob = []
        for row in rows:
            snap = row.get("scoring_snapshot") or {}
            prob = snap.get("profit_probability")
            if prob is not None and 52 <= float(prob) < 62:
                mid_prob.append(row)

        if len(mid_prob) >= 5:
            wr_mid = self._win_rate(mid_prob)
            if wr_mid is not None and wr_mid < 45.0:
                min_prob = 58.0
                min_opp = 48.0
                notes.append(
                    f"Options: 52–62% prob picks won {wr_mid:.0f}% — raised minimum to {min_prob:.0f}%"
                )

        decided = [r for r in rows if r.get("outcome") in ("win", "loss")]
        decided_n = len(decided)
        win_rate = self._win_rate(decided)
        proven = (
            decided_n >= OPTIONS_PROVEN_MIN_DECIDED
            and win_rate is not None
            and win_rate >= OPTIONS_PROVEN_MIN_WIN_RATE
        )
        budget_first = not proven
        if budget_first:
            if decided_n == 0:
                notes.append(
                    "Options: under-$100 contracts prioritized until Atlas proves a win rate"
                )
            else:
                wr_label = f"{win_rate:.0f}%" if win_rate is not None else "n/a"
                notes.append(
                    f"Options: {decided_n} graded · {wr_label} win rate — "
                    f"under-$100 priority until {OPTIONS_PROVEN_MIN_DECIDED}+ graded "
                    f"at ≥{OPTIONS_PROVEN_MIN_WIN_RATE:.0f}%"
                )
        else:
            notes.append(
                f"Options: proven on {decided_n} graded picks ({win_rate:.0f}% win rate) — "
                "higher-cost contracts allowed when edge is strong"
            )

        return {
            "min_profit_probability": min_prob,
            "min_opportunity": min_opp,
            "budget_first": budget_first,
            "proven": proven,
            "decided": decided_n,
            "win_rate": win_rate,
            "note": " · ".join(notes) if notes else None,
        }

    def _stock_adjustments(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        min_opp = 35.0
        note: str | None = None

        low_opp = [r for r in rows if self._opportunity(r) is not None and self._opportunity(r) < 42]
        if len(low_opp) >= 5:
            wr = self._win_rate(low_opp)
            if wr is not None and wr < 45.0:
                min_opp = 40.0
                note = f"Stocks: sub-42 opportunity picks won {wr:.0f}% — minimum raised to {min_opp:.0f}"

        return {"min_opportunity": min_opp, "note": note}

    def _confidence_accuracy(self, rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        buckets: dict[str, list[dict[str, Any]]] = {label: [] for _, _, label in CONFIDENCE_BUCKETS}
        for row in rows:
            conf = self._confidence(row)
            if conf is None:
                continue
            for low, high, label in CONFIDENCE_BUCKETS:
                if low <= conf < high:
                    buckets[label].append(row)
                    break

        out: dict[str, dict[str, Any]] = {}
        for label, bucket_rows in buckets.items():
            if not bucket_rows:
                continue
            wr = self._win_rate(bucket_rows)
            if wr is None:
                continue
            out[label] = {
                "count": len(bucket_rows),
                "win_rate": wr,
                "expected_mid": (int(label.split("-")[0]) + int(label.split("-")[1].replace("+", ""))) / 2
                if "+" not in label
                else 92,
            }
        return out

    @staticmethod
    def _win_rate(rows: list[dict[str, Any]]) -> float | None:
        decided = [r for r in rows if r.get("outcome") in ("win", "loss")]
        if not decided:
            return None
        wins = sum(1 for r in decided if r.get("outcome") == "win")
        return round(wins / len(decided) * 100, 1)

    @staticmethod
    def _confidence(row: dict[str, Any]) -> float | None:
        val = row.get("confidence_score")
        if val is not None:
            return float(val)
        snap = row.get("scoring_snapshot") or {}
        if snap.get("confidence_score") is not None:
            return float(snap["confidence_score"])
        return None

    @staticmethod
    def _opportunity(row: dict[str, Any]) -> float | None:
        val = row.get("opportunity_score")
        if val is not None:
            return float(val)
        snap = row.get("scoring_snapshot") or {}
        if snap.get("opportunity_score") is not None:
            return float(snap["opportunity_score"])
        return None
