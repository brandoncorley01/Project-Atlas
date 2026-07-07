from datetime import UTC, datetime

LAST_JOBS: dict[str, str | None] = {
    "refresh_options": None,
    "refresh_stocks": None,
    "refresh_sports": None,
    "refresh_news": None,
    "build_parlays": None,
    "coach_aggregate": None,
}


def set_last_job(job_name: str) -> None:
    LAST_JOBS[job_name] = datetime.now(UTC).isoformat()
