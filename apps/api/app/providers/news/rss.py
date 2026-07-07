"""Free RSS market headlines (no API key)."""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

logger = logging.getLogger(__name__)

RSS_FEEDS = [
    ("yahoo_finance", "https://finance.yahoo.com/news/rssindex"),
    ("marketwatch", "https://feeds.marketwatch.com/marketwatch/topstories/"),
]

USER_AGENT = "ProjectAtlas/1.0 (news-catalyst; +https://github.com)"


async def fetch_rss_news(*, limit_per_feed: int = 15) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=20.0, headers={"User-Agent": USER_AGENT}) as client:
        for source, url in RSS_FEEDS:
            try:
                response = await client.get(url)
                if response.status_code != 200:
                    continue
                items.extend(_parse_rss(response.text, source=source, limit=limit_per_feed))
            except Exception as exc:
                logger.warning("RSS %s failed: %s", source, exc)
    return items


def _parse_rss(xml_text: str, *, source: str, limit: int) -> list[dict[str, Any]]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    rows: list[dict[str, Any]] = []
    for item in root.iter("item"):
        title = _text(item.find("title"))
        link = _text(item.find("link"))
        desc = _strip_html(_text(item.find("description")))
        pub = _text(item.find("pubDate"))
        published = None
        if pub:
            try:
                published = parsedate_to_datetime(pub).astimezone(UTC).isoformat()
            except (TypeError, ValueError):
                published = None

        if not title:
            continue
        rows.append(
            {
                "source": source,
                "title": title,
                "url": link,
                "summary": desc[:500],
                "published_at": published,
                "hint_tickers": [],
                "raw_payload": {"pubDate": pub},
            }
        )
        if len(rows) >= limit:
            break
    return rows


def _text(node: ET.Element | None) -> str:
    if node is None or node.text is None:
        return ""
    return node.text.strip()


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()
