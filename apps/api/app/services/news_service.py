"""News ingestion, classification, and persistence."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from app.agents.news_ai import classify_news, filter_valid_related_tickers, news_matches_symbol
from app.db.supabase_client import SupabaseClient
from app.providers.market.universe import CORE_LIQUID, discover_market_symbols
from app.providers.news.finnhub import fetch_company_news_batch, fetch_market_news
from app.providers.news.rss import fetch_rss_news
from app.providers.stocks.quotes import fetch_stock_quotes
from app.services.freshness import is_news_fresh

logger = logging.getLogger(__name__)

KNOWN_TICKERS = set(CORE_LIQUID)


class NewsService:
    def __init__(self, db: SupabaseClient, user_id: str) -> None:
        self.db = db
        self.user_id = user_id
        self._known_tickers = set(KNOWN_TICKERS)

    async def _expand_known_tickers(self) -> None:
        try:
            items = await self.db.select(
                "watchlist_items",
                filters={"user_id": f"eq.{self.user_id}", "item_type": "eq.ticker"},
            )
            for item in items:
                sym = str(item.get("symbol", "")).upper().strip()
                if sym:
                    self._known_tickers.add(sym)
        except Exception as exc:
            logger.warning("Watchlist for news tickers: %s", exc)

        try:
            discovered, _ = discover_market_symbols(max_symbols=40)
            for entry in discovered:
                self._known_tickers.add(entry.symbol)
        except Exception as exc:
            logger.warning("Discovery for news tickers: %s", exc)

    async def gather_raw_news(self) -> tuple[list[dict[str, Any]], dict]:
        await self._expand_known_tickers()
        stats: dict = {"sources": {}, "raw": 0}

        market = await fetch_market_news(limit=40)
        stats["sources"]["finnhub_market"] = len(market)

        company = await fetch_company_news_batch(sorted(self._known_tickers)[:25])
        stats["sources"]["finnhub_company"] = len(company)

        rss = await fetch_rss_news(limit_per_feed=12)
        stats["sources"]["rss"] = len(rss)

        combined = market + company + rss
        stats["raw"] = len(combined)
        deduped = self._dedupe(combined)
        stats["unique"] = len(deduped)
        return deduped, stats

    @staticmethod
    def _dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[str] = set()
        out: list[dict[str, Any]] = []
        for item in items:
            title = item.get("title", "").strip().lower()
            if not title:
                continue
            key = hashlib.md5(f"{title}|{item.get('url', '')}".encode()).hexdigest()
            if key in seen:
                continue
            seen.add(key)
            out.append(item)
        return out

    def _to_row(self, raw: dict[str, Any]) -> dict[str, Any]:
        classified = classify_news(
            title=raw["title"],
            summary=raw.get("summary") or "",
            hint_tickers=raw.get("hint_tickers") or [],
            known_tickers=self._known_tickers,
            published_at=raw.get("published_at"),
        )
        return {
            "user_id": self.user_id,
            "source": raw.get("source", "unknown"),
            "title": raw["title"],
            "url": raw.get("url"),
            "summary": raw.get("summary"),
            "published_at": raw.get("published_at"),
            "sentiment": classified.sentiment,
            "impact_score": classified.impact_score,
            "time_sensitivity_score": classified.time_sensitivity_score,
            "explanation": classified.explanation,
            "related_tickers": classified.related_tickers,
            "related_sports": [],
            "raw_payload": raw.get("raw_payload") or {},
        }

    async def refresh_news(self, *, replace: bool = True, limit: int = 40) -> dict:
        raw_items, stats = await self.gather_raw_news()
        rows = [self._to_row(item) for item in raw_items]
        rows.sort(
            key=lambda r: (
                float(r["impact_score"]) + float(r["time_sensitivity_score"]) * 0.4,
                r.get("published_at") or "",
            ),
            reverse=True,
        )
        rows = rows[:limit]

        if replace and rows:
            await self.db.delete("news_items", {"user_id": f"eq.{self.user_id}"})

        saved = await self.db.insert("news_items", rows) if rows else []

        return {
            "news_created": len(saved),
            "stats": stats,
            "high_impact": sum(1 for r in rows if float(r["impact_score"]) >= 60),
        }

    async def list_news(
        self,
        *,
        limit: int = 20,
        sentiment: str | None = None,
        ticker: str | None = None,
        min_impact: float | None = None,
    ) -> list[dict]:
        fetch_limit = min(100, limit * 3)
        rows = await self.db.select(
            "news_items",
            filters={"user_id": f"eq.{self.user_id}"},
            order="impact_score.desc",
            limit=fetch_limit,
        )

        if sentiment:
            rows = [r for r in rows if r.get("sentiment") == sentiment]
        if ticker:
            sym = ticker.upper()
            rows = [
                r
                for r in rows
                if news_matches_symbol(
                    str(r.get("title") or ""),
                    str(r.get("summary") or ""),
                    sym,
                    related_tickers={str(t).upper() for t in (r.get("related_tickers") or [])},
                    company_feed=str(r.get("source") or "") == "finnhub_company",
                )
            ]
        if min_impact is not None:
            rows = [r for r in rows if float(r.get("impact_score") or 0) >= min_impact]

        rows = [r for r in rows if is_news_fresh(r)]

        rows.sort(
            key=lambda r: (
                float(r.get("impact_score") or 0) + float(r.get("time_sensitivity_score") or 0) * 0.3
            ),
            reverse=True,
        )
        return rows[:limit]

    async def get_news(self, news_id: str) -> dict | None:
        rows = await self.db.select(
            "news_items",
            filters={"id": f"eq.{news_id}", "user_id": f"eq.{self.user_id}"},
            limit=1,
        )
        return rows[0] if rows else None

    async def breaking_news(self, limit: int = 5, *, include_quotes: bool = True) -> list[dict]:
        rows = await self.list_news(limit=limit, min_impact=45)
        if include_quotes:
            return await self.format_items_with_quotes(rows)
        return [self._format_item(row, None) for row in rows]

    @staticmethod
    def _lookup_quote(quotes: dict[str, dict] | None, symbol: str) -> dict:
        if not quotes:
            return {}
        sym = symbol.upper()
        for key in (sym, sym.replace(".", "-"), sym.replace("-", ".")):
            hit = quotes.get(key)
            if hit:
                return hit
        return {}

    @staticmethod
    def _format_item(row: dict, quotes: dict[str, dict] | None = None) -> dict:
        raw_tickers = [str(t).upper() for t in (row.get("related_tickers") or []) if t]
        hints = raw_tickers if str(row.get("source") or "") == "finnhub_company" else []
        tickers = filter_valid_related_tickers(
            title=str(row.get("title") or ""),
            summary=str(row.get("summary") or ""),
            tickers=raw_tickers,
            hint_tickers=hints,
        )
        affected: list[dict] = []
        for sym in tickers[:6]:
            q = NewsService._lookup_quote(quotes, sym)
            affected.append(
                {
                    "symbol": sym,
                    "price": q.get("price"),
                    "change": q.get("change"),
                    "change_pct": q.get("change_pct"),
                }
            )

        return {
            "id": row["id"],
            "source": row["source"],
            "title": row["title"],
            "url": row.get("url"),
            "summary": row.get("summary"),
            "published_at": row.get("published_at"),
            "sentiment": row.get("sentiment"),
            "impact_score": float(row.get("impact_score") or 0),
            "time_sensitivity_score": float(row.get("time_sensitivity_score") or 0),
            "explanation": row.get("explanation"),
            "related_tickers": tickers,
            "affected_companies": affected,
        }

    async def format_items_with_quotes(self, rows: list[dict]) -> list[dict]:
        all_symbols: set[str] = set()
        for row in rows:
            for sym in row.get("related_tickers") or []:
                if sym:
                    all_symbols.add(str(sym).upper())
        quotes = await fetch_stock_quotes(list(all_symbols))
        return [self._format_item(row, quotes) for row in rows]

    async def catalyst_for_symbol(self, symbol: str) -> dict[str, Any]:
        """Best recent catalyst for an underlying during options scan."""
        sym = symbol.upper()
        rows = await self.list_news(limit=10, ticker=sym, min_impact=40)
        if rows:
            best = max(rows, key=lambda r: float(r.get("impact_score") or 0))
            return {
                "has_catalyst": True,
                "top_headline": best["title"],
                "catalyst_impact": float(best.get("impact_score") or 0),
                "catalyst_sentiment": best.get("sentiment"),
                "news_count": len(rows),
            }
        return {"has_catalyst": False, "news_count": 0, "catalyst_impact": 0}

    async def catalysts_for_symbols(
        self,
        symbols: list[str],
        *,
        min_impact: float = 40,
    ) -> dict[str, dict[str, Any]]:
        """Batch-match recent news to symbols for dashboard catalyst enrichment."""
        unique = sorted({s.upper().strip() for s in symbols if s and s.upper() != "?"})
        if not unique:
            return {}

        result: dict[str, dict[str, Any]] = {
            sym: {"has_catalyst": False, "news_count": 0, "catalyst_impact": 0} for sym in unique
        }
        rows = await self.list_news(limit=60, min_impact=min_impact)

        for row in rows:
            title = str(row.get("title") or "")
            summary = str(row.get("summary") or "")
            impact = float(row.get("impact_score") or 0)
            related = {str(t).upper() for t in (row.get("related_tickers") or [])}
            company_feed = str(row.get("source") or "") == "finnhub_company"

            for sym in unique:
                if not news_matches_symbol(
                    title,
                    summary,
                    sym,
                    related_tickers=related,
                    company_feed=company_feed,
                ):
                    continue
                current = result[sym]
                if impact > float(current.get("catalyst_impact") or 0):
                    result[sym] = {
                        "has_catalyst": True,
                        "top_headline": title,
                        "catalyst_impact": impact,
                        "catalyst_sentiment": row.get("sentiment"),
                        "news_count": int(current.get("news_count") or 0) + 1,
                    }

        return result
