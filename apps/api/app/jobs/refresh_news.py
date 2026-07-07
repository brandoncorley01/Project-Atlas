import logging

from app.db.supabase_client import SupabaseClient
from app.jobs.state import set_last_job
from app.services.news_service import NewsService

logger = logging.getLogger(__name__)


async def run_refresh_news_job(user_id: str, access_token: str) -> dict:
    service = NewsService(SupabaseClient(access_token), user_id)
    result = await service.refresh_news(replace=True)
    set_last_job("refresh_news")
    return result
