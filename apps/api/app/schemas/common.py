from pydantic import BaseModel, Field


class Scores(BaseModel):
    confidence: float = Field(ge=0, le=100)
    risk: float = Field(ge=0, le=100)
    opportunity: float = Field(ge=0, le=100)


class SignalSummary(BaseModel):
    id: str
    module: str
    title: str
    recommendation: str
    scores: Scores
    data_as_of: str | None = None


class HealthResponse(BaseModel):
    status: str
    version: str
    database: str
    last_jobs: dict[str, str | None]
