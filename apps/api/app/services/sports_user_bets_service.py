"""Cache-backed sports event search + user-entered bets for Atlas learning."""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Any

from app.agents.sports_analyst import (
    PREFERRED_BOOK_KEY,
    US_PREFERRED_BOOK_KEYS,
    american_to_decimal,
)
from app.db.supabase_client import SupabaseClient
from app.providers.sports.odds_api import _cache_age_minutes, _read_cache
from app.services.freshness import filter_upcoming_events, hours_until_event

logger = logging.getLogger(__name__)

SOURCE = "user_entry"


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _tokens(query: str) -> list[str]:
    return [t for t in _norm(query).split() if len(t) >= 2]


def _event_haystack(event: dict[str, Any]) -> str:
    parts = [
        str(event.get("home_team") or ""),
        str(event.get("away_team") or ""),
        str(event.get("_sport_label") or event.get("sport_title") or ""),
        str(event.get("_sport_key") or ""),
        str(event.get("id") or ""),
    ]
    return _norm(" ".join(parts))


def _match_score(haystack: str, tokens: list[str]) -> float:
    if not tokens:
        return 1.0
    hits = sum(1 for t in tokens if t in haystack)
    if hits == 0:
        return 0.0
    # Prefer full-token matches; bonus when all tokens hit.
    score = hits / len(tokens)
    if hits == len(tokens):
        score += 0.25
    return score


def _pick_book_markets(event: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten FanDuel/DraftKings markets into searchable bet chips."""
    books = list(event.get("bookmakers") or [])
    preferred = [b for b in books if str(b.get("key") or "") in US_PREFERRED_BOOK_KEYS]
    ordered = preferred or books
    # FanDuel first when present.
    ordered.sort(key=lambda b: 0 if b.get("key") == PREFERRED_BOOK_KEY else 1)

    markets_out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for book in ordered[:2]:
        book_key = str(book.get("key") or "")
        book_title = str(book.get("title") or book_key)
        for market in book.get("markets") or []:
            mkey = str(market.get("key") or "")
            bet_type = {"h2h": "moneyline", "spreads": "spread", "totals": "total"}.get(mkey)
            if not bet_type:
                continue
            for outcome in market.get("outcomes") or []:
                name = str(outcome.get("name") or "").strip()
                if not name:
                    continue
                try:
                    american = int(outcome.get("price"))
                except (TypeError, ValueError):
                    continue
                point = outcome.get("point")
                try:
                    point_f = float(point) if point is not None else None
                except (TypeError, ValueError):
                    point_f = None
                if bet_type == "spread" and point_f is not None:
                    sign = "+" if point_f > 0 else ""
                    selection = f"{name} {sign}{point_f:g}"
                elif bet_type == "total" and point_f is not None:
                    selection = f"{name} {point_f:g}"
                else:
                    selection = name
                dedupe = f"{bet_type}|{selection}|{american}"
                if dedupe in seen:
                    continue
                seen.add(dedupe)
                markets_out.append(
                    {
                        "bet_type": bet_type,
                        "selection": selection,
                        "odds_american": american,
                        "point": point_f,
                        "book_key": book_key,
                        "book_title": book_title,
                        "team_or_side": name,
                    }
                )
    return markets_out


def _serialize_event(event: dict[str, Any]) -> dict[str, Any]:
    home = str(event.get("home_team") or "")
    away = str(event.get("away_team") or "")
    start = event.get("commence_time")
    hours = hours_until_event(start)
    return {
        "event_id": str(event.get("id") or ""),
        "sport": str(event.get("_sport_label") or event.get("sport_title") or "Sports"),
        "sport_key": str(event.get("_sport_key") or ""),
        "home_team": home,
        "away_team": away,
        "event_name": f"{away} @ {home}" if home and away else (home or away or "Event"),
        "event_start": start,
        "hours_until_start": round(hours, 1) if hours is not None else None,
        "markets": _pick_book_markets(event),
    }


def search_cached_events(
    *,
    query: str = "",
    sport: str | None = None,
    limit: int = 40,
) -> dict[str, Any]:
    """Verified FanDuel/DraftKings search — teams, events, and player props (0 credits)."""
    from app.services.fanduel_catalog import search_verified_markets

    return search_verified_markets(query=query, sport=sport, limit=limit)


class SportsUserBetsService:
    def __init__(self, db: SupabaseClient, user_id: str) -> None:
        self.db = db
        self.user_id = user_id

    async def create_user_bet(self, payload: dict[str, Any]) -> dict[str, Any]:
        sport = str(payload.get("sport") or "Sports").strip()[:40] or "Sports"
        event_name = str(payload.get("event_name") or "").strip()[:160]
        selection = str(payload.get("selection") or "").strip()[:120]
        bet_type = str(payload.get("bet_type") or "moneyline").strip().lower()
        if bet_type not in {"moneyline", "spread", "total", "futures", "player_prop"}:
            bet_type = "moneyline"
        if not event_name or not selection:
            return {"ok": False, "message": "Event and selection are required."}

        try:
            odds_american = int(payload.get("odds_american"))
        except (TypeError, ValueError):
            return {"ok": False, "message": "Enter American odds (e.g. -110 or +145)."}

        event_start = payload.get("event_start")
        if event_start is not None:
            event_start = str(event_start).strip() or None
        event_id = str(payload.get("event_id") or "").strip() or None
        home = str(payload.get("home_team") or "").strip() or None
        away = str(payload.get("away_team") or "").strip() or None
        sport_key = str(payload.get("sport_key") or "").strip() or None
        book_key = str(payload.get("book_key") or PREFERRED_BOOK_KEY)
        book_title = str(payload.get("book_title") or "FanDuel")
        notes = str(payload.get("notes") or "").strip()[:400]
        stake = payload.get("stake")
        try:
            stake_f = float(stake) if stake is not None and str(stake).strip() != "" else None
        except (TypeError, ValueError):
            stake_f = None

        now = datetime.now(UTC).isoformat()
        confidence = 62.0
        risk = 48.0
        # Keep Search bets above typical scan noise so list fetches don't truncate them away.
        opportunity = 82.0
        explanation = notes or (
            f"Your logged bet: {selection} on {event_name} at {odds_american:+d}. "
            "Atlas will track and grade this pick to improve learning."
        )

        row = {
            "user_id": self.user_id,
            "sport": sport,
            "event_name": event_name,
            "event_start": event_start,
            "bet_type": bet_type,
            "selection": selection,
            "odds_american": odds_american,
            "odds_decimal": american_to_decimal(odds_american),
            "expected_value": None,
            "line_movement": {
                "preferred_book": book_key,
                "preferred_book_title": book_title,
                "source": SOURCE,
                "event_id": event_id,
                "stake": stake_f,
            },
            "injury_impact": None,
            "weather_impact": None,
            "travel_rest_impact": None,
            "public_betting_pct": None,
            "sharp_indicator": None,
            "confidence_score": confidence,
            "risk_score": risk,
            "opportunity_score": opportunity,
            "recommendation": f"My bet · {bet_type.title()} — {selection} · {event_name}",
            "explanation": explanation,
            "bull_case": "You logged this play for tracking and learning.",
            "bear_case": "Lines move — recheck FanDuel/DraftKings before betting more.",
            "invalidation": "Scratch if the game is postponed or the wrong market was logged.",
            "suggested_action": f"Track {selection} at {odds_american:+d} on {book_title}",
            "risk_warning": (
                "User-entered picks feed Atlas learning. Verify live odds on your book before wagering."
            ),
            "scoring_snapshot": {
                "source": SOURCE,
                "user_entry": True,
                "pick_origin": "user",
                "user_tracked": True,
                "event_id": event_id,
                "sport_key": sport_key,
                "home_team": home,
                "away_team": away,
                "preferred_book": book_key,
                "preferred_book_title": book_title,
                "stake": stake_f,
                "notes": notes or None,
                "pick": {
                    "bet_type": bet_type,
                    "team_or_side": selection,
                },
            },
            "status": "active",
            "data_as_of": now,
        }

        # Prefer reactivating a matching expired Search bet over inserting a duplicate.
        revived = await self._try_reactivate_match(row)
        if revived:
            item = revived
            saved = [revived]
        else:
            saved = await self.db.insert("sports_signals", [row])
            if not saved:
                return {"ok": False, "message": "Could not save bet — try again."}
            item = saved[0]

        watchlist_item = await self._save_bet_to_watchlist(item)

        try:
            from app.services.signal_registry_service import SignalRegistryService

            await SignalRegistryService(self.db, self.user_id).register_batch("sports", saved)
        except Exception as exc:
            logger.warning("User bet registry skipped: %s", exc)

        return {
            "ok": True,
            "signals_created": 1,
            "item": item,
            "watchlist_item": watchlist_item,
            "credits_used": 0,
            "message": (
                f"Saved {selection} on {event_name} to Watchlist — Atlas is tracking this pick "
                "(0 Odds API credits)."
            ),
        }

    async def _save_bet_to_watchlist(self, signal: dict[str, Any]) -> dict[str, Any] | None:
        """Persist a Search/My bet onto the Default watchlist Bets tab."""
        sid = str(signal.get("id") or "").strip()
        if not sid:
            return None
        meta = {
            "signal_id": sid,
            "sport": signal.get("sport") or "Sports",
            "event_name": signal.get("event_name") or "",
            "bet_type": signal.get("bet_type") or "moneyline",
            "selection": signal.get("selection") or "",
            "odds_american": signal.get("odds_american"),
            "opportunity_score": signal.get("opportunity_score"),
            "expected_value": signal.get("expected_value"),
            "event_start": signal.get("event_start"),
            "label": (
                f"{signal.get('selection') or ''} · {signal.get('event_name') or ''}".strip(" ·")
            ),
            "watchlist_kind": "sport_bet",
            "user_entry": True,
            "pick_origin": "user",
            "source": SOURCE,
        }
        try:
            from app.services.watchlist_service import WatchlistService

            # Store as legacy sport_event — DB check constraints often reject sport_bet;
            # watchlist_kind drives the Bets tab (same mapping as the web client).
            return await WatchlistService(self.db, self.user_id).add_item(
                symbol=sid,
                item_type="sport_event",
                metadata=meta,
            )
        except Exception as exc:
            logger.warning("Watchlist save for Search bet %s failed: %s", sid, exc)
            return None

    @staticmethod
    def _is_user_entry_row(row: dict[str, Any]) -> bool:
        from app.services.sports_ranking import is_user_entry_row

        return is_user_entry_row(row)

    def _identity_key(self, row: dict[str, Any]) -> str:
        snap = row.get("scoring_snapshot") or {}
        lm = row.get("line_movement") or {}
        event_id = str(snap.get("event_id") or lm.get("event_id") or "").strip()
        event_name = str(row.get("event_name") or "").strip().lower()
        bet_type = str(row.get("bet_type") or "").strip().lower()
        selection = str(row.get("selection") or "").strip().lower()
        return f"{event_id or event_name}|{bet_type}|{selection}"

    async def _try_reactivate_match(self, desired: dict[str, Any]) -> dict[str, Any] | None:
        """If an expired twin Search bet exists and is still listable, reactivate it."""
        from app.services.freshness import is_sports_listable

        try:
            expired = await self.db.select(
                "sports_signals",
                filters={"user_id": f"eq.{self.user_id}", "status": "eq.expired"},
                order="data_as_of.desc",
                limit=250,
            )
        except Exception as exc:
            logger.warning("User bet reactivate lookup failed: %s", exc)
            return None

        want = self._identity_key(desired)
        for row in expired:
            if not self._is_user_entry_row(row):
                continue
            if self._identity_key(row) != want:
                continue
            # Rebuild listable check against desired kickoff when expired row lost start.
            probe = {**row, "event_start": desired.get("event_start") or row.get("event_start")}
            if not is_sports_listable(probe):
                continue
            sid = row.get("id")
            if not sid:
                continue
            patch = {
                "status": "active",
                "data_as_of": desired.get("data_as_of"),
                "odds_american": desired.get("odds_american"),
                "odds_decimal": desired.get("odds_decimal"),
                "opportunity_score": desired.get("opportunity_score"),
                "confidence_score": desired.get("confidence_score"),
                "risk_score": desired.get("risk_score"),
                "event_start": desired.get("event_start") or row.get("event_start"),
                "line_movement": desired.get("line_movement") or row.get("line_movement"),
                "scoring_snapshot": desired.get("scoring_snapshot") or row.get("scoring_snapshot"),
                "recommendation": desired.get("recommendation"),
                "explanation": desired.get("explanation"),
                "suggested_action": desired.get("suggested_action"),
            }
            try:
                updated = await self.db.update(
                    "sports_signals",
                    {"id": f"eq.{sid}", "user_id": f"eq.{self.user_id}"},
                    patch,
                )
                if updated:
                    return updated[0]
            except Exception as exc:
                logger.warning("Failed to reactivate user bet %s: %s", sid, exc)
        return None

    async def recover_user_bets(self) -> dict[str, Any]:
        """Reactivate expired Search bets that still belong on the live board.

        Also restores missing live rows from signal_performance snapshots when the
        sports_signals row was purged incorrectly.
        """
        from app.services.freshness import is_sports_listable

        now = datetime.now(UTC).isoformat()
        restored_ids: list[str] = []
        rebuilt = 0

        try:
            expired = await self.db.select(
                "sports_signals",
                filters={"user_id": f"eq.{self.user_id}", "status": "eq.expired"},
                order="data_as_of.desc",
                limit=400,
            )
        except Exception as exc:
            logger.warning("Recover user bets: expired select failed: %s", exc)
            expired = []

        for row in expired:
            if not self._is_user_entry_row(row):
                continue
            if not is_sports_listable(row):
                continue
            sid = row.get("id")
            if not sid:
                continue
            try:
                updated = await self.db.update(
                    "sports_signals",
                    {"id": f"eq.{sid}", "user_id": f"eq.{self.user_id}"},
                    {
                        "status": "active",
                        "data_as_of": now,
                        "opportunity_score": max(
                            float(row.get("opportunity_score") or 0),
                            82.0,
                        ),
                    },
                )
                if updated:
                    restored_ids.append(str(sid))
                    await self._save_bet_to_watchlist(updated[0] if updated else {**row, "id": sid})
            except Exception as exc:
                logger.warning("Recover user bet %s failed: %s", sid, exc)

        # Rebuild from performance registry if the live row is gone entirely.
        try:
            active = await self.db.select(
                "sports_signals",
                filters={"user_id": f"eq.{self.user_id}", "status": "eq.active"},
                select="id",
                limit=500,
            )
            active_ids = {str(r.get("id")) for r in active if r.get("id")}
            perf = await self.db.select(
                "signal_performance",
                filters={
                    "user_id": f"eq.{self.user_id}",
                    "module": "eq.sports",
                    "outcome": "eq.pending",
                },
                order="created_at.desc",
                limit=300,
            )
        except Exception as exc:
            logger.warning("Recover user bets: performance lookup failed: %s", exc)
            perf = []
            active_ids = set()

        rebuild_rows: list[dict[str, Any]] = []
        for p in perf:
            sid = str(p.get("signal_id") or "")
            if not sid or sid in active_ids or sid in restored_ids:
                continue
            # Performance rows store the snapshot under scoring_snapshot.
            snap = p.get("scoring_snapshot") or p.get("signal_snapshot") or {}
            if not isinstance(snap, dict):
                continue
            nested = snap.get("scoring_snapshot") if isinstance(snap.get("scoring_snapshot"), dict) else {}
            probe = {**snap, "scoring_snapshot": nested or snap}
            if not self._is_user_entry_row(probe):
                continue
            if not is_sports_listable(probe):
                continue
            # Only rebuild if the sports_signals row is missing (deleted), not merely expired
            # (expired path above already handled listable ones).
            try:
                existing = await self.db.select(
                    "sports_signals",
                    filters={"id": f"eq.{sid}", "user_id": f"eq.{self.user_id}"},
                    select="id,status",
                    limit=1,
                )
            except Exception:
                existing = []
            if existing:
                continue
            row = self._row_from_performance_snapshot(sid, snap, nested or {})
            if row:
                rebuild_rows.append(row)

        if rebuild_rows:
            try:
                inserted = await self.db.insert("sports_signals", rebuild_rows)
                rebuilt = len(inserted or [])
                if inserted:
                    for row in inserted:
                        await self._save_bet_to_watchlist(row)
                    try:
                        from app.services.signal_registry_service import SignalRegistryService

                        await SignalRegistryService(self.db, self.user_id).register_batch(
                            "sports", inserted
                        )
                    except Exception as exc:
                        logger.warning("Recover rebuild registry skipped: %s", exc)
            except Exception as exc:
                logger.warning("Recover rebuild insert failed: %s", exc)

        # Also push any active Search bets that never made it onto the watchlist.
        watchlisted = 0
        try:
            active_user = await self.db.select(
                "sports_signals",
                filters={"user_id": f"eq.{self.user_id}", "status": "eq.active"},
                order="data_as_of.desc",
                limit=300,
            )
            for row in active_user:
                if not self._is_user_entry_row(row):
                    continue
                if not is_sports_listable(row):
                    continue
                saved_wl = await self._save_bet_to_watchlist(row)
                if saved_wl:
                    watchlisted += 1
        except Exception as exc:
            logger.warning("Recover watchlist sync skipped: %s", exc)

        return {
            "ok": True,
            "restored": len(restored_ids),
            "restored_ids": restored_ids,
            "rebuilt": rebuilt,
            "watchlisted": watchlisted,
            "message": (
                f"Recovered {len(restored_ids)} Search bet(s)"
                + (f", rebuilt {rebuilt} from history" if rebuilt else "")
                + (f", synced {watchlisted} to Watchlist" if watchlisted else "")
                + "."
                if (restored_ids or rebuilt or watchlisted)
                else "No missing Search bets to restore."
            ),
        }

    def _row_from_performance_snapshot(
        self,
        signal_id: str,
        snap: dict[str, Any],
        nested: dict[str, Any],
    ) -> dict[str, Any] | None:
        event_name = str(snap.get("event_name") or nested.get("event_name") or "").strip()
        selection = str(snap.get("selection") or nested.get("selection") or "").strip()
        if not event_name or not selection:
            return None
        try:
            odds_american = int(
                snap.get("odds_american")
                if snap.get("odds_american") is not None
                else nested.get("odds_american")
                or 0
            )
        except (TypeError, ValueError):
            return None
        if odds_american == 0:
            return None
        bet_type = str(snap.get("bet_type") or nested.get("bet_type") or "moneyline").lower()
        now = datetime.now(UTC).isoformat()
        book_key = str(nested.get("preferred_book") or "fanduel")
        book_title = str(nested.get("preferred_book_title") or "FanDuel")
        return {
            "id": signal_id,
            "user_id": self.user_id,
            "sport": str(snap.get("sport") or nested.get("sport") or "Sports")[:40],
            "event_name": event_name[:160],
            "event_start": snap.get("event_start") or nested.get("event_start"),
            "bet_type": bet_type,
            "selection": selection[:120],
            "odds_american": odds_american,
            "odds_decimal": american_to_decimal(odds_american),
            "expected_value": snap.get("expected_value"),
            "line_movement": snap.get("line_movement")
            if isinstance(snap.get("line_movement"), dict)
            else {
                "preferred_book": book_key,
                "preferred_book_title": book_title,
                "source": SOURCE,
                "event_id": nested.get("event_id"),
            },
            "confidence_score": float(snap.get("confidence_score") or 62),
            "risk_score": float(snap.get("risk_score") or 48),
            "opportunity_score": max(float(snap.get("opportunity_score") or 0), 82.0),
            "recommendation": snap.get("recommendation")
            or f"My bet · {bet_type.title()} — {selection} · {event_name}",
            "explanation": snap.get("explanation")
            or f"Restored Search bet: {selection} on {event_name}.",
            "bull_case": snap.get("bull_case") or "You logged this play for tracking and learning.",
            "bear_case": snap.get("bear_case")
            or "Lines move — recheck FanDuel/DraftKings before betting more.",
            "invalidation": snap.get("invalidation")
            or "Scratch if the game is postponed or the wrong market was logged.",
            "suggested_action": snap.get("suggested_action")
            or f"Track {selection} at {odds_american:+d}",
            "risk_warning": snap.get("risk_warning")
            or "User-entered picks feed Atlas learning.",
            "scoring_snapshot": {
                **nested,
                "source": SOURCE,
                "user_entry": True,
                "pick_origin": "user",
                "user_tracked": True,
                "recovered_from_performance": True,
            },
            "status": "active",
            "data_as_of": now,
        }
