from fastapi import APIRouter

from app.jobs.state import LAST_JOBS
from app.schemas.common import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    return HealthResponse(
        status="ok",
        version="0.2.0-one-side",
        database="not_connected",
        last_jobs=LAST_JOBS,
    )
