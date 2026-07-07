import asyncio
import logging

from app.config import settings
from app.db.supabase_client import SupabaseClient
from app.jobs.state import set_last_job
from app.services.options_service import OptionsRefreshService

logger = logging.getLogger(__name__)


async def run_refresh_options_job(user_id: str, access_token: str) -> dict:
    """Scheduled/manual job entrypoint."""
    service = OptionsRefreshService(SupabaseClient(access_token), user_id)
    result = await service.refresh_live_options(replace=True)
    set_last_job("refresh_options")
    return result


async def run_refresh_options_for_default_user() -> dict | None:
    """Cron-friendly runner when only DEFAULT_USER_ID + service role available."""
    if not settings.default_user_id:
        logger.warning("DEFAULT_USER_ID not set — skipping cron refresh")
        return None
    # Service-role based refresh is a future enhancement
    return None
