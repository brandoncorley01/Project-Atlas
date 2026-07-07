import logging

from app.db.supabase_client import SupabaseClient
from app.jobs.state import set_last_job
from app.services.sports_service import SportsRefreshService

logger = logging.getLogger(__name__)


async def run_refresh_sports_job(user_id: str, access_token: str) -> dict:
    service = SportsRefreshService(SupabaseClient(access_token), user_id)
    result = await service.refresh_sports(replace=True)
    set_last_job("refresh_sports")
    return result
