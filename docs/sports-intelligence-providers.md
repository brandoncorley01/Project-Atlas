# Sports Intelligence Providers

## Built-in providers

| ID | Type | Description |
|----|------|-------------|
| `rss_news` | `news_article` / `injury_update` | Authorized RSS feeds via `sports_news.py` |
| `manual_expert` | `expert_prediction` | Admin-entered picks in `sports_intelligence_items` |
| `mock` | `analyst_pick` | Development-only test data |

## Adding a licensed provider

1. Create `apps/api/app/sports_intelligence/providers/your_provider.py`
2. Implement `SportsIntelligenceProvider`
3. Register in `providers/registry.py`
4. Add credentials to `.env` — never hard-code keys in core logic

## Rules

- No paywall bypass or robots.txt violations
- Store summaries + links, not full articles
- Per-provider error isolation
- Independent enable flags per provider class

## Template

See `providers/base.py` for the interface:

```python
class SportsIntelligenceProvider(ABC):
    id: str
    name: str
    source_type: SourceType

    def is_enabled(self) -> bool: ...
    async def fetch_event_content(self, params: dict) -> list[RawIntelligenceItem]: ...
```
