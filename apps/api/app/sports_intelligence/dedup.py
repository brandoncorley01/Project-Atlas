"""Deduplicate intelligence items by content hash."""

from __future__ import annotations

from app.sports_intelligence.types import SportsIntelligenceItem


def deduplicate_items(
    items: list[SportsIntelligenceItem],
    existing_hashes: set[str],
) -> list[SportsIntelligenceItem]:
    seen: set[str] = set(existing_hashes)
    unique: list[SportsIntelligenceItem] = []
    for item in items:
        h = item.content_hash or ""
        if not h or h in seen:
            item.status = "duplicate"
            continue
        seen.add(h)
        unique.append(item)
    return unique


def mark_syndicate_duplicates(items: list[SportsIntelligenceItem]) -> list[SportsIntelligenceItem]:
    """Group near-duplicate titles from different sources."""
    title_map: dict[str, str] = {}
    for item in items:
        key = _title_key(item.title)
        if key in title_map:
            item.duplicate_group_id = title_map[key]
            if item.status == "active":
                item.status = "duplicate"
        else:
            group_id = item.content_hash or key
            title_map[key] = group_id
            item.duplicate_group_id = group_id
    return items


def _title_key(title: str) -> str:
    return "".join(c for c in title.lower() if c.isalnum())[:80]
