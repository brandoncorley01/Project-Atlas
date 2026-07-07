import logging

from app.db.supabase_client import SupabaseClient
from app.jobs.state import set_last_job
from app.services.stock_service import StockRefreshService

logger = logging.getLogger(__name__)


async def run_refresh_stocks_job(user_id: str, access_token: str) -> dict:
    service = StockRefreshService(SupabaseClient(access_token), user_id)
    result = await service.refresh_stocks(replace=True)
    set_last_job("refresh_stocks")
    return result
