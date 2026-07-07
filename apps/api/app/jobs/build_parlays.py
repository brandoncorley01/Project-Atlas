from app.db.supabase_client import SupabaseClient
from app.jobs.state import set_last_job
from app.services.parlay_service import ParlayService


async def run_build_parlays_job(user_id: str, access_token: str) -> dict:
    service = ParlayService(SupabaseClient(access_token), user_id)
    result = await service.build_parlays(replace=True)
    set_last_job("build_parlays")
    return result
